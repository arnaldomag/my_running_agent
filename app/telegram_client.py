import logging
from typing import Any

import requests

from .config import config

logger = logging.getLogger(__name__)


class TelegramNotifier:
    DEFAULT_TIMEOUT = 10

    def __init__(self):
        self.token = config.get_secret("TELEGRAM_TOKEN")
        self.chat_id = config.get_secret("TELEGRAM_CHAT_ID")
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.file_base_url = f"https://api.telegram.org/file/bot{self.token}"

        # Sessione persistente TCP/TLS Keep-Alive verso api.telegram.org
        self.session = requests.Session()

    def send_message(
        self,
        text: str,
        reply_markup: dict[str, Any] | None = None,
        chat_id: int | str | None = None
    ) -> bool:
        target_chat_id = chat_id or self.chat_id
        if not self.token or not target_chat_id:
            logger.warning("⚠️ Credenziali Telegram mancanti (Token o Chat ID). Notifica saltata.")
            return False

        url = f"{self.base_url}/sendMessage"
        payload: dict[str, Any] = {
            "chat_id": target_chat_id,
            "text": text,
            "parse_mode": "HTML"
        }

        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            # Usando json=payload, requests serializza nativamente anche i dict annidati (reply_markup)
            response = self.session.post(url, json=payload, timeout=self.DEFAULT_TIMEOUT)

            # Fallback automatico se l'AI ha generato tag HTML non chiusi/non validi (HTTP 400)
            if response.status_code == 400:
                logger.warning(
                    "⚠️ [TELEGRAM] Errore HTML rilevato (%s). Invio fallback in plain-text...",
                    response.text
                )
                payload.pop("parse_mode", None)
                fallback_resp = self.session.post(url, json=payload, timeout=self.DEFAULT_TIMEOUT)
                fallback_resp.raise_for_status()
                return True

            response.raise_for_status()
            return True

        except requests.exceptions.RequestException as e:
            logger.error("❌ [TELEGRAM] Errore nell'invio del messaggio: %s", e)
            return False

    def answer_callback_query(self, callback_query_id: str) -> bool:
        """Spegne l'indicatore di caricamento sui bottoni inline riutilizzando la Session."""
        if not self.token or not callback_query_id:
            return False
        try:
            url = f"{self.base_url}/answerCallbackQuery"
            self.session.post(url, json={"callback_query_id": callback_query_id}, timeout=5)
            return True
        except requests.exceptions.RequestException as e:
            logger.warning("⚠️ [TELEGRAM] Errore answerCallbackQuery: %s", e)
            return False

    def download_file(self, file_id: str) -> bytes | None:
        """Scarica un file dai server di Telegram riutilizzando la connessione Keep-Alive."""
        try:
            logger.info("⬇️ [TG_CLIENT] Richiesta path per file_id: %s", file_id)
            resp_path = self.session.get(
                f"{self.base_url}/getFile",
                params={"file_id": file_id},
                timeout=self.DEFAULT_TIMEOUT
            )
            resp_path.raise_for_status()
            file_path = resp_path.json()["result"]["file_path"]

            file_resp = self.session.get(
                f"{self.file_base_url}/{file_path}",
                timeout=self.DEFAULT_TIMEOUT
            )
            file_resp.raise_for_status()

            logger.info("✅ [TG_CLIENT] Immagine scaricata con successo (%d bytes).", len(file_resp.content))
            return file_resp.content

        except Exception as e:
            logger.error("❌ [TG_CLIENT] Errore nel download dell'immagine: %s", e)
            return None


notifier = TelegramNotifier()
