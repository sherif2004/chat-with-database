from typing import Any, TypedDict

from app.databases.query import QueryResult
from app.chat.generate.examples import SimilarExample
from app.chat.schemas import ChatResponse, Result


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
    conversation_id: int | None
    skip_cache: bool
    can_write: bool
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


def deps(config):
    cfg = config["configurable"]
    return cfg["timings"], cfg["debug"], cfg["background_tasks"]


def get_connection(config):
    """The resolved SessionConnection, held in a plain mutable dict on
    `config` rather than in graph state: it wraps a live SQLAlchemy engine,
    which doesn't belong in state alongside plain data — it's re-resolved
    (cheaply, from a cache) every turn anyway."""
    return config["configurable"]["session_data"].get("connection")
