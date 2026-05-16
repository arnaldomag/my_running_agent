from flask import Flask, request, jsonify
from app.strava_client import strava_client
from app.analyst import analyst
from app.telegram_client import notifier
import threading

app = Flask(__name__)

def process_run_analysis(activity_id):
    """Esegue il recupero e l'analisi in background"""
    try:
        # 1. Avviso di inizio (corretto, senza passare il chat_id)
        notifier.send_message(f"⏳ Recupero dettagli dell'allenamento da Strava...")
        
        # 2. Chiamata a Strava per estrarre Note Private e Dati Granulari
        activity_details = strava_client.fetch_activity_details(activity_id)
        
        if not activity_details:
            notifier.send_message(f"❌ Impossibile scaricare i dati per l'ID {activity_id}.")
            return
            
        # 3. Passiamo i dati all'Analista AI
        notifier.send_message("🧠 Dati ricevuti. L'Agente sta elaborando l'analisi dettagliata (Obiettivi vs Realtà)...")
        report_profondo = analyst.analyze_single_run(activity_details)
        
        # 4. Invio del report finale formattato per Telegram
        messaggio_finale = f"🎯 <b>Focus Allenamento: {activity_details['nome']}</b>\n\n{report_profondo}"
        notifier.send_message(messaggio_finale)
        
    except Exception as e:
        notifier.send_message(f"❌ Errore durante l'analisi in background: {e}")

@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    update = request.json
    
    # Intercettiamo il click sul bottone
    if 'callback_query' in update:
        query = update['callback_query']
        callback_data = query['data']
        
        if callback_data.startswith('analyze_'):
            activity_id = callback_data.split('_')[1]
            
            # Lanciamo il thread passando solo l'activity_id
            thread = threading.Thread(target=process_run_analysis, args=(activity_id,))
            thread.start()
            
    # Rispondiamo subito a Telegram con un 200 OK per confermare la ricezione
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)