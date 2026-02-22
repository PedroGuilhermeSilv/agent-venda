"""
Caso de uso: Enviar mensagem ao agent
"""

from ...application.agents.sales_agent import SalesAgent


class SendMessageUseCase:
    """Caso de uso para enviar mensagem ao agent de venda"""

    def __init__(self, sales_agent: SalesAgent):
        self.sales_agent = sales_agent

    async def execute(self, trace_id: str, message: str, system_prompt: str = None) -> str:
        """
        Executa o caso de uso

        Args:
            trace_id: ID único da conversa (número de celular com DDD)
            message: Mensagem do usuário
            system_prompt: Prompt do sistema (opcional)

        Returns:
            Resposta do agent
        """
        return await self.sales_agent.process_message(trace_id, message, system_prompt)
