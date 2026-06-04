import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

RUNALYZE_TOKEN = os.getenv("RUNALYZE_TOKEN")
BASE_URL = "https://runalyze.com/api/v1"
HEADERS = {'token': RUNALYZE_TOKEN}

def esplora_singola_attivita(id_attivita):
    print(f"🔄 Interrogo l'API di Runalyze per l'attività ID: {id_attivita}...")
    
    if not RUNALYZE_TOKEN:
        print("❌ Errore: RUNALYZE_TOKEN non trovato nel file .env!")
        return

    # Passiamo l'ID come query parameter, esattamente come indicato dalla documentazione ufficiale
    url = f"{BASE_URL}/activity?id={id_attivita}"
    
    try:
        res = requests.get(url, headers=HEADERS)
        
        if res.status_code != 200:
            print(f"❌ Errore API: Status {res.status_code}")
            print(res.text)
            return
            
        data = res.json()
        
        # L'API restituisce sempre una lista (array). Controlliamo se è vuota.
        if not data or len(data) == 0:
            print(f"📭 Nessuna attività trovata con ID {id_attivita}.")
            return
            
        # Prendiamo il primo (e unico) elemento della lista
        attivita = data[0]
        
        print("\n" + "="*60)
        print(f"📋 DETTAGLIO COMPLETO ATTIVITÀ {id_attivita}")
        print("="*60)
        
        # Iteriamo su ogni chiave (campo) e valore del dizionario
        for campo, valore in attivita.items():
            # Se il valore è a sua volta un dizionario o una lista (es. tags, equipment, sport)
            # lo formattiamo in JSON compatto per renderlo leggibile, altrimenti stampiamo il valore normale
            if isinstance(valore, (dict, list)):
                valore_formattato = json.dumps(valore, ensure_ascii=False)
            else:
                valore_formattato = str(valore)
                
            print(f"{campo:<35} : {valore_formattato}")
            
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"❌ Si è verificato un errore di connessione: {e}")

if __name__ == "__main__":
    # Inserisci qui l'ID dell'attività che vuoi ispezionare
    ID_DA_CERCARE = "180770199"
    esplora_singola_attivita(ID_DA_CERCARE)