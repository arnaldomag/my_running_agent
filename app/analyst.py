from google import genai
from .config import config
from .database import db

class RunningAnalyst:
    def __init__(self):
        # 1. Recupera la API Key (da .env o Secret Manager)
        api_key = config.get_secret("GEMINI_API_KEY")
        
        if not api_key:
            raise ValueError("GEMINI_API_KEY mancante. Inseriscila nel .env o in Secret Manager.")

        # 2. Inizializza il client Globale
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

    def analyze_weekly_summary(self, lista_corse, km_totali):
        """Genera un'analisi aggregata per la settimana in corso"""
        
        if not lista_corse:
            return "Nessuna corsa registrata questa settimana. Ottimo momento per pianificare la prossima uscita!"

        # Formatta la lista delle corse per il prompt
        dettagli_corse = "\n".join([
            f"- {r['data']}: {r['nome']} ({r['distanza']} km)"
            for r in lista_corse
        ])

        prompt = f"""
        Agisci come il mio coach personale di corsa.
        Ecco i dati aggregati degli allenamenti che ho fatto questa settimana (da lunedì a oggi):
        
        - Chilometri totali: {km_totali} km
        - Corse effettuate:
        {dettagli_corse}

        Il mio regime abituale prevede 2 o 3 allenamenti a settimana, focalizzati su distanze tra i 10km e la mezza maratona.
        
        Compiti:
        1. Fornisci un riassunto motivazionale e tecnico sul volume di allenamento della settimana, valutando se il carico è adeguato (max 100 parole).
        2. Cerca elementi in cui non sono andato bene, sii molto onesto e duro se serve e cerca di darmi consigli reali e pratici su come poter migliorare
        3. Elenca le singole corse in modo pulito e ordinato.
        
        REGOLE DI FORMATTAZIONE (CRITICHE):
        - Usa ESCLUSIVAMENTE i tag <b>testo</b> per il grassetto e <i>testo</i> per il corsivo.
        - Per gli elenchi, usa semplici trattini (-) o punti (•) testuali.
        - NON usare tag come <ul>, <li>, <p>, <html>, <body> o <div>.
        - NON includere il blocco di codice markdown (niente ```html all'inizio o alla fine).
        - Restituisci solo il testo pulito pronto per essere inviato.
        """

        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt
            )
            return response.text
        except Exception as e:
            return f"Errore durante la generazione del report settimanale: {e}"

analyst = RunningAnalyst()