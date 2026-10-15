import logging
import threading
from typing import Any

import google.genai.types as types
import httpx

logger = logging.getLogger(__name__)


class RunalyzeMCPBridge:
    MAX_TOOL_OUTPUT_CHARS = 15000
    MAX_AGENT_TURNS = 6  # Previene loop infiniti di tool-calling

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

        # Client HTTP persistente (Connection Pooling Keep-Alive)
        self._http_client = httpx.Client(
            headers=self.base_headers,
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )

        # Cache per Session ID e catalogo Tools Gemini (evita 2 round-trip HTTP per messaggio)
        self._session_id: str | None = None
        self._cached_gemini_tools: list[types.Tool] | None = None
        self._lock = threading.Lock()

    def _init_session_and_tools(self, force_refresh: bool = False) -> tuple[str, list[types.Tool] | None]:
        """Negozia la sessione MCP e mette in cache la mappatura dei tool Gemini."""
        with self._lock:
            if not force_refresh and self._session_id and self._cached_gemini_tools is not None:
                return self._session_id, self._cached_gemini_tools

            # 1. Handshake iniziale
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

            # 2. Scarica e mappa i tool solo se non sono già in cache
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
                logger.info("🧰 [MCP-Bridge] %d tool MCP caricati e salvati in cache.", len(mcp_tools))

            return self._session_id, self._cached_gemini_tools

    @staticmethod
    def _map_mcp_to_gemini(mcp_tools_list: list[dict[str, Any]]) -> list[types.Tool] | None:
        """Mappa il catalogo JSON di Runalyze nei Tools dell'SDK Gemini."""
        gemini_funcs = []
        for t in mcp_tools_list:
            props = {}
            input_schema = t.get("inputSchema", {})

            for p_name, p_val in input_schema.get("properties", {}).items():
                schema_type = p_val.get("type", "string").upper()
                schema_args: dict[str, Any] = {
                    "type": schema_type,
                    "description": p_val.get("description", "")
                }

                if schema_type == "ARRAY" and "items" in p_val:
                    item_type = p_val["items"].get("type", "string").upper()
                    schema_args["items"] = types.Schema(type=item_type)

                props[p_name] = types.Schema(**schema_args)

            gemini_funcs.append(types.FunctionDeclaration(
                name=t.get("name"),
                description=t.get("description", ""),
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

        # Se la sessione MCP su Runalyze è scaduta, rinegozia una sola volta in modo trasparente
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
        """Esegue il loop agente riutilizzando sessione e tool cachati."""
        session_id, gemini_tools = self._init_session_and_tools()

        gen_config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.7,
            tools=gemini_tools
        )

        logger.info("🧠 [MCP-HTTP] Invio contesto iniziale a Gemini...")
        response = self.gemini_client.models.generate_content(
            model=self.model_id,
            contents=contents,
            config=gen_config
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

            # NOTA CRITICA SDK GEMINI: Le risposte delle funzioni richiedono role="user" (non "tool")
            contents.append(types.Content(role="user", parts=tool_parts))

            logger.info("🧠 [MCP-HTTP] Invio dati estratti a Gemini (Turno %d)...", turn_count)
            response = self.gemini_client.models.generate_content(
                model=self.model_id,
                contents=contents,
                config=gen_config
            )

        logger.info("🎯 [MCP-HTTP] Elaborazione completata in %d turni tool.", turn_count)
        return response.text
