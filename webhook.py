from flask import Flask, request, jsonify
import requests
from app.config import config
from app.strava_client import strava_client
from app.analyst import analyst
from app.telegram_client import notifier
from app.database import db

app = Flask(__name__)

def answer_callback(callback_query_id):
    try:
        token = config.get_secret("TELEGRAM_TOKEN")
        url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
        requests.post(url, json={"callback_query_id": callback_query_id})
    except Exception as e:
        print(f"⚠️ Errore answerCallbackQuery: {e}")

# --- FUNZIONI CORSA E SETTIMANA ESISTENTI ---
def process_run_analysis(activity_id):
    # [Il codice è identico a prima]
    try:
        notifier.send_message(f"⏳ Recupero dettagli dell'allenamento da Strava...")
        activity_details = strava_client.fetch_activity_details(activity_id)
        if not activity_details:
            return
        notifier.send_message("🧠 Dati ricevuti. L'Agente sta elaborando l'analisi...")
        report_profondo = analyst.analyze_single_run(activity_details)
        notifier.send_message(f"🎯 <b>Focus Allenamento: {activity_details['nome']}</b>\n\n{report_profondo}")
    except Exception as e:
        notifier.send_message(f"❌ Errore durante l'analisi: {e}")

def process_fallback_weekly_report():
    try:
        print("📅 [WEBHOOK] Avvio recupero settimana di fallback...")

        # --- AGGIUNTA FONDAMENTALE: AUTO-SYNC IN BACKGROUND ---
        print("🔄 [WEBHOOK] Eseguo auto-sync delle ultime 30 attività prima del report...")
        strava_client.sync_latest_activities(db, limit=30)
        # ----------------------------------------------------

        notifier.send_message("🔍 Alla ricerca dell'ultimo periodo attivo su Strava...")
        lista_corse, km_totali, start_date, end_date = strava_client.fetch_last_active_week()
        
        if not lista_corse:
            notifier.send_message("❌ Non ho trovato nessuna sessione di corsa memorizzata nello storico recente.")
            return
            
        data_inizio = start_date.strftime("%d/%m")
        data_fine = end_date.strftime("%d/%m")
        
        notifier.send_message(f"🤖 Elaborazione del report per la settimana {data_inizio} - {data_fine}...")
        feedback_raw = analyst.analyze_weekly_summary(lista_corse, km_totali)
        
        # Pulizia da eventuale markdown di Gemini
        feedback_settimanale = feedback_raw.replace("```html", "").replace("```", "").strip()
        
        messaggio_telegram = f"📅 <b>Report Settimanale Fallback ({data_inizio} - {data_fine})</b>\n\n{feedback_settimanale}"
        
        # Creazione dei bottoni per ogni singola corsa trovata
        bottoni = []
        for corsa in lista_corse:
            bottone = {
                "text": f"📊 Analizza {corsa.get('nome', 'Corsa')}", 
                "callback_data": f"analyze_{corsa['id']}"
            }
            bottoni.append([bottone])
            
        tastiera_inline = {"inline_keyboard": bottoni} if bottoni else None
        
        notifier.send_message(messaggio_telegram, reply_markup=tastiera_inline)
        print("✅ [WEBHOOK] Report di fallback inviato correttamente.")
        
    except Exception as e:
        print(f"❌ [WEBHOOK] Errore in process_fallback_weekly_report: {e}")
        notifier.send_message(f"❌ Errore durante il recupero del report di fallback: {e}")
    
# --- NUOVE FUNZIONI SCARPIERA ---
def process_shoe_list():
    try:
        print("👟 [WEBHOOK] Recupero scarpiera...")
        scarpe = strava_client.fetch_athlete_shoes()
        
        if not scarpe:
            notifier.send_message("❌ La tua scarpiera virtuale su Strava è vuota!")
            return
            
        # Creiamo un bottone per ogni scarpa
        bottoni = []
        for scarpa in scarpe:
            km = scarpa.get('distance', 0) / 1000
            nome = scarpa.get('name', 'Scarpa Sconosciuta')
            bottone = {
                "text": f"👟 {nome} ({km:.0f} km)",
                "callback_data": f"shoe_{scarpa['id']}"
            }
            bottoni.append([bottone])
            
        tastiera_inline = {"inline_keyboard": bottoni}
        messaggio = "👟 <b>La tua Scarpiera Attuale</b>\n\nEcco le tue armi a disposizione. Seleziona un modello per fare il tagliando dei materiali:"
        
        notifier.send_message(messaggio, reply_markup=tastiera_inline)
    except Exception as e:
        print(f"❌ [WEBHOOK] Errore in process_shoe_list: {e}")
        notifier.send_message(f"❌ Errore durante il recupero delle scarpe: {e}")

def process_shoe_analysis(gear_id):
    try:
        print(f"🔍 [WEBHOOK] Avvio analisi tecnica scarpa: {gear_id}")
        notifier.send_message("🔍 Controllo la telemetria della scarpa nel garage Strava...")
        gear_details = strava_client.fetch_gear_details(gear_id)
        
        if not gear_details:
            notifier.send_message("❌ Impossibile leggere i dati di questo modello.")
            return
            
        # 1. Recupero dinamico del peso da Firestore
        peso_attuale = db.get_latest_weight()
        
        if peso_attuale:
            notifier.send_message(f"🧠 Calcolo l'usura della schiuma considerando il tuo peso aggiornato ({peso_attuale} kg) e l'impatto su asfalto...")
        else:
            notifier.send_message("🧠 Calcolo l'usura della schiuma considerando l'utilizzo su strada...")
            
        # 2. Passaggio dei dati aggiornati all'Agente
        report_scarpa = analyst.analyze_shoe(gear_details, peso_atleta=peso_attuale)
        
        # Pulizia da eventuale markdown aggiuntivo
        report_pulito = report_scarpa.replace("```html", "").replace("```", "").strip()
        
        messaggio_finale = f"👟 <b>Tagliando Materiali: {gear_details.get('name')}</b>\n\n{report_pulito}"
        notifier.send_message(messaggio_finale)
    except Exception as e:
        print(f"❌ [WEBHOOK] Errore in process_shoe_analysis: {e}")
        notifier.send_message(f"❌ Errore durante l'ispezione della scarpa: {e}")

# --- ROTTA PRINCIPALE AGGIORNATA ---
@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    try:
        update = request.json
        print(f"📥 [WEBHOOK] Ricevuto update: {update}")
        
        # 1. GESTIONE MESSAGGI DI TESTO (COMANDI E CHAT AI)
        if 'message' in update and 'text' in update['message']:
            testo = update['message']['text'].strip()
            testo_lower = testo.lower()
            chat_id = update['message']['chat']['id']
            
            # A) Comandi strutturati
            if testo.startswith('/'):
                if testo_lower in ['/elenco scarpe', '/elencoscarpe', '/scarpe']:
                    process_shoe_list()

                elif testo_lower.startswith('/syncstorico'):
                    parti = testo_lower.split()
                    if len(parti) > 1 and parti[1].isdigit():
                        anno = int(parti[1])
                        notifier.send_message(f"⏳ Avvio sincronizzazione storica per l'anno {anno}. Scarico i dati da Strava e aggiorno il database, un attimo di pazienza...")
                        
                        corse_elaborate = strava_client.sync_historical_data_by_year(db, anno)
                        
                        notifier.send_message(f"✅ Sincronizzazione {anno} completata! Ho importato o aggiornato {corse_elaborate} corse su Firestore.")
                    else:
                        notifier.send_message("⚠️ Formato del comando non valido. Per favore usa la sintassi: /syncstorico [anno] (es. /syncstorico 2026)")

                # --- PIANIFICAZIONE STRUTTURATA (TRAMITE RIGHE VUOTE) ---
                elif testo_lower.startswith('/pianifica'):
                    import re  # Aggiunto per gestire in modo sicuro gli a capo multipli
                    
                    testo_piano = testo[10:].strip()
                    
                    if not testo_piano:
                        messaggio_aiuto = (
                            "⚠️ Usa il comando separando le sessioni con una riga vuota, ad esempio:\n\n"
                            "/pianifica\n"
                            "Riscaldamento 20'\n"
                            "Ripetute 10x100\n\n"
                            "Lungo 15km"
                        )
                        notifier.send_message(messaggio_aiuto)
                        return jsonify({"status": "ok"}), 200
                        
                    # Dividiamo il testo in blocchi usando un'espressione regolare.
                    # \n\s*\n significa "un a capo, seguito (forse) da spazi invisibili, seguito da un altro a capo"
                    blocchi_sessioni = re.split(r'\n\s*\n', testo_piano)
                    
                    sessioni = []
                    counter_id = 0
                    
                    for blocco in blocchi_sessioni:
                        blocco = blocco.strip()
                        if not blocco:
                            continue
                            
                        # Spezziamo il singolo blocco nelle sue righe interne (gli step)
                        righe_step = [r.strip() for r in blocco.split('\n') if r.strip()]
                        
                        # Generiamo noi il nome della sessione per comodità visiva
                        sessioni.append({
                            "id": counter_id,
                            "name": f"Sessione {counter_id + 1}", 
                            "steps": righe_step,
                            "status": "todo",
                            "run_id": None
                        })
                        counter_id += 1
                    
                    if not sessioni:
                        notifier.send_message("⚠️ Non ho trovato allenamenti validi nel tuo messaggio.")
                        return jsonify({"status": "ok"}), 200
                        
                    # Salviamo la struttura gerarchica su Firestore
                    if db.save_weekly_plan_structured(sessioni):
                        notifier.send_message(f"📝 <b>Piano Settimanale Creato!</b>\n\nHo elaborato <b>{len(sessioni)} sessioni</b> di allenamento dal tuo elenco. Usa il comando /piano per gestirle.")
                    else:
                        notifier.send_message("❌ Errore tecnico durante il salvataggio del piano.")

                # --- VISUALIZZAZIONE PIANO AGGIORNATA (Con ID e bottone Elimina) ---
                elif testo_lower == '/piano':
                    piano = db.get_weekly_plan()
                    
                    if not piano or not piano.get("sessions"):
                        notifier.send_message("📝 Non hai ancora pianificato nulla per questa settimana. Inserisci il tuo piano con il comando /pianifica.")
                        return jsonify({"status": "ok"}), 200
                        
                    messaggio_piano = f"🗓️ <b>Il tuo Piano Settimanale ({piano['week_id']})</b>\n\n"
                    bottoni = []
                    
                    for s in piano["sessions"]:
                        stato_icona = "✅" if s["status"] == "done" else "🟡"
                        # Stampiamo anche l'ID per far sapere all'utente cosa inserire nel comando /modifica
                        messaggio_piano += f"{stato_icona} <b>{s['name']}</b> (ID: {s['id']})\n"
                        
                        for step in s.get("steps", []):
                            messaggio_piano += f"   • <i>{step}</i>\n"
                        messaggio_piano += "\n"
                        
                        if s["status"] == "todo":
                            # Creiamo una riga con DUE bottoni affiancati: Chiudi ed Elimina
                            bottoni.append([
                                {"text": f"✅ Chiudi", "callback_data": f"man_done_{s['id']}"},
                                {"text": f"❌ Elimina", "callback_data": f"del_sess_{s['id']}"}
                            ])
                            
                    tastiera = {"inline_keyboard": bottoni} if bottoni else None
                    notifier.send_message(messaggio_piano, reply_markup=tastiera)

                # --- MODIFICA DI UNA SINGOLA SESSIONE ---
                elif testo_lower.startswith('/modifica'):
                    # Dividiamo alla primissima riga a capo
                    parti = testo.split('\n', 1) 
                    
                    if len(parti) < 2:
                        notifier.send_message("⚠️ Formato errato. Usa la sintassi:\n\n/modifica [ID]\nnuovo step 1\nnuovo step 2")
                        return jsonify({"status": "ok"}), 200
                    
                    # Estraiamo l'ID dalla prima riga (es. "/modifica 0")
                    prima_riga = parti[0].strip().split()
                    if len(prima_riga) < 2 or not prima_riga[1].isdigit():
                        notifier.send_message("⚠️ Devi specificare l'ID numerico della sessione accanto al comando. Esempio:\n/modifica 0")
                        return jsonify({"status": "ok"}), 200
                    
                    session_id = prima_riga[1]
                    # Ricostruiamo i nuovi step ignorando le righe vuote
                    nuovi_step = [r.strip() for r in parti[1].split('\n') if r.strip()]
                    
                    if db.edit_session(session_id, nuovi_step):
                        notifier.send_message(f"✏️ Sessione (ID: {session_id}) aggiornata con successo! Usa /piano per vedere le modifiche.")
                    else:
                        notifier.send_message(f"❌ Impossibile modificare. Sicuro che l'ID {session_id} esista e non sia stato cancellato?")

                else:
                    notifier.send_message("Comando non riconosciuto. Puoi provare con /scarpe o /syncstorico 2026 o /pianifica o /piano o scrivermi semplicemente un messaggio per parlare del tuo allenamento!")
                return jsonify({"status": "ok"}), 200

            # B) Chat libera con l'Intelligenza Artificiale (MessageHandler)
            print(f"💬 [WEBHOOK] Dirottamento chat_id {chat_id} verso l'AI Agent...")
            notifier.send_message("✍️ L'agente sta elaborando la risposta...")
            
            risposta_agente = analyst.chat_with_strava_context(chat_id, testo)
            notifier.send_message(risposta_agente)
            
            return jsonify({"status": "ok"}), 200
        # --- BLOCCO: GESTIONE FOTO (SCREENSHOT BILANCIA) ---
        if 'message' in update and 'photo' in update['message']:
            print("📸 [WEBHOOK] Ricevuta foto in chat. Avvio pipeline OCR...")
            
            foto_array = update['message']['photo']
            best_photo = foto_array[-1]
            file_id = best_photo['file_id']
            
            notifier.send_message("🔍 Analisi visiva dello screenshot in corso...")
            
            image_bytes = notifier.download_file(file_id)
            
            if image_bytes:
                # 1. Estrazione tramite Gemini Flash
                dati_corporei = analyst.extract_body_metrics_from_image(image_bytes)
                
                if dati_corporei:
                    notifier.send_message("💾 Archiviazione dati nel Cloud di Firestore...")
                    
                    # 2. Scrittura su Firestore
                    if db.save_body_metrics(dati_corporei):
                        # 3. Conferma finale su Telegram
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
                        notifier.send_message(messaggio_successo)
                    else:
                        notifier.send_message("❌ Errore tecnico: Impossibile salvare i dati su Firestore.")
                else:
                    notifier.send_message("⚠️ Non sono riuscito a estrarre i dati formattati correttamente. Riprova.")
            else:
                notifier.send_message("❌ Errore durante il download dell'immagine da Telegram.")
            
            return jsonify({"status": "ok"}), 200
        
        # 2. GESTIONE DEI CLICK SUI BOTTONI
        if 'callback_query' in update:
            query = update['callback_query']
            callback_data = query['data']
            query_id = query['id']
            
            answer_callback(query_id)
            
            if callback_data.startswith('analyze_'):
                activity_id = callback_data.split('_')[1]
                process_run_analysis(activity_id)
                
            elif callback_data == 'fallback_last_week_show':
                process_fallback_weekly_report() # Qui tu hai il tuo codice funzionante di prima
                
            elif callback_data == 'fallback_last_week_ignore':
                notifier.send_message("👌 Ricevuto. Goditi il riposo, ci sentiamo alla prossima corsa!")
                
            # NUOVO BLOCCO PER I BOTTONI DELLE SCARPE
            elif callback_data.startswith('shoe_'):
                gear_id = callback_data.split('_')[1]
                process_shoe_analysis(gear_id)

            # --- AGGIORNAMENTO: COMPLETAMENTO SESSIONE STRUTTURATA ---
            elif callback_data.startswith('man_done_'):
               # session_id = callback_data.split('_')[1]
                session_id = callback_data.replace('man_done_', '')
                
                # Richiamiamo la nuova funzione definita in database.py
                if db.mark_session_as_done(session_id):
                    notifier.send_message("🎯 Sessione completata e archiviata! Usa /piano per vedere lo stato aggiornato.")
                else:
                    notifier.send_message("❌ Errore durante l'aggiornamento della sessione.")

            # --- ELIMINAZIONE SESSIONE ---
            elif callback_data.startswith('del_sess_'):
                session_id = callback_data.replace('del_sess_', '')
                
                if db.delete_session(session_id):
                    notifier.send_message("🗑️ Sessione rimossa dal piano settimanale! Usa /piano per aggiornare la visuale.")
                else:
                    notifier.send_message("❌ Errore durante l'eliminazione della sessione.")

        return jsonify({"status": "ok"}), 200
    except Exception as global_error:
        print(f"💥 [WEBHOOK] Errore critico globale nella rotta: {global_error}")
        return jsonify({"status": "error", "message": str(global_error)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
