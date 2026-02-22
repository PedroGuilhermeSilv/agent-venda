"""
Configuração da aplicação com validação de variáveis de ambiente
"""


from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações da aplicação com validação"""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # Gemini Configuration
    gemini_api_key: str = Field(..., description="API Key do Google Gemini", min_length=1)
    llm_model: str = Field(default="gemini-1.5-flash", description="Modelo do LLM (Gemini)")
    llm_temperature: float = Field(
        default=0.7, ge=0.0, le=2.0, description="Temperatura do LLM (0.0 a 2.0)"
    )

    # Redis Configuration
    redis_url: str = Field(default="redis://localhost:6379", description="URL de conexão do Redis")

    # A2A Stock Agent Server
    a2a_stock_agent_url: str = Field(
        default="http://localhost:8003", description="URL do servidor A2A Agent Estoque"
    )

    # Server Configuration
    host: str = Field(default="0.0.0.0", description="Host do servidor")
    port: int = Field(default=8000, ge=1, le=65535, description="Porta do servidor (1-65535)")

    @field_validator("gemini_api_key")
    @classmethod
    def validate_gemini_api_key(cls, v: str) -> str:
        """Valida se a API key do Gemini foi fornecida"""
        if not v or v.strip() == "":
            raise ValueError("GEMINI_API_KEY é obrigatória")
        return v.strip()

    @field_validator("a2a_stock_agent_url")
    @classmethod
    def validate_a2a_url(cls, v: str) -> str:
        """Valida formato da URL do servidor A2A"""
        if not v.startswith(("http://", "https://")):
            raise ValueError("A2A_STOCK_AGENT_URL deve começar com http:// ou https://")
        return v.rstrip("/")

    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, v: str) -> str:
        """Valida formato da URL do Redis"""
        if not v.startswith(("redis://", "rediss://")):
            raise ValueError("REDIS_URL deve começar com redis:// ou rediss://")
        return v


# Instância global de configuração
_settings: Settings | None = None


def get_settings() -> Settings:
    """Obtém a instância de configuração (singleton)"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
