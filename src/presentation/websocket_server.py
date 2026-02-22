"""
Servidor WebSocket para expor o agent de venda
"""

import json
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..application.use_cases.get_conversation_history import GetConversationHistoryUseCase
from ..application.use_cases.send_message import SendMessageUseCase


class WebSocketServer:
    """Servidor WebSocket para comunicação com o agent"""

    def __init__(
        self,
        send_message_use_case: SendMessageUseCase,
        get_history_use_case: GetConversationHistoryUseCase,
    ):
        self.send_message_use_case = send_message_use_case
        self.get_history_use_case = get_history_use_case
        self.app = FastAPI(title="Agent de Venda API")

        # Configurar CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # Em produção, especificar origens
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Registrar rotas estáticas primeiro
        self._register_static_routes()
        # Registrar rotas WebSocket depois
        self._register_routes()

    def _register_routes(self):
        """Registra as rotas do servidor"""

        @self.app.websocket("/ws/{trace_id}")
        async def websocket_endpoint(websocket: WebSocket, trace_id: str):
            """
            Endpoint WebSocket para comunicação com o agent

            Args:
                trace_id: Número de celular com DDD (ex: "11999999999")
            """
            await websocket.accept()

            try:
                # Enviar mensagem de boas-vindas
                await websocket.send_json(
                    {
                        "type": "welcome",
                        "message": "Conectado ao agent de venda! Como posso ajudar?",
                    }
                )

                # Enviar histórico se existir
                conversation = await self.get_history_use_case.execute(trace_id)
                if conversation and conversation.messages:
                    await websocket.send_json(
                        {
                            "type": "history",
                            "messages": [msg.to_dict() for msg in conversation.messages],
                        }
                    )

                # Loop principal para receber mensagens
                while True:
                    data = await websocket.receive_text()
                    message_data = json.loads(data)

                    message_type = message_data.get("type", "message")

                    if message_type == "message":
                        user_message = message_data.get("message", "")

                        if not user_message:
                            await websocket.send_json(
                                {"type": "error", "message": "Mensagem vazia"}
                            )
                            continue

                        # Enviar confirmação de recebimento
                        await websocket.send_json(
                            {"type": "processing", "message": "Processando sua mensagem..."}
                        )

                        # Processar mensagem com o agent
                        try:
                            system_prompt = message_data.get("system_prompt")
                            response = await self.send_message_use_case.execute(
                                trace_id=trace_id, message=user_message, system_prompt=system_prompt
                            )

                            # Enviar resposta
                            await websocket.send_json({"type": "response", "message": response})
                        except Exception as e:
                            await websocket.send_json(
                                {
                                    "type": "error",
                                    "message": f"Erro ao processar mensagem: {e!s}",
                                }
                            )

                    elif message_type == "get_history":
                        # Retornar histórico completo
                        conversation = await self.get_history_use_case.execute(trace_id)
                        if conversation:
                            await websocket.send_json(
                                {
                                    "type": "history",
                                    "messages": [msg.to_dict() for msg in conversation.messages],
                                }
                            )
                        else:
                            await websocket.send_json({"type": "history", "messages": []})

                    else:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": f"Tipo de mensagem desconhecido: {message_type}",
                            }
                        )

            except WebSocketDisconnect:
                print(f"Cliente desconectado: {trace_id}")
            except Exception as e:
                print(f"Erro na conexão WebSocket: {e}")
                try:
                    await websocket.send_json(
                        {"type": "error", "message": f"Erro interno: {e!s}"}
                    )
                except Exception:
                    pass

    def _register_static_routes(self):
        """Registra rotas para servir arquivos estáticos do frontend"""
        # Obter caminho do diretório frontend
        frontend_path = Path(__file__).parent.parent.parent.parent / "frontend"

        if frontend_path.exists():
            # Servir arquivos estáticos
            self.app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")

            # Rota raiz para servir index.html
            @self.app.get("/")
            async def serve_frontend():
                index_path = frontend_path / "index.html"
                if index_path.exists():
                    return FileResponse(str(index_path))
                return {"message": "Frontend não encontrado"}

        else:
            # Se frontend não existir, criar rota informativa
            @self.app.get("/")
            async def root():
                return {
                    "message": "Agent de Venda API",
                    "websocket": "/ws/{trace_id}",
                    "frontend": "Frontend não encontrado. Coloque os arquivos em ./frontend/",
                }

    def get_app(self) -> FastAPI:
        """Retorna a aplicação FastAPI"""
        return self.app
