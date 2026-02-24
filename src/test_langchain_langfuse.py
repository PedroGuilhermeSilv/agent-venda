import os
import asyncio
from dotenv import load_dotenv

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langfuse.callback import CallbackHandler
from config import get_settings

load_dotenv()
settings = get_settings()

langfuse_handler = CallbackHandler(
    public_key=settings.langfuse_public_key,
    secret_key=settings.langfuse_secret_key,
    host=settings.langfuse_host
)

llm = ChatGoogleGenerativeAI(
    model=settings.llm_model, 
    temperature=settings.llm_temperature, 
    google_api_key=settings.gemini_api_key
)

async def test():
    print(f"Testando langchain com Config Langfuse:")
    print(f"Host: {settings.langfuse_host}")
    msg = [HumanMessage(content="Diga o numero 1234. Apenas isso.")]
    res = await llm.ainvoke(msg, config={"callbacks": [langfuse_handler]})
    print("Resposta do LLM:", res.content)
    langfuse_handler.flush()
    print("Teste finalizado.")

asyncio.run(test())
