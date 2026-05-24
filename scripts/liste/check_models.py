import sys
import os
# Aggiunge la cartella root (due livelli più in alto) al path di Python
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google import genai
from app.config import config

def discover_models():
    api_key = config.get_secret("GEMINI_API_KEY")
    if not api_key:
        print("Errore: API Key non trovata.")
        return

    client = genai.Client(api_key=api_key)
    
    print("🔍 Interrogazione in corso...\nModelli 'Flash' disponibili per la tua API Key:")
    try:
        models = client.models.list()
        for m in models:
            if "flash" in m.name:
                print(f"✅ {m.name}")
    except Exception as e:
        print(f"Errore di connessione: {e}")

if __name__ == "__main__":
    discover_models()