"""
Agent de venda usando LangGraph
"""

from typing import Annotated, Any, TypedDict

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from ...domain.repositories.conversation_repository import ConversationRepository
from ...infrastructure.a2a.stock_client import StockA2AClient


class AgentState(TypedDict):
    """Estado do agent - usa add_messages como reducer para acumular mensagens"""

    messages: Annotated[list[BaseMessage], add_messages]


class SalesAgent:
    """Agent de venda usando LangGraph"""

    def __init__(
        self,
        conversation_repository: ConversationRepository,
        stock_a2a_client: StockA2AClient,
        gemini_api_key: str,
        llm_model: str = "gemini-1.5-flash",
        temperature: float = 0.7,
    ):
        self.conversation_repository = conversation_repository
        self.stock_a2a_client = stock_a2a_client

        # Inicializar LLM Gemini
        self.llm = ChatGoogleGenerativeAI(
            model=llm_model, temperature=temperature, google_api_key=gemini_api_key
        )

        # Ferramentas serão carregadas assincronamente
        self.tools = []
        self.llm_with_tools = None
        self.tool_node = None
        self.graph = None

        # Flag para indicar se está inicializado
        self._initialized = False

    async def _initialize_tools(self):
        """Inicializa as ferramentas MCP e o grafo"""
        if self._initialized:
            return

        # Obter ferramentas do A2A client
        self.tools = self.stock_a2a_client.get_tools()

        if not self.tools:
            print(
                "⚠️  Nenhuma ferramenta A2A carregada. O agent funcionará sem ferramentas."
            )

        # Bind tools ao LLM
        self.llm_with_tools = (
            self.llm.bind_tools(self.tools) if self.tools else self.llm
        )

        # Criar ToolNode para executar ferramentas
        self.tool_node = ToolNode(self.tools) if self.tools else None

        # Criar o grafo do agent
        self.graph = self._create_graph()

        self._initialized = True

    def _create_graph(self) -> StateGraph:
        """Cria o grafo do agent usando LangGraph"""

        def should_continue(state: AgentState) -> str:
            """Decide se deve continuar ou terminar"""
            messages = state["messages"]
            last_message = messages[-1]

            # Se a última mensagem tem tool_calls, precisa executar ferramentas
            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                print(f"🔧 Executando {len(last_message.tool_calls)} ferramenta(s)...")
                for tool_call in last_message.tool_calls:
                    print(
                        f"   - {tool_call.get('name', 'unknown')}: {tool_call.get('args', {})}"
                    )
                return "tools"

            # Caso contrário, termina
            return END

        def call_model(state: AgentState) -> dict[str, Any]:
            """Chama o modelo LLM"""
            messages = state["messages"]
            # Debug: verificar mensagens
            print(f"\n🤖 call_model recebeu {len(messages)} mensagens:")
            for i, m in enumerate(messages):
                msg_type = type(m).__name__
                content_preview = ""
                if hasattr(m, "content") and m.content:
                    content_preview = str(m.content)[:1000]
                print(f"   [{i}] {msg_type}: {content_preview}...")

            if not messages:
                print("   ⚠️ Nenhuma mensagem para processar!")
                return {"messages": []}

            response = self.llm_with_tools.invoke(messages)
            return {"messages": [response]}

        # Criar o grafo
        workflow = StateGraph(AgentState)

        # Adicionar nó do agent
        workflow.add_node("agent", call_model)

        # Adicionar nó de ferramentas apenas se houver ferramentas
        if self.tool_node:
            workflow.add_node("tools", self.tool_node)

        # Definir ponto de entrada
        workflow.set_entry_point("agent")

        # Adicionar arestas condicionais
        if self.tool_node:
            workflow.add_conditional_edges(
                "agent", should_continue, {"tools": "tools", END: END}
            )
            # Após executar ferramentas, volta para o agent
            workflow.add_edge("tools", "agent")
        else:
            # Se não houver ferramentas, sempre termina após o agent
            workflow.add_edge("agent", END)

        # Compilar sem checkpointer para evitar estados corrompidos
        # O histórico é gerenciado pelo Redis
        return workflow.compile()

    async def process_message(
        self, trace_id: str, user_message: str, system_prompt: str = None
    ) -> "AsyncGenerator[str, None]":
        """
        Processa uma mensagem do usuário e retorna a resposta do agent em forma de stream

        Args:
            trace_id: ID único da conversa (número de celular com DDD)
            user_message: Mensagem do usuário
            system_prompt: Prompt do sistema (opcional)

        Returns:
            Um iterador assíncrono (AsyncGenerator) gerando a resposta
        """
        # Garantir que as ferramentas estão inicializadas
        await self._initialize_tools()

        # Buscar histórico da conversa do Redis
        conversation = await self.conversation_repository.get_by_trace_id(trace_id)

        # Construir mensagens para o agent
        messages = []

        # Adicionar prompt do sistema se fornecido
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        else:
            # Prompt padrão para agent de venda
            default_prompt = """Você é um assistente de vendas da Shopee.

###############################################################################
# REGRA OBRIGATÓRIA - VOCÊ DEVE SEGUIR ISSO SEMPRE:
###############################################################################

ANTES de responder ao usuário ou confirmar informações de estoque e produtos, você DEVE chamar o Agente de Estoque (ferramenta ask_stock_agent).
Você NÃO conhece o estoque nem os produtos diretamente. O Agente de Estoque sabe tudo sobre produtos. Se você listar produtos sem consultar o Agente de Estoque, estará MENTINDO.

QUANDO O CLIENTE MUDAR DE PRODUTO:
- Se pediu "luvas" e agora pede "tênis" → Consulte o Agente de Estoque de novo
- CADA PRODUTO DIFERENTE = NOVA CONSULTA AO AGENTE

###############################################################################
# FERRAMENTA PRINCIPAL:
###############################################################################

ask_stock_agent(query="O que o cliente precisa, ex: Quais as luvas de academia disponíveis em estoque? Qual o preço daquele perfume?")

###############################################################################
# FORMATO DE RESPOSTA:
###############################################################################

Mantenha as respostas amigáveis e baseadas exclusivamente no que o Agente de Estoque retornar.
Formate bem a listagem de produtos com:
   [PRODUTO]
   nome: ...
   preco: R$ ...
   descricao: ...
   categoria: ...
   imagem: https://...
   link: https://...
   [/PRODUTO]

###############################################################################
# LEMBRE-SE:
###############################################################################

- Responda em português brasileiro de forma amigável
- Se não entender o pedido, pergunte ao cliente
- NUNCA invente produtos - SEMPRE consulte o Agente de Estoque"""
            messages.append(SystemMessage(content=default_prompt))

        # Adicionar histórico de mensagens do Redis (apenas as últimas para não exceder contexto)
        if conversation:
            # Pegar apenas as últimas 20 mensagens para não exceder o contexto do LLM
            recent_messages = conversation.messages[-20:]
            for msg in recent_messages:
                if msg.role.value == "user":
                    messages.append(HumanMessage(content=msg.content))
                elif msg.role.value == "assistant":
                    messages.append(AIMessage(content=msg.content))

        # Adicionar nova mensagem do usuário
        messages.append(HumanMessage(content=user_message))

        # Config para o LangGraph (sem checkpointer, usamos Redis para histórico)
        config = {}

        # Configurar Langfuse se as credenciais estiverem disponíveis
        from ...config import get_settings

        settings = get_settings()

        if settings.langfuse_public_key and settings.langfuse_secret_key:
            import os

            # O SDK v3 do Langfuse lerá estas variáveis de ambiente por padrão
            os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse_public_key
            os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse_secret_key
            os.environ["LANGFUSE_HOST"] = settings.langfuse_host

            try:
                from langfuse import Langfuse
                from langfuse.langchain import CallbackHandler

                # Verifica as chaves usando o Cliente puro
                lf_client = Langfuse()
                if not lf_client.auth_check():
                    print(
                        "⚠️ Langfuse: Falha na autenticação. Verifique suas chaves e host."
                    )
                else:
                    # Gera um trace customizado válido e único por mensagem para agrupar Vendas + Estoque
                    current_trace_id = lf_client.create_trace_id()
                    print(
                        f"📊 Langfuse tracing ativado para sessão {trace_id} (Trace unificado: {current_trace_id[:8]}...)"
                    )

                    langfuse_handler = CallbackHandler(
                        trace_context={"trace_id": current_trace_id}
                    )
                    config["callbacks"] = [langfuse_handler]
                    config["metadata"] = {
                        "langfuse_session_id": trace_id,
                        "langfuse_user_id": trace_id,
                        "langfuse_trace_id": current_trace_id,  # Salva pra repassar via metadados p/ ferramentas
                    }
            except ImportError as e:
                print(f"⚠️ Langfuse não carregado ({e}). Execute: poetry add langfuse")

        # Executar o agent usando astream para ver o progresso
        # yieldando chunks para o websocket
        all_new_messages = []

        import asyncio

        final_content = ""

        try:
            # Utilizamos o astream_events do langchain para capturar pedaços da stream da AI em tempo real
            async for event in self.graph.astream_events(
                {"messages": messages}, config=config, version="v1"
            ):
                kind = event["event"]

                # Se for um pedacinho de stream do modelo de chat gerando a resposta final
                if kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    if hasattr(chunk, "content") and chunk.content:
                        content_piece = chunk.content
                        if isinstance(content_piece, str):
                            final_content += content_piece
                            yield content_piece

                # Registrar as mensagens consolidadas que os nós devolvem para guardar no banco
                elif kind == "on_chain_end" and event.get("name") in ["agent", "tools"]:
                    node_outputs = event["data"].get("output", {})
                    if isinstance(node_outputs, dict) and "messages" in node_outputs:
                        new_msgs = node_outputs["messages"]
                        if isinstance(new_msgs, list):
                            all_new_messages.extend(
                                [
                                    m
                                    for m in new_msgs
                                    if m.id not in [x.id for x in all_new_messages]
                                ]
                            )
                        else:
                            all_new_messages.append(new_msgs)

        except asyncio.TimeoutError:
            print("⚠️ Timeout ao processar mensagem (60s)")
        except Exception as e:
            print(f"❌ Erro ao processar stream: {e}")
            import traceback

            traceback.print_exc()

        if not final_content:
            final_content = "Desculpe, não consegui processar sua mensagem."

        # Salvar mensagens no histórico
        from datetime import datetime

        from ...domain.entities.message import Message, MessageRole

        # Salvar mensagem do usuário
        user_msg = Message(
            role=MessageRole.USER, content=user_message, timestamp=datetime.now()
        )
        await self.conversation_repository.add_message(trace_id, user_msg)

        # Salvar resposta do agent
        assistant_msg = Message(
            role=MessageRole.ASSISTANT, content=final_content, timestamp=datetime.now()
        )
        await self.conversation_repository.add_message(trace_id, assistant_msg)

        # Garantir flush no langfuse ao final
        try:
            if "callbacks" in config:
                for callback in config["callbacks"]:
                    if hasattr(callback, "flush"):
                        callback.flush()
        except Exception:
            pass
