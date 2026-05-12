import requests
import datetime
import time

# 1. INCOLLA QUI IL TUO TOKEN (DEVE AVERE I PERMESSI 'activity:write')
ACCESS_TOKEN = "31fc3a115b0dbb64f7ff5c009928242d1daecdf3"

# 2. IMPOSTA I TUOI PARAMETRI
GEAR_ID_DA_ASSEGNARE = "g31016718"  # Il Gear ID che hai appena trovato
DATA_INIZIO = "2026-01-01"          # Modifica con la data da cui vuoi partire (AAAA-MM-GG)

def bonifica_storico():
    # Convertiamo la data in formato UNIX timestamp (richiesto da Strava)
    data_obj = datetime.datetime.strptime(DATA_INIZIO, "%Y-%m-%d")
    timestamp_inizio = int(data_obj.timestamp())
    
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    url_activities = "https://www.strava.com/api/v3/athlete/activities"
    
    # Chiediamo a Strava le attività successive alla data indicata (fino a 100 per pagina)
    params = {
        "after": timestamp_inizio,
        "per_page": 100 
    }
    
    print(f"\n🔍 Ricerca allenamenti senza scarpe dal {DATA_INIZIO} in poi...\n")
    response = requests.get(url_activities, headers=headers, params=params)
    
    if response.status_code != 200:
        print("❌ Errore nella lettura delle attività:", response.json())
        return

    corse = response.json()
    corse_da_aggiornare = [c for c in corse if c.get('gear_id') is None]
    
    print(f"Trovate {len(corse_da_aggiornare)} corse da bonificare su un totale di {len(corse)} estratte.\n")
    
    if not corse_da_aggiornare:
        print("✅ Nessun aggiornamento necessario. Tutto pulito!")
        return

    conferma = input(f"Vuoi procedere ad assegnare la scarpa {GEAR_ID_DA_ASSEGNARE} a queste {len(corse_da_aggiornare)} corse? (s/n): ")
    
    if conferma.lower() != 's':
        print("Operazione annullata.")
        return

    # Eseguiamo l'aggiornamento
    for corsa in corse_da_aggiornare:
        id_corsa = corsa['id']
        nome = corsa.get('name', 'Senza Titolo')
        
        url_update = f"https://www.strava.com/api/v3/activities/{id_corsa}"
        payload = {"gear_id": GEAR_ID_DA_ASSEGNARE}
        
        update_resp = requests.put(url_update, headers=headers, data=payload)
        
        if update_resp.status_code == 200:
            print(f"✅ Aggiornata: {nome} (ID: {id_corsa})")
        else:
            print(f"❌ Errore su: {nome} - {update_resp.json()}")
            
        # Pausa di 1 secondo per rispettare i limiti delle API di Strava (Rate Limiting)
        time.sleep(1)

    print("\n🎉 Bonifica completata!")

if __name__ == "__main__":
    bonifica_storico()