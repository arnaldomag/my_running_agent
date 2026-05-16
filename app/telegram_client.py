import requests
from .config import config

class TelegramNotifier:
    def __init__(self):
        self.token = config.get_secret("TELEGRAM_TOKEN")
        self.chat_id = config.get_secret("TELEGRAM_CHAT_ID")
        # Costruiamo l'URL base dell'API per il nostro bot
        self.api_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def send_message(self, text, reply_markup=None):
        if not self.token or not self.chat_id:
            print("⚠️ Credenziali Telegram mancanti (Token o Chat ID). Notifica saltata.")
            return False

        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML"
        }
        
        # Se passiamo dei bottoni, li aggiungiamo al payload
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            response = requests.post(self.api_url, json=payload)
            response.raise_for_status() 
            return True
        except requests.exceptions.RequestException as e:
            print(f"❌ Errore nell'invio a Telegram: {e}")
            return False

notifier = TelegramNotifier()