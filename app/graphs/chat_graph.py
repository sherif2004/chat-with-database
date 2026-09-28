import logging

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from langgraph.graph import END, StateGraph

from app.graphs.chat_state import GraphState
from app.guardrails.errors import GuardrailError, UnknownTableError
from app.guardrails.input_guard import check_question
from app.guardrails.sql_guard import validate_sql
from app.models.connection_model import DatabaseConnectionError, get_or_default
from app.models.history_model import get_cached_response, get_recent_history
from app.models.query_model import execute_sql
from app.models.workflow_model import get_workflow
from app.services.example_service import find_similar, remember
from app.services.llm_service import generate_answer, generate_route_and_sql, generate_sql
from app.services.router_service import classify_intent
from app.views.chat_view import (
    ChatResponse,
    ExampleUsed,
    MessageResult,
    QueryTable,
    TableResult,
)

logger = logging.getLogger(__name__)

GREETING_MESSAGE = (
    "Hello! Ask me a question about the data and I will look it up for you."
)
OFF_TOPIC_MESSAGE = "Your question is not related to the data."
UNSAFE_MESSAGE = "I can only answer read-only questions about the data."
CANNOT_ANSWER_MESSAGE = (
    "I couldn't answer that: the data doesn't contain the information "
    "needed for this question."
)

RECENT_HISTORY_LIMIT = 3

# Total attempts allowed at generating+running SQL for one question (the
# first try plus retries once the database rejects the query).
SQL_MAX_ATTEMPTS = 3


def _connection_unreachable_message(error: DatabaseConnectionError) -> str:
    return f"Your connected database is unreachable: {error}"


def _record_usage(debug, step, usage):
    if usage is not None:
        debug.token_usage[step] = usage


def _message_state(intent: str, text: str) -> dict:
    return {"intent": intent, "result": MessageResult(message=text)}


def _has_result(state: GraphState) -> str:
    return "end" if state.get("result") is not None else "next"


def _deps(config):
    cfg = config["configurable"]
    return cfg["timings"], cfg["debug"], cfg["background_tasks"]


def _connection(config):
    """The resolved SessionConnection, held in a plain mutable dict on
    `config` rather than in graph state: it wraps a live SQLAlchemy engine,
    which can't be checkpointed (msgpack has no encoding for it), and
    doesn't need to be — it's re-resolved (cheaply, from a cache) every
    turn anyway."""
    return config["configurable"]["session_data"].get("connection")


def _recent_history(session_id: str, limit: int = RECENT_HISTORY_LIMIT) -> list[dict]:
    """Last few exchanges, oldest first, as {"question", "answer", "sql"}.

    `sql` (when the turn was a data question) is what actually lets a
    follow-up like "just for Iron Maiden" work: the model needs the prior
    query's joins and aggregations to adapt, not just the text summary of
    its result — the same reason few-shot examples carry SQL, not prose.
    """

    rows = get_recent_history(session_id, limit)

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


# --- Nodes ------------------------------------------------------------


def input_guard_node(state: GraphState, config) -> dict:

    timings, _debug, _bg = _deps(config)

    try:
        with timings.step("input_guard"):
            question = check_question(state["raw_question"])
    except GuardrailError as e:
        return {"question": state["raw_question"], **_message_state("unsafe", str(e))}

    return {"question": question}


def cache_lookup_node(state: GraphState, config) -> dict:

    timings, _debug, _bg = _deps(config)

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

    timings, _debug, _bg = _deps(config)

    try:
        with timings.step("resolve_connection"):
            connection = get_or_default(state["session_id"])
    except DatabaseConnectionError as e:
        return _message_state("connection_error", _connection_unreachable_message(e))

    config["configurable"]["session_data"]["connection"] = connection
    return {}


def load_workflow_node(state: GraphState, config) -> dict:
    """Reads the session's router/no_router preference. Session-id-only
    lookup — needs neither the resolved connection nor history, so it runs
    before the two are fanned out in parallel below."""

    _timings, debug, _bg = _deps(config)

    workflow = get_workflow(state["session_id"])
    debug.workflow = workflow

    return {"workflow": workflow}


def load_history_node(state: GraphState, config) -> dict:
    """Independent of `resolve_connection` (both only need session_id), so
    the graph runs them as parallel branches that join before routing."""

    timings, _debug, _bg = _deps(config)

    with timings.step("load_history"):
        history = _recent_history(state["session_id"])

    return {"history": history}


def route_after_context_node(state: GraphState, config) -> dict:
    """Join point for the resolve_connection / load_history fan-out — no
    work of its own, just a place for both branches to converge before the
    router/no_router split."""
    return {}


def classify_intent_node(state: GraphState, config) -> dict:

    timings, debug, _bg = _deps(config)

    with timings.step("router"):
        decision, prompt, usage = classify_intent(
            state["question"], _connection(config).schema_text, state.get("history")
        )
    debug.prompts["router"] = prompt
    _record_usage(debug, "router", usage)

    if decision.intent == "greeting":
        return _message_state("greeting", decision.reply or GREETING_MESSAGE)
    if decision.intent == "off_topic":
        return _message_state("off_topic", decision.reply or OFF_TOPIC_MESSAGE)
    if decision.intent == "unsafe":
        return _message_state("unsafe", decision.reply or UNSAFE_MESSAGE)

    return {"intent": "data_question"}


def retrieve_examples_node(state: GraphState, config) -> dict:

    timings, debug, _bg = _deps(config)

    with timings.step("retrieve_examples"):
        examples, question_vector = find_similar(state["question"])

    debug.examples = [
        ExampleUsed(question=e.example.question, sql=e.example.sql, score=e.score)
        for e in examples
    ]

    return {"examples": examples, "question_vector": question_vector}


def generate_sql_node(state: GraphState, config) -> dict:
    """Generates SQL for the question — the router workflow's plain SQL
    generation, or the no_router workflow's combined route+SQL call.

    Also the retry target: when `sql_error` is set (a previous statement
    was rejected by the database), that failure is fed back to the model
    so it can fix its own mistake instead of repeating it.
    """

    timings, debug, _bg = _deps(config)
    connection = _connection(config)

    previous_attempt = None
    if state.get("sql_error"):
        previous_attempt = {"sql": state.get("sql"), "error": state["sql_error"]}

    if state["workflow"] == "router":
        with timings.step("generate_sql"):
            generation = generate_sql(
                state["question"],
                connection.schema_text,
                state.get("examples"),
                state.get("history"),
                previous_attempt=previous_attempt,
            )
        debug.prompts["generate_sql"] = generation.prompt
        _record_usage(debug, "generate_sql", generation.usage)

        if generation.clarification_question:
            return _message_state("needs_clarification", generation.clarification_question)
        if not generation.can_answer:
            return _message_state("off_topic", generation.cannot_answer_message or CANNOT_ANSWER_MESSAGE)

        return {"sql": generation.sql, "intent": "data_question"}

    with timings.step("route_and_generate_sql"):
        generation = generate_route_and_sql(
            state["question"],
            connection.schema_text,
            state.get("examples"),
            state.get("history"),
            previous_attempt=previous_attempt,
        )
    debug.prompts["route_and_generate_sql"] = generation.prompt
    _record_usage(debug, "route_and_generate_sql", generation.usage)

    if generation.intent == "greeting":
        return _message_state("greeting", generation.reply or GREETING_MESSAGE)
    if generation.intent == "off_topic":
        return _message_state("off_topic", generation.reply or OFF_TOPIC_MESSAGE)
    if generation.intent == "unsafe":
        return _message_state("unsafe", generation.reply or UNSAFE_MESSAGE)
    if generation.intent == "cannot_answer":
        return _message_state("off_topic", generation.reply or CANNOT_ANSWER_MESSAGE)
    if generation.intent == "needs_clarification":
        return _message_state("needs_clarification", generation.reply or CANNOT_ANSWER_MESSAGE)

    return {"sql": generation.sql, "intent": "data_question"}


def validate_sql_node(state: GraphState, config) -> dict:

    timings, _debug, _bg = _deps(config)
    connection = _connection(config)

    try:
        with timings.step("sql_guard"):
            statements = validate_sql(state["sql"], connection.schema.table_names)
    except UnknownTableError:
        return _message_state("off_topic", CANNOT_ANSWER_MESSAGE)
    except GuardrailError as e:
        return _message_state("unsafe", f"{UNSAFE_MESSAGE} ({e})")

    return {"statements": statements}


def execute_sql_node(state: GraphState, config) -> dict:
    """Runs the validated statements. A database-level rejection (bad
    column, syntax slip the guard let through, ...) is caught here rather
    than left to propagate — it's what feeds the retry loop below."""

    timings, _debug, background_tasks = _deps(config)
    connection = _connection(config)
    statements = state["statements"]

    try:
        with timings.step("execute_sql"):
            queries = [execute_sql(stmt, connection.engine) for stmt in statements]
    except SQLAlchemyError as e:
        retry_count = state.get("retry_count", 0) + 1
        return {
            "sql_error": str(getattr(e, "orig", None) or e),
            "retry_count": retry_count,
        }

    # Learn from the chat (after the response is sent): the pair passed
    # the guard, ran, and returned rows. Only worth remembering as an
    # example when every statement actually returned something.
    if all(query.rows for query in queries):
        background_tasks.add_task(
            remember, state["question"], "; ".join(statements), state.get("question_vector")
        )

    return {"queries": queries, "sql_error": None}


def sql_failed_node(state: GraphState, config) -> dict:
    return _message_state("off_topic", CANNOT_ANSWER_MESSAGE)


def generate_answer_node(state: GraphState, config) -> dict:

    timings, debug, _bg = _deps(config)
    statements = state["statements"]
    queries = state["queries"]

    answer_inputs = [
        {"sql": stmt, "rows": [dict(zip(query.columns, row)) for row in query.rows]}
        for stmt, query in zip(statements, queries)
    ]

    with timings.step("generate_answer"):
        answer, prompt, usage = generate_answer(state["question"], answer_inputs)
    debug.prompts["generate_answer"] = prompt
    _record_usage(debug, "generate_answer", usage)

    result = TableResult(
        queries=[
            QueryTable(sql=stmt, **query.model_dump(exclude={"rows"}), rows=query.rows)
            for stmt, query in zip(statements, queries)
        ],
        answer=answer,
    )

    return {"intent": "data_question", "result": result, "answer": answer}


# --- Conditional edges --------------------------------------------------


def _route_after_cache(state: GraphState) -> str:
    return "hit" if state.get("cache_hit") else "miss"


def _route_after_context(state: GraphState) -> str:
    """After the resolve_connection / load_history join: a connection
    failure short-circuits to END regardless of load_history's outcome
    (load_history never fails); otherwise branch on workflow."""
    if state.get("result") is not None:
        return "error"
    return state["workflow"]


def _route_after_execute(state: GraphState) -> str:
    if state.get("sql_error"):
        return "retry" if state.get("retry_count", 0) < SQL_MAX_ATTEMPTS else "give_up"
    return "continue"


def build_chat_graph(checkpointer=None):
    """`checkpointer`, when given, makes the graph persist its state after
    every node — a crash mid-turn can then resume from the last completed
    step instead of restarting the whole question. Each call site is
    expected to invoke with a fresh `thread_id` per turn (see
    chat_controller.py): conversation continuity across turns is handled
    separately, by chat_history, not by reusing a checkpoint thread."""

    graph = StateGraph(GraphState)

    graph.add_node("input_guard", input_guard_node)
    graph.add_node("cache_lookup", cache_lookup_node)
    graph.add_node("load_workflow", load_workflow_node)
    graph.add_node("resolve_connection", resolve_connection_node)
    graph.add_node("load_history", load_history_node)
    graph.add_node("route_after_context", route_after_context_node)
    graph.add_node("classify_intent", classify_intent_node)
    graph.add_node("retrieve_examples", retrieve_examples_node)
    graph.add_node("generate_sql", generate_sql_node)
    graph.add_node("validate_sql", validate_sql_node)
    graph.add_node("execute_sql", execute_sql_node)
    graph.add_node("sql_failed", sql_failed_node)
    graph.add_node("generate_answer", generate_answer_node)

    graph.set_entry_point("input_guard")

    graph.add_conditional_edges("input_guard", _has_result, {"end": END, "next": "cache_lookup"})
    graph.add_conditional_edges("cache_lookup", _route_after_cache, {"hit": END, "miss": "load_workflow"})

    # resolve_connection and load_history are independent (both need only
    # session_id) so they run as parallel branches, joining at
    # route_after_context before the router/no_router split.
    graph.add_edge("load_workflow", "resolve_connection")
    graph.add_edge("load_workflow", "load_history")
    graph.add_edge("resolve_connection", "route_after_context")
    graph.add_edge("load_history", "route_after_context")

    graph.add_conditional_edges(
        "route_after_context",
        _route_after_context,
        {"error": END, "router": "classify_intent", "no_router": "retrieve_examples"},
    )
    graph.add_conditional_edges("classify_intent", _has_result, {"end": END, "next": "retrieve_examples"})
    graph.add_edge("retrieve_examples", "generate_sql")
    graph.add_conditional_edges("generate_sql", _has_result, {"end": END, "next": "validate_sql"})
    graph.add_conditional_edges("validate_sql", _has_result, {"end": END, "next": "execute_sql"})
    graph.add_conditional_edges(
        "execute_sql",
        _route_after_execute,
        {"retry": "generate_sql", "give_up": "sql_failed", "continue": "generate_answer"},
    )
    graph.add_edge("sql_failed", END)
    graph.add_edge("generate_answer", END)

    return graph.compile(checkpointer=checkpointer)


# Compiled without a checkpointer by default (used by scripts/tests that
# import this module directly). The running app swaps this for a
# checkpointed graph at startup — see set_checkpointer() / main.py.
_compiled_graph = build_chat_graph()


def set_checkpointer(checkpointer) -> None:
    """Rebuild the compiled graph with a checkpointer attached. Called once
    at app startup after the checkpointer's own connection is ready."""

    global _compiled_graph
    _compiled_graph = build_chat_graph(checkpointer=checkpointer)


def get_chat_graph():
    return _compiled_graph
