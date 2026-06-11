# app/mcp_bridge.py
import httpx
import google.genai.types as types

class RunalyzeMCPBridge:
    def __init__(self, token, gemini_client, model_id="gemini-3.5-flash"):
        self.url = "https://runalyze.com/mcp"
        self.token = token.strip() if token else ""
        self.gemini_client = gemini_client
        self.model_id = model_id
        
        # Header base stabili per l'autenticazione
        self.base_headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def _get_mcp_session(self, client):
        """Inizializza la sessione e recupera l'Mcp-Session-Id in tempo reale"""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "my-running-agent", "version": "1.0.0"}
            }
        }
        resp = client.post(self.url, json=payload)
        resp.raise_for_status()
        return resp.headers.get("Mcp-Session-Id")

    def _map_mcp_to_gemini(self, mcp_tools_list):
        """Mappa dinamicamente il catalogo JSON di Runalyze nei Tools dell'SDK Gemini"""
        gemini_funcs = []
        for t in mcp_tools_list:
            props = {}
            input_schema = t.get("inputSchema", {})
            
            for p_name, p_val in input_schema.get("properties", {}).items():
                schema_type = p_val.get("type", "string").upper()
                props[p_name] = types.Schema(
                    type=schema_type,
                    description=p_val.get("description", "")
                )
            
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

    def execute_agent_loop(self, contents, system_instruction):
        """Motore lineare sincrono: esegue l'handshake e lascia decidere a Gemini"""
        with httpx.Client(headers=self.base_headers, timeout=30.0) as client:
            
            # 1. Stretta di mano e recupero ID Sessione
            session_id = self._get_mcp_session(client)
            if not session_id:
                raise ValueError("Impossibile negoziare l'Mcp-Session-Id con Runalyze")
            
            # Iniettiamo l'ID sessione negli header del client per le chiamate successive
            client.headers["Mcp-Session-Id"] = session_id

            # 2. Recupero del catalogo degli strumenti aggiornato
            tools_payload = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
            tools_resp = client.post(self.url, json=tools_payload)
            tools_resp.raise_for_status()
            
            mcp_tools = tools_resp.json().get("result", {}).get("tools", [])
            gemini_tools = self._map_mcp_to_gemini(mcp_tools)

            # 3. Configurazione dell'Agent con le istruzioni e i Tool a disposizione
            gen_config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.7,
                tools=gemini_tools
            )

            print("🧠 [MCP-HTTP] Invio contesto a Gemini...")
            response = self.gemini_client.models.generate_content(
                model=self.model_id,
                contents=contents,
                config=gen_config
            )

            # 4. Se Gemini decide di chiamare uno o più strumenti di Runalyze
            if response.function_calls:
                contents.append(response.candidates[0].content)
                
                for call in response.function_calls:
                    print(f"⚙️ [MCP-HTTP] Gemini esegue autonomamente: {call.name}")
                    
                    # Chiamata RPC esplicita in POST per eseguire il tool richiesto
                    call_payload = {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {
                            "name": call.name,
                            "arguments": call.args
                        }
                    }
                    call_resp = client.post(self.url, json=call_payload)
                    call_resp.raise_for_status()
                    
                    # Compattiamo i dati testuali restituiti dal tool
                    tool_result = call_resp.json().get("result", {})
                    content_list = tool_result.get("content", [])
                    tool_result_text = "\n".join([c.get("text", "") for c in content_list if c.get("type") == "text"])
                    
                    # Rispediamo i dati grezzi a Gemini come storico del tool
                    contents.append(
                        types.Content(
                            role="tool",
                            parts=[types.Part.from_function_response(
                                name=call.name,
                                response={"result": tool_result_text}
                            )]
                        )
                    )
                
                print("🧠 [MCP-HTTP] Generazione della risposta finale con i dati di Runalyze...")
                final_response = self.gemini_client.models.generate_content(
                    model=self.model_id,
                    contents=contents,
                    config=gen_config
                )
                return final_response.text
            
            # Se l'utente ha fatto una domanda generica che non richiede dati atletici
            return response.text