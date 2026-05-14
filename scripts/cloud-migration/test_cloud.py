import os
from google.cloud import secretmanager
from google.cloud import firestore

# Sostituisci con l'ID del tuo progetto creato prima
PROJECT_ID = "IL-TUO-PROJECT-ID" 

def test_connection():
    print(f"--- Test Connessione Google Cloud per {PROJECT_ID} ---")
    
    try:
        # 1. Test Secret Manager
        client = secretmanager.SecretManagerServiceClient()
        # Sostituisci 'TELEGRAM_TOKEN' con il nome del segreto che hai creato
        name = f"projects/{PROJECT_ID}/secrets/TELEGRAM_TOKEN/versions/latest"
        response = client.access_secret_version(request={"name": name})
        print("✅ Secret Manager: Connessione riuscita! Token recuperato.")
        
        # 2. Test Firestore
        db = firestore.Client(project=PROJECT_ID)
        # Proviamo a leggere la collezione 'activities' creata prima
        docs = db.collection('activities').limit(1).get()
        print("✅ Firestore: Connessione riuscita!")
        
    except Exception as e:
        print(f"❌ Errore durante il test: {e}")

if __name__ == "__main__":
    test_connection()