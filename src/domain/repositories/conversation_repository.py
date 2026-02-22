from abc import ABC, abstractmethod

from ..entities.conversation import Conversation


class ConversationRepository(ABC):
    """Interface do repositório de conversas"""

    @abstractmethod
    async def get_by_trace_id(self, trace_id: str) -> Conversation | None:
        """Busca uma conversa pelo trace_id"""
        pass

    @abstractmethod
    async def save(self, conversation: Conversation) -> None:
        """Salva ou atualiza uma conversa"""
        pass

    @abstractmethod
    async def add_message(self, trace_id: str, message) -> None:
        """Adiciona uma mensagem à conversa"""
        pass
