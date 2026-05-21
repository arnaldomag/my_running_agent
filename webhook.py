from flask import Flask, request, jsonify
import requests
from app.config import config
from app.strava_client import strava_client
from app.analyst import analyst
from app.telegram_client import notifier

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
            
        notifier.send_message(f"🧠 Calcolo l'usura della schiuma per il modello {gear_details.get('name')}...")
        report_scarpa = analyst.analyze_shoe(gear_details)
        
        # Pulizia da eventuale markdown aggiuntivo di Gemini
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
        
        # 1. GESTIONE DEI COMANDI TESTUALI IN CHAT
        if 'message' in update and 'text' in update['message']:
            testo = update['message']['text'].lower().strip()
            # Se scrivi /elenco scarpe, /elencoscarpe o /scarpe, si attiva
            if testo in ['/elenco scarpe', '/elencoscarpe', '/scarpe']:
                process_shoe_list()
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
                
        return jsonify({"status": "ok"}), 200
    except Exception as global_error:
        print(f"💥 [WEBHOOK] Errore critico globale nella rotta: {global_error}")
        return jsonify({"status": "error", "message": str(global_error)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
