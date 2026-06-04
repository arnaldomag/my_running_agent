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
        # Runalyze ora include le scarpe direttamente nel JSON dell'attività (campo 'equipment'),
        # ma manteniamo questo metodo per retrocompatibilità se servisse in futuro.
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
            # Usiamo l'endpoint corretto con la paginazione
            url = f"{self.base_url}/activity?page=1&itemsPerPage={limit}"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            activities = response.json()

            for act in activities:
                # Estraiamo il nome dello sport (es. "Running") dal nuovo nodo API
                sport_name = act.get('sport', {}).get('name', '').lower()

                if sport_name == 'running':
                    distanza_km = float(act.get("distance", 0))
                    tempo_sec = int(act.get("duration", 0))
                    passo_ms = ((distanza_km * 1000) / tempo_sec) if tempo_sec > 0 else 0

                    equip_list = act.get('equipment', [])
                    scarpe = ", ".join([e.get('name', 'Sconosciuta') for e in equip_list]) if equip_list else "Non specificate"

                    run_data = {
                        "id": str(act.get("id")),
                        "nome": act.get("title", "Corsa"),
                        "sport": act.get("sport", {}).get("name", "Running"),
                        "workout_type": act.get("type", {}).get("name", "N/D"),
                        "distanza": distanza_km, # Salviamo in km come richiesto
                        "tempo_movimento": tempo_sec / 60, # in minuti
                        "passo_medio": passo_ms, 
                        "bpm_medi": act.get("hr_avg", "N/D"),
                        "dislivello": act.get("elevation_up", 0), # in Runalyze si chiama elevation_up
                        "scarpe": scarpe,
                        "note_private": act.get("note", ""), # in Runalyze è al singolare
                        "start_date": act.get("date_time", ""), # Fondamentale per l'ordinamento
                        "laps": []
                    }
                    
                    # Scriviamo sulla NUOVA tabella 'attivita'
                    db_instance.db.collection("attivita").document(str(act['id'])).set(run_data, merge=True)
            return True
        except Exception as e:
            print(f"⚠️ [RUNALYZE] Mini-sync fallito: {e}")
            return False

    def sync_historical_data_by_year(self, db_instance, year):
        """Scarica tutte le corse di un anno specifico e le salva su Firestore"""
        try:
            print(f"🔄 [RUNALYZE] Avvio sync storico per l'anno {year} sulla tabella 'attivita'...")
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
                    # Runalyze restituisce le corse dalla più recente alla più vecchia.
                    # date_time è in formato "YYYY-MM-DD HH:MM:SS"
                    date_time = act.get('date_time', '')
                    if not date_time:
                        continue
                        
                    corsa_year = int(date_time[:4])
                    
                    if corsa_year < year:
                        # Siamo andati troppo indietro nel tempo, fermiamo il ciclo
                        anno_superato = True
                        break
                    
                    if corsa_year == year:
                        sport_name = act.get('sport', {}).get('name', '').lower()
                        
                        if sport_name == 'running':
                            distanza_km = float(act.get("distance", 0))
                            tempo_sec = int(act.get("duration", 0))
                            passo_ms = ((distanza_km * 1000) / tempo_sec) if tempo_sec > 0 else 0

                            equip_list = act.get('equipment', [])
                            scarpe = ", ".join([e.get('name', 'Sconosciuta') for e in equip_list]) if equip_list else "Non specificate"

                            run_data = {
                                "id": str(act.get("id")),
                                "nome": act.get("title", "Corsa"),
                                "sport": act.get("sport", {}).get("name", "Running"),
                                "workout_type": act.get("type", {}).get("name", "N/D"),
                                "distanza": distanza_km,
                                "tempo_movimento": tempo_sec / 60,
                                "passo_medio": passo_ms, 
                                "bpm_medi": act.get("hr_avg", "N/D"),
                                "dislivello": act.get("elevation_up", 0),
                                "scarpe": scarpe,
                                "note_private": act.get("note", ""),
                                "start_date": date_time,
                                "laps": []
                            }
                            db_instance.db.collection("attivita").document(str(act['id'])).set(run_data, merge=True)
                            corse_salvate += 1

                if len(activities) < items_per_page:
                    break # Abbiamo raggiunto l'ultima pagina di Runalyze
                page += 1

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
                    'distance': item.get('distance', 0) # Manteniamo km per standardizzare
                })
            return scarpe
        except requests.exceptions.RequestException as e:
            print(f"❌ Errore nel recupero della scarpiera: {e}")
            return []

    def fetch_gear_details(self, gear_id):
        """Recupera i dettagli tecnici e i km esatti di una singola scarpa (compatibilità)"""
        url = f"{self.base_url}/equipment" 
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            for item in data:
                if str(item.get('id')) == str(gear_id):
                    return {
                        'id': item['id'],
                        'name': item['name'],
                        'distance': item.get('distance', 0)
                    }
            return None
        except requests.exceptions.RequestException as e:
            print(f"❌ Errore nel recupero dei dettagli scarpa {gear_id}: {e}")
            return None

    def fetch_activity_details(self, activity_id):
        """Scarica il dettaglio completo di una singola attività da passare a Gemini"""
        # ATTENZIONE: Endpoint modificato per passare l'ID in querystring
        url = f"{self.base_url}/activity?id={activity_id}"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            
            if not data:
                return None
                
            act = data[0] # L'API restituisce un array con 1 elemento

            distanza_km = float(act.get("distance", 0))
            tempo_sec = int(act.get("duration", 0))
            passo_ms = ((distanza_km * 1000) / tempo_sec) if tempo_sec > 0 else 0

            equip_list = act.get('equipment', [])
            scarpe = ", ".join([e.get('name', 'Sconosciuta') for e in equip_list]) if equip_list else "Non specificate"

            data_pulita = {
                "id": str(act.get("id")),
                "nome": act.get("title", "Corsa"),
                "sport": act.get("sport", {}).get("name", "Sconosciuto"),
                "workout_type": act.get("type", {}).get("name", "N/D"),
                "distanza": distanza_km, # km
                "tempo_movimento": tempo_sec / 60, # minuti
                "passo_medio": passo_ms, 
                "bpm_medi": act.get("hr_avg", "N/D"),
                "dislivello": act.get("elevation_up", 0),
                "scarpe": scarpe,
                "note_private": act.get("note", ""),
                "start_date": act.get("date_time", ""),
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
            url = f"{self.base_url}/activity?page=1&itemsPerPage=30"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            activities = response.json()

            runs = [act for act in activities if act.get('sport', {}).get('name', '').lower() == 'running']
            if not runs:
                return [], 0, None, None

            ultima_corsa = runs[0]
            # date_time è in formato "YYYY-MM-DD HH:MM:SS"
            dt_str = ultima_corsa.get('date_time', '')
            if not dt_str:
                return [], 0, None, None
                
            run_date = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")

            start_of_week = run_date - timedelta(days=run_date.weekday())
            start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_week = start_of_week + timedelta(days=6, hours=23, minutes=59, seconds=59)

            settimana_attiva = []
            km_totali = 0

            for run in runs:
                r_date_str = run.get('date_time', '')
                if not r_date_str:
                    continue
                r_date = datetime.strptime(r_date_str, "%Y-%m-%d %H:%M:%S")
                
                if start_of_week <= r_date <= end_of_week:
                    distanza = float(run.get("distance", 0))
                    settimana_attiva.append({
                        "id": run.get("id"),
                        "nome": run.get("title", "Corsa"),
                        "distanza": distanza,
                        "data": r_date.strftime("%d/%m/%Y"),
                        "start_date": r_date.strftime('%Y-%m-%d'),
                        "workout_type": run.get("type", {}).get("name", "N/D")
                    })
                    km_totali += distanza

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