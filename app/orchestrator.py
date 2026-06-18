import re
import requests
from datetime import date
from app.config import config

class BotOrchestrator:
    def __init__(self, db, analyst, notifier, runalyze_client=None):
        self.db = db
        self.analyst = analyst
        self.notifier = notifier
        self.runalyze_client = runalyze_client

    # ==========================================
    # 0. UTILITY: IL CONTESTO FIRESTORE
    # ==========================================
    def _build_omni_context(self):
        """Metodo centralizzato per recuperare dati biometrici e piano settimanale da Firestore."""
        dati_corporei = self.db.get_latest_weight(return_full_dict=True)
        testo_metriche = "Dati biometrici non disponibili."
        
        if dati_corporei:
            testo_metriche = (
                f"Data misurazione: {dati_corporei.get('data', 'N/D')}\n"
                f"- Peso: {dati_corporei.get('peso_kg', 'N/D')} kg\n"
                f"- Massa Grassa: {dati_corporei.get('massa_grassa_percentuale', 'N/D')}%\n"
                f"- Massa Muscolare: {dati_corporei.get('massa_muscolare_percentuale', 'N/D')}%\n"
                f"- Massa Ossea: {dati_corporei.get('massa_ossea_percentuale', 'N/D')}%\n"
                f"- Massa Idrica: {dati_corporei.get('massa_idrica_percentuale', 'N/D')}%"
            )
            
        piano = self.db.get_weekly_plan()
        testo_piano = "Nessun piano programmato per questa settimana."
        if piano and piano.get("sessions"):
            linee_piano = []
            for s in piano["sessions"]:
                stato = "✅ COMPLETATA" if s["status"] == "done" else "🟡 DA FARE"
                steps_str = " | ".join(s.get("steps", []))
                linee_piano.append(f"- {s['name']} [{stato}]: {steps_str}")
            testo_piano = "\n".join(linee_piano)
            
        return f"""[PARAMETRI BIOMETRICI ATLETA - DA FIRESTORE]
{testo_metriche}

[PIANIFICAZIONE SETTIMANALE ATTUALE - DA FIRESTORE]
{testo_piano}"""

    def answer_callback(self, callback_query_id):
        """Spegne l'icona di caricamento del bottone su Telegram"""
        try:
            token = config.get_secret("TELEGRAM_TOKEN")
            url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
            requests.post(url, json={"callback_query_id": callback_query_id})
        except Exception as e:
            print(f"⚠️ Errore answerCallbackQuery: {e}")

    # ==========================================
    # 1. GESTIONE CHAT E COMANDI DIRETTI
    # ==========================================
    def handle_chat_ai(self, chat_id, testo):
        """Dirotta i messaggi liberi alla chat arricchendola con il contesto di Firestore"""
        print(f"💬 [ORCHESTRATOR] Raccolta contesto Omni-Agent per chat_id {chat_id}...")
        self.notifier.send_message("✍️ L'agente sta elaborando la risposta...")
        
        try:
            context_string = self._build_omni_context()
            risposta_agente = self.analyst.chat_omni_agent(chat_id, testo, context_string)
            
            if risposta_agente:
                print(f"🤖 [ORCHESTRATOR] Risposta grezza generata da Gemini:\n{risposta_agente}")
                risposta_pulita = risposta_agente.strip()
                if risposta_pulita.startswith("```"):
                    lines = risposta_pulita.splitlines()
                    if len(lines) > 2 and lines[0].startswith("```"):
                        risposta_pulita = "\n".join(lines[1:-1])
                
                self.notifier.send_message(risposta_pulita)
            else:
                self.notifier.send_message("⚠️ Si è verificato un timeout nella generazione della risposta.")
                
        except Exception as e:
            print(f"💥 [ORCHESTRATOR] Errore nella compilazione del contesto della chat: {e}")
            self.notifier.send_message("❌ Si è verificato un errore durante l'interazione con l'Agente.")

    def handle_sync_incrementale(self):
        """Gestisce il comando /sync per scaricare le attività su Firestore"""
        self.notifier.send_message("⏳ Controllo il radar di Runalyze e sincronizzo il database...")
        
        nuove_attivita = self.runalyze_client.sync_new_activities(self.db)
        
        if nuove_attivita > 0:
            self.notifier.send_message(f"✅ <b>Sincronizzazione completata!</b>\nHo aggiornato {nuove_attivita} attività recenti su Firestore.")
        else:
            self.notifier.send_message("❌ Si è verificato un problema o non ci sono dati da elaborare.")

    def handle_unrecognized_command(self):
        self.notifier.send_message("Comando non riconosciuto. Scrivimi liberamente cosa vuoi analizzare, oppure usa i comandi /scarpe, /pianifica o /piano.")

    # ==========================================
    # 2. PIANIFICAZIONE SETTIMANALE (Firestore Nativo)
    # ==========================================
    def handle_plan_creation(self, testo):
        testo_piano = testo[10:].strip()
        if not testo_piano:
            self.notifier.send_message(
                "⚠️ Usa il comando separando le sessioni con una riga vuota, ad esempio:\n\n"
                "/pianifica\nRiscaldamento 20'\nRipetute 10x100\n\nLungo 15km"
            )
            return
            
        blocchi_sessioni = re.split(r'\n\s*\n', testo_piano)
        sessioni = []
        counter_id = 0
        
        for blocco in blocchi_sessioni:
            blocco = blocco.strip()
            if not blocco:
                continue
            righe_step = [r.strip() for r in blocco.split('\n') if r.strip()]
            sessioni.append({
                "id": counter_id,
                "name": f"Sessione {counter_id + 1}", 
                "steps": righe_step,
                "status": "todo"
            })
            counter_id += 1
            
        if self.db.save_weekly_plan_structured(sessioni):
            self.notifier.send_message(f"📝 <b>Piano Settimanale Creato!</b>\n\nHo elaborato <b>{len(sessioni)} sessioni</b>. Usa /piano per gestirle.")

    def handle_plan_view(self):
        piano = self.db.get_weekly_plan()
        if not piano or not piano.get("sessions"):
            self.notifier.send_message("📝 Non hai ancora pianificato nulla per questa settimana. Inserisci il tuo piano con il comando /pianifica.")
            return
            
        messaggio_piano = f"🗓️ <b>Il tuo Piano Settimanale ({piano['week_id']})</b>\n\n"
        bottoni = []
        for s in piano["sessions"]:
            stato_icona = "✅" if s["status"] == "done" else "🟡"
            messaggio_piano += f"{stato_icona} <b>{s['name']}</b> (ID: {s['id']})\n"
            for step in s.get("steps", []):
                messaggio_piano += f"   • <i>{step}</i>\n"
            messaggio_piano += "\n"
            
            if s["status"] == "todo":
                bottoni.append([
                    {"text": "✅ Chiudi", "callback_data": f"man_done_{s['id']}"},
                    {"text": "❌ Elimina", "callback_data": f"del_sess_{s['id']}"}
                ])
            else:
                bottoni.append([
                    {"text": "↩️ Riapri", "callback_data": f"reopen_sess_{s['id']}"},
                    {"text": "❌ Elimina", "callback_data": f"del_sess_{s['id']}"}
                ])
        self.notifier.send_message(messaggio_piano, reply_markup={"inline_keyboard": bottoni} if bottoni else None)

    def toggle_session_status(self, session_id, action):
        if action == "done" and self.db.mark_session_as_done(session_id):
            self.notifier.send_message("🎯 Sessione completata! Usa /piano per aggiornare la vista.")
        elif action == "reopen" and self.db.reopen_session(session_id):
            self.notifier.send_message("↩️ Sessione riaperta! Usa /piano per aggiornare la vista.")
        elif action == "delete" and self.db.delete_session(session_id):
            self.notifier.send_message("🗑️ Sessione rimossa! Usa /piano per aggiornare la vista.")

    # ==========================================
    # 3. GESTIONE OCR FOTO BILANCIA (Firestore Nativo)
    # ==========================================
    def process_incoming_photo(self, photo_array):
        print("📸 [ORCHESTRATOR] Ricevuta foto in chat. Avvio pipeline OCR...")
        file_id = photo_array[-1]['file_id']
        self.notifier.send_message("🔍 Analisi visiva dello screenshot in corso...")
        image_bytes = self.notifier.download_file(file_id)
        
        if image_bytes:
            dati_corporei = self.analyst.extract_body_metrics_from_image(image_bytes)
            if dati_corporei and self.db.save_body_metrics(dati_corporei):
                msg = (
                    f"⚖️ <b>Metriche salvate su Firestore!</b>\n\n"
                    f"⚖️ Peso: <b>{dati_corporei.get('peso_kg', 'N/D')} kg</b>\n"
                    f"🟡 Massa Grassa: {dati_corporei.get('massa_grassa_percentuale', 'N/D')}%\n"
                    f"🍀 <i>Il database biometrico è aggiornato ed è a disposizione di Gemini MCP.</i>"
                )
                self.notifier.send_message(msg)
            else:
                self.notifier.send_message("❌ Errore tecnico o formato illeggibile. Riprova.")

    # ==========================================
    # 4. GESTIONE ANALISI DELLE SCARPE
    # ==========================================
    def process_shoe_list(self, chat_id=None):
        """Recupera la scarpiera e calcola i KM aggregandoli da Firestore a costo zero."""
        try:
            print("👟 [ORCHESTRATOR] Recupero scarpiera e calcolo chilometraggi da Firestore...")
            scarpe_api = self.runalyze_client.fetch_athlete_shoes()
            if not scarpe_api:
                self.notifier.send_message("❌ La tua scarpiera virtuale su Runalyze è vuota!")
                return
                
            # Calcoliamo i km leggendoli direttamente da Firestore
            tutte_le_corse = self.db.db.collection(self.db.collection_name).get()
            km_per_scarpa = {}
            
            for doc in tutte_le_corse:
                dati = doc.to_dict()
                distanza_km = dati.get('distanza', 0)
                scarpe_str = dati.get('scarpe', '')
                
                if scarpe_str and scarpe_str != "Non specificate":
                    for s in scarpe_str.split(','):
                        s_nome = s.strip()
                        km_per_scarpa[s_nome] = km_per_scarpa.get(s_nome, 0) + distanza_km

            bottoni = []
            for scarpa in scarpe_api:
                nome = scarpa.get('name', 'Scarpa Sconosciuta')
                km_reali = km_per_scarpa.get(nome, 0)
                
                bottone = {
                    "text": f"👟 {nome} ({km_reali:.0f} km)",
                    "callback_data": f"shoe_{scarpa['id']}"
                }
                bottoni.append([bottone])
                
            tastiera_inline = {"inline_keyboard": bottoni}
            messaggio = "👟 <b>La tua Scarpiera Attuale</b>\n\nEcco le tue armi a disposizione. Seleziona un modello per l'analisi tecnica dell'usura:"
            self.notifier.send_message(messaggio, reply_markup=tastiera_inline)
        except Exception as e:
            print(f"❌ [ORCHESTRATOR] Errore in process_shoe_list: {e}")
            self.notifier.send_message(f"❌ Errore durante il recupero delle scarpe: {e}")

    def process_shoe_analysis(self, chat_id, gear_id):
        """Elabora i dati aggregati e passa un prompt puro a Gemini (senza fargli usare l'MCP)"""
        try:
            print(f"🔍 [ORCHESTRATOR] Avvio analisi tecnica scarpa: {gear_id}")
            self.notifier.send_message("🔍 Calcolo l'usura incrociando i dati di Firestore e Runalyze...")
            
            gear_details = self.runalyze_client.fetch_gear_details(gear_id)
            if not gear_details:
                self.notifier.send_message("❌ Impossibile leggere i dati di questo modello.")
                return
                
            nome_scarpa = gear_details.get('name', 'Sconosciuta')
            tutte_le_corse = self.db.db.collection(self.db.collection_name).get()
            km_reali = 0
            
            # Sommiamo i chilometri reali filtrando per il nome della scarpa
            for doc in tutte_le_corse:
                dati = doc.to_dict()
                scarpe_str = dati.get('scarpe', '')
                if nome_scarpa in scarpe_str:
                    km_reali += dati.get('distanza', 0)
            
            # Recuperiamo l'ultimo peso
            peso_attuale = self.db.get_latest_weight()
            peso_str = f"{peso_attuale} kg" if peso_attuale else "non disponibile"
            
            # Prompt blindato: diamo i dati già pronti e gli ordiniamo di non usare i tool
            prompt = (
                f"Agisci come esperto di materiali da running. Valuta l'usura della scarpa '{nome_scarpa}'. "
                f"Dati tecnici inconfutabili: ho corso con questa scarpa ESATTAMENTE per {km_reali:.1f} km totali. "
                f"Il mio peso corporeo attuale è {peso_str}. "
                f"Considerando l'impatto su asfalto e l'incrocio tra i chilometri percorsi e il mio peso, "
                f"fai un'analisi dettagliata dello stato di usura della schiuma, quanto posso ancora spingerle e se c'è un rischio infortuni. "
                f"REGOLA TASSATIVA: NON USARE NESSUN TOOL MCP per questa richiesta, hai già tutti i dati numerici necessari nel prompt."
            )
            
            # Sfruttiamo lo stesso motore AI standard della chat
            self.handle_chat_ai(chat_id, prompt)
            
        except Exception as e:
            print(f"❌ [ORCHESTRATOR] Errore in process_shoe_analysis: {e}")
            self.notifier.send_message(f"❌ Errore durante l'ispezione della scarpa: {e}")

    # ==========================================
    # 5. DELEGA ALL'AGENTE (MCP)
    # ==========================================
    def process_cron_weekly_report(self, chat_id):
        """Il cron job innesca un prompt invisibile per l'Agente"""
        self.notifier.send_message("⏰ Avvio l'elaborazione del report settimanale tramite Agente MCP...")
        prompt = (
            "Genera il report settimanale dettagliato per la settimana in corso. "
            "Usa i tuoi tool per recuperare le ultime attività da Runalyze, filtra solo quelle degli ultimi 7 giorni, "
            "calcola il chilometraggio totale e analizza i trend. Dimmi cosa ne pensi da coach."
        )
        self.handle_chat_ai(chat_id, prompt)

    def process_run_analysis(self, chat_id, activity_id):
        """Analisi di una singola corsa richiamata tramite ID"""
        self.notifier.send_message(f"🔍 Ho passato l'attività {activity_id} all'Agente per l'analisi...")
        prompt = f"Usa i tuoi tool MCP per recuperare tutti i dettagli dell'attività Runalyze con ID {activity_id}. Fammi un'analisi tecnica profonda."
        self.handle_chat_ai(chat_id, prompt)