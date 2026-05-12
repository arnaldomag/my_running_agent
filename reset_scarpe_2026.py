import requests
import datetime
import time

# 1. INCOLLA IL TUO TOKEN (deve avere permesso activity:write)
ACCESS_TOKEN = "7f08a68bc00e19f69a8bc7269cf2e291b3993a83"

def reset_scarpe_2026():
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    
    # Limiti temporali 2026
    inizio_2026 = int(datetime.datetime(2026, 1, 1).timestamp())
    fine_2026 = int(datetime.datetime(2026, 12, 31, 23, 59, 59).timestamp())

    print("🔍 Recupero attività del 2026 per il reset...")
    
    corse_da_resettare = []
    pagina = 1
    
    while True:
        params = {"after": inizio_2026, "before": fine_2026, "per_page": 100, "page": pagina}
        resp = requests.get("https://www.strava.com/api/v3/athlete/activities", headers=headers, params=params)
        
        if resp.status_code != 200: break
        dati = resp.json()
        if not dati: break
            
        for att in dati:
            # Filtriamo solo le attività che HANNO una scarpa (gear_id non è None)
            # e che sono di tipo corsa
            tipo = att.get('sport_type') or att.get('type')
            if tipo and 'Run' in tipo and att.get('gear_id') is not None:
                corse_da_resettare.append({
                    "id": att['id'],
                    "nome": att['name'],
                    "data": att['start_date_local'][:10]
                })
        pagina += 1

    if not corse_da_resettare:
        print("✅ Non sono state trovate corse con scarpe associate nel 2026.")
        return

    print(f"\n⚠️ ATTENZIONE: Trovate {len(corse_da_resettare)} corse con scarpe associate.")
    conferma = input("Vuoi procedere alla RIMOZIONE delle scarpe da queste attività? (s/n): ")
    
    if conferma.lower() != 's':
        print("Operazione annullata.")
        return

    print("\n🚀 Avvio reset massivo...")
    
    for corsa in corse_da_resettare:
        url_update = f"https://www.strava.com/api/v3/activities/{corsa['id']}"
        # Per Strava, "none" rimuove l'attrezzatura
        payload = {"gear_id": "none"} 
        
        res = requests.put(url_update, headers=headers, data=payload)
        
        if res.status_code == 200:
            print(f"✅ Reset: {corsa['data']} | {corsa['nome']}")
        else:
            print(f"❌ Errore su {corsa['nome']}: {res.json()}")
        
        # Pausa per evitare il blocco delle API (Rate Limit)
        time.sleep(0.8)

    print("\n✨ Tutte le corse del 2026 sono state riportate a 'Senza attrezzatura'.")

if __name__ == "__main__":
    reset_scarpe_2026()