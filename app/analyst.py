# app/analyst.py
from google import genai
import google.genai.types as types
from .config import config
from .database import db
from .mcp_bridge import RunalyzeMCPBridge # IMPORTIAMO IL NUOVO PONTE
import PIL.Image
import io
import json
import traceback

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
        """Punto di ingresso per la chat: normalizza la cronologia per il nuovo SDK."""
        try:
            full_system_instruction = PROMPT_OMNI_AGENT.format(context_string=context_string)
            
            # 1. Recuperiamo i dizionari grezzi da Firestore
            _, history_dicts = db.get_chat_history(chat_id)
            
            # 2. ADATTATORE: Convertiamo i dati storici di Firestore in oggetti tipizzati strict
            contents = []
            if history_dicts:
                for turn in history_dicts:
                    role = turn.get("role")
                    parts_raw = turn.get("parts", [])
                    
                    processed_parts = []
                    for p in parts_raw:
                        if p is None:
                            continue
                        
                        # Se nel DB è salvato come stringa nativa (il tuo caso attuale)
                        if isinstance(p, str):
                            processed_parts.append(types.Part(text=p))
                        # Se è già un dizionario strutturato (es. chiamate precedenti)
                        elif isinstance(p, dict):
                            if "text" in p:
                                processed_parts.append(types.Part(text=p["text"]))
                            elif "function_call" in p:
                                fc = p["function_call"]
                                processed_parts.append(types.Part(
                                    function_call=types.FunctionCall(name=fc.get("name"), args=fc.get("args"))
                                ))
                            elif "function_response" in p:
                                fr = p["function_response"]
                                processed_parts.append(types.Part(
                                    function_response=types.FunctionResponse(name=fr.get("name"), response=fr.get("response"))
                                ))
                    
                    if processed_parts and role:
                        contents.append(types.Content(role=role, parts=processed_parts))

            # 3. Aggiungiamo l'ultimo messaggio dell'utente corrente (usando l'oggetto corretto)
            contents.append(
                types.Content(role="user", parts=[types.Part(text=user_text)])
            )

            print(f"🧠 [ANALYST] Inizio delegazione Omni-Agent via MCP...")
            bot_reply = self.mcp_bridge.execute_agent_loop(contents, full_system_instruction)

            db.save_chat_interaction(chat_id, history_dicts, user_text, bot_reply)
            return bot_reply

        except Exception as e:
            print("💥 [CRITICAL] Traceback dettagliato dell'errore MCP:")
            traceback.print_exc() 
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
