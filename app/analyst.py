from google import genai
from .config import config
from .database import db
import PIL.Image
import io
import json
import google.genai.types as types

# Importiamo i nostri prompt come costanti
from .prompts import (
    PROMPT_CHAT_SISTEMA,
    PROMPT_RECENT_PERFORMANCE,
    PROMPT_REPORT_SETTIMANALE,
    PROMPT_ANALISI_CORSA,
    PROMPT_ANALISI_SCARPA,
    PROMPT_OCR_BILANCIA
)

class RunningAnalyst:
    def __init__(self):
        # 1. Recupera la API Key
        api_key = config.get_secret("GEMINI_API_KEY")
        
        if not api_key:
            raise ValueError("GEMINI_API_KEY mancante. Inseriscila nel .env o in Secret Manager.")

        # 2. Inizializza il client Globale
        self.client = genai.Client(api_key=api_key)
        
        # 3. Usiamo la versione stabile e globale
        self.model_id = "gemini-3.5-flash"

    def chat_with_runalyze_context(self, chat_id, user_text):
        """Gestisce una conversazione fluida iniettando lo storico allenamenti come system instruction"""
        try:
            # 1. Recupero dinamico
            recent_runs = db.get_recent_runs(limit=100)
            
            if recent_runs:
                storico_compatto = []
                runalyze_workout_types = {
                    0: "Recupero/Base",
                    1: "Gara",
                    2: "Lungo",
                    3: "Qualità"
                }
                
                for run in recent_runs:
                    tipo_id = run.get('workout_type')
                    tipo_corsa = runalyze_workout_types.get(tipo_id, "Base") if tipo_id is not None else "Base"
                    distanza_km = run.get('distance', 0) / 1000
                    tempo_min = run.get('moving_time', 0) // 60
                    
                    riga = f"- {run.get('start_date', 'N/D')}: {run.get('name', 'Corsa')} | Tipo: {tipo_corsa} | {distanza_km:.1f}km in {tempo_min}m | Scarpa: {run.get('scarpe', 'N/D')}"
                    storico_compatto.append(riga)
                
                activity_context = "\n".join(storico_compatto)
            else:
                activity_context = "Nessun allenamento recente trovato nel database."

            # 2. Configurazione della System Instruction dinamica formattata dal prompt pulito
            full_system_instruction = PROMPT_CHAT_SISTEMA.format(activity_context=activity_context)

            # 3. Lettura dello stato precedente da Firestore
            contents, history_dicts = db.get_chat_history(chat_id)

            # 4. Aggiunta del nuovo input dell'utente
            contents.append(
                genai.types.Content(
                    role="user",
                    parts=[genai.types.Part.from_text(text=user_text)]
                )
            )

            # 5. Configurazione della chiamata all'SDK (usiamo gen_config per non sovrascrivere l'import config)
            gen_config = genai.types.GenerateContentConfig(
                system_instruction=full_system_instruction,
                temperature=0.7
            )

            print(f"🧠 [ANALYST] Invio sessione chat a {self.model_id} (History size: {len(contents)})")
            
            # Eseguiamo la chiamata
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=contents,
                config=gen_config
            )
            bot_reply = response.text

            # 6. Salvataggio asincrono su Firestore
            db.save_chat_interaction(chat_id, history_dicts, user_text, bot_reply)

            return bot_reply

        except Exception as e:
            print(f"❌ [ANALYST] Errore nella pipeline della chat AI: {e}")
            return "Scusami, ho riscontrato un problema tecnico nel processare i nostri messaggi. Riprova tra poco!"

    def analyze_recent_performance(self):
        runs = db.get_recent_runs(limit=10)
        
        running_data = [r for r in runs if r.get('distance', 0) > 0]
        
        if not running_data:
            return "Dati insufficienti per l'analisi (nessuna corsa con distanza rilevata)."

        stats = "\n".join([
            f"- {r['start_date']}: {r['name']} | {r['distance']/1000:.2f}km | Tempo: {r['moving_time']//60} min"
            for r in running_data
        ])

        prompt = PROMPT_RECENT_PERFORMANCE.format(stats=stats)

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

        # Formatta la lista delle corse
        dettagli_corse = "\n".join([
            f"- {r['data']}: {r['nome']} ({r['distanza']} km)"
            for r in lista_corse
        ])

        prompt = PROMPT_REPORT_SETTIMANALE.format(
            km_totali=km_totali,
            dettagli_corse=dettagli_corse
        )

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

        # 1. Preparazione dei Lap
        laps_info = "Dati lap non disponibili."
        if dati_corsa.get('laps'):
            laps_str_list = []
            for i, lap in enumerate(dati_corsa['laps'][:15]):
                passo_lap_ms = lap.get('average_speed', 0)
                if passo_lap_ms > 0:
                    pace_min_km = 16.6667 / passo_lap_ms
                    mins = int(pace_min_km)
                    secs = int((pace_min_km - mins) * 60)
                    pace_str = f"{mins}:{secs:02d}"
                else:
                    pace_str = "N/D"
                laps_str_list.append(f"Km {i+1}: {pace_str}")
            laps_info = " | ".join(laps_str_list)

        # 2. Conversione Passo Medio Totale
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

        # 4. Compilazione del prompt usando le chiavi estratte in runalyze_client.py
        prompt = PROMPT_ANALISI_CORSA.format(
            nome=dati_corsa['nome'],
            distanza=dati_corsa['distanza'],
            tempo_movimento=dati_corsa['tempo_movimento'],
            passo_medio_str=passo_medio_str,
            bpm_medi=dati_corsa['bpm_medi'],
            dislivello=dati_corsa['dislivello'],
            scarpe=dati_corsa['scarpe'],
            note=note,
            laps_info=laps_info
        )

        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt
            )
            return response.text
        except Exception as e:
            return f"Errore durante l'analisi della singola corsa: {e}"

    def analyze_shoe(self, gear_details, peso_atleta=None):
        """Analizza l'usura e le caratteristiche tecniche della scarpa"""
        nome = gear_details.get('name', 'Scarpa')
        brand = gear_details.get('brand_name', 'Sconosciuto')
        model_name = gear_details.get('model_name', 'Sconosciuto')
        km_attuali = gear_details.get('distance', 0) / 1000
        
        peso_info = f"{peso_atleta} kg" if peso_atleta else "N/D (considera un peso medio di 70-75 kg)"

        prompt = PROMPT_ANALISI_SCARPA.format(
            nome=nome,
            brand=brand,
            model_name=model_name,
            km_attuali=km_attuali,
            peso_info=peso_info
        )

        try:
            risposta = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt
            )
            return risposta.text
        except Exception as e:
            print(f"Errore Gemini durante analisi scarpa: {e}")
            return f"❌ Impossibile generare l'analisi per questa scarpa: {e}"

    def extract_body_metrics_from_image(self, image_bytes):
        """Utilizza Gemini Flash per estrarre le metriche corporee e restituirle in JSON"""
        try:
            image = PIL.Image.open(io.BytesIO(image_bytes))
            
            print("🧠 [ANALYST] Invio screenshot a Gemini Flash per estrazione JSON...")
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=[PROMPT_OCR_BILANCIA, image]
            )
            
            json_text = response.text.strip()
            if json_text.startswith("```json"):
                json_text = json_text[7:]
            if json_text.startswith("```"):
                json_text = json_text[3:]
            if json_text.endswith("```"):
                json_text = json_text[:-3]
                
            json_text = json_text.strip()
            
            try:
                dati_corporei = json.loads(json_text)
                print(f"✅ [ANALYST] Metriche estratte: {dati_corporei}")
                return dati_corporei
            except json.JSONDecodeError as e:
                print(f"⚠️ [ANALYST] Errore di decodifica JSON. Risposta grezza: {json_text}")
                return None
                
        except Exception as e:
            print(f"❌ [ANALYST] Errore durante analisi ottica: {e}")
            return None

analyst = RunningAnalyst()