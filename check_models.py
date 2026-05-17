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
        # Recupera tutti i modelli disponibili
        models = client.models.list()
        for m in models:
            # Filtriamo solo quelli che contengono "flash" per comodità
            if "flash" in m.name:
                print(f"✅ {m.name}")
    except Exception as e:
        print(f"Errore di connessione: {e}")

if __name__ == "__main__":
    discover_models()