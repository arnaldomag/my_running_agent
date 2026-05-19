import requests
import datetime
import time
import json
import os
from dotenv import load_dotenv

# 1. Carica le chiavi in modo sicuro dal file .env
load_dotenv()

# 2. CONFIGURAZIONE CREDENZIALI E ID
CLIENT_ID = os.getenv('STRAVA_CLIENT_ID')
CLIENT_SECRET = os.getenv('STRAVA_CLIENT_SECRET')
REFRESH_TOKEN = os.getenv('STRAVA_REFRESH_TOKEN')

FILE_CONFIG = os.path.join("scripts", "bonifiche", "bonifiche_2026.json")
ID_SCARPA_DEFAULT = "g31016718"  # ID per le corse del 2026 NON presenti nel JSON

def ottieni_nuovo_access_token():
    """Richiede un nuovo access_token a Strava utilizzando il refresh_token."""
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
            return response.json().get('access_token')
        else:
            print(f"❌ Errore rigenerazione Token: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Errore di connessione durante il refresh: {e}")
        return None

def carica_dizionario_json(nome_file):
    if not os.path.exists(nome_file):
        print(f"❌ Errore: Il file {nome_file} non esiste.")
        return None
    try:
        with open(nome_file, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"❌ Errore: Il file {nome_file} non è un JSON valido.")
        return None

def update_batch_da_json():
    # Caricamento dati dal file esterno (servirà come lista di esclusione)
    dizionario_date = carica_dizionario_json(FILE_CONFIG)
    if dizionario_date is None:
        return

    # Ottieni dinamicamente il token valido
    access_token = ottieni_nuovo_access_token()
    if not access_token:
        print("⚠️ Impossibile procedere: recupero del token fallito.")
        return

    headers = {"Authorization": f"Bearer {access_token}"}
    
    # Range temporale (tutto il 2026)
    ts_inizio = int(datetime.datetime(2026, 1, 1).timestamp())
    ts_fine = int(datetime.datetime(2026, 12, 31, 23, 59).timestamp())

    print(f"🔍 Caricato JSON con {len(dizionario_date)} date da escludere. Controllo corse 2026 su Strava...")
    
    corse_da_processare = []
    pagina = 1
    
    while True:
        params = {"after": ts_inizio, "before": ts_fine, "per_page": 100, "page": pagina}
        resp = requests.get("https://www.strava.com/api/v3/athlete/activities", headers=headers, params=params)
        
        if resp.status_code != 200: 
            print(f"❌ Errore nel recupero delle attività: {resp.status_code}")
            break
        
        dati = resp.json()
        if not dati: 
            break
            
        for att in dati:
            tipo = att.get('sport_type') or att.get('type')
            data_corsa = att.get('start_date_local', '')[:10]
            
            # MODIFICA: Se è una corsa ("Run") e la data NON è presente nel file JSON
            if tipo == "Run" and data_corsa not in dizionario_date:
                
                # Verifica se l'attività non ha già associata la scarpa corretta
                if att.get('gear_id') != ID_SCARPA_DEFAULT:
                    corse_da_processare.append({
                        "id": att['id'],
                        "nome": att['name'],
                        "data": data_corsa,
                        "nuovo_gear": ID_SCARPA_DEFAULT
                    })
        pagina += 1

    if not corse_da_processare:
        print("✅ Tutte le corse del 2026 fuori dal JSON hanno già la scarpa corretta associata.")
        return

    print(f"\n🚀 Trovate {len(corse_da_processare)} corse da aggiornare (non incluse nel JSON).")
    for c in corse_da_processare:
        print(f"   - {c['data']}: {c['nome']} -> associazioni a scarpa: {c['nuovo_gear']}")
    
    conferma = input("\nVuoi procedere con l'aggiornamento su Strava? (s/n): ")
    if conferma.lower() == 's':
        for corsa in corse_da_processare:
            url_update = f"https://www.strava.com/api/v3/activities/{corsa['id']}"
            res = requests.put(url_update, headers=headers, data={"gear_id": corsa['nuovo_gear']})
            if res.status_code == 200:
                print(f"✅ OK Aggiornata: {corsa['data']} - {corsa['nome']}")
            else:
                print(f"❌ Errore nell'aggiornamento della corsa in data {corsa['data']}")
            
            # Rispetto dei limiti di quota dell'API di Strava
            time.sleep(0.8)
        print("\n✨ Bonifica delle attività fuori dal JSON completata!")

if __name__ == "__main__":
    update_batch_da_json()