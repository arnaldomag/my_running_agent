# app/mcp_bridge.py
import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client
import google.genai.types as types

class RunalyzeMCPBridge:
    def __init__(self, token, gemini_client, model_id="gemini-3.5-flash"):
        self.url = "https://runalyze.com/mcp"
        # Runalyze di solito accetta il token direttamente nell'header 'token' 
        # (In alternativa, potresti dover usare: {"token": token})
        clean_token = token.strip() if token else ""
        self.headers = {"Authorization": f"Bearer {clean_token}"} 
        self.gemini_client = gemini_client
        self.model_id = model_id

    def _map_mcp_to_gemini(self, mcp_tools):
        """Traduce gli strumenti NoSQL di MCP nel formato accettato dall'SDK di Gemini"""
        gemini_funcs = []
        for t in mcp_tools.tools:
            props = {}
            for p_name, p_val in t.inputSchema.get("properties", {}).items():
                schema_type = p_val.get("type", "string").upper()
                props[p_name] = types.Schema(
                    type=schema_type,
                    description=p_val.get("description", "")
                )
            
            gemini_funcs.append(types.FunctionDeclaration(
                name=t.name,
                description=t.description,
                parameters=types.Schema(
                    type="OBJECT",
                    properties=props,
                    required=t.inputSchema.get("required", [])
                )
            ))
        
        return [types.Tool(function_declarations=gemini_funcs)] if gemini_funcs else None

    async def _run_async(self, contents, system_instruction):
        """Gestisce il loop vitale dell'Agente tramite connessione SSE"""
        async with sse_client(self.url, headers=self.headers) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                
                # 1. Leggiamo il "catalogo attrezzi" dinamico da Runalyze
                mcp_tools = await session.list_tools()
                gemini_tools = self._map_mcp_to_gemini(mcp_tools)
                
                # 2. Prepariamo Gemini dandogli accesso agli attrezzi
                gen_config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.7,
                    tools=gemini_tools
                )

                print("🧠 [MCP] Valutazione del contesto e intenti in corso...")
                response = self.gemini_client.models.generate_content(
                    model=self.model_id,
                    contents=contents,
                    config=gen_config
                )

                # 3. Function Calling: Gemini decide se e quali dati gli servono
                if response.function_calls:
                    # Salviamo la sua richiesta nel log della conversazione
                    contents.append(response.candidates[0].content)
                    
                    for call in response.function_calls:
                        print(f"⚙️ [MCP] Esecuzione tool autonomo su Runalyze: {call.name}")
                        
                        # Eseguiamo REALMENTE lo strumento sul server di Runalyze
                        mcp_result = await session.call_tool(call.name, arguments=call.args)
                        
                        # Compattiamo la risposta JSON e la passiamo a Gemini
                        tool_result_text = "\n".join([c.text for c in mcp_result.content])
                        
                        contents.append(
                            types.Content(
                                role="tool",
                                parts=[types.Part.from_function_response(
                                    name=call.name,
                                    response={"result": tool_result_text}
                                )]
                            )
                        )
                    
                    print("🧠 [MCP] Dati ricevuti dal server. Generazione della risposta per Telegram...")
                    # 4. Seconda chiamata: Gemini ha letto i dati e ora formula la risposta umana
                    final_response = self.gemini_client.models.generate_content(
                        model=self.model_id,
                        contents=contents,
                        config=gen_config
                    )
                    return final_response.text
                
                # Se l'utente ha solo salutato, risponde direttamente senza usare i tool
                return response.text

    def execute_agent_loop(self, contents, system_instruction):
        """Avvia il motore asincrono isolandolo all'interno del thread Flask"""
        return asyncio.run(self._run_async(contents, system_instruction))
