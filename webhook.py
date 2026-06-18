import os
from flask import Flask, request, jsonify
# Importiamo moduli e servizi
from app.analyst import analyst
from app.telegram_client import notifier
from app.database import db
from app.orchestrator import BotOrchestrator
import hashlib
from urllib.parse import parse_qsl
import hmac
from collections import deque
import threading
from app.runalyze_client import runalyze_client

app = Flask(__name__)

# Inizializziamo l'orchestratore
orchestrator = BotOrchestrator(db, analyst, notifier, runalyze_client)

# --- MEMORIA ANTI-DOPPIONI ---
processed_updates = deque(maxlen=100)

# ==================================================
# OTTIMIZZAZIONE CACHE E SICUREZZA HEADERS
# ==================================================
@app.after_request
def add_security_and_cache_headers(response):
    """
    Aggiunge header di sicurezza a tutte le risposte e disabilita la cache 
    aggressiva per le chiamate API per garantire dati sempre freschi.
    """
    # 1. Security Headers base
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'

    # 2. Gestione Caching
    # Se la richiesta è diretta all'API JSON, forziamo il browser a non usare la cache
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    else:
        # Per i file statici e l'HTML della dashboard, permettiamo una cache breve (es. 1 ora)
        # per velocizzare l'apertura successiva su Telegram
        response.headers['Cache-Control'] = 'public, max-age=3600'

    return response

# --- LOGICA DI VALIDAZIONE TELEGRAM ---
def verify_telegram_data(init_data_str):
    """Verifica l'autenticità del payload di Telegram tramite HMAC-SHA256"""
    bot_token = os.environ.get("TELEGRAM_TOKEN")
    if not bot_token or not init_data_str:
        return False
        
    try:
        parsed_data = dict(parse_qsl(init_data_str))
        if "hash" not in parsed_data:
            return False
            
        received_hash = parsed_data.pop("hash")
        
        # Le specifiche di Telegram richiedono l'ordinamento alfabetico delle chiavi
        sorted_items = sorted(parsed_data.items())
        data_check_string = "\n".join([f"{k}={v}" for k, v in sorted_items])
        
        # Calcolo della chiave derivata
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        return hmac.compare_digest(computed_hash, received_hash)
    except Exception as e:
        print(f"⚠️ [SECURITY] Errore validazione initData: {e}")
        return False

@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    try:
        update = request.json

        # ==================================================
        # SISTEMA ANTI-DOPPIONI (TIMEOUT TELEGRAM)
        # ==================================================
        update_id = update.get('update_id')
        if update_id:
            if update_id in processed_updates:
                print(f"♻️ [WEBHOOK] Retry di Telegram ignorato (Update ID: {update_id})")
                return jsonify({"status": "ok"}), 200
            
            # Se è un messaggio nuovo, lo salviamo in memoria
            processed_updates.append(update_id)
        # ==================================================

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
                    threading.Thread(target=orchestrator.process_shoe_list, args=(chat_id,)).start()
                elif testo_lower.startswith('/syncstorico'):
                    threading.Thread(target=orchestrator.handle_sync_storico, args=(testo,)).start()
                elif testo_lower == '/sync':
                    threading.Thread(target=orchestrator.handle_sync_incrementale).start()
                elif testo_lower.startswith('/pianifica'):
                    threading.Thread(target=orchestrator.handle_plan_creation, args=(testo,)).start()
                elif testo_lower == '/piano':
                    threading.Thread(target=orchestrator.handle_plan_view).start()
                elif testo_lower.startswith('/modifica'):
                    threading.Thread(target=orchestrator.handle_plan_modification, args=(testo,)).start()
                else:
                    threading.Thread(target=orchestrator.handle_unrecognized_command).start()
                return jsonify({"status": "ok"}), 200

            # B) Chat libera con l'Intelligenza Artificiale (MessageHandler)
            # orchestrator.handle_chat_ai(chat_id, testo)

            # NUOVO CODICE: Creiamo un thread in background
            thread = threading.Thread(target=orchestrator.handle_chat_ai, args=(chat_id, testo))
            thread.start()
            
            # Restituiamo SUBITO l'OK a Telegram in 1 millisecondo
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
                # orchestrator.process_run_analysis(activity_id)
                threading.Thread(target=orchestrator.process_run_analysis, args=(activity_id,)).start()
                
            elif callback_data == 'fallback_last_week_show':
                orchestrator.process_fallback_weekly_report()
                
            elif callback_data == 'fallback_last_week_ignore':
                orchestrator.handle_fallback_ignore()
                
            elif callback_data.startswith('shoe_'):
                gear_id = callback_data.replace('shoe_', '')
                # Estraiamo il chat_id dalla query del bottone
                chat_id_btn = query['message']['chat']['id']
                threading.Thread(target=orchestrator.process_shoe_analysis, args=(chat_id_btn, gear_id)).start()

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
        mio_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        threading.Thread(target=orchestrator.process_cron_weekly_report, args=(mio_chat_id,)).start()
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        print(f"❌ [CRON] Errore durante l'esecuzione del cron job: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
