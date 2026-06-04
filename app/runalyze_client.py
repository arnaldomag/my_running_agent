import os
import requests
from datetime import datetime
from dotenv import load_dotenv

# Importa l'istanza del database dalla tua app
# Se il tuo path è diverso, aggiusta l'import di conseguenza
from app.database import db

load_dotenv()

class RunalyzeClient:
    def __init__(self):
        self.token = os.getenv("RUNALYZE_TOKEN")
        self.base_url = "https://runalyze.com/api/v1"
        self.headers = {'token': self.token}
        self.db = db.db

    def sync_nuove_corse(self):
        """
        Scarica le attività da Runalyze e le salva nella nuova collection 'attivita'.
        Si ferma non appena incontra un'attività già presente nel database.
        """
        if not self.token:
            print("❌ Errore: RUNALYZE_TOKEN non configurato.")
            return 0

        print("🔄 Avvio sincronizzazione incrementale da Runalyze (tabella 'attivita')...")
        collection_ref = self.db.collection("attivita")
        
        page = 1
        items_per_page = 50
        corse_sincronizzate = 0
        fermati = False

        while not fermati:
            url = f"{self.base_url}/activity?page={page}&itemsPerPage={items_per_page}"
            res = requests.get(url, headers=self.headers)
            
            if res.status_code != 200:
                print(f"❌ Errore API Runalyze: {res.status_code}")
                break
                
            data = res.json()
            if not data:
                break
                
            for act in data:
                id_corsa = str(act.get('id'))
                
                # ---------------------------------------------------------
                # 1. CONTROLLO ESISTENZA (Early Exit)
                # ---------------------------------------------------------
                # Se la corsa esiste già nella tabella 'attivita', ci fermiamo.
                # Significa che abbiamo raggiunto lo storico già sincronizzato.
                doc_ref = collection_ref.document(id_corsa)
                if doc_ref.get().exists:
                    print(f"🛑 Trovata corsa esistente (ID: {id_corsa}). Sincronizzazione terminata.")
                    fermati = True
                    break

                # ---------------------------------------------------------
                # 2. CALCOLI E TRASFORMAZIONI
                # ---------------------------------------------------------
                distanza_km = float(act.get("distance", 0))
                tempo_sec = int(act.get("duration", 0))
                
                # Calcolo del passo (espresso in metri/secondo come suggerisce la tua variabile passo_ms)
                passo_ms = (distanza_km * 1000) / tempo_sec if tempo_sec > 0 else 0

                # Estrazione delle scarpe dall'array equipment
                equip_list = act.get('equipment', [])
                if equip_list:
                    scarpe = ", ".join([e.get('name', 'Sconosciuta') for e in equip_list])
                else:
                    scarpe = "Non specificate"

                # ---------------------------------------------------------
                # 3. CREAZIONE DEL DOCUMENTO
                # ---------------------------------------------------------
                nuova_attivita = {
                    "id": id_corsa,
                    "start_date": act.get("date_time", ""), # Aggiunto: vitale per ordinare cronologicamente in futuro!
                    "nome": act.get("title", "Corsa"),
                    "sport": act.get("sport", {}).get("name", "Sconosciuto"),
                    "workout_type": act.get("type", {}).get("name", "N/D"),
                    "distanza": distanza_km,
                    "tempo_movimento": tempo_sec / 60,
                    "passo_medio": passo_ms,
                    "bpm_medi": act.get("hr_avg", "N/D"),
                    
                    # N.B. Runalyze chiama l'altitudine 'elevation_up' e le note 'note'
                    "dislivello": act.get("elevation_up", 0), 
                    "scarpe": scarpe,
                    "note_private": act.get("note", ""), 
                    
                    "laps": []
                }

                # ---------------------------------------------------------
                # 4. SALVATAGGIO SU FIRESTORE
                # ---------------------------------------------------------
                try:
                    doc_ref.set(nuova_attivita)
                    corse_sincronizzate += 1
                    print(f"✅ Nuova attività salvata: {nuova_attivita['nome']} ({nuova_attivita['start_date'][:10]})")
                except Exception as e:
                    print(f"❌ Errore nel salvataggio di {id_corsa}: {e}")

            if len(data) < items_per_page:
                break
                
            page += 1

        print(f"🎉 Processo completato! Aggiunte {corse_sincronizzate} nuove corse alla collection 'attivita'.")
        return corse_sincronizzate

# Permette di testare lo script lanciandolo direttamente da riga di comando
if __name__ == "__main__":
    client = RunalyzeClient()
    client.sync_nuove_corse()