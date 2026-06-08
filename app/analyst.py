# app/analyst.py
from google import genai
import google.genai.types as types
from .config import config
from .database import db
import PIL.Image
import io
import json

from .prompts import PROMPT_OMNI_AGENT, PROMPT_OCR_BILANCIA

class RunningAnalyst:
    def __init__(self):
        api_key = config.get_secret("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY mancante. Controlla le variabili d'ambiente.")

        self.client = genai.Client(api_key=api_key)
        self.model_id = "gemini-3.5-flash"

    def chat_omni_agent(self, chat_id, user_text, context_string):
        """Unico punto di ingresso per l'analisi testuale. Gestisce la chat iniettando tutto il contesto."""
        try:
            # 1. Iniettiamo il mega-stringone di contesto generato dall'orchestratore
            full_system_instruction = PROMPT_OMNI_AGENT.format(context_string=context_string)

            # 2. Recuperiamo la cronologia da Firestore (memoria storica dei messaggi)
            contents, history_dicts = db.get_chat_history(chat_id)

            # 3. Appendiamo l'ultimo messaggio dell'utente alla lista dell'SDK
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=user_text)]
                )
            )

            # 4. Configurazione dei parametri di generazione
            gen_config = types.GenerateContentConfig(
                system_instruction=full_system_instruction,
                temperature=0.7
            )

            print(f"🧠 [ANALYST] Chiamata Omni-Agent (Modello: {self.model_id} | Turni History: {len(contents)})")
            
            # 5. Richiesta all'SDK ufficiale
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=contents,
                config=gen_config
            )
            bot_reply = response.text

            # 6. Salvataggio della nuova interazione su Firestore per non perdere la memoria al prossimo turno
            db.save_chat_interaction(chat_id, history_dicts, user_text, bot_reply)

            return bot_reply

        except Exception as e:
            print(f"❌ [ANALYST] Errore critico nel motore Omni-Agent: {e}")
            return "Scusami, ho riscontrato un'anomalia temporanea nell'elaborare i dati. Puoi riprovare tra un attimo?"

    def extract_body_metrics_from_image(self, image_bytes):
        """Estrattore OCR tramite Vision Engine."""
        try:
            image = PIL.Image.open(io.BytesIO(image_bytes))
            print("🧠 [ANALYST] Invio screenshot bilancia a Gemini...")
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=[PROMPT_OCR_BILANCIA, image]
            )
            
            json_text = response.text.replace("```json", "").replace("```", "").strip()
            dati_corporei = json.loads(json_text)
            print(f"✅ [ANALYST] Metriche estratte con successo: {dati_corporei}")
            return dati_corporei
        except Exception as e:
            print(f"❌ [ANALYST] Errore durante l'analisi ottica dell'immagine: {e}")
            return None

analyst = RunningAnalyst()