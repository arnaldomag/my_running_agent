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
                    "id": activity.get('id'),
                    "workout_type": activity.get('workout_type')
                })
                
        return lista_corse, round(km_totali, 2)

    def fetch_last_active_week(self):
        """
        Scarica le attività recenti, individua l'ultima corsa effettuata
        e restituisce tutti gli allenamenti di quella specifica settimana.
        """
        token = self.get_access_token()
        headers = {'Authorization': f"Bearer {token}"}
        
        # Chiediamo le ultime 30 attività per essere sicuri di andare abbastanza indietro
        url = f"{self.base_url}/athlete/activities?per_page=30"
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            activities = response.json()
            
            # Filtriamo per tenere solo le corse
            runs = [act for act in activities if act.get('type') == 'Run']
            
            if not runs:
                return [], 0, None, None  # Nessuna corsa trovata nello storico recente
                
            # La corsa in indice 0 è la più recente in assoluto
            ultima_corsa = runs[0]
            
            # Gestione della data
            data_str = ultima_corsa['start_date_local'].replace('Z', '+00:00')
            run_date = datetime.fromisoformat(data_str)
            
            # Calcoliamo i confini (Lunedì e Domenica) della settimana a cui appartiene questa corsa
            start_of_week = run_date - timedelta(days=run_date.weekday())
            start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_week = start_of_week + timedelta(days=6, hours=23, minutes=59, seconds=59)
            
            # Ora raccogliamo TUTTE le corse di QUELLA settimana specifica
            settimana_attiva = []
            km_totali = 0
            
            for run in runs:
                r_date = datetime.fromisoformat(run['start_date_local'].replace('Z', '+00:00'))
                if start_of_week <= r_date <= end_of_week:
                    settimana_attiva.append({
                        "id": run.get("id"),
                        "nome": run.get("name"),
                        "distanza": run.get("distance", 0) / 1000,
                        "data": r_date.strftime("%d/%m/%Y"),  # 👈 ECCO LA CHIAVE RIPRISTINATA!
                        "start_date": run.get("start_date_local"), # Per massima compatibilità interna
                        "workout_type": run.get("workout_type")
                    })
                    km_totali += run.get("distance", 0) / 1000
                    
            # Giriamo in ordine cronologico corretto
            settimana_attiva.reverse()
            
            return settimana_attiva, km_totali, start_of_week, end_of_week

        except requests.exceptions.RequestException as e:
            print(f"❌ Errore nel recupero della settimana attiva retroattiva: {e}")
            return [], 0, None, None

    def fetch_athlete_shoes(self):
        """Recupera la lista delle scarpe registrate sul profilo atleta"""
        token = self.get_access_token()
        headers = {'Authorization': f"Bearer {token}"}
        url = f"{self.base_url}/athlete"
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            athlete_data = response.json()
            # Strava restituisce un array 'shoes' con le scarpe
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
        """
        Scarica il dettaglio completo di una singola attività.
        È l'unico endpoint che restituisce il campo 'private_note'.
        """
        token = self.get_access_token()
        headers = {'Authorization': f"Bearer {token}"}
        
        # Endpoint specifico per il dettaglio
        url = f"{self.base_url}/activities/{activity_id}"
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            activity_details = response.json()
            
            # Estraiamo i campi chiave per l'analisi dell'agente
            # Se un campo è mancante, usiamo dei valori di default sicuri
            data_pulita = {
                "id": activity_details.get("id"),
                "nome": activity_details.get("name"),
                "tipo": activity_details.get("type"),
                "workout_type": activity_details.get("workout_type"),
                "distanza": activity_details.get("distance", 0) / 1000, # in km
                "tempo_movimento": activity_details.get("moving_time", 0) / 60, # in minuti
                "passo_medio": activity_details.get("average_speed", 0), # m/s
                "bpm_medi": activity_details.get("average_heartrate", "N/D"),
                "dislivello": activity_details.get("total_elevation_gain", 0),
                "scarpe": activity_details.get("gear", {}).get("name", "Non specificate"),
                "note_private": activity_details.get("private_note", ""), # Qui c'è la struttura dell'allenamento
                "laps": activity_details.get("laps", []) # Utile per vedere i ritmi ogni lap
            }
            
            return data_pulita
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Errore nel recupero del dettaglio attività {activity_id}: {e}")
            return None

strava_client = StravaClient()