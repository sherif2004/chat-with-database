"""The question pipeline. Read this file to see the whole flow; each
phase's logic lives in its own folder:

    understand  ->  generate  ->  execute  ->  respond
"""

from langgraph.graph import END, StateGraph

from app.chat.execute.nodes import (
    SQL_MAX_ATTEMPTS,
    execute_sql_node,
    preview_write_node,
    sql_failed_node,
    validate_sql_node,
    validate_write_node,
)
from app.chat.generate.nodes import generate_sql_node, generate_write_node, retrieve_examples_node
from app.chat.respond.nodes import generate_answer_node
from app.chat.state import GraphState
from app.chat.understand.nodes import (
    cache_lookup_node,
    classify_intent_node,
    input_guard_node,
    load_history_node,
    resolve_connection_node,
    route_after_context_node,
)


def has_result(state: GraphState) -> str:
    return "end" if state.get("result") is not None else "next"


def _route_after_cache(state: GraphState):
    """Returns node names directly (no path_map) so a miss can fan out to
    both resolve_connection and load_history at once."""
    if state.get("cache_hit"):
        return END
    return ["resolve_connection", "load_history"]


def _route_after_context(state: GraphState) -> str:
    """After the resolve_connection / load_history join: a connection
    failure short-circuits to END regardless of load_history's outcome
    (load_history never fails)."""
    return "error" if state.get("result") is not None else "ok"


def _route_after_classify(state: GraphState) -> str:
    if state.get("result") is not None:
        return "end"
    return "write" if state.get("intent") == "data_change" else "next"


def _route_after_execute(state: GraphState) -> str:
    if state.get("sql_error"):
        return "retry" if state.get("retry_count", 0) < SQL_MAX_ATTEMPTS else "give_up"
    return "continue"


def build_chat_graph():

    graph = StateGraph(GraphState)

    graph.add_node("input_guard", input_guard_node)
    graph.add_node("cache_lookup", cache_lookup_node)
    graph.add_node("resolve_connection", resolve_connection_node)
    graph.add_node("load_history", load_history_node)
    graph.add_node("route_after_context", route_after_context_node)
    graph.add_node("classify_intent", classify_intent_node)
    graph.add_node("retrieve_examples", retrieve_examples_node)
    graph.add_node("generate_sql", generate_sql_node)
    graph.add_node("validate_sql", validate_sql_node)
    graph.add_node("execute_sql", execute_sql_node)
    graph.add_node("generate_write", generate_write_node)
    graph.add_node("validate_write", validate_write_node)
    graph.add_node("preview_write", preview_write_node)
    graph.add_node("sql_failed", sql_failed_node)
    graph.add_node("generate_answer", generate_answer_node)

    graph.set_entry_point("input_guard")

    graph.add_conditional_edges("input_guard", has_result, {"end": END, "next": "cache_lookup"})

    # On a cache miss, resolve_connection and load_history are independent
    # (both need only session_id), so they run as parallel branches —
    # _route_after_cache returns both node names directly to fan out.
    graph.add_conditional_edges("cache_lookup", _route_after_cache)
    graph.add_edge("resolve_connection", "route_after_context")
    graph.add_edge("load_history", "route_after_context")

    graph.add_conditional_edges(
        "route_after_context", _route_after_context, {"error": END, "ok": "classify_intent"}
    )
    graph.add_conditional_edges(
        "classify_intent",
        _route_after_classify,
        {"end": END, "next": "retrieve_examples", "write": "generate_write"},
    )
    graph.add_conditional_edges("generate_write", has_result, {"end": END, "next": "validate_write"})
    graph.add_conditional_edges("validate_write", has_result, {"end": END, "next": "preview_write"})
    graph.add_edge("preview_write", END)
    graph.add_edge("retrieve_examples", "generate_sql")
    graph.add_conditional_edges("generate_sql", has_result, {"end": END, "next": "validate_sql"})
    graph.add_conditional_edges("validate_sql", has_result, {"end": END, "next": "execute_sql"})
    graph.add_conditional_edges(
        "execute_sql",
        _route_after_execute,
        {"retry": "generate_sql", "give_up": "sql_failed", "continue": "generate_answer"},
    )
    graph.add_edge("sql_failed", END)
    graph.add_edge("generate_answer", END)

    return graph.compile()


chat_graph = build_chat_graph()
