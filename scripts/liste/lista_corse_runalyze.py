import os
import requests
from dotenv import load_dotenv

load_dotenv()

RUNALYZE_TOKEN = os.getenv("RUNALYZE_TOKEN")
BASE_URL = "https://runalyze.com/api/v1"
HEADERS = {'token': RUNALYZE_TOKEN}

def elenca_giugno_runalyze():
    print("🔄 Interrogo l'API di Runalyze (GET /api/v1/activity)...")
    
    if not RUNALYZE_TOKEN:
        print("❌ Errore: RUNALYZE_TOKEN non trovato nel file .env!")
        return

    corse_giugno = []
    page = 1
    items_per_page = 100
    
    while True:
        url = f"{BASE_URL}/activity?page={page}&itemsPerPage={items_per_page}"
        res = requests.get(url, headers=HEADERS)
        
        if res.status_code != 200:
            print(f"❌ Errore API sulla pagina {page}: Status {res.status_code}")
            print(res.text[:200])
            break
            
        data = res.json()
        
        # Se la pagina è vuota, abbiamo finito di scorrere lo storico
        if not data:
            break
            
        # Filtriamo le corse di giugno 2026
        for act in data:
            # Il formato stringa di date_time fornito da Runalyze inizia con YYYY-MM
            date_time = act.get('date_time', '')
            
            if date_time.startswith("2026-06"):
                corse_giugno.append(act)
                
        # Se la pagina scaricata ha meno elementi del massimo, è l'ultima pagina
        if len(data) < items_per_page:
            break
            
        page += 1

    if not corse_giugno:
        print("📭 Nessuna corsa trovata per Giugno 2026 su Runalyze.")
        return

    # Ordiniamo per data (dal 1 al 30 giugno)
    corse_giugno = sorted(corse_giugno, key=lambda x: x.get('date_time', ''))

    print(f"\n✅ Trovate {len(corse_giugno)} corse a Giugno 2026.\n")
    
    # Intestazione della tabella
    print("-" * 90)
    print(f"{'DATA E ORA':<20} | {'ID CORSA':<12} | {'DISTANZA':<10} | {'DURATA':<8} | {'SCARPE'}")
    print("-" * 90)
    
    for corsa in corse_giugno:
        data_pulita = corsa.get('date_time', 'N/D')[:16] # Tagliamo i secondi/timezone per pulizia
        id_corsa = corsa.get('id', 'N/D')
        
        distanza_km = corsa.get('distance', 0)
        
        # L'API restituisce 'duration' in secondi
        durata_secondi = corsa.get('duration', 0)
        minuti = int(durata_secondi / 60)
        
        # Estraiamo l'array dell'equipaggiamento per leggere il nome della scarpa
        equip_list = corsa.get('equipment', [])
        if equip_list:
            # Se ci sono più equipaggiamenti (es. fascia cardio e scarpe), li uniamo
            scarpe = ", ".join([e.get('name', 'Sconosciuta') for e in equip_list])
        else:
            scarpe = "Nessuna"
            
        print(f"{data_pulita:<20} | {str(id_corsa):<12} | {distanza_km:>6.2f} km | {minuti:>4} min | {scarpe}")
        
    print("-" * 90 + "\n")

if __name__ == "__main__":
    elenca_giugno_runalyze()