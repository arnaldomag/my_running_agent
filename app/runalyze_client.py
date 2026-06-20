# app/runalyze_client.py
from datetime import datetime
import requests
from app.config import config

class RunalyzeClient:
    def __init__(self):
        # Utilizziamo il Personal Token standard (senza "pt#")
        self.token = config.get_secret("RUNALYZE_TOKEN").replace("pt#", "") 
        self.base_url = "https://runalyze.com/api/v1"
        self.headers = {"token": self.token}

     def sync_new_activities(self, db):
        """Scarica le ultime attività e salva SOLO quelle nuove"""
        print("🔄 [ETL] Avvio sincronizzazione incrementale da Runalyze...")
        try:
            # Puoi regolare il limite se vuoi, 20 o 100 non cambia nulla ora
            # perché il ciclo si fermerà automaticamente appena trova dati già noti.
            url = f"{self.base_url}/activity?limit=20"
            res = requests.get(url, headers=self.headers)
            res.raise_for_status()
            
            activities = res.json()
            synced_count = 0
            
            for act in activities:
                activity_id = str(act.get("id"))
                
                # --- NOVITÀ: CONTROLLO INCREMENTALE ---
                doc_ref = db.db.collection(db.collection_name).document(activity_id)
                if doc_ref.get().exists:
                    # Trovata un'attività già presente! 
                    # Siccome le API restituiscono le corse in ordine decrescente,
                    # se questa esiste già, significa che tutte le successive sono storiche.
                    # Blocchiamo il ciclo per risparmiare tempo e operazioni.
                    print(f"ℹ️ Attività {activity_id} già presente, interrompo il sync.")
                    break 
                # --------------------------------------

                # Estraiamo l'equipaggiamento per salvare le scarpe usate
                scarpe_usate = "Non specificate"
                equip_list = act.get('equipment', [])
                if equip_list:
                    scarpe_usate = ", ".join([e.get('name', '') for e in equip_list])

                # Mappatura dei dati per Firestore
                dati_corsa = {
                    "id": activity_id,
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

    def upload_body_metrics(self, dati_corporei):
        """Carica le metriche corporee su Runalyze tramite chiamata POST"""
        print("🏋️ [API] Invio composizione corporea a Runalyze...")
        try:
            url = f"{self.base_url}/metrics/bodyComposition"
            
            # Timestamp in formato standard ISO 8601 compatibile con l'API
            now_iso = datetime.now().isoformat()
            
            # Helper interno per garantire che i valori passati siano float validi per il JSON
            def _safe_float(key):
                val = dati_corporei.get(key, 0)
                if not val: 
                    return 0.0
                try:
                    return float(str(val).replace(',', '.'))
                except ValueError:
                    return 0.0

            payload = {
                "date_time": now_iso,
                "weight": _safe_float('peso_kg'),
                "fat_percentage": _safe_float('massa_grassa_percentuale'),
                "water_percentage": _safe_float('massa_idrica_percentuale'),
                "muscle_percentage": _safe_float('massa_muscolare_percentuale'),
                "bone_percentage": _safe_float('massa_ossea_percentuale')
            }
            
            res = requests.post(url, headers=self.headers, json=payload)
            res.raise_for_status()
            
            print("✅ [API] Dati corporei caricati con successo su Runalyze.")
            return True
            
        except requests.exceptions.HTTPError as errh:
            print(f"❌ [API] Errore HTTP Runalyze: {errh}")
            if hasattr(errh, 'response') and errh.response is not None:
                print(f"Dettaglio: {errh.response.text}")
            return False
        except Exception as e:
            print(f"❌ [API] Errore di sistema nel caricamento metriche: {e}")
            return False

# Istanza pronta all'uso
runalyze_client = RunalyzeClient()