# app/runalyze_client.py
import requests
from app.config import config

class RunalyzeClient:
    def __init__(self):
        # Utilizziamo il Personal Token standard (senza "pt#")
        self.token = config.get_secret("RUNALYZE_TOKEN").replace("pt#", "") 
        self.base_url = "https://runalyze.com/api/v1"
        self.headers = {"token": self.token}

    def sync_new_activities(self, db):
        """Scarica le ultime 20 attività e le salva/aggiorna su Firestore"""
        print("🔄 [ETL] Avvio sincronizzazione da Runalyze a Firestore...")
        try:
            url = f"{self.base_url}/activity?limit=20"
            res = requests.get(url, headers=self.headers)
            res.raise_for_status()
            
            activities = res.json()
            synced_count = 0
            
            for act in activities:
                # Estraiamo l'equipaggiamento per salvare le scarpe usate
                scarpe_usate = "Non specificate"
                equip_list = act.get('equipment', [])
                if equip_list:
                    scarpe_usate = ", ".join([e.get('name', '') for e in equip_list])

                # Mappatura dei dati per Firestore
                dati_corsa = {
                    "id": str(act.get("id")),
                    "nome": act.get("name", "Corsa"),
                    "start_date": act.get("date_time", ""),
                    "distanza": act.get("distance", 0),
                    "tempo_movimento": act.get("duration", 0) / 60, # Convertito in minuti
                    "scarpe": scarpe_usate,
                    "sport": act.get("sport", {}).get("name", "Running")
                }
                
                # Salvataggio su database
                if db.update_activity(dati_corsa):
                    synced_count += 1
                    
            return synced_count
            
        except Exception as e:
            print(f"❌ [ETL] Errore durante il sync API: {e}")
            return 0

    def fetch_athlete_shoes(self):
        """Recupera l'elenco completo delle scarpe dal profilo"""
        try:
            url = f"{self.base_url}/equipment"
            res = requests.get(url, headers=self.headers)
            res.raise_for_status()
            return res.json()
        except Exception as e:
            print(f"❌ [API] Errore recupero scarpe: {e}")
            return []

    def fetch_gear_details(self, gear_id):
        """Recupera i dettagli di un singolo modello tramite ID"""
        try:
            url = f"{self.base_url}/equipment/{gear_id}"
            res = requests.get(url, headers=self.headers)
            res.raise_for_status()
            return res.json()
        except Exception as e:
            print(f"❌ [API] Errore recupero dettaglio equipaggiamento {gear_id}: {e}")
            return None

# Istanza pronta all'uso
runalyze_client = RunalyzeClient()