# 🛒 Agent de Venda - Shopee API

Bem-vindo à documentação do **Agent de Venda**. Este projeto consiste em um Agente Inteligente desenvolvido para atuar como um assistente de vendas simulado da Shopee. Ele atende os clientes através de um canal WebSocket, mantendo o histórico de mensagens, compreendendo as necessidades do usuário, e se comunicando com um **Agente de Estoque** primário usando o protocolo **A2A (Agent-To-Agent)** para consultar inventários em tempo real.

---

## 🏗️ Arquitetura e Bibliotecas

A aplicação utiliza conceitos fortes da **Clean Architecture** (Domain, Application, Infrastructure, Presentation) para separar responsabilidades.

As principais bibliotecas e ferramentas utilizadas são:

- **FastAPI**: Framwork web veloz, responsável por levantar o servidor e disponibilizar as conexões WebSocket (na porta `8000`).
- **Uvicorn**: Servidor ASGI que garante alta performance na execução do FastAPI.
- **LangChain / LangGraph**: Forma o "cérebro" principal do Agente. Orquestra a execução das LLMs, uso de ferramentas corporativas e gerencia o grafo de estados (as falas entre o assistente e o usuário).
- **Google GenAI (Gemini)**: O motor de inteligência artificial (LLM) que analisa as mensagens e gera textos extremamente complexos.
- **Google ADK (`a2a`)**: Pacote do *Agent Development Kit*, usado para fazer chamadas JSON-RPC rigorosas a outros assistentes baseados em IA. É ele que possibilita a conversa estruturada entre o *Agent de Venda* e o *Agent de Estoque*.
- **Redis (Redis Asyncio)**: Banco de dados em memória super rápido. Funciona como banco de "short-term memory", retendo e hidratando instantaneamente o histórico das conversas vinculado ao "trace_id" (o número do celular).
- **Pydantic / Pydantic Settings**: Responsável pela validação estrita de dados e coleta das variáveis de ambiente (`.env`).
- **Poetry**: Orquestrador das dependências e criação do ambiente virtual Python de forma isolada e rastreável.
- **Ruff**: Um linter em Rust, extremamente rigoroso, que garante as melhores práticas e limpeza total de código Python morto.

---

## 🗂️ Estrutura de Pastas e Código

O diretório principal reside em `src/`, dividido em:

### 1. `domain/` (Coração do Negócio)
Esta camada abriga as entidades puras e abstratas, sem nenhum conhecimento sobre bancos, roteadores ou APIs do mundo externo.
- **`entities/message.py`**: A representação individual de uma fala. Define se quem falou foi o "humano", a "IA" ou o "sistema".
- **`entities/conversation.py`**: Modela uma sessão de conversa inteira atrelada a um `trace_id`. Suporta agrupamentos e limites da janela de contexto.
- **`repositories/conversation_repository.py`**: Um contrato (Interface) exigindo como qualquer banco de dados que quiser salvar conversas neste sistema deverá se comportar (get, save).

### 2. `infrastructure/` (O Mundo Externo)
Aqui implementamos a sujeira: requisições HTTP, buscas em banco, conexões externas.
- **`repositories/redis_conversation_repository.py`**: Cumpre o contrato da `domain/`. Transforma os objetos `Conversation` em cache serializável e vice-versa, comunicando-se com o Redis local na porta 6379.
- **`a2a/stock_client.py`**: O arquivo essencial de integração com o Google ADK.
  - Ele se comunica com o Agente de Estoque através de um Proxy/Socket Web RPC (na porta `8003`).
  - O cliente mapeia essa porta externa do Estoque e *transforma essa habilidade numa "Tool" (Ferramenta) do Langchain*.
  - Ele escuta os metadados reativos com "streamings", desembrulha as tarefas respondidas por agentes ADK e retorna apenas o puro texto.

### 3. `application/` (Regras da Aplicação / Orquestração)
Orquestra o tráfego do domínio.
- **`agents/sales_agent.py`**: A espinha dorsal. Ele constrói o `StateGraph` da conversa no LangGraph. Injeta a memória persistente usando um *Checkpointer*, anexa a Tool (fabricada pelo nosso A2A Client) e passa ao modelo as regras supremas (o System Prompt). Sempre que receber uma mensagem, ele avaliará se deve processar ele próprio ou encaminhar uma busca à Ferramenta de Estoque.
- **`use_cases/`**: Os controladores da funcionalidade. O `send_message.py` aciona as chamadas do Agente, e o `get_conversation_history.py` interroga o Redis.

### 4. `presentation/` (Roteadores)
Interação direta com os inputs.
- **`websocket_server.py`**: Levanta as rotas `/ws/{trace_id}`. Ao ocorrer um ping via *WebSocket* de um celular ou Frontend, essa classe autentica a conexão, escuta as streams contínuas de resposta, e trafega os *Use Cases* devolvendo o histórico, os *prints* e o JSON final do LLM de cara com o front.
- `src/main.py`: Constrói todas as dependências do sistema por *Injeção de Dependências*, sobe os bancos de memória e empacota toda a vida do Uvicorn para voar.

---

## 🔄 Como Funciona o Fluxo Principal

1. **Início da Conexão**: O front-end (ou o seu script `make run` cliente de chat) dispara uma abertura de WebSocket ao servidor em `ws://localhost:8000/ws/11999999999`. A `presentation` pega o ID e restaura a conversa armazenada no Redis se houver.
2. **Recebimento e Disparo do Prompts**: Quando um usuário pergunta `"Quais luvas tem disponível?"`, o `SalesAgent` (`application`) cria o ciclo no grafo do LangGraph.
3. **Tomada de Decisão (Tool Call / A2A)**: Ao passar pelo nó do Gemini, a IA é instruída estritamente por seu mega System Prompt a **nunca mentir o estoque**. O nó central então nota que precisa acionar uma "Ferramenta" (A tool A2A do Stock Agent). O grafo é interrompido.
4. **Resolução e ADK**: O nó passa o texto ao `StockA2AClient` (`infrastructure`). Este cliente encapsula e adapta o conteúdo, roteia JSON-RPCs assíncronos para o seu A2A Stock Agent local (na `8003`). O Agente de Estoque varre todo seu próprio universo e responde!
5. **Apresentação e Continuidade**: O cliente de estoque captura e retorna o texto gerado de lá. O Langchain retoma o processamento incorporando a resposta do armazém da Shopee no modelo, formata um conteúdo cativante para o usuário de forma amigável e embala tudo.
6. **Output Pelo WebSocket**: Por fim a camada do FastAPI despacha a string de volta pela conexão para ser renderizada na tela do chat com o usuário.

---

## 🚀 Como Rodar o Venda Agent

1. Certifique-se de que o **Agente de Estoque** (`agent-estoque`) está rodando corretamente na porta definida (`8003`) com a devida chave da API Gemini nele.
2. Com Redis de pé no projeto, verifique o `.env` no `agent-venda`:
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   A2A_STOCK_AGENT_URL=http://localhost:8003
   ```
3. Rode `make run` para subir o servidor e inicializar todo o ciclo.

