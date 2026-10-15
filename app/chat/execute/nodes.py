"""Phase 3, execute: check the SQL is safe, run it, and prepare changes for
confirmation."""

from sqlalchemy.exc import SQLAlchemyError

from app.chat.common import (
    CANNOT_ANSWER_MESSAGE,
    CANNOT_CHANGE_MESSAGE,
    UNSAFE_MESSAGE,
    get_connection,
    deps,
    message_state,
)
from app.chat.errors import GuardrailError, UnknownTableError
from app.chat.execute import pending_change
from app.chat.execute.sql_guard import validate_sql, validate_write_sql
from app.chat.generate.examples import remember
from app.chat.schemas import ChangeResult
from app.chat.state import GraphState
from app.config import settings
from app.databases.query import dry_run_write, execute_sql

# Total attempts allowed at generating+running SQL for one question (the
# first try plus retries once the database rejects the query).
SQL_MAX_ATTEMPTS = 3


def validate_sql_node(state: GraphState, config) -> dict:

    timings, _debug, _bg = deps(config)
    connection = get_connection(config)

    try:
        with timings.step("sql_guard"):
            statements = validate_sql(
                state["sql"], connection.schema.table_names, connection.dialect, connection.schema_name
            )
    except UnknownTableError:
        return message_state("off_topic", CANNOT_ANSWER_MESSAGE)
    except GuardrailError as e:
        return message_state("unsafe", f"{UNSAFE_MESSAGE} ({e})")

    return {"statements": statements}


def execute_sql_node(state: GraphState, config) -> dict:
    """Runs the validated statements. A database-level rejection (bad
    column, syntax slip the guard let through, ...) is caught here rather
    than left to propagate — it's what feeds the retry loop below."""

    timings, _debug, background_tasks = deps(config)
    connection = get_connection(config)
    statements = state["statements"]

    try:
        with timings.step("execute_sql"):
            queries = [execute_sql(stmt, connection.engine, connection.dialect) for stmt in statements]
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


def validate_write_node(state: GraphState, config) -> dict:

    timings, _debug, _bg = deps(config)
    connection = get_connection(config)

    try:
        with timings.step("sql_guard"):
            statement = validate_write_sql(state["sql"], connection.schema.table_names)
    except UnknownTableError:
        return message_state("off_topic", CANNOT_CHANGE_MESSAGE)
    except GuardrailError as e:
        return message_state("unsafe", f"I can't make that change. ({e})")

    return {"statements": [statement]}


def preview_write_node(state: GraphState, config) -> dict:
    """Runs the change inside a transaction that is always rolled back, to
    learn how many rows it would touch. The admin sees that count and must
    confirm before anything is saved."""

    timings, _debug, _bg = deps(config)
    connection = get_connection(config)
    statement = state["statements"][0]

    try:
        with timings.step("execute_sql"):
            rows = dry_run_write(statement, connection.engine)
    except SQLAlchemyError as e:
        reason = str(getattr(e, "orig", None) or e).strip().splitlines()[0]
        return message_state("off_topic", f"I couldn't prepare that change: {reason}")

    if rows < 1:
        return message_state("off_topic", "That change wouldn't affect any rows, so I didn't prepare it.")

    if rows > settings.max_write_rows:
        return message_state(
            "unsafe",
            f"That change would affect {rows} rows; the limit is {settings.max_write_rows}. "
            "Narrow it down and try again.",
        )

    token = pending_change.store({
        "owner": state["session_id"],
        "conversation_id": state.get("conversation_id"),
        "question": state["question"],
        "sql": statement,
        "rows": rows,
        "connection_label": connection.label,
    })

    return {
        "intent": "data_change",
        "result": ChangeResult(
            message=(
                f"This will change {rows} row{'s' if rows != 1 else ''}. "
                "Nothing is saved until you confirm."
            ),
            sql=statement,
            affected_rows=rows,
            token=token,
        ),
    }


def sql_failed_node(state: GraphState, config) -> dict:
    return message_state("off_topic", CANNOT_ANSWER_MESSAGE)
