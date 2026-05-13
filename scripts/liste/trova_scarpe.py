import requests
import os
from dotenv import load_dotenv

# 1. Carica le chiavi in modo sicuro dal file .env
load_dotenv()

ACCESS_TOKEN = os.getenv('STRAVA_ACCESS_TOKEN')

def trova_gear_id():
    url = "https://www.strava.com/api/v3/athlete"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        dati = response.json()
        scarpe = dati.get('shoes', [])
        
        if not scarpe:
            print("\n⚠️ Nessuna scarpa trovata sul profilo Strava. Aggiungile prima dall'app!")
            return
            
        print("\n👟 Le tue scarpe su Strava:")
        for scarpa in scarpe:
            print(f"- {scarpa['name']} -> Gear ID: {scarpa['id']}")
    else:
        print("❌ Errore:", response.json())

if __name__ == "__main__":
    trova_gear_id()