import os
import sys
import csv
import requests
from datetime import datetime
from dotenv import load_dotenv

# Diciamo a Python di considerare la cartella principale del progetto
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.database import db

load_dotenv()

RUNALYZE_TOKEN = os.getenv("RUNALYZE_TOKEN")
BASE_URL = "https://runalyze.com/api/v1"
HEADERS = {'token': RUNALYZE_TOKEN}

def associa_scarpe_da_csv():
    print("🔄 Inizio associazione definitiva tramite file CSV locale...")
    
    if not RUNALYZE_TOKEN:
        print("❌ Errore: RUNALYZE_TOKEN non trovato nel file .env!")
        return

    firestore_client = db.db
    
    # ---------------------------------------------------------
    # 1. MAPPA EQUIPAGGIAMENTO
    # ---------------------------------------------------------
    try:
        print("👟 Scarico la scarpiera aggiornata da Runalyze...")
        resp_eq = requests.get(f"{BASE_URL}/equipment", headers=HEADERS)
        resp_eq.raise_for_status()
        mappa_scarpe = {eq.get("name"): eq.get("id") for eq in resp_eq.json()}
    except Exception as e:
        print(f"❌ Errore di connessione API Scarpe: {e}")
        return
        
    # ---------------------------------------------------------
    # 2. LETTURA DEL FILE CSV (Mappa Data -> Lista ID Corse)
    # ---------------------------------------------------------
    # Cerchiamo il file CSV nella stessa cartella di questo script
    csv_path = os.path.join(os.path.dirname(__file__), "runalyze-activities.csv")
    
    if not os.path.exists(csv_path):
        print(f"❌ ERRORE: Non trovo il file CSV!")
        print(f"Assicurati di aver salvato il file esattamente qui: {csv_path}")
        return

    print("📥 Lettura del file CSV in corso...")
    mappa_corse_per_data = {}
    corse_totali_csv = 0
    
    with open(csv_path, mode='r', encoding='utf-8-sig') as file_csv:
        lettore = csv.DictReader(file_csv)
        for riga in lettore:
            corse_totali_csv += 1
            id_corsa = riga['id']
            # Convertiamo il timestamp Unix in stringa YYYY-MM-DD
            timestamp = int(riga['time'])
            data_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
            
            if data_str not in mappa_corse_per_data:
                mappa_corse_per_data[data_str] = []
            mappa_corse_per_data[data_str].append(id_corsa)

    print(f"✅ Trovate {corse_totali_csv} corse nel file CSV.\n")

    # ---------------------------------------------------------
    # 3. ESTRAZIONE CALENDARIO DA FIRESTORE (Data -> Scarpa)
    # ---------------------------------------------------------
    print("📊 Estrazione coppie (Data, Scarpa) da Firestore in corso...")
    corse_ref = firestore_client.collection("activities").stream()
    
    calendario_scarpe = {}
    for doc in corse_ref:
        dati_corsa = doc.to_dict()
        data_corsa = dati_corsa.get("start_date", "")[:10]
        scarpa = dati_corsa.get("scarpe")
        
        if data_corsa and scarpa and scarpa not in ["N/D", "Non specificate"]:
            calendario_scarpe[data_corsa] = scarpa
            
    print(f"✅ Trovate {len(calendario_scarpe)} giornate uniche con scarpe su Firestore.\n")

    # ---------------------------------------------------------
    # 4. ESECUZIONE DELL'ASSOCIAZIONE SU RUNALYZE
    # ---------------------------------------------------------
    print("🚀 Inizio scrittura massiva tramite API Runalyze...")
    corse_aggiornate = 0
    errori = 0
    
    for data_corsa, nome_scarpa in calendario_scarpe.items():
        equipment_id = mappa_scarpe.get(nome_scarpa)
        
        if not equipment_id:
            print(f"⚠️ Salto {data_corsa}: La scarpa '{nome_scarpa}' non esiste su Runalyze.")
            continue

        lista_id_runalyze = mappa_corse_per_data.get(data_corsa)

        if not lista_id_runalyze:
            print(f"⚠️ Salto {data_corsa}: Nessuna corsa nel CSV in questa data.")
            continue

        # Invia il comando PATCH a tutte le corse trovate in quel giorno nel CSV
        for runalyze_id in lista_id_runalyze:
            print(f"🔄 Aggiorno corsa del {data_corsa} (ID: {runalyze_id}) -> Associo: {nome_scarpa}")
            
            url_patch = f"{BASE_URL}/activities/{runalyze_id}"
            payload = {"equipment_ids": [equipment_id]}
            
            try:
                res = requests.patch(url_patch, headers=HEADERS, json=payload)
                if res.status_code in [200, 201, 204]:
                    corse_aggiornate += 1
                else:
                    print(f"❌ Errore API per la corsa {runalyze_id}: Status {res.status_code} - {res.text}")
                    errori += 1
            except Exception as e:
                print(f"❌ Errore di connessione: {e}")
                errori += 1
            
    print("\n" + "="*50)
    print("✅ PROCESSO COMPLETATO")
    print(f"👟 Corse storiche aggiornate con successo: {corse_aggiornate}")
    if errori > 0:
        print(f"❌ Errori di sistema: {errori}")
    print("="*50 + "\n")

if __name__ == "__main__":
    associa_scarpe_da_csv()