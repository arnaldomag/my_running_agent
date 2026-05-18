from flask import Flask, request, jsonify
import requests
from app.config import config
from app.strava_client import strava_client
from app.analyst import analyst
from app.telegram_client import notifier

app = Flask(__name__)

def answer_callback(callback_query_id):
    """Informa Telegram che il click è stato ricevuto, spegnendo la rotella di caricamento"""
    try:
        token = config.get_secret("TELEGRAM_TOKEN")
        url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
        requests.post(url, json={"callback_query_id": callback_query_id})
    except Exception as e:
        print(f"⚠️ Errore durante answerCallbackQuery: {e}")

def process_run_analysis(activity_id):
    try:
        print(f"🏃‍♂️ [WEBHOOK] Avvio analisi corsa ID: {activity_id}")
        notifier.send_message(f"⏳ Recupero dettagli dell'allenamento da Strava...")
        activity_details = strava_client.fetch_activity_details(activity_id)
        
        if not activity_details:
            notifier.send_message(f"❌ Impossibile scaricare i dati per l'ID {activity_id}.")
            return
            
        notifier.send_message("🧠 Dati ricevuti. L'Agente sta elaborando l'analisi dettagliata...")
        report_profondo = analyst.analyze_single_run(activity_details)
        
        messaggio_finale = f"🎯 <b>Focus Allenamento: {activity_details['nome']}</b>\n\n{report_profondo}"
        notifier.send_message(messaggio_finale)
    except Exception as e:
        print(f"❌ [WEBHOOK] Errore in process_run_analysis: {e}")
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
        feedback_settimanale = feedback_raw.replace("```html", "").replace("```", "").strip()
        
        messaggio_telegram = f"📅 <b>Report Settimanale Fallback ({data_inizio} - {data_fine})</b>\n\n{feedback_settimanale}"
        
        bottoni = []
        for corsa in lista_corse:
            bottone = {
                "text": f"📊 Analizza {corsa['nome']}", 
                "callback_data": f"analyze_{corsa['id']}"
            }
            bottoni.append([bottone])
            
        tastiera_inline = {"inline_keyboard": bottoni} if bottoni else None
        notifier.send_message(messaggio_telegram, reply_markup=tastiera_inline)
        print("✅ [WEBHOOK] Report di fallback inviato correttamente.")
        
    except Exception as e:
        print(f"❌ [WEBHOOK] Errore in process_fallback_weekly_report: {e}")
        notifier.send_message(f"❌ Errore durante il recupero del report di fallback: {e}")

@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    try:
        update = request.json
        print(f"📥 [WEBHOOK] Ricevuto update da Telegram: {update}")
        
        if 'callback_query' in update:
            query = update['callback_query']
            callback_data = query['data']
            query_id = query['id']
            
            # Sblocca immediatamente l'interfaccia di Telegram
            answer_callback(query_id)
            
            if callback_data.startswith('analyze_'):
                activity_id = callback_data.split('_')[1]
                process_run_analysis(activity_id)
                
            elif callback_data == 'fallback_last_week_show':
                process_fallback_weekly_report()
                
            elif callback_data == 'fallback_last_week_ignore':
                notifier.send_message("👌 Ricevuto. Goditi il riposo, ci sentiamo alla prossima corsa!")
                
        return jsonify({"status": "ok"}), 200
    except Exception as global_error:
        print(f"💥 [WEBHOOK] Errore critico globale nella rotta: {global_error}")
        return jsonify({"status": "error", "message": str(global_error)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)