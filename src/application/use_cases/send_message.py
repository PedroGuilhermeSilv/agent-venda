"""
Caso de uso: Enviar mensagem ao agent
"""

from ...application.agents.sales_agent import SalesAgent


from typing import AsyncGenerator


class SendMessageUseCase:
    """Caso de uso para enviar mensagem ao agent de venda"""

    def __init__(self, sales_agent: SalesAgent):
        self.sales_agent = sales_agent

    async def execute(
        self, trace_id: str, message: str, system_prompt: str = None
    ) -> "AsyncGenerator[str, None]":
        """
        Executa o caso de uso
        Args:
            trace_id: ID único da conversa (número de celular com DDD)
            message: Mensagem do usuário
            system_prompt: Prompt do sistema (opcional)
        Returns:
            Resposta do agent (AsyncGenerator emitindo as pedaços da resposta)
        """
        async for chunk in self.sales_agent.process_message(
            trace_id, message, system_prompt
        ):
            yield chunk
