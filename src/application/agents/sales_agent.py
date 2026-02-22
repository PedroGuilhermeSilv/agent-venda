"""
Agent de venda usando LangGraph
"""

from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
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
            print("⚠️  Nenhuma ferramenta A2A carregada. O agent funcionará sem ferramentas.")

        # Bind tools ao LLM
        self.llm_with_tools = self.llm.bind_tools(self.tools) if self.tools else self.llm

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
                    print(f"   - {tool_call.get('name', 'unknown')}: {tool_call.get('args', {})}")
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
            workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
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
    ) -> str:
        """
        Processa uma mensagem do usuário e retorna a resposta do agent

        Args:
            trace_id: ID único da conversa (número de celular com DDD)
            user_message: Mensagem do usuário
            system_prompt: Prompt do sistema (opcional)

        Returns:
            Resposta do agent
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

        # Executar o agent usando astream para ver o progresso
        # O LangGraph vai executar automaticamente as ferramentas quando necessário
        all_new_messages = []

        import asyncio

        async def process_stream():
            """Processa o stream do graph com logs detalhados"""
            async for event in self.graph.astream(
                {"messages": messages}, config=config, stream_mode="updates"
            ):
                # Acumular todas as atualizações de cada nó
                for node_name, node_data in event.items():
                    if "messages" in node_data:
                        new_msgs = node_data["messages"]
                        all_new_messages.extend(new_msgs)

                        # Log detalhado de cada mensagem do nó
                        print(f"\n📝 Node '{node_name}' retornou {len(new_msgs)} mensagem(ns):")
                        for msg in new_msgs:
                            if isinstance(msg, ToolMessage):
                                print(f"   🔧 ToolMessage ({msg.name}):")
                                content = msg.content
                                if isinstance(content, str):
                                    print(
                                        f"      📄 {content[:300]}{'...' if len(content) > 300 else ''}"
                                    )
                                else:
                                    import json

                                    content_str = json.dumps(content, indent=2, ensure_ascii=False)
                                    print(
                                        f"      📄 {content_str[:300]}{'...' if len(content_str) > 300 else ''}"
                                    )
                            elif isinstance(msg, AIMessage):
                                if hasattr(msg, "tool_calls") and msg.tool_calls:
                                    print(f"   🤖 AIMessage (com {len(msg.tool_calls)} tool_calls)")
                                    for tc in msg.tool_calls:
                                        print(f"      - {tc.get('name')}: {tc.get('args')}")
                                else:
                                    content_preview = (
                                        msg.content[:150] if msg.content else "(vazio)"
                                    )
                                    print(
                                        f"   🤖 AIMessage: {content_preview}{'...' if len(msg.content or '') > 150 else ''}"
                                    )

        try:
            # Timeout de 60 segundos para evitar travamento
            await asyncio.wait_for(process_stream(), timeout=60.0)
        except asyncio.TimeoutError:
            print("⚠️ Timeout ao processar mensagem (60s)")
        except Exception as e:
            print(f"❌ Erro ao processar stream: {e}")
            import traceback

            traceback.print_exc()

        # Combinar mensagens originais com as novas
        final_messages = messages + all_new_messages

        print(f"\n{'='*60}")
        print(
            f"📊 Resumo: {len(messages)} msgs originais + {len(all_new_messages)} novas = {len(final_messages)} total"
        )
        print(f"{'='*60}")

        # Obter resposta do agent (última mensagem do assistente que não seja tool call)
        ai_response = None

        for msg in reversed(final_messages):
            # Verificar se é uma mensagem de ferramenta (resultado de tool execution)
            if isinstance(msg, ToolMessage):
                continue

            # Verificar se é uma mensagem do assistente com conteúdo
            if isinstance(msg, AIMessage):
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    # Esta mensagem tem tool_calls, mas não é a resposta final
                    continue
                if msg.content and msg.content.strip():
                    ai_response = msg.content
                    print(f"💬 Resposta final selecionada: {len(ai_response)} caracteres")
                    break

        # Se ainda não encontrou resposta, pegar qualquer mensagem do assistente
        if not ai_response:
            for msg in reversed(final_messages):
                if isinstance(msg, AIMessage) and msg.content:
                    ai_response = msg.content
                    break

        if not ai_response:
            ai_response = "Desculpe, não consegui processar sua mensagem."

        # Salvar mensagens no histórico
        from datetime import datetime

        from ...domain.entities.message import Message, MessageRole

        # Salvar mensagem do usuário
        user_msg = Message(role=MessageRole.USER, content=user_message, timestamp=datetime.now())
        await self.conversation_repository.add_message(trace_id, user_msg)

        # Salvar resposta do agent
        assistant_msg = Message(
            role=MessageRole.ASSISTANT, content=ai_response, timestamp=datetime.now()
        )
        await self.conversation_repository.add_message(trace_id, assistant_msg)

        return ai_response
