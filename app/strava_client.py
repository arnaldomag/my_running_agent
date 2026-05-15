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

    def fetch_recent_activities(self, limit=5):
        """Scarica le ultime attività dall'API di Strava"""
        token = self.get_access_token()
        headers = {'Authorization': f"Bearer {token}"}
        params = {'per_page': limit}
        
        response = requests.get(f"{self.base_url}/athlete/activities", headers=headers, params=params)
        response.raise_for_status()
        return response.json()

    def fetch_weekly_runs(self):
        """Scarica e aggrega solo le corse della settimana corrente (da lunedì a oggi)"""
        token = self.get_access_token()
        headers = {'Authorization': f"Bearer {token}"}
        
        # 1. Calcolo del Lunedì di questa settimana a mezzanotte
        oggi = datetime.now()
        giorni_da_lunedi = oggi.weekday()  # 0 = Lunedì, 6 = Domenica
        lunedi = oggi - timedelta(days=giorni_da_lunedi)
        inizio_settimana = lunedi.replace(hour=0, minute=0, second=0, microsecond=0)
        
        epoch_after = int(inizio_settimana.timestamp())
        
        # 2. Parametri per la chiamata API
        params = {
            "after": epoch_after,
            "per_page": 30  # Limite di sicurezza ampio per una singola settimana
        }
        
        response = requests.get(f"{self.base_url}/athlete/activities", headers=headers, params=params)
        response.raise_for_status()
        activities = response.json()
        
        # 3. Filtraggio e Aggregazione dei dati
        lista_corse = []
        km_totali = 0.0
        
        for activity in activities:
            # Filtriamo solo le attività registrate come corsa
            if activity.get('type') == 'Run':
                distanza_km = activity.get('distance', 0) / 1000
                km_totali += distanza_km
                
                # Estraiamo la data formattata YYYY-MM-DD
                data_str = activity.get('start_date_local', '')[:10]
                
                lista_corse.append({
                    "nome": activity.get('name'),
                    "data": data_str,
                    "distanza": round(distanza_km, 2),
                    "id": activity.get('id')
                })
                
        return lista_corse, round(km_totali, 2)

strava_client = StravaClient()