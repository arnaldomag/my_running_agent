import os
import sys
import requests
from dotenv import load_dotenv

# Carica automaticamente il file .env dalla cartella principale
load_dotenv()

def elenca_scarpiera():
    token = os.getenv("RUNALYZE_TOKEN")
    
    if not token:
        print("❌ Errore: RUNALYZE_TOKEN non trovato. Assicurati di averlo inserito nel file .env alla radice del progetto.")
        return

    base_url = "https://runalyze.com/api/v1"
    headers = {'token': token}

    print("🔍 Connessione a Runalyze in corso...")
    
    try:
        # Chiamata all'endpoint equipment
        response = requests.get(f"{base_url}/equipment", headers=headers)
        response.raise_for_status()
        equipment_list = response.json()
        
        if not equipment_list:
            print("📭 Nessun equipaggiamento trovato sul tuo account Runalyze.")
            return

        print("\n👟 LA TUA SCARPIERA SU RUNALYZE:")
        print("=" * 60)
        print(f"{'ID':<10} | {'NOME MODELLO':<30} | {'DISTANZA (km)'}")
        print("-" * 60)
        
        # Iteriamo e stampiamo i dettagli
        for eq in equipment_list:
            eq_id = eq.get("id")
            nome = eq.get("name", "Senza Nome")
            # Runalyze API restituisce nativamente la distanza in km
            distanza = eq.get("distance", 0) 
            
            print(f"{eq_id:<10} | {nome:<30} | {distanza:.2f} km")
            
        print("=" * 60)
        print(f"Totale modelli registrati: {len(equipment_list)}\n")

    except requests.exceptions.RequestException as e:
        print(f"❌ Errore di rete durante il recupero dei dati: {e}")
    except Exception as e:
        print(f"❌ Errore imprevisto: {e}")

if __name__ == "__main__":
    elenca_scarpiera()