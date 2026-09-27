import logging

from fastapi import BackgroundTasks
from pydantic import ValidationError

from app.guardrails.errors import GuardrailError, UnknownTableError
from app.guardrails.input_guard import check_question
from app.guardrails.sql_guard import validate_sql
from app.models.connection_model import DatabaseConnectionError, SessionConnection, get_or_default
from app.models.history_model import get_cached_response, get_history, get_recent_history, save_message
from app.models.query_model import execute_sql
from app.models.workflow_model import get_workflow
from app.services.example_service import find_similar, remember
from app.services.llm_service import MODEL, generate_answer, generate_route_and_sql, generate_sql
from app.services.router_service import classify_intent
from app.timing import Timings
from app.views.chat_view import (
    ChatRequest,
    ChatResponse,
    DebugInfo,
    ExampleUsed,
    HistoryEntry,
    MessageResult,
    QueryTable,
    TableResult,
)

GREETING_MESSAGE = (
    "Hello! Ask me a question about the data and I will look it up for you."
)
OFF_TOPIC_MESSAGE = "Your question is not related to the data."
UNSAFE_MESSAGE = "I can only answer read-only questions about the data."
CANNOT_ANSWER_MESSAGE = (
    "I couldn't answer that: the data doesn't contain the information "
    "needed for this question."
)


def _connection_unreachable_message(error: DatabaseConnectionError) -> str:
    return f"Your connected database is unreachable: {error}"


logger = logging.getLogger(__name__)


def _finish(timings, background_tasks, session_id, debug, **fields):

    response = ChatResponse(timings_ms=timings.as_model(), debug=debug, **fields)

    logger.info(
        "intent=%s timings_ms=%s",
        response.intent,
        response.timings_ms
    )

    background_tasks.add_task(
        save_message, session_id, fields["question"], response.model_dump(mode="json")
    )

    return response


def _message(timings, background_tasks, session_id, intent, question, message, debug):

    return _finish(
        timings,
        background_tasks,
        session_id,
        debug,
        intent=intent,
        question=question,
        result=MessageResult(message=message)
    )


def _record_usage(debug, step, usage):
    if usage is not None:
        debug.token_usage[step] = usage


RECENT_HISTORY_LIMIT = 3


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


def _answer_data_question(
    sql,
    question,
    connection: SessionConnection,
    timings,
    background_tasks,
    session_id,
    debug,
    question_vector=None,
):
    """Shared tail for both workflows once SQL has been generated: guard
    it, run it, learn from it, and turn the result into a reply."""

    try:
        with timings.step("sql_guard"):
            statements = validate_sql(sql, connection.schema.table_names)
    except UnknownTableError:
        return _message(timings, background_tasks, session_id, "off_topic", question, CANNOT_ANSWER_MESSAGE, debug)
    except GuardrailError as e:
        return _message(timings, background_tasks, session_id, "unsafe", question, f"{UNSAFE_MESSAGE} ({e})", debug)

    with timings.step("execute_sql"):
        queries = [execute_sql(stmt, connection.engine) for stmt in statements]

    # Learn from the chat (after the response is sent): the pair passed
    # the guard, ran, and returned rows. Only worth remembering as an
    # example when every statement actually returned something.
    if all(query.rows for query in queries):
        background_tasks.add_task(remember, question, "; ".join(statements), question_vector)

    # Format the result — return both the raw table(s) and an LLM-generated
    # natural-language answer together. The LLM is asked even when there
    # are no rows, so the "no data" reply is still in the question's own
    # language instead of a fixed English string.
    answer_inputs = [
        {"sql": stmt, "rows": [dict(zip(query.columns, row)) for row in query.rows]}
        for stmt, query in zip(statements, queries)
    ]

    with timings.step("generate_answer"):
        answer, answer_prompt, answer_usage = generate_answer(question, answer_inputs)
    debug.prompts["generate_answer"] = answer_prompt
    _record_usage(debug, "generate_answer", answer_usage)

    result = TableResult(
        queries=[
            QueryTable(sql=stmt, **query.model_dump(exclude={"rows"}), rows=query.rows)
            for stmt, query in zip(statements, queries)
        ],
        answer=answer,
    )

    return _finish(
        timings,
        background_tasks,
        session_id,
        debug,
        intent="data_question",
        question=question,
        sql=statements,
        result=result
    )


def _chat_with_router(question, connection, timings, background_tasks, session_id, debug, history):

    with timings.step("router"):
        decision, router_prompt, router_usage = classify_intent(question, connection.schema_text, history)
    intent = decision.intent
    debug.prompts["router"] = router_prompt
    _record_usage(debug, "router", router_usage)

    if intent == "greeting":
        return _message(timings, background_tasks, session_id, intent, question, decision.reply or GREETING_MESSAGE, debug)

    if intent == "off_topic":
        return _message(timings, background_tasks, session_id, intent, question, decision.reply or OFF_TOPIC_MESSAGE, debug)

    if intent == "unsafe":
        return _message(timings, background_tasks, session_id, intent, question, decision.reply or UNSAFE_MESSAGE, debug)

    # Only worth the embedding + Qdrant lookup once we know this is a
    # data question.
    with timings.step("retrieve_examples"):
        examples, question_vector = find_similar(question)
    debug.examples = [
        ExampleUsed(question=e.example.question, sql=e.example.sql, score=e.score)
        for e in examples
    ]

    with timings.step("generate_sql"):
        generation = generate_sql(
            question,
            connection.schema_text,
            examples,
            history
        )
    debug.prompts["generate_sql"] = generation.prompt
    _record_usage(debug, "generate_sql", generation.usage)

    if generation.clarification_question:
        return _message(
            timings, background_tasks, session_id, "needs_clarification",
            question, generation.clarification_question, debug
        )

    if not generation.can_answer:
        message = generation.cannot_answer_message or CANNOT_ANSWER_MESSAGE
        return _message(timings, background_tasks, session_id, "off_topic", question, message, debug)

    return _answer_data_question(
        generation.sql, question, connection, timings, background_tasks, session_id, debug,
        question_vector=question_vector
    )


def _chat_without_router(question, connection, timings, background_tasks, session_id, debug, history):

    # Same few-shot examples as the router workflow, fetched unconditionally
    # here since this workflow doesn't know the intent until after the
    # merged call below — that's the one cost this workflow still pays
    # even though it skips the separate router call.
    with timings.step("retrieve_examples"):
        examples, question_vector = find_similar(question)
    debug.examples = [
        ExampleUsed(question=e.example.question, sql=e.example.sql, score=e.score)
        for e in examples
    ]

    # One call does both the routing and (if applicable) the SQL generation.
    with timings.step("route_and_generate_sql"):
        generation = generate_route_and_sql(question, connection.schema_text, examples, history)
    debug.prompts["route_and_generate_sql"] = generation.prompt
    _record_usage(debug, "route_and_generate_sql", generation.usage)

    if generation.intent == "greeting":
        return _message(timings, background_tasks, session_id, "greeting", question, generation.reply or GREETING_MESSAGE, debug)

    if generation.intent == "off_topic":
        return _message(timings, background_tasks, session_id, "off_topic", question, generation.reply or OFF_TOPIC_MESSAGE, debug)

    if generation.intent == "unsafe":
        return _message(timings, background_tasks, session_id, "unsafe", question, generation.reply or UNSAFE_MESSAGE, debug)

    if generation.intent == "cannot_answer":
        return _message(timings, background_tasks, session_id, "off_topic", question, generation.reply or CANNOT_ANSWER_MESSAGE, debug)

    if generation.intent == "needs_clarification":
        return _message(timings, background_tasks, session_id, "needs_clarification", question, generation.reply or CANNOT_ANSWER_MESSAGE, debug)

    return _answer_data_question(
        generation.sql, question, connection, timings, background_tasks, session_id, debug,
        question_vector=question_vector
    )


def chat_with_database(
    request: ChatRequest,
    background_tasks: BackgroundTasks
) -> ChatResponse:

    timings = Timings()
    session_id = request.session_id
    debug = DebugInfo(model=MODEL)

    try:
        with timings.step("input_guard"):
            question = check_question(request.question)
    except GuardrailError as e:
        return _message(timings, background_tasks, session_id, "unsafe", request.question, str(e), debug)

    with timings.step("cache_lookup"):
        cached = get_cached_response(session_id, question)

    if cached is not None:
        try:
            cached_response = ChatResponse.model_validate(cached)
        except ValidationError:
            logger.warning("Skipping unparseable cached response for session %s", session_id)
        else:
            return _finish(
                timings,
                background_tasks,
                session_id,
                cached_response.debug,
                intent=cached_response.intent,
                question=question,
                sql=cached_response.sql,
                result=cached_response.result,
                cache_hit=True,
            )

    # Resolve which database this session is talking to
    try:
        with timings.step("resolve_connection"):
            connection = get_or_default(session_id)
    except DatabaseConnectionError as e:
        return _message(
            timings, background_tasks, session_id, "connection_error",
            question, _connection_unreachable_message(e), debug
        )

    workflow = get_workflow(session_id)
    debug.workflow = workflow

    with timings.step("load_history"):
        history = _recent_history(session_id)

    if workflow == "no_router":
        return _chat_without_router(question, connection, timings, background_tasks, session_id, debug, history)

    return _chat_with_router(question, connection, timings, background_tasks, session_id, debug, history)


def get_chat_history(session_id: str) -> list[HistoryEntry]:

    rows = get_history(session_id)

    entries = []

    for row in rows:
        try:
            entries.append(HistoryEntry(
                question=row.question,
                response=ChatResponse.model_validate(row.response),
                created_at=row.created_at
            ))
        except ValidationError:
            logger.warning("Skipping unparseable chat_history row for session %s", session_id)

    return entries
