from typing import Any, TypedDict

from app.models.query_model import QueryResult
from app.services.example_service import SimilarExample
from app.views.chat_view import ChatResponse, Result


class GraphState(TypedDict, total=False):
    """State threaded through the chat graph for one request.

    The resolved SessionConnection is deliberately NOT here: it wraps a
    live SQLAlchemy engine, which doesn't belong alongside plain data (a
    fresh turn just re-resolves it, cheaply, from connection_model's
    cache). It's threaded through `config["configurable"]["session_data"]`
    instead — see chat_graph._connection().
    """

    # Request identity
    session_id: str
    raw_question: str
    question: str

    # Cache short-circuit
    cache_hit: bool
    cached_response: ChatResponse

    # Session context
    history: list[dict]

    # Few-shot retrieval
    examples: list[SimilarExample]
    question_vector: Any

    # SQL generation / retry
    sql: str | None
    sql_error: str | None
    retry_count: int

    # Execution
    statements: list[str]
    queries: list[QueryResult]

    # Final answer
    answer: str | None

    # Terminal fields, set by whichever node ends the graph
    intent: str
    result: Result
