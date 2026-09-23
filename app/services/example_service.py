import logging

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from app.config import settings
from app.models.example_model import QdrantExampleStore, SimilarExample
from app.services.embedding_service import EmbeddingUnavailable, embed_texts

logger = logging.getLogger(__name__)

# Qdrant errors that mean "the example store is unreachable or unhappy".
STORE_ERRORS = (ResponseHandlingException, UnexpectedResponse)

store = QdrantExampleStore(
    client=QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key),
    collection=settings.qdrant_collection,
)


def load_examples():
    """Detect the embedding size and create the Qdrant collection if missing.

    The store starts empty and fills up from the questions asked in the chat.
    """

    try:
        # The vector size comes from the model itself, so it never has to be configured.
        store.setup(len(embed_texts(["dimension probe"])[0]))

    except (EmbeddingUnavailable, *STORE_ERRORS, ValueError) as e:
        logger.warning("Few-shot examples are off: %s", e)
        return

    logger.info("Few-shot examples ready (%d stored).", store.count())


def find_similar(question):
    """Return (similar examples, question vector). Vector is None when off."""

    if not store.ready:
        return [], None

    try:
        vector = embed_texts([question])[0]
        examples: list[SimilarExample] = store.search(
            vector,
            settings.few_shot_min_score
        )
    except (EmbeddingUnavailable, *STORE_ERRORS) as e:
        logger.warning("Example retrieval skipped: %s", e)
        return [], None

    return examples, vector


def remember(question, sql, vector=None) -> bool:
    """Save a verified pair. Never lets a storage problem break an answer.

    `vector` is the question's embedding, if already computed (the normal
    workflow computes one for few-shot retrieval and can reuse it here).
    When it's not available — e.g. a workflow that skips retrieval — this
    embeds the question itself. Either way this runs as a background task,
    so the extra embedding call never adds latency to the response.
    """

    if vector is None:
        if not store.ready:
            return False

        try:
            vector = embed_texts([question])[0]
        except (EmbeddingUnavailable, *STORE_ERRORS) as e:
            logger.warning("Could not embed question to remember: %s", e)
            return False

    try:
        return store.add(question, sql, vector)
    except STORE_ERRORS as e:
        logger.warning("Could not save example: %s", e)
        return False
