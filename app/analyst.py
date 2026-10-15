import json
import logging
from typing import Any

from google import genai
import google.genai.types as types

from .config import config
from .database import db
from .mcp_bridge import RunalyzeMCPBridge
from .prompts import PROMPT_OCR_BILANCIA, PROMPT_OMNI_AGENT

logger = logging.getLogger(__name__)


class RunningAnalyst:
    def __init__(self):
        api_key = config.get_secret("GEMINI_API_KEY")
        runalyze_token = config.get_secret("RUNALYZE_TOKEN")

        if not api_key or not runalyze_token:
            raise ValueError("Chiavi API mancanti (GEMINI_API_KEY o RUNALYZE_TOKEN).")

        self.client = genai.Client(api_key=api_key)
        self.model_id = "gemini-3.5-flash"

        # Inizializziamo il ponte MCP con caching e connection pooling
        self.mcp_bridge = RunalyzeMCPBridge(runalyze_token, self.client, self.model_id)

    @staticmethod
    def _build_typed_contents(history_dicts: list[dict[str, Any]], user_text: str) -> list[types.Content]:
        """Converte lo storico grezzo di Firestore in oggetti tipizzati google.genai.types.Content."""
        contents: list[types.Content] = []

        for turn in history_dicts:
            role = turn.get("role")
            if not role:
                continue

            parts_raw = turn.get("parts", [])
            if not isinstance(parts_raw, list):
                parts_raw = [parts_raw]

            processed_parts: list[types.Part] = []
            for p in parts_raw:
                if not p:
                    continue
                if isinstance(p, str):
                    processed_parts.append(types.Part.from_text(text=p))
                elif isinstance(p, dict):
                    if "text" in p:
                        processed_parts.append(types.Part.from_text(text=p["text"]))
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

            if processed_parts:
                contents.append(types.Content(role=role, parts=processed_parts))

        # Aggiunge il messaggio corrente dell'utente
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=user_text)]))
        return contents

    def chat_omni_agent(self, chat_id: int | str, user_text: str, context_string: str) -> str:
        """Punto di ingresso per la chat: prepara la history ed esegue il loop MCP."""
        try:
            full_system_instruction = PROMPT_OMNI_AGENT.format(context_string=context_string)

            # Recuperiamo lo storico da Firestore
            _, history_dicts = db.get_chat_history(chat_id)
            contents = self._build_typed_contents(history_dicts, user_text)

            logger.info("🧠 [ANALYST] Avvio delegazione Omni-Agent via MCP per chat %s...", chat_id)
            bot_reply = self.mcp_bridge.execute_agent_loop(contents, full_system_instruction)

            if bot_reply:
                db.save_chat_interaction(chat_id, history_dicts, user_text, bot_reply)

            return bot_reply

        except Exception as e:
            logger.exception("💥 [CRITICAL] Errore durante l'esecuzione dell'Omni-Agent MCP: %s", e)
            return "C'è stata un'anomalia di connessione con Runalyze. Dammi un minuto e riproviamo."

    def extract_body_metrics_from_image(self, image_bytes: bytes) -> dict[str, Any] | None:
        """
        Estrattore OCR tramite Vision Engine.
        Passa i byte grezzi direttamente all'SDK senza decodifica PIL intermedia
        e forza l'output JSON strutturato nativo.
        """
        try:
            logger.info("🧠 [ANALYST] Invio screenshot bilancia a Gemini (%d bytes)...", len(image_bytes))
            image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")

            response = self.client.models.generate_content(
                model=self.model_id,
                contents=[PROMPT_OCR_BILANCIA, image_part],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1  # Bassa temperatura per massima precisione OCR numerica
                )
            )

            dati_corporei = json.loads(response.text.strip())
            logger.info("✅ [ANALYST] Metriche estratte con successo: %s", dati_corporei)
            return dati_corporei
        except Exception as e:
            logger.exception("❌ [ANALYST] Errore durante l'analisi ottica dell'immagine: %s", e)
            return None


analyst = RunningAnalyst()
