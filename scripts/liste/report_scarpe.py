import requests
import pandas as pd
import datetime
import os
from dotenv import load_dotenv

# 1. Carica le chiavi in modo sicuro dal file .env
load_dotenv()

# INCOLLA QUI IL TUO ACCESS TOKEN (con permessi activity:read_all e profile:read_all)
ACCESS_TOKEN = os.getenv('STRAVA_ACCESS_TOKEN')

def genera_report_2026():
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    mappa_scarpe = {}
    
    # 1. Recupero anagrafica scarpe
    print("1️⃣ Recupero anagrafica scarpe dal profilo...")
    resp_atleta = requests.get("https://www.strava.com/api/v3/athlete", headers=headers)
    
    if resp_atleta.status_code == 200:
        scarpe_profilo = resp_atleta.json().get('shoes', [])
        for scarpa in scarpe_profilo:
            mappa_scarpe[scarpa['id']] = scarpa['name']
    else:
        print("⚠️ Errore nel recupero dei nomi scarpe. Vedrai solo i codici ID.")

    # 2. Definizione limiti temporali per il 2026
    # 'after' e 'before' richiedono timestamp UNIX
    timestamp_inizio = int(datetime.datetime(2026, 1, 1).timestamp())
    timestamp_fine = int(datetime.datetime(2026, 12, 31, 23, 59, 59).timestamp())

    print(f"2️⃣ Estrazione di TUTTI gli allenamenti del 2026...")
    corse = []
    pagina = 1
    
    while True:
        params = {
            "after": timestamp_inizio,
            "before": timestamp_fine,
            "per_page": 100,
            "page": pagina
        }
        
        resp_corse = requests.get("https://www.strava.com/api/v3/athlete/activities", headers=headers, params=params)
        
        if resp_corse.status_code != 200:
            print(f"❌ Errore API alla pagina {pagina}:", resp_corse.json())
            break
            
        dati = resp_corse.json()
        
        # Se la pagina è vuota, abbiamo finito di scaricare il 2026
        if not dati:
            break
            
        for att in dati:
            tipo = att.get('sport_type') or att.get('type')
            
            # Filtriamo solo le attività di corsa
            if tipo and 'Run' in tipo:
                corse.append({
                    "id": att['id'],
                    "nome_corsa": att.get('name', 'Senza Titolo'),
                    "data": att.get('start_date_local', '')[:10],
                    "tipo": tipo,
                    "distanza_km": att.get('distance', 0) / 1000,
                    "gear_id": att.get('gear_id')
                })
        
        print(f"   ...scaricata pagina {pagina}")
        pagina += 1

    print(f"\n✅ Estrazione completata: {len(corse)} corse trovate nel 2026.")
    
    if not corse:
        print("Nessuna corsa trovata per il periodo selezionato.")
        return

    # 3. Elaborazione con Pandas
    df = pd.DataFrame(corse)
    df['gear_id'] = df['gear_id'].fillna('Senza_Scarpa')
    df['nome_scarpa'] = df['gear_id'].map(mappa_scarpe).fillna(df['gear_id'])
    
    # Aggregazione per ordinamento testata
    totali_scarpe = df.groupby('nome_scarpa')['distanza_km'].sum().sort_values(ascending=False)
    
    # 4. Output a schermo
    print("\n📊 REPORT CORSE 2026 📊")
    print("=" * 80)
    
    for scarpa, totale_km in totali_scarpe.items():
        print(f"\n👟 {scarpa.upper()} | Totale Anno: {totale_km:.2f} km")
        print("-" * 80)
        
        dettaglio_scarpa = df[df['nome_scarpa'] == scarpa].sort_values(by='data', ascending=False)
        
        for _, riga in dettaglio_scarpa.iterrows():
            data_str = riga['data']
            tipo_str = riga['tipo'].ljust(10)
            dist_str = f"{riga['distanza_km']:>6.2f} km"
            nome_str = riga['nome_corsa'][:35].ljust(35)
            
            print(f"   📅 {data_str} | {tipo_str} | {dist_str} | 🏃 {nome_str}")
            
    print("\n" + "=" * 80)
    print(f"TOTALE KM CORSI NEL 2026: {df['distanza_km'].sum():.2f} km")

if __name__ == "__main__":
    genera_report_2026()