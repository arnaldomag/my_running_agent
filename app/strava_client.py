import requests
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

strava_client = StravaClient()