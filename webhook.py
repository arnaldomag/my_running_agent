from flask import Flask, request, jsonify
from app.strava_client import strava_client
from app.analyst import analyst
from app.telegram_client import notifier
import threading

app = Flask(__name__)

def process_run_analysis(activity_id):
    """Esegue il recupero e l'analisi della singola corsa in background"""
    try:
        notifier.send_message(f"⏳ Recupero dettagli dell'allenamento da Strava...")
        activity_details = strava_client.fetch_activity_details(activity_id)
        
        if not activity_details:
            notifier.send_message(f"❌ Impossibile scaricare i dati per l'ID {activity_id}.")
            return
            
        notifier.send_message("🧠 Dati ricevuti. L'Agente sta elaborando l'analisi dettagliata (Obiettivi vs Realtà)...")
        report_profondo = analyst.analyze_single_run(activity_details)
        
        messaggio_finale = f"🎯 <b>Focus Allenamento: {activity_details['nome']}</b>\n\n{report_profondo}"
        notifier.send_message(messaggio_finale)
    except Exception as e:
        notifier.send_message(f"❌ Errore durante l'analisi in background: {e}")

def process_fallback_weekly_report():
    """Recupera la vecchia settimana attiva e rigenera il report con i relativi bottoni"""
    try:
        notifier.send_message("🔍 Alla ricerca dell'ultimo periodo attivo su Strava...")
        lista_corse, km_totali, start_date, end_date = strava_client.fetch_last_active_week()
        
        if not lista_corse:
            notifier.send_message("❌ Non ho trovato nessuna sessione di corsa memorizzata nello storico recente.")
            return
            
        # Formattiamo l'intervallo temporale reale per non fare confusione
        data_inizio = start_date.strftime("%d/%m")
        data_fine = end_date.strftime("%d/%m")
        
        notifier.send_message(f"🤖 Elaborazione del report per la settimana {data_inizio} - {data_fine}...")
        feedback_raw = analyst.analyze_weekly_summary(lista_corse, km_totali)
        feedback_settimanale = feedback_raw.replace("```html", "").replace("```", "").strip()
        
        # Costruiamo il messaggio definitivo mostrando chiaramente la settimana di riferimento
        messaggio_telegram = f"📅 <b>Report Settimanale Fallback ({data_inizio} - {data_fine})</b>\n\n{feedback_settimanale}"
        
        # Rigeneriamo dinamicamente i bottoni per le corse di quella specifica settimana recuperata
        bottoni = []
        for corsa in lista_corse:
            bottone = {
                "text": f"📊 Analizza {corsa['nome']}", 
                "callback_data": f"analyze_{corsa['id']}"
            }
            bottoni.append([bottone])
            
        tastiera_inline = {"inline_keyboard": bottoni} if bottoni else None
        notifier.send_message(messaggio_telegram, reply_markup=tastiera_inline)
        
    except Exception as e:
        notifier.send_message(f"❌ Errore durante il recupero del report di fallback: {e}")

@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    update = request.json
    
    if 'callback_query' in update:
        query = update['callback_query']
        callback_data = query['data']
        
        # Caso 1: Click sul bottone di analisi singola corsa
        if callback_data.startswith('analyze_'):
            activity_id = callback_data.split('_')[1]
            thread = threading.Thread(target=process_run_analysis, args=(activity_id,))
            thread.start()
            
        # Caso 2: Cliccato "Sì" sulla proposta di fallback della settimana passata
        elif callback_data == 'fallback_last_week_show':
            thread = threading.Thread(target=process_fallback_weekly_report)
            thread.start()
            
        # Caso 3: Cliccato "No" sulla proposta di fallback
        elif callback_data == 'fallback_last_week_ignore':
            notifier.send_message("👌 Ricevuto. Goditi il riposo, ci sentiamo alla prossima corsa!")
            
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)