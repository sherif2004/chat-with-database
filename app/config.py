from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    azure_openai_api_key: str
    azure_openai_endpoint: str
    azure_openai_deployment: str

    azure_openai_embedding_deployment: str

    database_url: str

    # Guardrails / limits
    max_question_length: int = 500
    max_rows: int = 100
    statement_timeout_ms: int = 10000

    # Dynamic few-shot examples (stored in Qdrant)
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "chat_examples"
    few_shot_min_score: float = 0.7


settings = Settings()
