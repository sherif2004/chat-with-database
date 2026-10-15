"""Phase 1, understand: check the input, look in the cache, find the
user's database and recent history, and decide what the user wants."""

import logging

from pydantic import ValidationError

from app.chat.common import (
    GREETING_MESSAGE,
    OFF_TOPIC_MESSAGE,
    UNSAFE_MESSAGE,
    get_connection,
    deps,
    message_state,
    record_usage,
)
from app.chat.errors import GuardrailError
from app.chat.history import get_recent_history
from app.chat.schemas import ChatResponse
from app.chat.state import GraphState
from app.chat.understand.input_guard import check_question
from app.chat.understand.intent import classify_intent
from app.databases.connection import DatabaseConnectionError, get_or_default
from app.shared.cache import get_cached_response

logger = logging.getLogger(__name__)

RECENT_HISTORY_LIMIT = 3


def connection_unreachable_message(error: DatabaseConnectionError) -> str:
    return f"Your connected database is unreachable: {error}"


def recent_history(
    session_id: str, conversation_id: int | None, limit: int = RECENT_HISTORY_LIMIT
) -> list[dict]:
    """Last few exchanges, oldest first, as {"question", "answer", "sql"}.

    `sql` (when the turn was a data question) is what actually lets a
    follow-up like "just for Iron Maiden" work: the model needs the prior
    query's joins and aggregations to adapt, not just the text summary of
    its result — the same reason few-shot examples carry SQL, not prose.
    """

    rows = get_recent_history(session_id, conversation_id, limit)

    turns = []

    for row in rows:
        result = row.response.get("result") or {}
        answer = result.get("answer") or result.get("message") or ""
        turns.append({
            "question": row.question,
            "answer": answer,
            "sql": row.response.get("sql"),
        })

    return turns


def input_guard_node(state: GraphState, config) -> dict:

    timings, _debug, _bg = deps(config)

    try:
        with timings.step("input_guard"):
            question = check_question(state["raw_question"])
    except GuardrailError as e:
        return {"question": state["raw_question"], **message_state("unsafe", str(e))}

    return {"question": question}


def cache_lookup_node(state: GraphState, config) -> dict:

    timings, _debug, _bg = deps(config)

    if state.get("skip_cache"):
        return {"cache_hit": False}

    with timings.step("cache_lookup"):
        cached = get_cached_response(state["session_id"], state["question"])

    if cached is None:
        return {"cache_hit": False}

    try:
        cached_response = ChatResponse.model_validate(cached)
    except ValidationError:
        logger.warning("Skipping unparseable cached response for session %s", state["session_id"])
        return {"cache_hit": False}

    return {"cache_hit": True, "cached_response": cached_response}


def resolve_connection_node(state: GraphState, config) -> dict:

    timings, _debug, _bg = deps(config)

    try:
        with timings.step("resolve_connection"):
            connection = get_or_default(state["session_id"])
    except DatabaseConnectionError as e:
        return message_state("connection_error", connection_unreachable_message(e))

    config["configurable"]["session_data"]["connection"] = connection
    return {}


def load_history_node(state: GraphState, config) -> dict:
    """Independent of `resolve_connection` (both only need session_id), so
    the graph runs them as parallel branches that join before routing."""

    timings, _debug, _bg = deps(config)

    with timings.step("load_history"):
        history = recent_history(state["session_id"], state.get("conversation_id"))

    return {"history": history}


def route_after_context_node(state: GraphState, config) -> dict:
    """Join point for the resolve_connection / load_history fan-out — no
    work of its own, just a place for both branches to converge before
    classify_intent."""
    return {}


def classify_intent_node(state: GraphState, config) -> dict:

    timings, debug, _bg = deps(config)

    with timings.step("router"):
        decision, prompt, usage = classify_intent(
            state["question"],
            get_connection(config).schema_text,
            state.get("history"),
            can_write=state.get("can_write", False) and get_connection(config).dialect.supports_writes,
        )
    debug.prompts["router"] = prompt
    record_usage(debug, "router", usage)

    if decision.intent == "greeting":
        return message_state("greeting", decision.reply or GREETING_MESSAGE)
    if decision.intent == "off_topic":
        return message_state("off_topic", decision.reply or OFF_TOPIC_MESSAGE)
    if decision.intent == "unsafe":
        return message_state("unsafe", decision.reply or UNSAFE_MESSAGE)

    if decision.intent == "data_change":
        # Only offered to roles with data:write, but never trust the model:
        # re-check here so a stray answer cannot open the write path.
        if not state.get("can_write") or not get_connection(config).dialect.supports_writes:
            return message_state("unsafe", UNSAFE_MESSAGE)
        return {"intent": "data_change"}

    return {"intent": "data_question"}
