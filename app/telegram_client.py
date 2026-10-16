import logging
import re
from typing import Any

import requests

from .config import config

logger = logging.getLogger(__name__)

# Regex pre-compilate per sanificare l'HTML di Telegram in < 0.1 ms
RE_BR_TAGS = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)
RE_P_CLOSE = re.compile(r"<\s*/\s*p\s*>", re.IGNORECASE)
RE_LI_OPEN = re.compile(r"<\s*li\s*>", re.IGNORECASE)
# Cattura i tag supportati ufficialmente da Telegram per proteggerli dall'escape
RE_VALID_TG_TAGS = re.compile(
    r"(</?(?:b|strong|i|em|u|ins|s|strike|del|code|pre|blockquote|tg-spoiler)\b[^>]*>|"
    r"<a\s+href=[\"'][^\"']+[\"']\s*>|</a>)",
    re.IGNORECASE
)
RE_ALL_HTML_TAGS = re.compile(r"<[^>]+>")


def sanitize_telegram_html(text: str) -> str:
    """
    Rende il testo generato dall'LLM 100% compatibile con il parser HTML di Telegram:
    1. Sostituisce <br>, </p>, <li> con a capo/elenchi testuali.
    2. Fa l'escape di '<', '>' e '&' (es. 'passo < 4:30') preservando solo i tag Telegram validi.
    """
    # 1. Normalizza tag di blocco comuni che Gemini potrebbe inserire per errore
    text = RE_BR_TAGS.sub("\n", text)
    text = RE_P_CLOSE.sub("\n\n", text)
    text = RE_LI_OPEN.sub("- ", text)

    # 2. Divide la stringa isolando i tag Telegram validi dal resto del testo
    parts = RE_VALID_TG_TAGS.split(text)
    sanitized_parts = []

    for i, part in enumerate(parts):
        if i % 2 == 1:
            # È un tag Telegram valido (es. <b>, </i>, <a href="...">): lo manteniamo intatto
            sanitized_parts.append(part)
        else:
            # È testo normale (o contiene tag HTML non supportati come <ul>, <h3> o simboli '< 4:30'):
            # rimuoviamo eventuali tag strutturali residui come <p>, <ul>, <li>, <h3>
            cleaned = re.sub(r"</?(?:p|ul|ol|li|h[1-6]|div|span|html|body)\b[^>]*>", "", part, flags=re.IGNORECASE)
            # Facciamo l'escape di &, < e > liberi nel testo
            cleaned = cleaned.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            sanitized_parts.append(cleaned)

    return "".join(sanitized_parts)


def strip_html_tags(text: str) -> str:
    """Rimuove tutti i tag HTML nel caso estremo in cui serva il fallback plain-text."""
    clean = RE_ALL_HTML_TAGS.sub("", text)
    return clean.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


class TelegramNotifier:
    DEFAULT_TIMEOUT = 10
    MAX_MESSAGE_LENGTH = 4000

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
        safe_html_text = sanitize_telegram_html(text_chunk)

        payload: dict[str, Any] = {
            "chat_id": target_chat_id,
            "text": safe_html_text,
            "parse_mode": "HTML"
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            # 1. Tentativo standard con HTML sanificato
            response = self.session.post(url, json=payload, timeout=self.DEFAULT_TIMEOUT)
            if response.ok:
                return True

            # 2. Se c'è ancora un errore 400 (es. tag <b> aperto e mai chiuso a metà blocco),
            # inviamo in plain-text PULITO (senza mostrare <b> o <i> in chiaro!)
            if response.status_code == 400:
                logger.warning(
                    "⚠️ [TELEGRAM] Rifiuto 400 (%s). Invio fallback plain-text pulito...",
                    response.text
                )
                payload.pop("parse_mode", None)
                payload["text"] = strip_html_tags(safe_html_text)

                fallback_resp = self.session.post(url, json=payload, timeout=self.DEFAULT_TIMEOUT)
                if fallback_resp.ok:
                    return True

                # 3. Se il 400 dipende da reply_markup malformato, rimuoviamo i bottoni ma teniamo l'HTML!
                if reply_markup:
                    logger.warning("⚠️ [TELEGRAM] Riprovo rimuovendo reply_markup ma mantenendo HTML...")
                    payload.pop("reply_markup", None)
                    payload["text"] = safe_html_text
                    payload["parse_mode"] = "HTML"
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

        if len(text) <= self.MAX_MESSAGE_LENGTH:
            return self._post_single_chunk(target_chat_id, text, reply_markup)

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
