from google import genai
from .config import config
from .database import db

class RunningAnalyst:
    def __init__(self):
        # 1. Recupera la API Key (da .env o Secret Manager)
        api_key = config.get_secret("GEMINI_API_KEY")
        
        if not api_key:
            raise ValueError("GEMINI_API_KEY mancante. Inseriscila nel .env o in Secret Manager.")

        # 2. Inizializza il client Globale (Senza Vertex AI)
        # Questo forza l'uso della chiave e bypassa le restrizioni di Google Cloud
        self.client = genai.Client(api_key=api_key)
        
        # 3. Usiamo la versione stabile e globale
        self.model_id = "gemini-2.5-flash-lite"

    def analyze_recent_performance(self):
        runs = db.get_recent_runs(limit=10)
        
        running_data = [r for r in runs if r.get('distance', 0) > 0]
        
        if not running_data:
            return "Dati insufficienti per l'analisi (nessuna corsa con distanza rilevata)."

        stats = "\n".join([
            f"- {r['start_date']}: {r['name']} | {r['distance']/1000:.2f}km | Tempo: {r['moving_time']//60} min"
            for r in running_data
        ])

        prompt = f"""
        Sei un coach di corsa esperto. Analizza queste ultime attività e fornisci un feedback 
        tecnico, motivante e sintetico (max 120 parole). 
        Punta l'attenzione sulla costanza e sul ritmo.
        
        ATTIVITÀ RECENTI:
        {stats}
        """

        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt
            )
            return response.text
        except Exception as e:
            return f"Errore durante la generazione del feedback: {e}"

analyst = RunningAnalyst()