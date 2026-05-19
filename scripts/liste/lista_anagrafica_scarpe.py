import requests
import os
from dotenv import load_dotenv

# 1. Carica le chiavi in modo sicuro dal file .env
load_dotenv()

# 2. CONFIGURAZIONE CREDENZIALI
# Assicurati di avere queste variabili valorizzate nel tuo file .env
CLIENT_ID = os.getenv('STRAVA_CLIENT_ID')
CLIENT_SECRET = os.getenv('STRAVA_CLIENT_SECRET')
REFRESH_TOKEN = os.getenv('STRAVA_REFRESH_TOKEN')

def ottieni_nuovo_access_token():
    """Richiede un nuovo access_token a Strava utilizzando il refresh_token."""
    print("🔄 Richiesta di un nuovo Access Token in corso...")
    
    auth_url = "https://www.strava.com/oauth/token"
    payload = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'refresh_token': REFRESH_TOKEN,
        'grant_type': 'refresh_token',
        'f': 'json'
    }

    try:
        response = requests.post(auth_url, data=payload)
        
        if response.status_code == 200:
            token_data = response.json()
            access_token = token_data.get('access_token')
            print("✅ Nuovo Access Token ottenuto con successo!\n")
            return access_token
        else:
            print(f"❌ Errore durante il refresh del token: {response.status_code}")
            print(response.json())
            return None
            
    except Exception as e:
        print(f"❌ Si è verificato un errore di connessione (Refresh Token): {e}")
        return None

def elenca_anagrafica_scarpe():
    # Ottieni dinamicamente il token prima di fare la chiamata API
    access_token = ottieni_nuovo_access_token()
    
    if not access_token:
        print("⚠️ Impossibile procedere: recupero del token fallito.")
        return

    headers = {"Authorization": f"Bearer {access_token}"}
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
            print("❌ Errore 401: Token non valido o scaduto.")
        else:
            print(f"❌ Errore API: {response.status_code}")
            print(response.json())
            
    except Exception as e:
        print(f"❌ Si è verificato un errore durante la lettura del profilo: {e}")

if __name__ == "__main__":
    elenca_anagrafica_scarpe()