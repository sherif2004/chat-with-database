"""Small pieces every phase of the question pipeline shares."""

from app.chat.schemas import MessageResult
from app.chat.state import GraphState

GREETING_MESSAGE = (
    "Hello! Ask me a question about the data and I will look it up for you."
)
OFF_TOPIC_MESSAGE = "Your question is not related to the data."
UNSAFE_MESSAGE = "I can only answer read-only questions about the data."
CANNOT_ANSWER_MESSAGE = (
    "I couldn't answer that: the data doesn't contain the information "
    "needed for this question."
)
CANNOT_CHANGE_MESSAGE = (
    "I couldn't prepare that change: the data doesn't contain what it refers to."
)


def record_usage(debug, step, usage):
    if usage is not None:
        debug.token_usage[step] = usage


def message_state(intent: str, text: str) -> dict:
    return {"intent": intent, "result": MessageResult(message=text)}


def has_result(state: GraphState) -> str:
    return "end" if state.get("result") is not None else "next"


def deps(config):
    cfg = config["configurable"]
    return cfg["timings"], cfg["debug"], cfg["background_tasks"]


def get_connection(config):
    """The resolved SessionConnection, held in a plain mutable dict on
    `config` rather than in graph state: it wraps a live SQLAlchemy engine,
    which doesn't belong in state alongside plain data — it's re-resolved
    (cheaply, from a cache) every turn anyway."""
    return config["configurable"]["session_data"].get("connection")
