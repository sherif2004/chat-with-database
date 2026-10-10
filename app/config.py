from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    azure_openai_api_key: str
    azure_openai_endpoint: str
    azure_openai_deployment: str
    azure_openai_deployment_light: str
    azure_openai_api_version: str = "2025-03-01-preview"
    llm_timeout_seconds: float = 30

    azure_openai_embedding_deployment: str

    database_url: str

    max_question_length: int = 500
    max_rows: int = 100
    statement_timeout_ms: int = 10000

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "chat_examples"
    few_shot_min_score: float = 0.6

    # Signs nothing; used to derive the key that encrypts saved database URLs
    # at rest. Generate one with: python -c "import secrets; print(secrets.token_urlsafe(48))"
    app_secret_key: str | None = None
    session_ttl_days: int = 14
    cookie_secure: bool = False
    cors_origins: str = "http://localhost:5173"

    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 3600


settings = Settings()
