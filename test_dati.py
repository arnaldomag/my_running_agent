import requests

# RICORDATI DI REINCOLLARE IL TUO ACCESS TOKEN QUI SOTTO
ACCESS_TOKEN = "f2408e5926eeef79a17e53736acbc58997317a56"

def esplora_dettaglio_corsa(id_corsa):
    print(f"Connessione a Strava per l'ID {id_corsa} in corso...\n")
    
    # L'endpoint specifico per aprire i dettagli di una singola corsa
    url = f"https://www.strava.com/api/v3/activities/{id_corsa}"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        dettagli = response.json()
        print("✅ Dettagli estratti con successo! Ispezioniamo i campi:\n")

        print(f"Titolo: {dettagli.get('name', 'N/D')}")
        
        # IL CAMPO CRUCIALE: La descrizione
        descrizione = dettagli.get('description')
        print(f"Descrizione/Note: {descrizione}")
        
        # Un controllo extra: Strava ha un suo campo nativo per le scarpe
        gear_id = dettagli.get('gear_id')
        print(f"Gear ID (Scarpe native Strava): {gear_id}")

    else:
        print(f"❌ Errore durante il recupero dei dati: {response.status_code}")
        print(response.json())

if __name__ == "__main__":
    # Usiamo l'ID del tuo "Fartlek della domenica"
    ID_TEST = 18447359866
    esplora_dettaglio_corsa(ID_TEST)