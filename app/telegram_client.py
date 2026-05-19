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

    def download_file(self, file_id):
        """Scarica un file dai server di Telegram e ne restituisce i bytes"""
        try:
            print(f"⬇️ [TG_CLIENT] Richiesta path per file_id: {file_id}")
            
            # 1. Chiediamo a Telegram dove si trova fisicamente il file
            url_path = f"https://api.telegram.org/bot{self.token}/getFile?file_id={file_id}"
            response = requests.get(url_path)
            response.raise_for_status()
            path_data = response.json()
            
            file_path = path_data['result']['file_path']
            
            # 2. Scarichiamo i bytes dell'immagine
            url_file = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
            file_response = requests.get(url_file)
            file_response.raise_for_status()
            
            print("✅ [TG_CLIENT] Immagine scaricata con successo.")
            return file_response.content
            
        except Exception as e:
            print(f"❌ [TG_CLIENT] Errore nel download dell'immagine: {e}")
            return None

notifier = TelegramNotifier()