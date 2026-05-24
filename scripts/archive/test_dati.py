import requests
import datetime

def estrai_corse_senza_scarpe_2026(access_token):
    # 1. Definiamo i limiti del 2026 convertiti in timestamp UNIX
    inizio_2026 = int(datetime.datetime(2026, 1, 1).timestamp())
    fine_2026 = int(datetime.datetime(2026, 12, 31, 23, 59, 59).timestamp())
    
    url = "https://www.strava.com/api/v3/athlete/activities"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    corse_senza_scarpe = []
    pagina = 1
    
    print("🔍 Ricerca delle corse senza attrezzatura del 2026 in corso...\n")
    
    # 2. Ciclo while per scorrere tutte le pagine di Strava
    while True:
        params = {
            "after": inizio_2026,
            "before": fine_2026,
            "per_page": 100,
            "page": pagina
        }
        
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code != 200:
            print("❌ Errore API:", response.json())
            break
            
        dati = response.json()
        
        # Se la pagina scaricata è vuota, abbiamo finito lo storico
        if not dati:
            break
            
        # 3. Filtraggio in memoria
        for attivita in dati:
            is_corsa = attivita.get('type') == 'Run' or attivita.get('sport_type') == 'Run'
            no_scarpe = attivita.get('gear_id') is None
            
            if is_corsa and no_scarpe:
                corse_senza_scarpe.append(attivita)
        
        pagina += 1
        
    # 4. Stampa del report finale
    print(f"✅ Trovate {len(corse_senza_scarpe)} corse senza scarpe nel 2026.\n")
    
    for corsa in corse_senza_scarpe:
        # Estraiamo solo YYYY-MM-DD dalla data ISO
        data_str = corsa.get('start_date_local', '')[:10] 
        nome = corsa.get('name', 'Senza Titolo')
        id_corsa = corsa.get('id')
        distanza = corsa.get('distance', 0) / 1000
        
        print(f"🏃 {data_str} | {nome} ({distanza:.2f} km) - ID: {id_corsa}")
        
    return corse_senza_scarpe

if __name__ == "__main__":
    # INCOLLA QUI IL TUO ACCESS TOKEN
    MIO_TOKEN = "f2408e5926eeef79a17e53736acbc58997317a56"
    
    lista_corse = estrai_corse_senza_scarpe_2026(MIO_TOKEN)