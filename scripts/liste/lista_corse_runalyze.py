import os
import requests
from datetime import datetime
from dotenv import load_dotenv

# Carica automaticamente le variabili dal file .env
load_dotenv()

RUNALYZE_TOKEN = os.getenv("RUNALYZE_TOKEN")
BASE_URL = "https://runalyze.com/api/v1"

def elenca_corse_runalyze():
    print("🔄 Connessione a Runalyze in corso...")
    
    if not RUNALYZE_TOKEN:
        print("❌ Errore: RUNALYZE_TOKEN non trovato nel file .env!")
        return

    headers = {'token': RUNALYZE_TOKEN}
    
    print("📥 Scarico la cronologia delle attività...")
    runalyze_activities = []
    limit = 100
    offset = 0
    
    # Ciclo per scaricare tutte le pagine
    while True:
        try:
            res = requests.get(f"{BASE_URL}/activities?limit={limit}&offset={offset}", headers=headers)
            if res.status_code != 200:
                print(f"❌ Errore API: Status {res.status_code} - {res.text}")
                break
            
            data = res.json()
            if not data or len(data) == 0:
                break
                
            runalyze_activities.extend(data)
            
            # Se la pagina scaricata ha meno elementi del limite, significa che è l'ultima
            if len(data) < limit:
                break
                
            offset += limit
        except Exception as e:
            print(f"❌ Errore di connessione: {e}")
            break

    print(f"\n✅ Trovate {len(runalyze_activities)} corse totali su Runalyze.\n")
    
    if len(runalyze_activities) == 0:
        print("📭 Nessuna corsa trovata. Verifica di aver completato l'importazione dello storico dal sito di Runalyze.")
        return

    # Intestazione della tabella formattata
    print("📋 ELENCO COMPLETO DELLE CORSE SU RUNALYZE:")
    print("-" * 85)
    print(f"{'DATA':<12} | {'ID CORSA':<12} | {'DISTANZA':<10} | {'DURATA':<10} | {'TITOLO'}")
    print("-" * 85)
    
    # Iteriamo sui dati per stampare ogni riga
    for act in runalyze_activities:
        # Runalyze fornisce un timestamp in secondi, lo convertiamo in formato leggibile
        data_str = datetime.fromtimestamp(act['time']).strftime('%Y-%m-%d')
        id_corsa = act['id']
        dist_km = act.get('distance', 0)
        durata_sec = act.get('duration', 0)
        durata_min = int(durata_sec / 60)
        
        # Tronchiamo il titolo a 25 caratteri per evitare che scombini l'impaginazione della tabella
        titolo = act.get('title', 'Senza Titolo')
        if titolo and len(titolo) > 25:
            titolo = titolo[:22] + "..."
            
        print(f"{data_str:<12} | {id_corsa:<12} | {dist_km:>6.2f} km | {durata_min:>6} min | {titolo}")
        
    print("-" * 85 + "\n")

if __name__ == "__main__":
    elenca_corse_runalyze()