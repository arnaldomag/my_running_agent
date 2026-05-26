import os
from flask import Flask, request, jsonify, render_template

# Importiamo moduli e servizi
from app.strava_client import strava_client
from app.analyst import analyst
from app.telegram_client import notifier
from app.database import db
from app.orchestrator import BotOrchestrator

app = Flask(__name__)

# Inizializziamo l'orchestratore
orchestrator = BotOrchestrator(db, strava_client, analyst, notifier)

@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    try:
        update = request.json
        print(f"📥 [WEBHOOK] Ricevuto update: {update}")
        
        # ==================================================
        # 1. GESTIONE MESSAGGI DI TESTO
        # ==================================================
        if 'message' in update and 'text' in update['message']:
            testo = update['message']['text'].strip()
            testo_lower = testo.lower()
            chat_id = update['message']['chat']['id']
            
            # A) Comandi strutturati
            if testo.startswith('/'):
                if testo_lower in ['/elenco scarpe', '/elencoscarpe', '/scarpe']:
                    orchestrator.process_shoe_list()
                elif testo_lower.startswith('/syncstorico'):
                    orchestrator.handle_sync_storico(testo)
                elif testo_lower.startswith('/pianifica'):
                    orchestrator.handle_plan_creation(testo)
                elif testo_lower == '/piano':
                    orchestrator.handle_plan_view()
                elif testo_lower.startswith('/modifica'):
                    orchestrator.handle_plan_modification(testo)
                else:
                    orchestrator.handle_unrecognized_command()
                return jsonify({"status": "ok"}), 200

            # B) Chat libera con l'Intelligenza Artificiale (MessageHandler)
            orchestrator.handle_chat_ai(chat_id, testo)
            return jsonify({"status": "ok"}), 200

        # ==================================================
        # 2. GESTIONE FOTO (OCR BILANCIA E ALTRO)
        # ==================================================
        if 'message' in update and 'photo' in update['message']:
            orchestrator.process_incoming_photo(update['message']['photo'])
            return jsonify({"status": "ok"}), 200
        
        # ==================================================
        # 3. GESTIONE DEI CLICK SUI BOTTONI (CALLBACK QUERIES)
        # ==================================================
        if 'callback_query' in update:
            query = update['callback_query']
            callback_data = query['data']
            query_id = query['id']
            
            # Spegniamo subito l'icona di caricamento su Telegram
            orchestrator.answer_callback(query_id)
            
            if callback_data.startswith('analyze_'):
                activity_id = callback_data.replace('analyze_', '')
                orchestrator.process_run_analysis(activity_id)
                
            elif callback_data == 'fallback_last_week_show':
                orchestrator.process_fallback_weekly_report()
                
            elif callback_data == 'fallback_last_week_ignore':
                orchestrator.handle_fallback_ignore()
                
            elif callback_data.startswith('shoe_'):
                gear_id = callback_data.replace('shoe_', '')
                orchestrator.process_shoe_analysis(gear_id)

            elif callback_data.startswith('man_done_'):
                session_id = callback_data.replace('man_done_', '')
                orchestrator.toggle_session_status(session_id, action="done")

            elif callback_data.startswith('del_sess_'):
                session_id = callback_data.replace('del_sess_', '')
                orchestrator.toggle_session_status(session_id, action="delete")

            elif callback_data.startswith('reopen_sess_'):
                session_id = callback_data.replace('reopen_sess_', '')
                orchestrator.toggle_session_status(session_id, action="reopen")

        return jsonify({"status": "ok"}), 200
    except Exception as global_error:
        print(f"💥 [WEBHOOK] Errore critico globale nella rotta: {global_error}")
        return jsonify({"status": "error", "message": str(global_error)}), 500

# ==================================================
# 4. ENDPOINT PER CLOUD SCHEDULER (CRON JOB)
# ==================================================
@app.route('/tasks/weekly-report', methods=['POST'])
def tasks_weekly_report():
    try:
        print("⏰ [CRON] Chiamata temporizzata ricevuta da Cloud Scheduler!")
        orchestrator.process_cron_weekly_report()
        return jsonify({"status": "ok", "message": "Report settimanale avviato con successo."}), 200
    except Exception as e:
        print(f"❌ [CRON] Errore durante l'esecuzione del cron job: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ==================================================
# NEW: ROTTA PER SERVIRE LA TELEGRAM MINI APP
# ==================================================
@app.route('/dashboard', methods=['GET'])
def dashboard_view():
    try:
        print("🌐 [WEBHOOK] Richiesta di apertura della Mini App ricevuta.")
        return render_template('dashboard.html')
    except Exception as e:
        print(f"💥 [WEBHOOK] Errore nel caricamento del template della dashboard: {e}")
        return "Errore interno nel caricamento della dashboard.", 500

# ==================================================
# API JSON PER I DATI DELLA DASHBOARD
# ==================================================
@app.route('/api/metrics', methods=['GET'])
def api_metrics():
    try:
        print("📊 [WEBHOOK] Richiesta API per i dati della dashboard...")
        dati_json = orchestrator.get_dashboard_metrics()
        
        if dati_json.get("status") == "error":
            return jsonify(dati_json), 500
            
        return jsonify(dati_json), 200
    except Exception as e:
        print(f"💥 [WEBHOOK] Errore fatale nella rotta API: {e}")
        return jsonify({"status": "error", "message": "Errore interno del server"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)