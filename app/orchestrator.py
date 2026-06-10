import traceback
import re
import requests
from datetime import date, timedelta, datetime
from app.config import config

class BotOrchestrator:
    def __init__(self, db, analyst, notifier):
        self.db = db
        self.analyst = analyst
        self.notifier = notifier

    # ==========================================
    # 0. UTILITY DI SISTEMA
    # ==========================================
    def answer_callback(self, callback_query_id):
        """Spegne l'icona di caricamento del bottone su Telegram"""
        try:
            token = config.get_secret("TELEGRAM_TOKEN")
            url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
            requests.post(url, json={"callback_query_id": callback_query_id})
        except Exception as e:
            print(f"⚠️ Errore answerCallbackQuery: {e}")

    # ==========================================
    # 1. GESTIONE COMANDI TESTUALI DIRETTI
    # ==========================================
    def handle_sync_storico(self, testo):
        parti = testo.split()
        if len(parti) > 1 and parti[1].isdigit():
            anno = int(parti[1])
            self.notifier.send_message(f"⏳ Avvio sincronizzazione storica per l'anno {anno}. Scarico i dati da Runalyze e aggiorno il database, un attimo di pazienza...")
            corse_elaborate = self.runalyze_client.sync_historical_data_by_year(self.db, anno)
            self.notifier.send_message(f"✅ Sincronizzazione {anno} completata! Ho importato o aggiornato {corse_elaborate} corse su Firestore.")
        else:
            self.notifier.send_message("⚠️ Formato del comando non valido. Per favore usa la sintassi: /syncstorico [anno] (es. /syncstorico 2026)")

    def handle_sync_incrementale(self):
        """Gestisce il comando /sync per scaricare solo le novità"""
        self.notifier.send_message("⏳ Controllo il radar di Runalyze alla ricerca di nuovi allenamenti...")
        
        nuove_attivita = self.runalyze_client.sync_new_activities(self.db)
        
        if nuove_attivita > 0:
            self.notifier.send_message(f"✅ <b>Sincronizzazione completata!</b>\nHo aggiunto {nuove_attivita} nuove attività al tuo database.")
        else:
            self.notifier.send_message("✅ <b>Sei già perfettamente allineato!</b>\nNon ci sono nuove attività da scaricare.")

    def handle_chat_ai(self, chat_id, testo):
        """Dirotta i messaggi liberi alla chat arricchendola con tutto il patrimonio informativo di Firestore"""
        print(f"💬 [ORCHESTRATOR] Raccolta contesto Omni-Agent per chat_id {chat_id}...")
        self.notifier.send_message("✍️ L'agente sta elaborando la risposta...")
        
        try:
            # 1. Recupero metriche corporee complete (usando return_full_dict=True)
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
                
            # 2. Recupero del piano settimanale corrente
            piano = self.db.get_weekly_plan()
            testo_piano = "Nessun piano programmato per questa settimana."
            if piano and piano.get("sessions"):
                linee_piano = []
                for s in piano["sessions"]:
                    stato = "✅ COMPLETATA" if s["status"] == "done" else "🟡 DA FARE"
                    steps_str = " | ".join(s.get("steps", []))
                    linee_piano.append(f"- {s['name']} [{stato}]: {steps_str}")
                testo_piano = "\n".join(linee_piano)
                
            # 3. Consolidamento finale dell'Omni-Context String
            context_string = f"""[PARAMETRI BIOMETRICI ATLETA]
{testo_metriche}

[PIANIFICAZIONE SETTIMANALE ATTUALE]
{testo_piano}"""

            # 4. Invocazione dell'unico metodo dell'analyst passando la domanda originale e il contesto
            risposta_agente = self.analyst.chat_omni_agent(chat_id, testo, context_string)
            
            self.notifier.send_message(risposta_agente)
            
        except Exception as e:
            print(f"💥 [ORCHESTRATOR] Errore nella compilazione del contesto della chat: {e}")
            self.notifier.send_message("❌ Si è verificato un errore durante l'allineamento dei dati di contesto.")

    def handle_unrecognized_command(self):
        self.notifier.send_message("Comando non riconosciuto. Puoi provare con /scarpe o /syncstorico 2026 o /pianifica o /piano o scrivermi semplicemente un messaggio per parlare del tuo allenamento!")

    # ==========================================
    # 2. PIANIFICAZIONE SETTIMANALE
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
                "status": "todo",
                "run_id": None
            })
            counter_id += 1
            
        if not sessioni:
            self.notifier.send_message("⚠️ Non ho trovato allenamenti validi nel tuo messaggio.")
            return
            
        if self.db.save_weekly_plan_structured(sessioni):
            self.notifier.send_message(f"📝 <b>Piano Settimanale Creato!</b>\n\nHo elaborato <b>{len(sessioni)} sessioni</b> di allenamento dal tuo elenco. Usa il comando /piano per gestirle.")
        else:
            self.notifier.send_message("❌ Errore tecnico durante il salvataggio del piano.")

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
                
        tastiera = {"inline_keyboard": bottoni} if bottoni else None
        self.notifier.send_message(messaggio_piano, reply_markup=tastiera)

    def handle_plan_modification(self, testo):
        parti = testo.split('\n', 1) 
        if len(parti) < 2:
            self.notifier.send_message("⚠️ Formato errato. Usa la sintassi:\n\n/modifica [ID]\nnuovo step 1\nnuovo step 2")
            return
        
        prima_riga = parti[0].strip().split()
        if len(prima_riga) < 2 or not prima_riga[1].isdigit():
            self.notifier.send_message("⚠️ Devi specificare l'ID numerico della sessione accanto al comando. Esempio:\n/modifica 0")
            return
        
        session_id = prima_riga[1]
        nuovi_step = [r.strip() for r in parti[1].split('\n') if r.strip()]
        
        if self.db.edit_session(session_id, nuovi_step):
            self.notifier.send_message(f"✏️ Sessione (ID: {session_id}) aggiornata con successo! Usa /piano per vedere le modifiche.")
        else:
            self.notifier.send_message(f"❌ Impossibile modificare. Sicuro che l'ID {session_id} esista e non sia stato cancellato?")

    def toggle_session_status(self, session_id, action):
        if action == "done":
            if self.db.mark_session_as_done(session_id):
                self.notifier.send_message("🎯 Sessione completata e archiviata! Usa /piano per vedere lo stato aggiornato.")
            else:
                self.notifier.send_message("❌ Errore durante l'aggiornamento della sessione.")
        elif action == "reopen":
            if self.db.reopen_session(session_id):
                self.notifier.send_message("↩️ Sessione riaperta! È di nuovo attiva nel tuo piano. Digita /piano per aggiornare la visualizzazione.")
            else:
                self.notifier.send_message("❌ Errore durante la riapertura della sessione.")
        elif action == "delete":
            if self.db.delete_session(session_id):
                self.notifier.send_message("🗑️ Sessione rimossa dal piano settimanale! Usa /piano per aggiornare la visuale.")
            else:
                self.notifier.send_message("❌ Errore durante l'eliminazione della sessione.")

    # ==========================================
    # 3. GESTIONE SCARPE
    # ==========================================
    def process_shoe_list(self):
        try:
            print("👟 [ORCHESTRATOR] Recupero scarpiera e calcolo chilometraggi...")
            scarpe_api = self.runalyze_client.fetch_athlete_shoes()
            if not scarpe_api:
                self.notifier.send_message("❌ La tua scarpiera virtuale su Runalyze è vuota!")
                return
                
            # Calcoliamo i km leggendoli direttamente dalla NOSTRA fonte di verità (Firestore).
            # Questo bypassa la mancanza del dato aggregato sull'API dell'equipment di Runalyze.
            tutte_le_corse = self.db.db.collection(self.db.collection_name).get()
            km_per_scarpa = {}
            
            for doc in tutte_le_corse:
                dati = doc.to_dict()
                distanza_km = dati.get('distanza', 0)
                scarpe_str = dati.get('scarpe', '')
                
                # Dividiamo la stringa nel caso ci siano più equipaggiamenti associati (es. "Scarpa, Fascia Cardio")
                if scarpe_str and scarpe_str != "Non specificate":
                    for s in scarpe_str.split(','):
                        s_nome = s.strip()
                        if s_nome not in km_per_scarpa:
                            km_per_scarpa[s_nome] = 0
                        km_per_scarpa[s_nome] += distanza_km

            bottoni = []
            for scarpa in scarpe_api:
                nome = scarpa.get('name', 'Scarpa Sconosciuta')
                # Recuperiamo i KM reali dal nostro dizionario calcolato (di default 0 se è nuova e mai usata)
                km_reali = km_per_scarpa.get(nome, 0)
                
                bottone = {
                    "text": f"👟 {nome} ({km_reali:.0f} km)",
                    "callback_data": f"shoe_{scarpa['id']}"
                }
                bottoni.append([bottone])
                
            tastiera_inline = {"inline_keyboard": bottoni}
            messaggio = "👟 <b>La tua Scarpiera Attuale</b>\n\nEcco le tue armi a disposizione. Seleziona un modello per fare il tagliando dei materiali:"
            self.notifier.send_message(messaggio, reply_markup=tastiera_inline)
        except Exception as e:
            print(f"❌ [ORCHESTRATOR] Errore in process_shoe_list: {e}")
            self.notifier.send_message(f"❌ Errore durante il recupero delle scarpe: {e}")

    def process_shoe_analysis(self, gear_id):
        try:
            print(f"🔍 [ORCHESTRATOR] Avvio analisi tecnica scarpa: {gear_id}")
            self.notifier.send_message("🔍 Controllo la telemetria della scarpa incrociando i dati del database...")
            gear_details = self.runalyze_client.fetch_gear_details(gear_id)
            
            if not gear_details:
                self.notifier.send_message("❌ Impossibile leggere i dati di questo modello.")
                return
                
            # Poiché l'API Runalyze non riporta la distanza, la ricalcoliamo al volo da Firestore
            nome_scarpa = gear_details.get('name', 'Sconosciuta')
            tutte_le_corse = self.db.db.collection(self.db.collection_name).get()
            km_reali = 0
            
            for doc in tutte_le_corse:
                dati = doc.to_dict()
                scarpe_str = dati.get('scarpe', '')
                if nome_scarpa in scarpe_str:
                    km_reali += dati.get('distanza', 0)
                    
            # Iniettiamo il dato corretto e vitale nel dizionario prima di passarlo a Gemini per l'analisi
            gear_details['distance'] = km_reali
                
            peso_attuale = self.db.get_latest_weight()
            if peso_attuale:
                self.notifier.send_message(f"🧠 Calcolo l'usura della schiuma considerando il tuo peso aggiornato ({peso_attuale} kg) e l'impatto su asfalto...")
            else:
                self.notifier.send_message("🧠 Calcolo l'usura della schiuma considerando l'utilizzo su strada...")
                
            report_scarpa = self.analyst.analyze_shoe(gear_details, peso_atleta=peso_attuale)
            report_pulito = report_scarpa.replace("```html", "").replace("```", "").strip()
            
            messaggio_finale = f"👟 <b>Tagliando Materiali: {nome_scarpa} ({km_reali:.0f} km)</b>\n\n{report_pulito}"
            self.notifier.send_message(messaggio_finale)
        except Exception as e:
            print(f"❌ [ORCHESTRATOR] Errore in process_shoe_analysis: {e}")
            self.notifier.send_message(f"❌ Errore durante l'ispezione della scarpa: {e}")

    # ==========================================
    # 4. GESTIONE OCR FOTO (BILANCIA)
    # ==========================================
    def process_incoming_photo(self, photo_array):
        print("📸 [ORCHESTRATOR] Ricevuta foto in chat. Avvio pipeline OCR...")
        best_photo = photo_array[-1]
        file_id = best_photo['file_id']
        
        self.notifier.send_message("🔍 Analisi visiva dello screenshot in corso...")
        image_bytes = self.notifier.download_file(file_id)
        
        if image_bytes:
            dati_corporei = self.analyst.extract_body_metrics_from_image(image_bytes)
            if dati_corporei:
                self.notifier.send_message("💾 Archiviazione dati nel Cloud di Firestore...")
                if self.db.save_body_metrics(dati_corporei):
                    messaggio_successo = (
                        f"⚖️ <b>Metriche salvate su Firestore!</b>\n\n"
                        f"📅 Data misurazione: {dati_corporei.get('data', 'N/D')}\n"
                        f"⚖️ Peso: <b>{dati_corporei.get('peso_kg', 'N/D')} kg</b>\n"
                        f"📊 IMC: {dati_corporei.get('imc', 'N/D')}\n"
                        f"🟡 Massa Grassa: {dati_corporei.get('massa_grassa_percentuale', 'N/D')}%\n"
                        f"🔴 Massa Muscolare: {dati_corporei.get('massa_muscolare_percentuale', 'N/D')}%\n"
                        f"🦴 Massa Ossea: {dati_corporei.get('massa_ossea_percentuale', 'N/D')}%\n"
                        f"💧 Massa Idrica: {dati_corporei.get('massa_idrica_percentuale', 'N/D')}%\n\n"
                        f"🍀 <i>Il database del coach è aggiornato.</i>"
                    )
                    self.notifier.send_message(messaggio_successo)
                else:
                    self.notifier.send_message("❌ Errore tecnico: Impossibile salvare i dati su Firestore.")
            else:
                self.notifier.send_message("⚠️ Non sono riuscito a estrarre i dati formattati correttamente. Riprova.")
        else:
            self.notifier.send_message("❌ Errore durante il download dell'immagine da Telegram.")

    # ==========================================
    # 5. GESTIONE ANALISI E REPORT (CRON E MANUALI)
    # ==========================================
    def process_run_analysis(self, activity_id):
        try:
            self.notifier.send_message(f"⏳ Recupero dettagli dell'allenamento da Runalyze...")
            activity_details = self.runalyze_client.fetch_activity_details(activity_id)
            if not activity_details:
                return
            self.notifier.send_message("🧠 Dati ricevuti. L'Agente sta elaborando l'analisi...")
            report_profondo = self.analyst.analyze_single_run(activity_details)
            self.notifier.send_message(f"🎯 <b>Focus Allenamento: {activity_details['nome']}</b>\n\n{report_profondo}")
        except Exception as e:
            self.notifier.send_message(f"❌ Errore durante l'analisi: {e}")

    def process_cron_weekly_report(self):
        try:
            print("⏰ [ORCHESTRATOR] Avvio report settimanale schedulato...")
            self.runalyze_client.sync_new_activities(self.db)

            oggi = date.today()
            giorno_settimana = oggi.weekday()
            lunedi_corrente = oggi - timedelta(days=giorno_settimana)
            domenica_corrente = lunedi_corrente + timedelta(days=6)
            
            str_lunedi = lunedi_corrente.strftime("%Y-%m-%d")
            str_domenica = domenica_corrente.strftime("%Y-%m-%d")
            
            # Utilizziamo la proprietà collection_name per puntare ad 'attivita'
            query_corse = self.db.db.collection(self.db.collection_name) \
                .where("start_date", ">=", str_lunedi) \
                .where("start_date", "<=", str_domenica) \
                .order_by("start_date", direction="DESCENDING") \
                .get()

            lista_corse = []
            for doc in query_corse:
                corsa_dict = doc.to_dict()
                corsa_dict['data'] = corsa_dict.get('start_date', 'N/D')
                corsa_dict['nome'] = corsa_dict.get('nome', 'Corsa')
                corsa_dict['distanza'] = corsa_dict.get('distanza', 0)
                corsa_dict['tempo'] = corsa_dict.get('tempo_movimento', 0)
                lista_corse.append(corsa_dict)

            data_inizio_it = lunedi_corrente.strftime("%d/%m")
            data_fine_it = domenica_corrente.strftime("%d/%m")

            if not lista_corse:
                self.notifier.send_message(
                    f"📭 <b>Report Settimanale ({data_inizio_it} - {data_fine_it})</b>\n\n"
                    "Non ho trovato nessuna attività registrata in questa settimana. Ricordati di aggiornare il piano! 🏃‍♂️"
                )
                return

            # Sommiamo le distanze (già salvate in km)
            km_totali = sum([c.get('distanza', 0) for c in lista_corse])
            self.notifier.send_message(f"🤖 Elaborazione del report parziale per la settimana {data_inizio_it} - {data_fine_it}...")
            
            feedback_raw = self.analyst.analyze_weekly_summary(lista_corse, km_totali)
            feedback_settimanale = feedback_raw.replace("```html", "").replace("```", "").strip()
            messaggio_telegram = f"📅 <b>Report Settimanale ({data_inizio_it} - {data_fine_it})</b>\n\n{feedback_settimanale}"
            
            bottoni = []
            for corsa in lista_corse:
                nome_corsa = corsa.get('nome', 'Corsa')
                bottoni.append([{
                    "text": f"📊 Analizza {nome_corsa}", 
                    "callback_data": f"analyze_{corsa['id']}"
                }])
                
            tastiera_inline = {"inline_keyboard": bottoni} if bottoni else None
            self.notifier.send_message(messaggio_telegram, reply_markup=tastiera_inline)
        except Exception as e:
            print(f"❌ [ORCHESTRATOR] Errore in process_cron_weekly_report: {e}")
            self.notifier.send_message("❌ Si è verificato un errore tecnico nella generazione del report automatico.")

    # ==========================================
    # 6. GESTIONE DASHBOARD
    # ==========================================
    def get_dashboard_metrics(self):
        """
        Estrae le ultime attività da Firestore, calcola le metriche aggregate
        e prepara il time-series payload per il frontend della Mini App.
        """
        try:
            recent_runs = self.db.get_recent_runs(limit=15)
            
            if not recent_runs:
                return {
                    "status": "success",
                    "data": {"labels": [], "kilometers": [], "paces": [], "latest_weight": 0}
                }
            
            recent_runs.reverse()
            
            labels = []
            kilometers = []
            paces = []
            
            for run in recent_runs:
                start_date = run.get('start_date', '')
                if len(start_date) >= 10:
                    label_data = start_date[5:10] # Estrae "MM-DD"
                else:
                    label_data = "Corsa"
                labels.append(label_data)
                
                # Il campo 'distanza' è già in km
                km = run.get('distanza', 0)
                kilometers.append(round(km, 2))
                
                # Il tempo movimento è in minuti
                tempo_min = run.get('tempo_movimento', 0)
                
                # Passo medio in minuti decimali per km (es: 5'30" -> 5.5)
                if km > 0:
                    passo_totale_minuti = tempo_min / km
                    paces.append(round(passo_totale_minuti, 2))
                else:
                    paces.append(0)
            
            latest_weight = self.db.get_latest_weight()
            
            return {
                "status": "success",
                "data": {
                    "labels": labels,
                    "kilometers": kilometers,
                    "paces": paces,
                    "latest_weight": latest_weight or 0
                }
            }
            
        except Exception as e:
            print(f"❌ [ORCHESTRATOR] Errore critico nel calcolo delle metriche dashboard: {e}")
            return {"status": "error", "message": f"Errore elaborazione dati: {str(e)}"}

    def process_fallback_weekly_report(self):
        try:
            print("📅 [ORCHESTRATOR] Avvio recupero settimana di fallback...")
            self.runalyze_client.sync_new_activities(self.db)
            
            self.notifier.send_message("🔍 Alla ricerca dell'ultimo periodo attivo su Runalyze...")
            lista_corse, km_totali, start_date, end_date = self.runalyze_client.fetch_last_active_week()
            
            if not lista_corse:
                self.notifier.send_message("❌ Non ho trovato nessuna sessione di corsa memorizzata nello storico recente.")
                return
                
            data_inizio = start_date.strftime("%d/%m")
            data_fine = end_date.strftime("%d/%m")
            
            self.notifier.send_message(f"🤖 Elaborazione del report per la settimana {data_inizio} - {data_fine}...")
            feedback_raw = self.analyst.analyze_weekly_summary(lista_corse, km_totali)
            feedback_settimanale = feedback_raw.replace("```html", "").replace("```", "").strip()
            
            messaggio_telegram = f"📅 <b>Report Settimanale Fallback ({data_inizio} - {data_fine})</b>\n\n{feedback_settimanale}"
            
            bottoni = []
            for corsa in lista_corse:
                bottoni.append([{
                    "text": f"📊 Analizza {corsa.get('nome', 'Corsa')}", 
                    "callback_data": f"analyze_{corsa['id']}"
                }])
                
            tastiera_inline = {"inline_keyboard": bottoni} if bottoni else None
            self.notifier.send_message(messaggio_telegram, reply_markup=tastiera_inline)
        except Exception as e:
            print(f"❌ [ORCHESTRATOR] Errore in process_fallback_weekly_report: {e}")
            self.notifier.send_message(f"❌ Errore durante il recupero del report di fallback: {e}")

    def handle_dashboard_view(self, chat_id):
        """Genera e invia il bottone inline per aprire la Telegram Mini App"""
        app_url = config.webapp_url
        if not app_url:
            self.notifier.send_message(chat_id, "⚠️ URL della Web App non configurato.")
            return True
            
        markup = {
            "inline_keyboard": [
                [
                    {
                        "text": "📊 Apri le tue Metriche",
                        "web_app": {"url": app_url}
                    }
                ]
            ]
        }
        
        messaggio = "Ecco la tua dashboard interattiva con i trend di allenamento e i dati del peso corporeo."
        self.notifier.send_message(messaggio, reply_markup=markup)
        return True

    def handle_fallback_ignore(self):
        self.notifier.send_message("👌 Ricevuto. Goditi il riposo, ci sentiamo alla prossima corsa!")
