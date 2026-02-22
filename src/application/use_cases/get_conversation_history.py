"""
Caso de uso: Obter histórico de conversa
"""


from ...domain.entities.conversation import Conversation
from ...domain.repositories.conversation_repository import ConversationRepository


class GetConversationHistoryUseCase:
    """Caso de uso para obter histórico de conversa"""

    def __init__(self, conversation_repository: ConversationRepository):
        self.conversation_repository = conversation_repository

    async def execute(self, trace_id: str) -> Conversation | None:
        """
        Executa o caso de uso

        Args:
            trace_id: ID único da conversa (número de celular com DDD)

        Returns:
            Conversa com histórico de mensagens ou None se não existir
        """
        return await self.conversation_repository.get_by_trace_id(trace_id)
