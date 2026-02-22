import json

import redis.asyncio as redis

from ...domain.entities.conversation import Conversation
from ...domain.entities.message import Message
from ...domain.repositories.conversation_repository import ConversationRepository


class RedisConversationRepository(ConversationRepository):
    """Implementação do repositório de conversas usando Redis"""

    def __init__(self, redis_client: redis.Redis, key_prefix: str = "conversation:"):
        self.redis = redis_client
        self.key_prefix = key_prefix

    def _get_key(self, trace_id: str) -> str:
        """Gera a chave Redis para uma conversa"""
        return f"{self.key_prefix}{trace_id}"

    async def get_by_trace_id(self, trace_id: str) -> Conversation | None:
        """Busca uma conversa pelo trace_id"""
        key = self._get_key(trace_id)
        data = await self.redis.get(key)

        if not data:
            return None

        conversation_data = json.loads(data)
        return Conversation.from_dict(conversation_data)

    async def save(self, conversation: Conversation) -> None:
        """Salva ou atualiza uma conversa"""
        key = self._get_key(conversation.trace_id)
        data = json.dumps(conversation.to_dict())
        await self.redis.set(key, data)

    async def add_message(self, trace_id: str, message: Message) -> None:
        """Adiciona uma mensagem à conversa"""
        conversation = await self.get_by_trace_id(trace_id)

        if not conversation:
            conversation = Conversation(trace_id=trace_id)

        conversation.add_message(message)
        await self.save(conversation)
