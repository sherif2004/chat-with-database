from openai import OpenAIError

from app.config import settings
from app.services.llm_service import client


class EmbeddingUnavailable(Exception):
    """The embedding call failed."""


def embed_texts(texts: list[str]) -> list[list[float]]:

    try:
        response = client.embeddings.create(
            model=settings.azure_openai_embedding_deployment,
            input=texts
        )

    except OpenAIError as e:
        raise EmbeddingUnavailable(str(e)) from e

    return [item.embedding for item in response.data]
