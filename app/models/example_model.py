import uuid
from datetime import datetime, timezone

from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from app.utils import normalize_text

# Qdrant needs an upper bound on results. Similarity threshold decides which
# examples qualify; this only guards against an unusually crowded neighbourhood.
MAX_RESULTS = 20


class Example(BaseModel):
    question: str
    sql: str


class SimilarExample(BaseModel):
    example: Example
    score: float


def _point_id(question_key: str) -> str:
    """Same question, same id, so a question can only be stored once."""

    return str(uuid.uuid5(uuid.NAMESPACE_URL, question_key))


# ============================================================
# Example store: question -> verified SQL pairs in Qdrant
# ============================================================

class QdrantExampleStore:

    def __init__(self, client: QdrantClient, collection: str):

        self.client = client
        self.collection = collection

        self.ready = False

    # -------------------------
    # Setup
    # -------------------------

    def setup(self, dimensions: int) -> None:
        """Create the collection if missing.

        `dimensions` is the size of the embedding model's vectors. If the
        collection already exists with a different size (the model was
        changed), this raises instead of touching the stored data.
        """

        if not self.client.collection_exists(self.collection):

            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=dimensions, distance=Distance.COSINE)
            )

            self.client.create_payload_index(
                self.collection, "sql_key", PayloadSchemaType.KEYWORD
            )

        stored = self.client.get_collection(self.collection).config.params.vectors.size

        if stored != dimensions:
            raise ValueError(
                f"Collection {self.collection} stores {stored}-dimensional vectors "
                f"but the embedding model returns {dimensions}. Delete the "
                f"collection to rebuild it for the new model."
            )

        self.ready = True

    # -------------------------
    # Search / add
    # -------------------------

    def search(self, vector, min_score: float) -> list[SimilarExample]:
        """Every stored example at least `min_score` similar, best first."""

        response = self.client.query_points(
            collection_name=self.collection,
            query=vector,
            score_threshold=min_score,
            limit=MAX_RESULTS,
            with_payload=True
        )

        return [
            SimilarExample(
                example=Example(
                    question=point.payload["question"],
                    sql=point.payload["sql"]
                ),
                score=point.score
            )
            for point in response.points
        ]

    def add(self, question: str, sql: str, vector) -> bool:
        """Remember a pair. Returns False if the question or SQL is already stored."""

        question_key = normalize_text(question)
        sql_key = normalize_text(sql)
        point_id = _point_id(question_key)

        if self.client.retrieve(self.collection, ids=[point_id]):
            return False

        same_sql = self.client.count(
            self.collection,
            count_filter=Filter(must=[
                FieldCondition(key="sql_key", match=MatchValue(value=sql_key))
            ]),
            exact=True
        ).count

        if same_sql:
            return False

        self.client.upsert(
            self.collection,
            points=[PointStruct(
                id=point_id,
                vector=list(vector),
                payload={
                    "question": question,
                    "sql": sql,
                    "sql_key": sql_key,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )]
        )

        return True

    def count(self) -> int:

        return self.client.count(self.collection, exact=True).count
