import requests
from .config import config

class TelegramNotifier:
    def __init__(self):
        self.token = config.get_secret("TELEGRAM_TOKEN")
        self.chat_id = config.get_secret("TELEGRAM_CHAT_ID")
        # Costruiamo l'URL base dell'API per il nostro bot
        self.api_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def send_message(self, text):
        if not self.token or not self.chat_id:
            print("⚠️ Credenziali Telegram mancanti (Token o Chat ID). Notifica saltata.")
            return False

        # Prepariamo il payload formattato in Markdown per renderlo leggibile
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }

        try:
            response = requests.post(self.api_url, json=payload)
            response.raise_for_status() # Lancia un errore se la chiamata fallisce
            return True
        except requests.exceptions.RequestException as e:
            print(f"❌ Errore nell'invio a Telegram: {e}")
            return False

notifier = TelegramNotifier()