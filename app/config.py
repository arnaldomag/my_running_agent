import os
import google.auth
from google.cloud import secretmanager
from dotenv import load_dotenv
load_dotenv() # Questo carica il file .env nelle variabili d'ambiente

class Config:
    def __init__(self):
        # 1. Riconoscimento Ambiente
        # Se esiste K_SERVICE, siamo su Google Cloud Run
        self.is_cloud = os.getenv('K_SERVICE') is not None
        
        # 2. Identificazione Progetto
        try:
            _, self.project_id = google.auth.default()
        except:
            self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "my-running-agent")

        # ==================================================
        # 3. VARIABILI DI CONFIGURAZIONE (Task 4.2)
        # ==================================================
        # Inizializziamo l'URL della WebApp usando il tuo gestore dei segreti.
        # N.B. Deve essere messo DOPO aver definito self.is_cloud e self.project_id
        self.webapp_url = self.get_secret("WEBAPP_URL")

    def get_secret(self, name, default=None):
        """Recupera un segreto da Secret Manager (Cloud) o .env (Locale)"""
        if self.is_cloud:
            try:
                client = secretmanager.SecretManagerServiceClient()
                resource_name = f"projects/{self.project_id}/secrets/{name}/versions/latest"
                response = client.access_secret_version(request={"name": resource_name})
                return response.payload.data.decode("UTF-8")
            except Exception as e:
                print(f"⚠️ Errore Secret Manager per {name}: {e}")
                return os.getenv(name, default)
        
        # In locale usa le variabili d'ambiente caricate da VS Code o .env
        return os.getenv(name, default)

# Creiamo un'istanza pronta all'uso
config = Config()