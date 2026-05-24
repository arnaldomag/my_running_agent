import requests
from datetime import datetime, timedelta
from .config import config

class StravaClient:
    def __init__(self):
        self.client_id = config.get_secret("STRAVA_CLIENT_ID")
        self.client_secret = config.get_secret("STRAVA_CLIENT_SECRET")
        self.refresh_token = config.get_secret("STRAVA_REFRESH_TOKEN")
        self.base_url = "https://www.strava.com/api/v3"

    def get_access_token(self):
        """Ottiene un nuovo access token usando il refresh token"""
        payload = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'refresh_token': self.refresh_token,
            'grant_type': 'refresh_token'
        }
        response = requests.post(f"{self.base_url}/oauth/token", data=payload)
        response.raise_for_status()
        return response.json()['access_token']

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
            token = self.get_access_token()
            headers = {'Authorization': f'Bearer {token}'}
            
            mappa_scarpe = self._get_shoe_mapping()

            url = f"https://www.strava.com/api/v3/athlete/activities?per_page={limit}"
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            activities = response.json()
            
            for act in activities:
                if act.get('type') == 'Run':
                    gear_id = act.get('gear_id')
                    nome_scarpa = mappa_scarpe.get(gear_id, 'N/D') if gear_id else 'N/D'
                    
                    run_data = {
                        'id': act['id'],
                        'name': act['name'],
                        'distance': act['distance'],
                        'moving_time': act['moving_time'],
                        'start_date': act['start_date_local'][:10],
                        'workout_type': act.get('workout_type', 0),
                        'scarpe': nome_scarpa
                    }
                    db_instance.db.collection("activities").document(str(act['id'])).set(run_data, merge=True)
            return True
        except Exception as e:
            print(f"⚠️ [STRAVA] Mini-sync fallito: {e}")
            return False

    def sync_historical_data_by_year(self, db_instance, year):
        """Scarica tutte le corse di un anno specifico e le aggiorna/salva su Firestore"""
        try:
            print(f"🔄 [STRAVA] Avvio sync storico per l'anno {year}...")
            token = self.get_access_token()
            headers = {'Authorization': f'Bearer {token}'}

            mappa_scarpe = self._get_shoe_mapping()

            start_date = datetime(year, 1, 1)
            end_date = datetime(year, 12, 31, 23, 59, 59)
            after_ts = int(start_date.timestamp())
            before_ts = int(end_date.timestamp())
            
            corse_salvate = 0
            page = 1
            
            while True:
                url = f"https://www.strava.com/api/v3/athlete/activities?after={after_ts}&before={before_ts}&per_page=200&page={page}"
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                activities = response.json()
                
                if not activities:
                    break
                    
                for act in activities:
                    if act.get('type') == 'Run':
                        gear_id = act.get('gear_id')
                        nome_scarpa = mappa_scarpe.get(gear_id, 'N/D') if gear_id else 'N/D'
                        
                        run_data = {
                            'id': act['id'],
                            'name': act['name'],
                            'distance': act['distance'],
                            'moving_time': act['moving_time'],
                            'start_date': act['start_date_local'][:10],
                            'workout_type': act.get('workout_type', 0),
                            'scarpe': nome_scarpa
                        }
                        db_instance.db.collection("activities").document(str(act['id'])).set(run_data, merge=True)
                        corse_salvate += 1
                
                page += 1
            
            print(f"✅ [STRAVA] Sync {year} completato: {corse_salvate} corse elaborate (nuove o aggiornate).")
            return corse_salvate
        except Exception as e:
            print(f"❌ [STRAVA] Errore durante il sync dell'anno {year}: {e}")
            return 0

    # ==========================================
    # 3. LETTURE LIVE DA STRAVA (Dettagli AI)
    # ==========================================
    def fetch_athlete_shoes(self):
        """Recupera la lista delle scarpe registrate sul profilo atleta"""
        token = self.get_access_token()
        headers = {'Authorization': f"Bearer {token}"}
        url = f"{self.base_url}/athlete"
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            athlete_data = response.json()
            return athlete_data.get('shoes', [])
        except requests.exceptions.RequestException as e:
            print(f"❌ Errore nel recupero della scarpiera: {e}")
            return []

    def fetch_gear_details(self, gear_id):
        """Recupera i dettagli tecnici e i km esatti di una singola scarpa"""
        token = self.get_access_token()
        headers = {'Authorization': f"Bearer {token}"}
        url = f"{self.base_url}/gear/{gear_id}"
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ Errore nel recupero dei dettagli scarpa {gear_id}: {e}")
            return None

    def fetch_activity_details(self, activity_id):
        """Scarica il dettaglio completo di una singola attività (incluso private_note e laps)"""
        token = self.get_access_token()
        headers = {'Authorization': f"Bearer {token}"}
        url = f"{self.base_url}/activities/{activity_id}"
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            activity_details = response.json()
            
            data_pulita = {
                "id": activity_details.get("id"),
                "nome": activity_details.get("name"),
                "tipo": activity_details.get("type"),
                "workout_type": activity_details.get("workout_type"),
                "distanza": activity_details.get("distance", 0) / 1000,
                "tempo_movimento": activity_details.get("moving_time", 0) / 60,
                "passo_medio": activity_details.get("average_speed", 0),
                "bpm_medi": activity_details.get("average_heartrate", "N/D"),
                "dislivello": activity_details.get("total_elevation_gain", 0),
                "scarpe": activity_details.get("gear", {}).get("name", "Non specificate"),
                "note_private": activity_details.get("private_note", ""),
                "laps": activity_details.get("laps", [])
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
        token = self.get_access_token()
        headers = {'Authorization': f"Bearer {token}"}
        url = f"{self.base_url}/athlete/activities?per_page=30"
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            activities = response.json()
            
            runs = [act for act in activities if act.get('type') == 'Run']
            if not runs:
                return [], 0, None, None
                
            ultima_corsa = runs[0]
            data_str = ultima_corsa['start_date_local'].replace('Z', '+00:00')
            run_date = datetime.fromisoformat(data_str)
            
            start_of_week = run_date - timedelta(days=run_date.weekday())
            start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_week = start_of_week + timedelta(days=6, hours=23, minutes=59, seconds=59)
            
            settimana_attiva = []
            km_totali = 0
            
            for run in runs:
                r_date = datetime.fromisoformat(run['start_date_local'].replace('Z', '+00:00'))
                if start_of_week <= r_date <= end_of_week:
                    settimana_attiva.append({
                        "id": run.get("id"),
                        "nome": run.get("name"),
                        "distanza": run.get("distance", 0) / 1000,
                        "data": r_date.strftime("%d/%m/%Y"),
                        "start_date": run.get("start_date_local"),
                        "workout_type": run.get("workout_type")
                    })
                    km_totali += run.get("distance", 0) / 1000
                    
            settimana_attiva.reverse()
            return settimana_attiva, km_totali, start_of_week, end_of_week

        except requests.exceptions.RequestException as e:
            print(f"❌ Errore nel recupero della settimana attiva retroattiva: {e}")
            return [], 0, None, None

# Istanziazione globale usata in webhook.py
strava_client = StravaClient()