"""
Ponto de entrada da aplicação
"""

import redis.asyncio as redis
import uvicorn

from .application.agents.sales_agent import SalesAgent
from .application.use_cases.get_conversation_history import GetConversationHistoryUseCase
from .application.use_cases.send_message import SendMessageUseCase
from .config import get_settings
from .infrastructure.a2a.stock_client import StockA2AClient
from .infrastructure.repositories.redis_conversation_repository import RedisConversationRepository
from .presentation.websocket_server import WebSocketServer


async def create_app():
    """Cria e configura a aplicação"""

    # Carregar configurações validadas
    settings = get_settings()

    # Inicializar Redis
    redis_client = redis.from_url(settings.redis_url, decode_responses=False)

    # Criar repositórios
    conversation_repository = RedisConversationRepository(redis_client)

    # Criar cliente A2A para consultar o Agente de Estoque
    stock_a2a_client = StockA2AClient(a2a_server_url=settings.a2a_stock_agent_url)

    # Criar agent
    sales_agent = SalesAgent(
        conversation_repository=conversation_repository,
        stock_a2a_client=stock_a2a_client,
        gemini_api_key=settings.gemini_api_key,
        llm_model=settings.llm_model,
        temperature=settings.llm_temperature,
    )

    # Criar casos de uso
    send_message_use_case = SendMessageUseCase(sales_agent)
    get_history_use_case = GetConversationHistoryUseCase(conversation_repository)

    # Criar servidor WebSocket
    websocket_server = WebSocketServer(
        send_message_use_case=send_message_use_case, get_history_use_case=get_history_use_case
    )

    return websocket_server.get_app()


async def main():
    """Função principal"""
    app = await create_app()
    settings = get_settings()

    config = uvicorn.Config(app=app, host=settings.host, port=settings.port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
