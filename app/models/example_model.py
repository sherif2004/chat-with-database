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


class QdrantExampleStore:
    """Question -> verified SQL pairs, stored in Qdrant."""

    def __init__(self, client: QdrantClient, collection: str):

        self.client = client
        self.collection = collection

        self.ready = False

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

        # Idempotent, so collections created before question_key existed get the index too.
        for field in ("question_key", "sql_key"):
            self.client.create_payload_index(
                self.collection, field, PayloadSchemaType.KEYWORD
            )

        stored = self.client.get_collection(self.collection).config.params.vectors.size

        if stored != dimensions:
            raise ValueError(
                f"Collection {self.collection} stores {stored}-dimensional vectors "
                f"but the embedding model returns {dimensions}. Delete the "
                f"collection to rebuild it for the new model."
            )

        self.ready = True

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
        """Remember a pair. Returns False if the question or SQL is already stored.

        The SQL check is deliberate: many phrasings of one query would
        otherwise fill the few-shot prompt with near-identical examples.
        """

        question_key = normalize_text(question)
        sql_key = normalize_text(sql)

        already_stored = self.client.count(
            self.collection,
            count_filter=Filter(should=[
                FieldCondition(key="question_key", match=MatchValue(value=question_key)),
                FieldCondition(key="sql_key", match=MatchValue(value=sql_key)),
            ]),
            exact=True
        ).count

        if already_stored:
            return False

        self.client.upsert(
            self.collection,
            points=[PointStruct(
                id=str(uuid.uuid4()),
                vector=list(vector),
                payload={
                    "question": question,
                    "sql": sql,
                    "question_key": question_key,
                    "sql_key": sql_key,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )]
        )

        return True

    def count(self) -> int:

        return self.client.count(self.collection, exact=True).count
