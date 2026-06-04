import requests
import json
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
        
        # OTTIMIZZAZIONE: Convertiamo il dizionario in stringa JSON esplicita per evitare 
        # rari errori 400 "Bad Request" dall'API di Telegram sui bottoni inline
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)

        try:
            # 1. PRIMO TENTATIVO: Invio con formattazione HTML
            response = requests.post(self.api_url, data=payload)
            
            # Se Telegram rifiuta il pacchetto per via di tag HTML rotti (Errore 400)
            if response.status_code == 400:
                print(f"⚠️ [TELEGRAM] Errore di formattazione HTML rilevato ({response.text}). Attivazione Fallback...")
                
                # Rimuoviamo il vincolo HTML
                payload.pop("parse_mode", None)
                
                # 2. SECONDO TENTATIVO: Invio come testo semplice
                fallback_response = requests.post(self.api_url, data=payload)
                fallback_response.raise_for_status() # Solleva errore se fallisce anche questo
                
                print("✅ Messaggio di emergenza inviato con successo (senza HTML).")
                return True
                
            # Se la richiesta originale ha dato un errore diverso (es. 401 Unauthorized), lo solleva
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
            
            # 2. Scarichiamo i bytes dell'immagine vera e propria
            url_file = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
            file_response = requests.get(url_file)
            file_response.raise_for_status()
            
            print("✅ [TG_CLIENT] Immagine scaricata con successo.")
            return file_response.content
            
        except Exception as e:
            print(f"❌ [TG_CLIENT] Errore nel download dell'immagine: {e}")
            return None

notifier = TelegramNotifier()