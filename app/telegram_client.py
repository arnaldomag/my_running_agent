import logging
from typing import Any

import requests

from .config import config

logger = logging.getLogger(__name__)


class TelegramNotifier:
    DEFAULT_TIMEOUT = 10
    MAX_MESSAGE_LENGTH = 4000  # Limite Telegram è 4096, teniamo margine di sicurezza

    def __init__(self):
        self.token = config.get_secret("TELEGRAM_TOKEN")
        self.chat_id = config.get_secret("TELEGRAM_CHAT_ID")
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.file_base_url = f"https://api.telegram.org/file/bot{self.token}"

        self.session = requests.Session()

    def _post_single_chunk(
        self,
        target_chat_id: int | str,
        text_chunk: str,
        reply_markup: dict[str, Any] | None = None
    ) -> bool:
        url = f"{self.base_url}/sendMessage"
        payload: dict[str, Any] = {
            "chat_id": target_chat_id,
            "text": text_chunk,
            "parse_mode": "HTML"
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            # 1. Tentativo standard con HTML e bottoni
            response = self.session.post(url, json=payload, timeout=self.DEFAULT_TIMEOUT)
            if response.ok:
                return True

            # 2. Se errore 400 (es. tag HTML non chiusi da Gemini), riprova senza HTML
            if response.status_code == 400:
                logger.warning(
                    "⚠️ [TELEGRAM] Rifiuto 400 (%s). Riprovo senza parse_mode HTML...",
                    response.text
                )
                payload.pop("parse_mode", None)
                fallback_resp = self.session.post(url, json=payload, timeout=self.DEFAULT_TIMEOUT)
                if fallback_resp.ok:
                    return True

                # 3. Se fallisce ancora (es. reply_markup malformato), invia almeno il testo puro
                if reply_markup:
                    logger.warning("⚠️ [TELEGRAM] Riprovo rimuovendo anche reply_markup...")
                    payload.pop("reply_markup", None)
                    last_resp = self.session.post(url, json=payload, timeout=self.DEFAULT_TIMEOUT)
                    if last_resp.ok:
                        return True

                logger.error("❌ [TELEGRAM] Falliti tutti i tentativi 400: %s", fallback_resp.text)
                return False

            response.raise_for_status()
            return True

        except requests.exceptions.RequestException as e:
            logger.error("❌ [TELEGRAM] Errore di rete nell'invio a Telegram: %s", e)
            return False

    def send_message(
        self,
        text: str,
        reply_markup: dict[str, Any] | None = None,
        chat_id: int | str | None = None
    ) -> bool:
        target_chat_id = chat_id or self.chat_id
        if not self.token or not target_chat_id:
            logger.error("❌ [TELEGRAM] Credenziali mancanti (Token o Chat ID=%s). Invio annullato.", target_chat_id)
            return False

        if not text or not text.strip():
            logger.warning("⚠️ [TELEGRAM] Tentativo di inviare un messaggio vuoto. Ignorato.")
            return False

        # Se il messaggio sta in un solo blocco (< 4000 chars), invio diretto
        if len(text) <= self.MAX_MESSAGE_LENGTH:
            return self._post_single_chunk(target_chat_id, text, reply_markup)

        # Altrimenti spezziamo il messaggio per paragrafi per non rompere il limite di 4096 chars
        logger.info("✂️ [TELEGRAM] Messaggio lungo (%d chars), suddivisione in blocchi...", len(text))
        chunks = []
        current = ""
        for line in text.splitlines(keepends=True):
            if len(current) + len(line) > self.MAX_MESSAGE_LENGTH:
                if current:
                    chunks.append(current)
                    current = line
                else:
                    chunks.append(line[:self.MAX_MESSAGE_LENGTH])
                    current = line[self.MAX_MESSAGE_LENGTH:]
            else:
                current += line
        if current:
            chunks.append(current)

        success = True
        for i, chunk in enumerate(chunks):
            # Attacchiamo i bottoni solo all'ultimo blocco del messaggio
            markup = reply_markup if (i == len(chunks) - 1) else None
            if not self._post_single_chunk(target_chat_id, chunk, markup):
                success = False

        return success

    def answer_callback_query(self, callback_query_id: str) -> bool:
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
