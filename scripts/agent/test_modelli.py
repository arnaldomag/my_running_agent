import google as genai
from ...app.config import config

# 1. Recupera la chiave
api_key = config.get_secret("GEMINI_API_KEY")
genai.configure(api_key=api_key)

# 2. Cerca i modelli
print("🔍 Ricerca modelli disponibili...")
for m in genai.list_models():
    # Filtriamo solo i modelli che generano contenuto (ignorando quelli vecchi o solo embedding)
    if 'generateContent' in m.supported_generation_methods:
        print(f"✅ Nome: {m.name}")
        print(f"   Descrizione: {m.description}\n")