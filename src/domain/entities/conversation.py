from dataclasses import dataclass, field
from datetime import datetime

from .message import Message


@dataclass
class Conversation:
    """Entidade de conversa do domínio"""

    trace_id: str  # Número de celular com DDD
    messages: list[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def add_message(self, message: Message):
        """Adiciona uma mensagem à conversa"""
        self.messages.append(message)
        self.updated_at = datetime.now()

    def to_dict(self) -> dict:
        """Converte a instância para dicionário"""
        return {
            "trace_id": self.trace_id,
            "messages": [msg.to_dict() for msg in self.messages],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Conversation":
        """Cria uma instância de Conversation a partir de um dicionário"""
        return cls(
            trace_id=data["trace_id"],
            messages=[Message.from_dict(msg) for msg in data.get("messages", [])],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )
