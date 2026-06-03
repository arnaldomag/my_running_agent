import requests
from datetime import datetime, timedelta
from app.config import config

class RunalyzeClient:
    def __init__(self):
        # Runalyze richiede un solo token statico, molto più semplice!
        self.token = config.get_secret("RUNALYZE_TOKEN")
        self.base_url = "https://runalyze.com/api/v1"
        self.headers = {'token': self.token}  # L'header specifico richiesto da Runalyze

    # ==========================================
    # 1. UTILITY INTERNE
    # ==========================================
    def _get_shoe_mapping(self):
        """Genera un dizionario {gear_id: nome_scarpa} scaricando la scarpiera"""
        scarpe_atleta = self.fetch_athlete_shoes()
        mappa_scarpe = {}
        if scarpe_atleta:
            for scarpa in scarpe_atleta:
                mappa_scarpe[scarpa['id']] = scarpa.get('name', 'Scarpa')
        return mappa_scarpe

    # ==========================================
    # 2. PIPELINE DI SINCRONIZZAZIONE (FIRESTORE)
    # ==========================================
    def sync_latest_activities(self, db_instance, limit=30):
        """Sync leggero e veloce delle ultime N attività per aggiornare modifiche recenti"""
        try:
            mappa_scarpe = self._get_shoe_mapping()

            # Runalyze API endpoint per le attività
            url = f"{self.base_url}/activities?limit={limit}"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            activities = response.json()
            
            for act in activities:
                # In Runalyze, lo sport è tipicamente un ID. Filtriamo le corse.
                # Assumiamo che ID 1 o 'running' sia la corsa (modifica se necessario)
                sport_id = act.get('sport_id', 1) 
                
                if sport_id == 1 or act.get('sport_name', '').lower() == 'running':
                    # Recupero array di equipaggiamenti
                    equipments = act.get('equipment_ids', [])
                    gear_id = equipments[0] if equipments else None
                    nome_scarpa = mappa_scarpe.get(gear_id, 'N/D') if gear_id else 'N/D'
                    
                    # Runalyze restituisce il tempo in Unix Timestamp, lo convertiamo
                    timestamp = act.get('time', 0)
                    start_date = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
                    
                    run_data = {
                        'id': act['id'],
                        'name': act.get('title', 'Corsa'),
                        'distance': act.get('distance', 0) * 1000, # Convertiamo km in metri per Firestore
                        'moving_time': act.get('duration', 0), # in secondi
                        'start_date': start_date,
                        'workout_type': act.get('is_race', False), 
                        'scarpe': nome_scarpa
                    }
                    db_instance.db.collection("activities").document(str(act['id'])).set(run_data, merge=True)
            return True
        except Exception as e:
            print(f"⚠️ [RUNALYZE] Mini-sync fallito: {e}")
            return False

    def sync_historical_data_by_year(self, db_instance, year):
        """Scarica tutte le corse di un anno specifico e le salva su Firestore"""
        try:
            print(f"🔄 [RUNALYZE] Avvio sync storico per l'anno {year}...")
            mappa_scarpe = self._get_shoe_mapping()

            start_date = datetime(year, 1, 1)
            end_date = datetime(year, 12, 31, 23, 59, 59)
            after_ts = int(start_date.timestamp())
            before_ts = int(end_date.timestamp())
            
            corse_salvate = 0
            limit = 200
            offset = 0
            
            while True:
                url = f"{self.base_url}/activities?after={after_ts}&before={before_ts}&limit={limit}&offset={offset}"
                response = requests.get(url, headers=self.headers)
                response.raise_for_status()
                activities = response.json()
                
                if not activities:
                    break
                    
                for act in activities:
                    sport_id = act.get('sport_id', 1)
                    if sport_id == 1 or act.get('sport_name', '').lower() == 'running':
                        equipments = act.get('equipment_ids', [])
                        gear_id = equipments[0] if equipments else None
                        nome_scarpa = mappa_scarpe.get(gear_id, 'N/D') if gear_id else 'N/D'
                        
                        timestamp = act.get('time', 0)
                        start_date_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
                        
                        run_data = {
                            'id': act['id'],
                            'name': act.get('title', 'Corsa'),
                            'distance': act.get('distance', 0) * 1000,
                            'moving_time': act.get('duration', 0),
                            'start_date': start_date_str,
                            'workout_type': act.get('is_race', False),
                            'scarpe': nome_scarpa
                        }
                        db_instance.db.collection("activities").document(str(act['id'])).set(run_data, merge=True)
                        corse_salvate += 1
                
                if len(activities) < limit:
                    break # Abbiamo raggiunto l'ultima pagina
                offset += limit
            
            print(f"✅ [RUNALYZE] Sync {year} completato: {corse_salvate} corse salvate.")
            return corse_salvate
        except Exception as e:
            print(f"❌ [RUNALYZE] Errore durante il sync dell'anno {year}: {e}")
            return 0

    # ==========================================
    # 3. LETTURE LIVE DA RUNALYZE (Dettagli AI)
    # ==========================================
    def fetch_athlete_shoes(self):
        """Recupera la lista delle scarpe registrate. Runalyze ha una gestione dell'equipaggiamento generica"""
        url = f"{self.base_url}/equipment"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            equipment_data = response.json()
            
            scarpe = []
            for item in equipment_data:
                scarpe.append({
                    'id': item.get('id'),
                    'name': item.get('name', 'Scarpa'),
                    'distance': item.get('distance', 0) * 1000 # Riconversione km -> metri per compatibilità DB
                })
            return scarpe
        except requests.exceptions.RequestException as e:
            print(f"❌ Errore nel recupero della scarpiera: {e}")
            return []

    def fetch_gear_details(self, gear_id):
        """Recupera i dettagli tecnici e i km esatti di una singola scarpa (compatibilità)"""
        url = f"{self.base_url}/equipment" # Runalyze restituisce spesso tutto l'equipment
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            for item in data:
                if str(item.get('id')) == str(gear_id):
                    # Formattiamo come si aspetta l'AI
                    return {
                        'id': item['id'],
                        'name': item['name'],
                        'distance': item.get('distance', 0) * 1000
                    }
            return None
        except requests.exceptions.RequestException as e:
            print(f"❌ Errore nel recupero dei dettagli scarpa {gear_id}: {e}")
            return None

    def fetch_activity_details(self, activity_id):
        """Scarica il dettaglio completo di una singola attività da passare a Gemini"""
        url = f"{self.base_url}/activities/{activity_id}"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            act = response.json()
            
            # Calcolo passo in m/s (come Strava) per compatibilità con l'analyst
            distanza_km = act.get("distance", 0)
            tempo_sec = act.get("duration", 0)
            passo_ms = ((distanza_km * 1000) / tempo_sec) if tempo_sec > 0 else 0
            
            data_pulita = {
                "id": act.get("id"),
                "nome": act.get("title", "Corsa"),
                "tipo": "Run",
                "workout_type": act.get("is_race", False),
                "distanza": distanza_km, # km
                "tempo_movimento": tempo_sec / 60, # minuti
                "passo_medio": passo_ms, 
                "bpm_medi": act.get("hr_avg", "N/D"),
                "dislivello": act.get("elevation", 0),
                "scarpe": "Non specificate", # Aggiornabile iterando sull'equipment
                "note_private": act.get("notes", ""),
                "laps": [] # Runalyze supporta i laps in un altro formato, per ora lo passiamo vuoto
            }
            return data_pulita
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Errore nel recupero del dettaglio attività {activity_id}: {e}")
            return None

    # ==========================================
    # 4. METODI FALLBACK / LEGACY
    # ==========================================
    def fetch_last_active_week(self):
        """Individua l'ultima corsa effettuata e restituisce la relativa settimana."""
        try:
            url = f"{self.base_url}/activities?limit=30"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            activities = response.json()
            
            runs = [act for act in activities if act.get('sport_id', 1) == 1]
            if not runs:
                return [], 0, None, None
                
            ultima_corsa = runs[0]
            timestamp = ultima_corsa.get('time', 0)
            run_date = datetime.fromtimestamp(timestamp)
            
            start_of_week = run_date - timedelta(days=run_date.weekday())
            start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_week = start_of_week + timedelta(days=6, hours=23, minutes=59, seconds=59)
            
            settimana_attiva = []
            km_totali = 0
            
            for run in runs:
                r_date = datetime.fromtimestamp(run.get('time', 0))
                if start_of_week <= r_date <= end_of_week:
                    settimana_attiva.append({
                        "id": run.get("id"),
                        "nome": run.get("title", "Corsa"),
                        "distanza": run.get("distance", 0), # Runalyze restituisce già km
                        "data": r_date.strftime("%d/%m/%Y"),
                        "start_date": r_date.strftime('%Y-%m-%d'),
                        "workout_type": run.get("is_race", False)
                    })
                    km_totali += run.get("distance", 0)
                    
            settimana_attiva.reverse()
            return settimana_attiva, km_totali, start_of_week, end_of_week

        except requests.exceptions.RequestException as e:
            print(f"❌ Errore nel recupero della settimana attiva retroattiva: {e}")
            return [], 0, None, None


# =========================================================================
# FACADE PATTERN: Istanziamo RunalyzeClient ma lo chiamiamo strava_client!
# In questo modo webhook.py e orchestrator.py continueranno a funzionare
# alla perfezione senza dover cambiare nemmeno una virgola nel loro codice.
# =========================================================================
runalyze_client = RunalyzeClient()