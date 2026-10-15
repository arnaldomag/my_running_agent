import hashlib
import hmac
import logging
import os
import sys
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable
from urllib.parse import parse_qsl

from flask import Flask, Response, jsonify, request

from app.analyst import analyst
from app.config import config
from app.database import db
from app.orchestrator import BotOrchestrator
from app.runalyze_client import runalyze_client
from app.telegram_client import notifier

# Configurazione Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger("webhook")

app = Flask(__name__)

# Inizializzazione Orchestratore
orchestrator = BotOrchestrator(db, analyst, notifier, runalyze_client)

# ==================================================
# THREAD POOL & DEDUPLICAZIONE O(1) THREAD-SAFE
# ==================================================
MAX_WORKERS = int(os.environ.get("WEBHOOK_MAX_WORKERS", 8))
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="bot_worker")


def submit_background_task(func: Callable, *args: Any, **kwargs: Any) -> None:
    """Invia un task al ThreadPool catturando e loggando eventuali eccezioni silenti."""
    def _wrapper():
        try:
            func(*args, **kwargs)
        except Exception as exc:
            logger.exception("💥 Errore nel background worker [%s]: %s", func.__name__, exc)

    executor.submit(_wrapper)


class UpdateDeduplicator:
    """Struttura thread-safe con ricerca O(1) tramite set + deque per l'eviction FIFO."""
    def __init__(self, maxlen: int = 200):
        self.maxlen = maxlen
        self._queue: deque[int] = deque(maxlen=maxlen)
        self._set: set[int] = set()
        self._lock = threading.Lock()

    def is_duplicate(self, update_id: int) -> bool:
        with self._lock:
            if update_id in self._set:
                return True
            if len(self._queue) == self.maxlen:
                oldest = self._queue.popleft()
                self._set.discard(oldest)
            self._queue.append(update_id)
            self._set.add(update_id)
            return False


deduplicator = UpdateDeduplicator(maxlen=200)

# Pre-calcolo della chiave segreta HMAC per evitare ricalcoli ad ogni richiesta
_BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN") or config.get_secret("TELEGRAM_TOKEN")
_TELEGRAM_WEBAPP_SECRET: bytes | None = (
    hmac.new(b"WebAppData", _BOT_TOKEN.encode("utf-8"), hashlib.sha256).digest()
    if _BOT_TOKEN else None
)


# ==================================================
# OTTIMIZZAZIONE CACHE E SICUREZZA HEADERS
# ==================================================
@app.after_request
def add_security_and_cache_headers(response: Response) -> Response:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"

    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    else:
        response.headers["Cache-Control"] = "public, max-age=3600"

    return response


# ==================================================
# LOGICA DI VALIDAZIONE TELEGRAM
# ==================================================
def verify_telegram_data(init_data_str: str) -> bool:
    """Verifica l'autenticità del payload di Telegram tramite chiave HMAC pre-calcolata."""
    if not _TELEGRAM_WEBAPP_SECRET or not init_data_str:
        return False

    try:
        parsed_data = dict(parse_qsl(init_data_str, keep_blank_values=True))
        received_hash = parsed_data.pop("hash", None)
        if not received_hash:
            return False

        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
        computed_hash = hmac.new(
            _TELEGRAM_WEBAPP_SECRET,
            data_check_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(computed_hash, received_hash)
    except Exception as e:
        logger.warning("⚠️ [SECURITY] Errore validazione initData: %s", e)
        return False


# ==================================================
# DISPATCHING COMANDI E CALLBACK
# ==================================================
def _dispatch_text_command(chat_id: int, testo: str, testo_lower: str) -> None:
    """Instrada i comandi slash verso il ThreadPool (senza più sincronizzazione Firestore)."""
    if testo_lower in ("/elenco scarpe", "/elencoscarpe", "/scarpe"):
        submit_background_task(orchestrator.process_shoe_list, chat_id)
    elif testo_lower.startswith("/pianifica"):
        submit_background_task(orchestrator.handle_plan_creation, testo)
    elif testo_lower == "/piano":
        submit_background_task(orchestrator.handle_plan_view)
    elif testo_lower.startswith("/modifica"):
        submit_background_task(orchestrator.handle_plan_modification, testo)
    else:
        submit_background_task(orchestrator.handle_unrecognized_command)


def _dispatch_callback_query(query: dict[str, Any]) -> None:
    """Instrada i click sui bottoni inline senza bloccare il thread HTTP di Flask."""
    callback_data: str = query.get("data", "")
    query_id: str = query.get("id", "")
    chat_id_btn = query.get("message", {}).get("chat", {}).get("id")

    # Spegniamo subito lo spinner di caricamento sul bottone Telegram
    if query_id:
        submit_background_task(orchestrator.answer_callback, query_id)

    if callback_data.startswith("analyze_"):
        activity_id = callback_data.removeprefix("analyze_")
        submit_background_task(orchestrator.process_run_analysis, activity_id, chat_id_btn)

    elif callback_data.startswith("shoe_"):
        gear_id = callback_data.removeprefix("shoe_")
        submit_background_task(orchestrator.process_shoe_analysis, chat_id_btn, gear_id)

    elif callback_data == "fallback_last_week_show":
        submit_background_task(orchestrator.process_fallback_weekly_report)

    elif callback_data == "fallback_last_week_ignore":
        submit_background_task(orchestrator.handle_fallback_ignore)

    elif callback_data.startswith("man_done_"):
        session_id = callback_data.removeprefix("man_done_")
        submit_background_task(orchestrator.toggle_session_status, session_id, action="done")

    elif callback_data.startswith("del_sess_"):
        session_id = callback_data.removeprefix("del_sess_")
        submit_background_task(orchestrator.toggle_session_status, session_id, action="delete")

    elif callback_data.startswith("reopen_sess_"):
        session_id = callback_data.removeprefix("reopen_sess_")
        submit_background_task(orchestrator.toggle_session_status, session_id, action="reopen")


# ==================================================
# ROUTES
# ==================================================
@app.route("/telegram-webhook", methods=["POST"])
def telegram_webhook():
    try:
        update = request.get_json(silent=True)
        if not update:
            return jsonify({"status": "ignored", "reason": "empty_payload"}), 200

        # 0. Controllo Anti-Doppioni O(1)
        update_id = update.get("update_id")
        if update_id is not None and deduplicator.is_duplicate(update_id):
            logger.info("♻️ [WEBHOOK] Retry di Telegram ignorato (Update ID: %s)", update_id)
            return jsonify({"status": "ok"}), 200

        logger.info("📥 [WEBHOOK] Ricevuto update ID: %s", update_id)

        message = update.get("message")
        if message:
            # 1. Gestione messaggi di testo
            if "text" in message:
                testo = message["text"].strip()
                chat_id = message["chat"]["id"]

                if testo.startswith("/"):
                    _dispatch_text_command(chat_id, testo, testo.lower())
                else:
                    submit_background_task(orchestrator.handle_chat_ai, chat_id, testo)

                return jsonify({"status": "ok"}), 200

            # 2. Gestione Foto (OCR Bilancia)
            if "photo" in message:
                submit_background_task(orchestrator.process_incoming_photo, message["photo"])
                return jsonify({"status": "ok"}), 200

        # 3. Gestione Callback Queries (Bottoni Inline)
        if "callback_query" in update:
            _dispatch_callback_query(update["callback_query"])
            return jsonify({"status": "ok"}), 200

        return jsonify({"status": "ok"}), 200

    except Exception as global_error:
        logger.exception("💥 [WEBHOOK] Errore critico nella rotta: %s", global_error)
        return jsonify({"status": "error", "message": str(global_error)}), 200


@app.route("/tasks/weekly-report", methods=["POST"])
def tasks_weekly_report():
    try:
        logger.info("⏰ [CRON] Chiamata temporizzata ricevuta da Cloud Scheduler!")
        mio_chat_id = os.environ.get("TELEGRAM_CHAT_ID") or config.get_secret("TELEGRAM_CHAT_ID")
        orchestrator.process_cron_weekly_report(mio_chat_id)
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        logger.exception("❌ [CRON] Errore durante l'esecuzione del cron job: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

