import requests
import datetime
import os
from dotenv import load_dotenv

# 1. Carica le chiavi in modo sicuro dal file .env
load_dotenv()

# 1. CONFIGURAZIONE
ACCESS_TOKEN = os.getenv('STRAVA_ACCESS_TOKEN')

# Mappatura ufficiale Strava per workout_type nelle corse
MAPPA_WORKOUT = {
    0: "Corsa generica / Allenamento",
    1: "Gara (Race)",
    2: "Lungo (Long Run)",
    3: "Allenamento strutturato / Ripetute (Workout)"
}

def elenca_tipi_di_corsa():
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    
    # Filtriamo per il 2026
    ts_inizio = int(datetime.datetime(2026, 1, 1).timestamp())
    
    print("🔍 Analisi delle tipologie di corsa nel 2026...")
    
    url = "https://www.strava.com/api/v3/athlete/activities"
    params = {"after": ts_inizio, "per_page": 100}
    
    resp = requests.get(url, headers=headers, params=params)
    
    if resp.status_code != 200:
        print("❌ Errore API:", resp.json())
        return

    attività = resp.json()
    corse = [a for a in attività if (a.get('sport_type') == 'Run' or a.get('type') == 'Run')]

    if not corse:
        print("Nessuna corsa trovata nel 2026.")
        return

    print("\n📋 ELENCO CORSE E TIPOLOGIA:")
    print("-" * 80)
    print(f"{'DATA':<12} | {'TITOLO':<30} | {'KM':<8} | {'TIPOLOGIA'}")
    print("-" * 80)

    for c in corse:
        data = c.get('start_date_local', '')[:10]
        titolo = c.get('name', 'Senza titolo')[:30]
        km = f"{c.get('distance', 0) / 1000:.2f}"
        
        # Estraiamo il workout_type
        w_type = c.get('workout_type')
        # Se è None, lo forziamo a 0 (generico)
        label_tipo = MAPPA_WORKOUT.get(w_type if w_type is not None else 0, "Altro")

        print(f"{data:<12} | {titolo:<30} | {km:<8} | {label_tipo}")

    print("-" * 80)
    
    # Facciamo anche un piccolo conteggio statistico
    conteggio = {}
    for c in corse:
        wt = c.get('workout_type' if c.get('workout_type') is not None else 0)
        label = MAPPA_WORKOUT.get(wt, "Altro")
        conteggio[label] = conteggio.get(label, 0) + 1

    print("\n📊 RIEPILOGO STATISTICO:")
    for tipo, qta in conteggio.items():
        print(f"🔹 {tipo}: {qta} attività")

if __name__ == "__main__":
    elenca_tipi_di_corsa()