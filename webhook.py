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

                # --- NUOVA FUNZIONALITÀ: PIANIFICAZIONE SETTIMANALE ---
                elif testo_lower.startswith('/pianifica'):
                    # Rimuoviamo la parola chiave '/pianifica' e teniamo il resto
                    testo_piano = testo[10:].strip()
                    
                    if not testo_piano:
                        notifier.send_message("⚠️ Usa il comando così:\n/pianifica \nFartlek 10k\nRipetute 5x1000\nLungo 15k")
                        return jsonify({"status": "ok"}), 200
                        
                    # Dividiamo gli allenamenti andando a capo (o usando la virgola)
                    # Supportiamo sia l'andata a capo che la virgola come separatore
                    separa_per = '\n' if '\n' in testo_piano else ','
                    allenamenti = [a for a in testo_piano.split(separa_per) if a.strip()]
                    
                    if db.save_weekly_plan(allenamenti):
                        notifier.send_message(f"✅ Piano salvato con successo! Hai {len(allenamenti)} sessioni previste questa settimana. Usa /piano per gestirle.")
                    else:
                        notifier.send_message("❌ Errore durante il salvataggio del piano.")
                        
                elif testo_lower == '/piano':
                    piano = db.get_weekly_plan()
                    
                    if not piano or not piano.get("workouts"):
                        notifier.send_message("📝 Non hai ancora pianificato nulla per questa settimana. Inserisci il tuo piano con il comando /pianifica.")
                        return jsonify({"status": "ok"}), 200
                        
                    messaggio_piano = f"🗓️ <b>Il tuo Piano Settimanale ({piano['week_id']})</b>\n\n"
                    bottoni = []
                    
                    for w in piano["workouts"]:
                        stato_icona = "✅" if w["status"] == "done" else "🟡"
                        messaggio_piano += f"{stato_icona} {w['descrizione']}\n"
                        
                        # Se non è ancora fatto, creiamo un bottone per spuntarlo
                        if w["status"] == "todo":
                            bottone = {
                                "text": f"Spunta '{w['descrizione'][:15]}...'",
                                "callback_data": f"markdone_{w['id']}"
                            }
                            bottoni.append([bottone])
                    
                    tastiera = {"inline_keyboard": bottoni} if bottoni else None
                    notifier.send_message(messaggio_piano, reply_markup=tastiera)

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

            # BLOCCO PER I BOTTONI DEL WEEKLY PLAN
            elif callback_data.startswith('markdone_'):
                workout_id = callback_data.split('_')[1]
                if db.mark_workout_as_done(workout_id):
                    notifier.send_message("✅ Ottimo lavoro! Allenamento completato. Usa di nuovo /piano per vedere la situazione aggiornata.")
                else:
                    notifier.send_message("❌ Errore durante l'aggiornamento.")

        return jsonify({"status": "ok"}), 200
    except Exception as global_error:
        print(f"💥 [WEBHOOK] Errore critico globale nella rotta: {global_error}")
        return jsonify({"status": "error", "message": str(global_error)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
