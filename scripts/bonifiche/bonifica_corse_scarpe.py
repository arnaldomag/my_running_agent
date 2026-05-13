import requests
import datetime
import time
import json
import os
from dotenv import load_dotenv

# 1. Carica le chiavi in modo sicuro dal file .env
load_dotenv()

# 1. CONFIGURAZIONE
ACCESS_TOKEN = os.getenv('STRAVA_ACCESS_TOKEN')
FILE_CONFIG = os.path.join("bonifiche", "bonifiche_2026.json")

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
    # Caricamento dati dal file esterno
    dizionario_date = carica_dizionario_json(FILE_CONFIG)
    if not dizionario_date:
        return

    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    
    # Range temporale (tutto il 2026)
    ts_inizio = int(datetime.datetime(2026, 1, 1).timestamp())
    ts_fine = int(datetime.datetime(2026, 12, 31, 23, 59).timestamp())

    print(f"🔍 Caricato JSON con {len(dizionario_date)} date. Controllo corse su Strava...")
    
    corse_da_processare = []
    pagina = 1
    
    while True:
        params = {"after": ts_inizio, "before": ts_fine, "per_page": 100, "page": pagina}
        resp = requests.get("https://www.strava.com/api/v3/athlete/activities", headers=headers, params=params)
        
        if resp.status_code != 200: break
        dati = resp.json()
        if not dati: break
            
        for att in dati:
            tipo = att.get('sport_type') or att.get('type')
            data_corsa = att.get('start_date_local', '')[:10]
            
            # Match tra data corsa e chiavi nel JSON
            if tipo == "Run" and data_corsa in dizionario_date:
                nuovo_gear = dizionario_date[data_corsa]
                
                if att.get('gear_id') != nuovo_gear:
                    corse_da_processare.append({
                        "id": att['id'],
                        "nome": att['name'],
                        "data": data_corsa,
                        "nuovo_gear": nuovo_gear
                    })
        pagina += 1

    if not corse_da_processare:
        print("✅ Nessun aggiornamento necessario per le date nel JSON.")
        return

    print(f"\n🚀 Trovate {len(corse_da_processare)} corse da aggiornare.")
    for c in corse_da_processare:
        print(f"   - {c['data']}: {c['nome']} -> {c['nuovo_gear']}")
    
    conferma = input("\nVuoi procedere? (s/n): ")
    if conferma.lower() == 's':
        for corsa in corse_da_processare:
            url_update = f"https://www.strava.com/api/v3/activities/{corsa['id']}"
            res = requests.put(url_update, headers=headers, data={"gear_id": corsa['nuovo_gear']})
            if res.status_code == 200:
                print(f"✅ OK: {corsa['data']}")
            else:
                print(f"❌ Errore su {corsa['data']}")
            time.sleep(0.8)
        print("\n✨ Bonifica da JSON completata!")

if __name__ == "__main__":
    update_batch_da_json()