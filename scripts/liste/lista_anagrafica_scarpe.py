import requests
import os
from dotenv import load_dotenv

# 1. Carica le chiavi in modo sicuro dal file .env
load_dotenv()

# 1. CONFIGURAZIONE
# Assicurati che il token abbia il permesso 'profile:read_all'
ACCESS_TOKEN = os.getenv('STRAVA_ACCESS_TOKEN')

def elenca_anagrafica_scarpe():
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    url = "https://www.strava.com/api/v3/athlete"
    
    print("🔍 Recupero informazioni dal profilo atleta...")
    
    try:
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            dati_atleta = response.json()
            scarpe = dati_atleta.get('shoes', [])
            
            if not scarpe:
                print("⚠️ Nessuna scarpa trovata. Aggiungile prima dall'app o dal sito di Strava!")
                return

            print("\n👟 ANAGRAFICA SCARPE REGISTRATE:")
            print("-" * 85)
            # Intestazione tabella
            print(f"{'NOME MODELLO':<35} | {'NICKNAME':<25} | {'ID (GEAR_ID)':<15}")
            print("-" * 85)
            
            for s in scarpe:
                nome = s.get('name', 'N/D')
                # Il nickname spesso coincide col nome se non personalizzato su Strava
                nickname = s.get('nickname', 'N/D')
                id_scarpa = s.get('id', 'N/D')
                
                print(f"{nome[:33]:<35} | {nickname[:23]:<25} | {id_scarpa:<15}")
            
            print("-" * 85)
            print(f"\n✅ Totale scarpe censite: {len(scarpe)}")
            
        elif response.status_code == 401:
            print("❌ Errore 401: Token non valido o scaduto. Rigeneralo con main.py.")
        else:
            print(f"❌ Errore API: {response.status_code}")
            print(response.json())
            
    except Exception as e:
        print(f"❌ Si è verificato un errore: {e}")

if __name__ == "__main__":
    elenca_anagrafica_scarpe()