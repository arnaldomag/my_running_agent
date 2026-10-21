import logging
import threading
import time
from typing import Any

import google.genai.types as types
import httpx

logger = logging.getLogger(__name__)


class RunalyzeMCPBridge:
    MAX_TOOL_OUTPUT_CHARS = 15000
    MAX_AGENT_TURNS = 6
    MAX_DESC_LEN = 160  # Limita la lunghezza delle descrizioni schema per evitare 503 sul compilatore tool

    def __init__(self, token: str, gemini_client: Any, model_id: str = "gemini-3.5-flash"):
        self.url = "https://runalyze.com/mcp"
        self.token = token.strip() if token else ""
        self.gemini_client = gemini_client
        self.model_id = model_id

        mcp_token = self.token if self.token.startswith("pt#") else f"pt#{self.token}"
        logger.info("🔐 [MCP-Bridge] Token Runalyze configurato: %s***", mcp_token[:5])

        self.base_headers = {
            "Authorization": f"Bearer {mcp_token}",
            "Content-Type": "application/json"
        }

        self._http_client = httpx.Client(
            headers=self.base_headers,
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )

        self._session_id: str | None = None
        self._cached_gemini_tools: list[types.Tool] | None = None
        self._discovered_fallbacks: list[str] | None = None
        self._lock = threading.Lock()

    def _get_available_fallback_models(self) -> list[str]:
        """
        Interroga dinamicamente l'API di Google (una sola volta) per scoprire quali modelli
        sono realmente attivi sulla chiave dell'utente, evitando qualsiasi errore 404.
        """
        if self._discovered_fallbacks is not None:
            return self._discovered_fallbacks

        fallbacks = []
        try:
            for m in self.gemini_client.models.list():
                name = (m.name or "").removeprefix("models/")
                actions = m.supported_actions or []
                if (
                    "generateContent" in actions
                    and "gemini" in name
                    and name != self.model_id
                    and not any(x in name for x in ("embedding", "vision", "imagen", "tts", "audio", "1.5"))
                ):
                    fallbacks.append(name)

            # Ordiniamo dando priorità ai modelli 'lite' e 'flash' (più veloci e meno soggetti a 503)
            fallbacks.sort(key=lambda x: (0 if "lite" in x else (1 if "flash" in x else 2), x), reverse=False)
            logger.info("🔍 [MCP-Bridge] Modelli di fallback scoperti dinamicamente: %s", fallbacks[:4])
        except Exception as e:
            logger.warning("⚠️ [MCP-Bridge] Impossibile elencare i modelli dinamicamente: %s", e)
            fallbacks = ["gemini-3.8-flash"]

        self._discovered_fallbacks = fallbacks[:4]
        return self._discovered_fallbacks

    def _generate_resilient(
        self,
        contents: list[Any],
        config: types.GenerateContentConfig,
        preferred_model: str | None = None
    ) -> tuple[Any, str]:
        """
        Tenta sul modello primario (gemini-3.5-flash) disabilitando i retry lenti di tenacity,
        e in caso di 503 scala sui modelli attivi scoperti dinamicamente sull'account.
        """
        start_model = preferred_model or self.model_id
        dynamic_fallbacks = self._get_available_fallback_models()

        attempt_sequence = [start_model] + [m for m in dynamic_fallbacks if m != start_model]
        last_exception = None

        # Riduciamo a 2 i tentativi interni di tenacity per non bloccare il thread per 30s su un singolo 503
        fast_config = config.model_copy(
            update={"http_options": types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=2))}
        )

        for idx, target_model in enumerate(attempt_sequence):
            try:
                if idx > 0:
                    logger.warning(
                        "🔄 [MCP-HTTP] Switch su modello attivo '%s' (tentativo %d/%d)...",
                        target_model, idx + 1, len(attempt_sequence)
                    )
                resp = self.gemini_client.models.generate_content(
                    model=target_model,
                    contents=contents,
                    config=fast_config
                )
                return resp, target_model

            except Exception as err:
                last_exception = err
                err_str = str(err).upper()
                if any(code in err_str for code in ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "500", "404", "NOT_FOUND")):
                    logger.warning(
                        "⚠️ [MCP-HTTP] Modello '%s' ha restituito %s. Passo al successivo...",
                        target_model, err
                    )
                    time.sleep(1.0)
                    continue
                raise

        raise last_exception

    def _init_session_and_tools(self, force_refresh: bool = False) -> tuple[str, list[types.Tool] | None]:
        """Negozia la sessione MCP e mette in cache la mappatura snellita dei tool Gemini."""
        with self._lock:
            if not force_refresh and self._session_id and self._cached_gemini_tools is not None:
                return self._session_id, self._cached_gemini_tools

            init_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "my-running-agent", "version": "1.0.0"}
                }
            }
            resp = self._http_client.post(self.url, json=init_payload)
            resp.raise_for_status()
            session_id = resp.headers.get("Mcp-Session-Id")
            if not session_id:
                raise ValueError("Impossibile negoziare l'Mcp-Session-Id con Runalyze")

            self._session_id = session_id

            if self._cached_gemini_tools is None or force_refresh:
                tools_payload = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
                tools_resp = self._http_client.post(
                    self.url,
                    json=tools_payload,
                    headers={"Mcp-Session-Id": session_id}
                )
                tools_resp.raise_for_status()
                mcp_tools = tools_resp.json().get("result", {}).get("tools", [])
                self._cached_gemini_tools = self._map_mcp_to_gemini(mcp_tools)
                logger.info("🧰 [MCP-Bridge] %d tool MCP caricati, snelliti e salvati in cache.", len(mcp_tools))

            return self._session_id, self._cached_gemini_tools

    @classmethod
    def _short_desc(cls, text: str | None) -> str:
        """Accorcia le descrizioni JSON dello schema per alleggerire il payload dei tool."""
        if not text:
            return ""
        clean = " ".join(text.split())
        return clean[:cls.MAX_DESC_LEN] if len(clean) > cls.MAX_DESC_LEN else clean

    @classmethod
    def _map_mcp_to_gemini(cls, mcp_tools_list: list[dict[str, Any]]) -> list[types.Tool] | None:
        """Mappa e snellisce il catalogo JSON di Runalyze nei Tools dell'SDK Gemini."""
        gemini_funcs = []
        for t in mcp_tools_list:
            props = {}
            input_schema = t.get("inputSchema", {})

            for p_name, p_val in input_schema.get("properties", {}).items():
                schema_type = p_val.get("type", "string").upper()
                schema_args: dict[str, Any] = {
                    "type": schema_type,
                    "description": cls._short_desc(p_val.get("description", ""))
                }

                if schema_type == "ARRAY" and "items" in p_val:
                    item_type = p_val["items"].get("type", "string").upper()
                    schema_args["items"] = types.Schema(type=item_type)

                props[p_name] = types.Schema(**schema_args)

            gemini_funcs.append(types.FunctionDeclaration(
                name=t.get("name"),
                description=cls._short_desc(t.get("description", "")),
                parameters=types.Schema(
                    type="OBJECT",
                    properties=props,
                    required=input_schema.get("required", [])
                )
            ))

        return [types.Tool(function_declarations=gemini_funcs)] if gemini_funcs else None

    def _call_mcp_tool(self, session_id: str, name: str, args: dict[str, Any]) -> tuple[str, str]:
        """Esegue la chiamata RPC al tool gestendo il rinnovo automatico della sessione se scaduta."""
        call_payload = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": name, "arguments": args}
        }
        resp = self._http_client.post(
            self.url,
            json=call_payload,
            headers={"Mcp-Session-Id": session_id}
        )

        if resp.status_code in (400, 401, 403, 404):
            logger.info("🔄 [MCP-HTTP] Sessione MCP scaduta, rinegoziazione in corso...")
            session_id, _ = self._init_session_and_tools(force_refresh=True)
            resp = self._http_client.post(
                self.url,
                json=call_payload,
                headers={"Mcp-Session-Id": session_id}
            )

        resp.raise_for_status()
        tool_result = resp.json().get("result", {})
        content_list = tool_result.get("content", [])
        tool_result_text = "\n".join(c.get("text", "") for c in content_list if c.get("type") == "text")

        if len(tool_result_text) > self.MAX_TOOL_OUTPUT_CHARS:
            logger.warning(
                "⚠️ [MCP-HTTP] Payload troppo lungo (%d chars). Troncamento a %d...",
                len(tool_result_text),
                self.MAX_TOOL_OUTPUT_CHARS
            )
            tool_result_text = (
                tool_result_text[:self.MAX_TOOL_OUTPUT_CHARS]
                + "\n...[DATI TRONCATI PER LIMITE TOKEN. ANALIZZA SOLO I DATI RICEVUTI FINO A QUI]..."
            )

        return session_id, tool_result_text

    def execute_agent_loop(self, contents: list[Any], system_instruction: str) -> str:
        """Esegue il loop agente mantenendo lo stesso modello funzionante per tutti i turni del tool."""
        session_id, gemini_tools = self._init_session_and_tools()

        gen_config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.7,
            tools=gemini_tools
        )

        logger.info("🧠 [MCP-HTTP] Invio contesto iniziale a Gemini (%s)...", self.model_id)
        response, active_model = self._generate_resilient(
            contents=contents,
            config=gen_config,
            preferred_model=self.model_id
        )

        turn_count = 0
        while response.function_calls and turn_count < self.MAX_AGENT_TURNS:
            turn_count += 1
            contents.append(response.candidates[0].content)

            tool_parts = []
            for call in response.function_calls:
                logger.info("⚙️ [MCP-HTTP] Turno %d - Esecuzione tool: %s", turn_count, call.name)
                session_id, tool_result_text = self._call_mcp_tool(session_id, call.name, call.args)

                tool_parts.append(
                    types.Part.from_function_response(
                        name=call.name,
                        response={"result": tool_result_text}
                    )
                )

            contents.append(types.Content(role="user", parts=tool_parts))

            logger.info("🧠 [MCP-HTTP] Invio dati estratti a Gemini (Turno %d su %s)...", turn_count, active_model)
            response, active_model = self._generate_resilient(
                contents=contents,
                config=gen_config,
                preferred_model=active_model
            )

        logger.info("🎯 [MCP-HTTP] Elaborazione completata in %d turni tool con %s.", turn_count, active_model)
        return response.text
