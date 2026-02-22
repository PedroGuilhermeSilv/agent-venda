"""
Cliente A2A para consultar o Agente de Estoque
"""


from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


class AskStockAgentArgs(BaseModel):
    """Argumentos para a ferramenta ask_stock_agent"""

    query: str = Field(
        ...,
        description="A pergunta clara e detalhada para o Agente de Estoque. Inclua o máximo de contexto sobre a intenção do usuário.",
    )


class StockA2AClient:
    """Cliente que se comunica com o Agente de Estoque via protocolo A2A"""

    def __init__(self, a2a_server_url: str):
        self.a2a_server_url = a2a_server_url.rstrip("/")

    def _create_tool(self) -> BaseTool:
        """Cria uma LangChain Tool para consultar o Agente de Estoque"""
        client_instance = self

        class AskStockAgentTool(BaseTool):
            name: str = "ask_stock_agent"
            description: str = (
                "Útil para consultar informações de estoque, buscar produtos na Shopee, ou saber mais sobre disponibilidade, preços e categorias."
            )
            args_schema: type[BaseModel] = AskStockAgentArgs

            def _run(self, query: str) -> str:
                raise NotImplementedError("Use a versão assíncrona _arun")

            async def _arun(self, query: str) -> str:
                return await client_instance.ask_agent(query)

        return AskStockAgentTool()

    def get_tools(self) -> list[BaseTool]:
        """Retorna as ferramentas para o Agent de Vendas"""
        return [self._create_tool()]

    async def ask_agent(self, query: str) -> str:
        """
        Envia uma mensagem para o Agente de Estoque via A2A.
        """
        print(f"🔌 Consultando Agente de Estoque: {query}")

        import httpx
        from a2a.client import ClientConfig, ClientFactory
        from a2a.client.helpers import create_text_message_object
        from a2a.types import Message

        try:
            config = ClientConfig(httpx_client=httpx.AsyncClient(timeout=120.0))
            client = await ClientFactory.connect(self.a2a_server_url, client_config=config)
            message = create_text_message_object("user", query)

            responses = []

            async for chunk in client.send_message(message):
                # O SDK A2A pode retornar uma tupla: (Task/Message, UpdateEvent)
                print("Chunks: ", chunk)
                item = chunk[0] if isinstance(chunk, tuple) else chunk

                # 1) If it's a simple Message chunk
                if isinstance(item, Message):
                    if getattr(item, "parts", None):
                        for part in item.parts:
                            if hasattr(part.root, "text"):
                                responses.append(part.root.text)

                # 2) If it's a Task chunk (with history or status stream)
                elif hasattr(item, "history") or hasattr(item, "status"):

                    # Sometimes final answer is just in the history of a completed Task
                    if hasattr(item, "history") and item.history:
                        for hist_msg in item.history:
                            if hasattr(hist_msg, "role") and getattr(hist_msg.role, "value", None) == "agent":
                                if getattr(hist_msg, "parts", None):
                                    for part in hist_msg.parts:
                                        if hasattr(part.root, "text"):
                                            responses.append(part.root.text)

                    # Or intermediate updates might be in status
                    if hasattr(item, "status") and item.status:
                        message_obj = item.status.message
                        if message_obj and getattr(message_obj, "parts", None):
                            for part in message_obj.parts:
                                if hasattr(part.root, "text"):
                                    responses.append(part.root.text)

            if responses:
                # Remove possible duplicates
                unique_responses = []
                for r in responses:
                    if r not in unique_responses:
                        unique_responses.append(r)
                return "\n".join(unique_responses).strip()

            return "O Agente de Estoque respondeu, mas não consegui extrair o texto."

        except Exception as e:
            print(f"❌ Erro ao consultar Agente de Estoque: {e}")
            return f"Desculpe, não consegui obter informações do estoque no momento. Erro: {e}"
