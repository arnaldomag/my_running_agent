# app/analyst.py
from google import genai
import google.genai.types as types
from .config import config
from .database import db
from .mcp_bridge import RunalyzeMCPBridge # IMPORTIAMO IL NUOVO PONTE
import PIL.Image
import io
import json

from .prompts import PROMPT_OMNI_AGENT, PROMPT_OCR_BILANCIA

class RunningAnalyst:
    def __init__(self):
        api_key = config.get_secret("GEMINI_API_KEY")
        runalyze_token = config.get_secret("RUNALYZE_TOKEN") # RECUPERO IL TOKEN DI RUNALYZE
        
        if not api_key or not runalyze_token:
            raise ValueError("Chiavi API mancanti (Gemini o Runalyze).")

        self.client = genai.Client(api_key=api_key)
        self.model_id = "gemini-3.5-flash"
        
        # INIZIALIZZIAMO IL PONTE MCP
        self.mcp_bridge = RunalyzeMCPBridge(runalyze_token, self.client, self.model_id)

    def chat_omni_agent(self, chat_id, user_text, context_string):
        """L'interfaccia verso Telegram. Ora non processa più logica, delega tutto all'MCP."""
        try:
            full_system_instruction = PROMPT_OMNI_AGENT.format(context_string=context_string)
            contents, history_dicts = db.get_chat_history(chat_id)

            contents.append(
                types.Content(role="user", parts=[types.Part.from_text(text=user_text)])
            )

            print(f"🧠 [ANALYST] Inizio delegazione Omni-Agent via MCP...")
            
            # DELEGHIAMO LA GESTIONE AL BRIDGE CHE FARÀ LE CHIAMATE A RUNALYZE IN AUTOMATICO
            bot_reply = self.mcp_bridge.execute_agent_loop(contents, full_system_instruction)

            db.save_chat_interaction(chat_id, history_dicts, user_text, bot_reply)
            return bot_reply

        except Exception as e:
            print(f"❌ [ANALYST] Errore critico nel motore MCP: {e}")
            return "C'è stata un'anomalia di connessione con Runalyze. Dammi un minuto e riproviamo."

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
