import logging
from concurrent.futures import ThreadPoolExecutor

from fastapi import BackgroundTasks
from pydantic import ValidationError

from app.guardrails.errors import GuardrailError, UnknownTableError
from app.guardrails.input_guard import check_question
from app.guardrails.sql_guard import validate_sql
from app.models.history_model import get_history, save_message
from app.models.query_model import execute_sql
from app.models.schema_model import (
    DatabaseSchema,
    get_database_schema,
    schema_to_text,
)
from app.services.example_service import find_similar, remember
from app.services.llm_service import generate_answer, generate_sql
from app.services.router_service import classify_intent
from app.timing import Timings
from app.views.chat_view import (
    ChatRequest,
    ChatResponse,
    HistoryEntry,
    MessageResult,
    TableResult,
    TextResult,
)

GREETING_MESSAGE = (
    "Hello! Ask me a question about the data and I will look it up for you."
)
OFF_TOPIC_MESSAGE = "Your question is not related to the data."
UNSAFE_MESSAGE = "I can only answer read-only questions about the data."
NO_DATA_MESSAGE = "No matching data was found."
CANNOT_ANSWER_MESSAGE = (
    "I couldn't answer that: the data doesn't contain the information "
    "needed for this question."
)

logger = logging.getLogger(__name__)

# Runs the router and the example lookup at the same time.
_executor = ThreadPoolExecutor(max_workers=16)

schema: DatabaseSchema | None = None
schema_text = None


def load_schema():

    global schema, schema_text

    schema = get_database_schema()

    schema_text = schema_to_text(schema)


def _finish(timings, background_tasks, session_id, **fields):

    response = ChatResponse(timings_ms=timings.as_model(), **fields)

    logger.info(
        "intent=%s timings_ms=%s",
        response.intent,
        response.timings_ms
    )

    background_tasks.add_task(
        save_message, session_id, fields["question"], response.model_dump(mode="json")
    )

    return response


def _message(timings, background_tasks, session_id, intent, question, message):

    return _finish(
        timings,
        background_tasks,
        session_id,
        intent=intent,
        question=question,
        result=MessageResult(message=message)
    )


# ============================================================
# Chat With Database
# ============================================================

def _timed(timings, step, function, *args):

    with timings.step(step):
        return function(*args)


def chat_with_database(
    request: ChatRequest,
    background_tasks: BackgroundTasks
) -> ChatResponse:

    timings = Timings()
    session_id = request.session_id

    # Step 0: Input guardrail
    try:
        with timings.step("input_guard"):
            question = check_question(request.question)
    except GuardrailError as e:
        return _message(timings, background_tasks, session_id, "unsafe", request.question, str(e))

    # Step 1: Route the question, while looking up similar examples in parallel
    router_call = _executor.submit(
        _timed, timings, "router", classify_intent, question, schema_text
    )
    examples_call = _executor.submit(
        _timed, timings, "retrieve_examples", find_similar, question
    )

    intent = router_call.result().intent

    if intent == "greeting":
        return _message(timings, background_tasks, session_id, intent, question, GREETING_MESSAGE)

    if intent == "off_topic":
        return _message(timings, background_tasks, session_id, intent, question, OFF_TOPIC_MESSAGE)

    if intent == "unsafe":
        return _message(timings, background_tasks, session_id, intent, question, UNSAFE_MESSAGE)

    # Step 2: Similar solved examples (dynamic few-shot)
    examples, question_vector = examples_call.result()

    # Step 3: Generate SQL and check it
    with timings.step("generate_sql"):
        generation = generate_sql(
            question,
            schema_text,
            examples
        )

    if not generation.can_answer:
        return _message(timings, background_tasks, session_id, "off_topic", question, CANNOT_ANSWER_MESSAGE)

    try:
        with timings.step("sql_guard"):
            sql = validate_sql(generation.sql, schema.table_names)
    except UnknownTableError:
        return _message(timings, background_tasks, session_id, "off_topic", question, CANNOT_ANSWER_MESSAGE)
    except GuardrailError as e:
        return _message(timings, background_tasks, session_id, "unsafe", question, f"{UNSAFE_MESSAGE} ({e})")

    # Step 4: Execute SQL (read-only transaction)
    with timings.step("execute_sql"):
        query = execute_sql(sql)

    # Step 5: Learn from the chat (after the response is sent): the pair
    # passed the guard, ran, and returned rows
    if query.rows:
        background_tasks.add_task(remember, question, sql, question_vector)

    # Step 6: Format the result — return both the raw table and an
    # LLM-generated natural-language answer together
    if not query.rows:
        result = TextResult(answer=NO_DATA_MESSAGE)

    else:
        records = [dict(zip(query.columns, row)) for row in query.rows]

        with timings.step("generate_answer"):
            answer = generate_answer(question, sql, records)

        result = TableResult(**query.model_dump(), answer=answer)

    return _finish(
        timings,
        background_tasks,
        session_id,
        intent="data_question",
        question=question,
        sql=sql,
        result=result
    )


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
