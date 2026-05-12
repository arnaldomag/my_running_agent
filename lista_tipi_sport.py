import requests

# Incolla il tuo Access Token (basta il permesso activity:read_all)
ACCESS_TOKEN = "7f08a68bc00e19f69a8bc7269cf2e291b3993a83"

def elenca_tipi_attivita():
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    tipi_rilevati = set() # Usiamo un set per avere solo valori univoci
    
    print("🔍 Analisi del tuo storico Strava per mappare i tipi di sport...")
    
    pagina = 1
    while True:
        # Estraiamo blocchi da 200 per fare in fretta
        params = {"per_page": 200, "page": pagina}
        resp = requests.get("https://www.strava.com/api/v3/athlete/activities", headers=headers, params=params)
        
        if resp.status_code != 200:
            print("❌ Errore API:", resp.json())
            break
            
        dati = resp.json()
        if not dati:
            break
            
        for att in dati:
            # Strava usa 'sport_type' per le app più recenti 
            # e 'type' per la compatibilità con il passato
            tipo = att.get('sport_type') or att.get('type')
            if tipo:
                tipi_rilevati.add(tipo)
        
        print(f"   Controllate {pagina * 200} attività...")
        pagina += 1
        
        # Limite di sicurezza: se hai più di 1000 attività fermati
        if pagina > 5: break

    print("\n✅ Tipi di attività trovati nel tuo account:")
    print("-" * 40)
    for t in sorted(tipi_rilevati):
        print(f"🔹 {t}")
    print("-" * 40)
    print("\nPuoi usare questi nomi esatti nei tuoi script di filtraggio.")

if __name__ == "__main__":
    elenca_tipi_attivita()