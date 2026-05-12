import requests
import pandas as pd
import os
from dotenv import load_dotenv

# 1. Carica le chiavi in modo sicuro dal file .env
load_dotenv()

# 1. CONFIGURAZIONE
ACCESS_TOKEN = os.getenv('STRAVA_ACCESS_TOKEN')

def analizza_allenamento(id_attivita):
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    
    # 1. Recupero dati dettagliati
    url_base = f"https://www.strava.com/api/v3/activities/{id_attivita}"
    res = requests.get(url_base, headers=headers)
    
    if res.status_code != 200:
        print(f"❌ Impossibile recuperare l'attività {id_attivita}")
        return
    
    dati = res.json()
    
    # 2. Recupero degli "Streams" (i dati secondo per secondo)
    # Chiediamo tempo, distanza, battiti e cadenza
    url_streams = f"{url_base}/streams?keys=time,distance,heartrate,cadence&key_by_type=true"
    res_streams = requests.get(url_streams, headers=headers)
    
    print(f"\n🧠 ANALISI AGENTE - Attività: {dati.get('name')}")
    print(f"📅 Data: {dati.get('start_date_local')[:10]}")
    print("-" * 50)

    if res_streams.status_code == 200:
        streams = res_streams.json()
        
        # Trasformiamo in DataFrame per analisi rapida
        df_data = {}
        for key in streams:
            df_data[key] = streams[key]['data']
        
        df = pd.DataFrame(df_data)
        
        # Esempio di analisi intelligente dell'agente:
        print(f"📈 Battito Medio: {df['heartrate'].mean():.0f} bpm")
        print(f"📈 Battito Max: {df['heartrate'].max():.0f} bpm")
        print(f"👟 Cadenza Media: {df['cadence'].mean():.0f} spm")
        
        # Calcolo del passo (Pace) medio al km (secondi al metro -> min/km)
        passo_medio_secondi = dati.get('moving_time') / (dati.get('distance') / 1000)
        minuti = int(passo_medio_secondi // 60)
        secondi = int(passo_medio_secondi % 60)
        print(f"⏱️ Passo Medio Reale: {minuti}:{secondi:02d} min/km")
        
    else:
        print("⚠️ Nota: Non è stato possibile recuperare i dati telemetrici dettagliati.")

if __name__ == "__main__":
    # Puoi copiare un ID da uno degli script precedenti o dall'URL di Strava
    id_test = input("Inserisci l'ID dell'attività da analizzare: ")
    analizza_allenamento(id_test.strip())