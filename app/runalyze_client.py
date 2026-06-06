import requests
from datetime import datetime, timedelta
from app.config import config

class RunalyzeClient:
    def __init__(self):
        self.token = config.get_secret("RUNALYZE_TOKEN")
        self.base_url = "https://runalyze.com/api/v1"
        self.headers = {'token': self.token}

    # ==========================================
    # 1. UTILITY INTERNE
    # ==========================================
    def _format_date(self, date_string):
        """Converte 'YYYY-MM-DD HH:MM:SS' in 'YYYY-MM-DDTHH:MM:SSZ' per ordinamento Firestore"""
        if not date_string:
            return ""
        return date_string.replace(' ', 'T') + "Z"

    # ==========================================
    # 2. PIPELINE DI SINCRONIZZAZIONE (FIRESTORE)
    # ==========================================
    def sync_new_activities(self, db_instance):
        """Sync Incrementale: Scarica solo le attività non ancora presenti su Firestore."""
        try:
            print("🔄 [RUNALYZE] Avvio sync incrementale (ricerca nuove attività)...")
            collection_ref = db_instance.db.collection("attivita")
            page = 1
            items_per_page = 50
            attivita_salvate = 0
            fermati = False

            while not fermati:
                url = f"{self.base_url}/activity?page={page}&itemsPerPage={items_per_page}"
                response = requests.get(url, headers=self.headers)
                response.raise_for_status()
                activities = response.json()

                if not activities:
                    break

                for act in activities:
                    id_attivita = str(act.get("id"))
                    
                    # -----------------------------------------------------
                    # EARLY EXIT: Se l'ID esiste già, fermiamo il ciclo!
                    # -----------------------------------------------------
                    if collection_ref.document(id_attivita).get().exists:
                        print(f"🛑 Attività {id_attivita} già presente. Sincronizzazione terminata.")
                        fermati = True
                        break

                    # Elaborazione Dati (Nessun filtro sportivo)
                    distanza_km = float(act.get("distance", 0))
                    tempo_sec = int(act.get("duration", 0))
                    passo_ms = ((distanza_km * 1000) / tempo_sec) if tempo_sec > 0 else 0

                    equip_list = act.get('equipment', [])
                    scarpe = ", ".join([e.get('name', 'Sconosciuta') for e in equip_list]) if equip_list else "Non specificate"

                    run_data = {
                        "id": id_attivita,
                        "nome": act.get("title", "Allenamento"),
                        "sport": act.get("sport", {}).get("name", "Generico"),
                        "workout_type": act.get("type", {}).get("name", "N/D"),
                        "distanza": distanza_km,
                        "tempo_movimento": tempo_sec / 60,
                        "passo_medio": passo_ms, 
                        "bpm_medi": act.get("hr_avg", "N/D"),
                        "dislivello": act.get("elevation_up", 0),
                        "scarpe": scarpe,
                        "note_private": act.get("note", ""),
                        "start_date": self._format_date(act.get("date_time", "")),
                        "laps": []
                    }
                    
                    collection_ref.document(id_attivita).set(run_data, merge=True)
                    attivita_salvate += 1

                if len(activities) < items_per_page:
                    break
                page += 1

            print(f"✅ [RUNALYZE] Sync incrementale completato: {attivita_salvate} nuove attività aggiunte.")
            return attivita_salvate
        except Exception as e:
            print(f"⚠️ [RUNALYZE] Errore nel sync incrementale: {e}")
            return 0

    def sync_historical_data_by_year(self, db_instance, year):
        """Sync Storico: Scarica tutte le attività di un anno specifico sovrascrivendo i dati."""
        try:
            print(f"🔄 [RUNALYZE] Avvio sync storico per l'anno {year}...")
            corse_salvate = 0
            page = 1
            items_per_page = 100
            anno_superato = False

            while not anno_superato:
                url = f"{self.base_url}/activity?page={page}&itemsPerPage={items_per_page}"
                response = requests.get(url, headers=self.headers)
                response.raise_for_status()
                activities = response.json()

                if not activities:
                    break

                for act in activities:
                    date_time = act.get('date_time', '')
                    if not date_time:
                        continue
                        
                    corsa_year = int(date_time[:4])
                    
                    if corsa_year < year:
                        anno_superato = True
                        break
                    
                    if corsa_year == year:
                        distanza_km = float(act.get("distance", 0))
                        tempo_sec = int(act.get("duration", 0))
                        passo_ms = ((distanza_km * 1000) / tempo_sec) if tempo_sec > 0 else 0

                        equip_list = act.get('equipment', [])
                        scarpe = ", ".join([e.get('name', 'Sconosciuta') for e in equip_list]) if equip_list else "Non specificate"

                        run_data = {
                            "id": str(act.get("id")),
                            "nome": act.get("title", "Allenamento"),
                            "sport": act.get("sport", {}).get("name", "Generico"),
                            "workout_type": act.get("type", {}).get("name", "N/D"),
                            "distanza": distanza_km,
                            "tempo_movimento": tempo_sec / 60,
                            "passo_medio": passo_ms, 
                            "bpm_medi": act.get("hr_avg", "N/D"),
                            "dislivello": act.get("elevation_up", 0),
                            "scarpe": scarpe,
                            "note_private": act.get("note", ""),
                            "start_date": self._format_date(date_time),
                            "laps": []
                        }
                        db_instance.db.collection("attivita").document(str(act['id'])).set(run_data, merge=True)
                        corse_salvate += 1

                if len(activities) < items_per_page:
                    break
                page += 1

            print(f"✅ [RUNALYZE] Sync {year} completato: {corse_salvate} attività salvate.")
            return corse_salvate
        except Exception as e:
            print(f"❌ [RUNALYZE] Errore durante il sync dell'anno {year}: {e}")
            return 0

    # ==========================================
    # 3. LETTURE LIVE DA RUNALYZE (Non toccano il DB)
    # ==========================================
    def fetch_athlete_shoes(self):
        url = f"{self.base_url}/equipment"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return [{'id': item.get('id'), 'name': item.get('name', 'Scarpa'), 'distance': item.get('distance', 0)} for item in response.json()]
        except requests.exceptions.RequestException as e:
            print(f"❌ Errore nel recupero della scarpiera: {e}")
            return []

    def fetch_gear_details(self, gear_id):
        url = f"{self.base_url}/equipment" 
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            for item in response.json():
                if str(item.get('id')) == str(gear_id):
                    return {'id': item['id'], 'name': item['name'], 'distance': item.get('distance', 0)}
            return None
        except requests.exceptions.RequestException as e:
            return None

    def fetch_activity_details(self, activity_id):
        url = f"{self.base_url}/activity?id={activity_id}"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            if not data: return None
            
            act = data[0]
            distanza_km = float(act.get("distance", 0))
            tempo_sec = int(act.get("duration", 0))
            passo_ms = ((distanza_km * 1000) / tempo_sec) if tempo_sec > 0 else 0
            equip_list = act.get('equipment', [])
            scarpe = ", ".join([e.get('name', 'Sconosciuta') for e in equip_list]) if equip_list else "Non specificate"

            return {
                "id": str(act.get("id")),
                "nome": act.get("title", "Allenamento"),
                "sport": act.get("sport", {}).get("name", "Sconosciuto"),
                "workout_type": act.get("type", {}).get("name", "N/D"),
                "distanza": distanza_km,
                "tempo_movimento": tempo_sec / 60,
                "passo_medio": passo_ms, 
                "bpm_medi": act.get("hr_avg", "N/D"),
                "dislivello": act.get("elevation_up", 0),
                "scarpe": scarpe,
                "note_private": act.get("note", ""),
                "start_date": self._format_date(act.get("date_time", "")),
                "laps": []
            }
        except requests.exceptions.RequestException as e:
            return None

    def fetch_last_active_week(self):
        try:
            url = f"{self.base_url}/activity?page=1&itemsPerPage=30"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            runs = response.json()
            if not runs: return [], 0, None, None

            dt_str = runs[0].get('date_time', '')
            if not dt_str: return [], 0, None, None
                
            run_date = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
            start_of_week = run_date - timedelta(days=run_date.weekday())
            start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_week = start_of_week + timedelta(days=6, hours=23, minutes=59, seconds=59)

            settimana_attiva = []
            km_totali = 0

            for run in runs:
                r_date_str = run.get('date_time', '')
                if not r_date_str: continue
                r_date = datetime.strptime(r_date_str, "%Y-%m-%d %H:%M:%S")
                
                if start_of_week <= r_date <= end_of_week:
                    distanza = float(run.get("distance", 0))
                    settimana_attiva.append({
                        "id": run.get("id"),
                        "nome": run.get("title", "Allenamento"),
                        "distanza": distanza,
                        "data": r_date.strftime("%d/%m/%Y"),
                        "start_date": self._format_date(r_date_str),
                        "workout_type": run.get("type", {}).get("name", "N/D")
                    })
                    km_totali += distanza

            settimana_attiva.reverse()
            return settimana_attiva, km_totali, start_of_week, end_of_week
        except requests.exceptions.RequestException:
            return [], 0, None, None

runalyze_client = RunalyzeClient()