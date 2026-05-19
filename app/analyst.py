from google import genai
from .config import config
from .database import db
import PIL.Image
import io

class RunningAnalyst:
    def __init__(self):
        # 1. Recupera la API Key (da .env o Secret Manager)
        api_key = config.get_secret("GEMINI_API_KEY")
        
        if not api_key:
            raise ValueError("GEMINI_API_KEY mancante. Inseriscila nel .env o in Secret Manager.")

        # 2. Inizializza il client Globale
        self.client = genai.Client(api_key=api_key)
        
        # 3. Usiamo la versione stabile e globale
        self.model_id = "gemini-3.5-flash"

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
        
    def analyze_single_run(self, dati_corsa):
        """Genera un'analisi profonda di una singola corsa confrontando target e realtà"""
        
        if not dati_corsa:
            return "Nessun dato disponibile per questa attività."

        # 1. Preparazione dei Lap (Convertiamo i m/s in min/km se disponibili)
        laps_info = "Dati lap non disponibili."
        if dati_corsa.get('laps'):
            laps_str_list = []
            # Prendiamo i primi 15 lap per non sovraccaricare il prompt
            for i, lap in enumerate(dati_corsa['laps'][:15]):
                passo_lap_ms = lap.get('average_speed', 0)
                if passo_lap_ms > 0:
                    # Formula di conversione da m/s a min/km
                    pace_min_km = 16.6667 / passo_lap_ms
                    mins = int(pace_min_km)
                    secs = int((pace_min_km - mins) * 60)
                    pace_str = f"{mins}:{secs:02d}"
                else:
                    pace_str = "N/D"
                laps_str_list.append(f"Km {i+1}: {pace_str}")
            laps_info = " | ".join(laps_str_list)

        # 2. Conversione Passo Medio Totale (da m/s a min/km)
        passo_medio_ms = dati_corsa.get('passo_medio', 0)
        if passo_medio_ms > 0:
            pace_min_km = 16.6667 / passo_medio_ms
            mins = int(pace_min_km)
            secs = int((pace_min_km - mins) * 60)
            passo_medio_str = f"{mins}:{secs:02d} min/km"
        else:
            passo_medio_str = "N/D"

        # 3. Gestione Note Private vuote
        note = dati_corsa.get('note_private', '').strip()
        if not note:
            note = "Nessun obiettivo o struttura specificata nelle note private."

        # 4. Prompt Ingegnerizzato per l'Analisi Dettagliata
        prompt = f"""
        Agisci come il mio coach di corsa e analista dati sportivo.
        Valuta questa singola sessione confrontando le mie note private (l'obiettivo dell'allenamento) con i dati reali registrati.
        
        DATI DELLA CORSA A CONSUNTIVO:
        - Nome: {dati_corsa['nome']}
        - Distanza: {dati_corsa['distanza']:.2f} km
        - Tempo in movimento: {dati_corsa['tempo_movimento']:.1f} min
        - Passo Medio: {passo_medio_str}
        - Battiti Medi: {dati_corsa['bpm_medi']} bpm
        - Dislivello: {dati_corsa['dislivello']} m
        - Scarpe utilizzate: {dati_corsa['scarpe']}
        
        DATI A PREVENTIVO (STRUTTURA/OBIETTIVO):
        "{note}"
        
        ANDAMENTO DEL PASSO PER KM:
        {laps_info}
        
        COMPITI ANALITICI:
        1. Esegui un'analisi degli scostamenti: ho rispettato quanto scritto nelle note private? (Es. se l'obiettivo era 1 minuto veloce / 1 lento, i lap riflettono variazioni di ritmo coerenti?).
        2. Valuta il dispendio energetico (passo e BPM) e controlla se la scarpa registrata è adeguata al tipo di lavoro svolto, tenendo conto delle dinamiche per preparare una mezza maratona.
        3. Scrivi un responso tecnico e netto (max 150 parole)
        4. Cerca elementi in cui non sono andato bene, sii molto onesto e duro se serve e cerca di darmi consigli reali e pratici su come poter migliorare (max 150 parole).
        
        REGOLE DI FORMATTAZIONE PER TELEGRAM:
        - Formatta in HTML (usa SOLO i tag <b> per grassetto e <i> per corsivo).
        - NON usare Markdown (no **, no #).
        - NON inserire tag di blocco come <html>, <body>, <p>, <ul> o <li>.
        - Usa il trattino testuale (-) per eventuali elenchi.
        - NON inserire blocchi di codice testuali (no ```html).
        - Restituisci esclusivamente il testo formattato pronto per l'invio.
        """

        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt
            )
            return response.text
        except Exception as e:
            return f"Errore durante l'analisi della singola corsa: {e}"

    def analyze_shoe(self, gear_details):
        """Analizza l'usura e le caratteristiche tecniche della scarpa"""
        nome = gear_details.get('name', 'Scarpa')
        brand = gear_details.get('brand_name', 'Sconosciuto')
        model_name = gear_details.get('model_name', 'Sconosciuto')
        km_attuali = gear_details.get('distance', 0) / 1000

        prompt = f"""
        Analizza tecnicamente la seguente scarpa da running e il suo stato di usura:
        - Nome in Strava: {nome}
        - Marca: {brand}
        - Modello: {model_name}
        - Chilometri attuali: {km_attuali:.2f} km

        L'atleta la utilizza principalmente per allenamenti e gare su distanze di 10km e mezze maratone (21km).
        
        Struttura la risposta in modo chiaro:
        1. Fai un breve focus tecnico sul modello (es. tipo di schiuma PEBA/EVA, drop, presenza di piastre, reattività).
        2. Indica qual è la durata media o "lifespan" (in km) per questa tipologia esatta di schiuma e modello.
        3. Confronta i km attuali con la durata media, indicando se la scarpa è ancora nel suo "sweet spot", se sta perdendo ammortizzazione o se il rischio infortuni inizia ad alzarsi.
        4. Dai un verdetto finale: è ora di iniziare a cercare la sostituta?

        REGOLE DI FORMATTAZIONE PER TELEGRAM:
        - Formatta in HTML (usa SOLO i tag <b> per grassetto e <i> per corsivo).
        - NON usare Markdown (no **, no #).
        - NON inserire tag di blocco come <html>, <body>, <p>, <ul> o <li>.
        - Usa il trattino testuale (-) per eventuali elenchi.
        - NON inserire blocchi di codice testuali (no ```html).
        - Restituisci esclusivamente il testo formattato pronto per l'invio.
        """
        try:
            risposta = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt
            )
            return risposta.text
        except Exception as e:
            print(f"Errore Gemini durante analisi scarpa: {e}")
            return f"❌ Impossibile generare l'analisi per questa scarpa: {e}"

    def extract_weight_from_image(self, image_bytes):
        """Utilizza Gemini Flash per estrarre il peso numerico dallo screenshot"""
        try:
            # Convertiamo i bytes in un oggetto immagine che Gemini può leggere
            image = PIL.Image.open(io.BytesIO(image_bytes))
            
            # Creiamo un prompt mirato per l'interfaccia dell'app Decathlon
            prompt = """
            Analizza questa immagine. È uno screenshot dell'app della bilancia Decathlon Scale 700.
            Trova e restituiscimi ESCLUSIVAMENTE il numero che indica il peso corporeo attuale in kg.
            Non aggiungere testo, commenti o l'unità di misura, solo il numero con il punto decimale.
            Esempio di risposta corretta: 70.9
            """
            
            print("🧠 [ANALYST] Invio screenshot a Gemini Flash...")
            
            # Passiamo al modello SIA il testo CHE l'immagine in una singola lista
            response = self.model.generate_content([prompt, image])
            
            # Puliamo la risposta
            peso_str = response.text.strip()
            
            try:
                peso = float(peso_str)
                print(f"✅ [ANALYST] Peso estratto correttamente dall'immagine: {peso} kg")
                return peso
            except ValueError:
                print(f"⚠️ [ANALYST] Gemini ha risposto con formato non valido: {peso_str}")
                return None
                
        except Exception as e:
            print(f"❌ [ANALYST] Errore durante analisi ottica: {e}")
            return None

analyst = RunningAnalyst()