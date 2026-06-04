import os
import requests
from dotenv import load_dotenv

load_dotenv()

RUNALYZE_TOKEN = os.getenv("RUNALYZE_TOKEN")
BASE_URL = "https://runalyze.com/api/v1"
HEADERS = {'token': RUNALYZE_TOKEN}

def calcola_km_scarpe():
    print("🔄 Scarico lo storico da Runalyze per aggregare i dati (potrebbe volerci qualche secondo)...")
    
    if not RUNALYZE_TOKEN:
        print("❌ Errore: RUNALYZE_TOKEN non trovato nel file .env!")
        return

    statistiche_scarpe = {}
    corse_totali = 0
    page = 1
    items_per_page = 100
    
    while True:
        url = f"{BASE_URL}/activity?page={page}&itemsPerPage={items_per_page}"
        res = requests.get(url, headers=HEADERS)
        
        if res.status_code != 200:
            print(f"❌ Errore API sulla pagina {page}: Status {res.status_code}")
            break
            
        data = res.json()
        
        if not data:
            break
            
        for act in data:
            corse_totali += 1
            distanza = act.get('distance', 0)
            equip_list = act.get('equipment', [])
            
            if equip_list:
                for eq in equip_list:
                    nome_scarpa = eq.get('name', 'Sconosciuta')
                    
                    # Inizializza il contatore per la scarpa se è la prima volta che la incontra
                    if nome_scarpa not in statistiche_scarpe:
                        statistiche_scarpe[nome_scarpa] = {"km": 0.0, "uscite": 0}
                    
                    # Aggiunge i km e somma 1 al numero di uscite
                    statistiche_scarpe[nome_scarpa]["km"] += distanza
                    statistiche_scarpe[nome_scarpa]["uscite"] += 1
            else:
                # Gestione delle corse a cui non è stata assegnata nessuna scarpa
                nome = "Nessuna scarpa assegnata"
                if nome not in statistiche_scarpe:
                    statistiche_scarpe[nome] = {"km": 0.0, "uscite": 0}
                statistiche_scarpe[nome]["km"] += distanza
                statistiche_scarpe[nome]["uscite"] += 1
                
        if len(data) < items_per_page:
            break
            
        page += 1

    print(f"✅ Lette {corse_totali} corse totali.\n")
    
    # Ordiniamo il dizionario in base ai chilometri percorsi (in ordine decrescente)
    scarpe_ordinate = sorted(statistiche_scarpe.items(), key=lambda x: x[1]['km'], reverse=True)

    # Intestazione della tabella
    print("👟 CHILOMETRAGGIO TOTALE PER SCARPA:")
    print("-" * 65)
    print(f"{'MODELLO SCARPA':<35} | {'CHILOMETRI':<12} | {'USCITE'}")
    print("-" * 65)
    
    for nome, dati in scarpe_ordinate:
        km_totali = dati['km']
        uscite = dati['uscite']
        
        # Tronchiamo il nome a 32 caratteri per non sfasare la tabella
        nome_display = (nome[:32] + '...') if len(nome) > 35 else nome
        
        print(f"{nome_display:<35} | {km_totali:>9.2f} km | {uscite:>4}")
        
    print("-" * 65 + "\n")

if __name__ == "__main__":
    calcola_km_scarpe()