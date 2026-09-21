import logging

from app.guardrails.errors import GuardrailError, UnknownTableError
from app.guardrails.input_guard import check_question
from app.guardrails.sql_guard import validate_sql
from app.models.query_model import execute_sql
from app.models.schema_model import (
    DatabaseSchema,
    get_database_schema,
    schema_to_text,
)
from app.services.llm_service import generate_answer, generate_sql
from app.services.router_service import classify_intent
from app.timing import Timings
from app.views.chat_view import (
    ChatRequest,
    ChatResponse,
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

schema: DatabaseSchema | None = None
schema_text = None


def load_schema():

    global schema, schema_text

    schema = get_database_schema()

    schema_text = schema_to_text(schema)


def _finish(timings, **fields):

    response = ChatResponse(timings_ms=timings.as_model(), **fields)

    logger.info(
        "intent=%s timings_ms=%s",
        response.intent,
        response.timings_ms
    )

    return response


def _message(timings, intent, question, message):

    return _finish(
        timings,
        intent=intent,
        question=question,
        result=MessageResult(message=message)
    )


# ============================================================
# Chat With Database
# ============================================================

def chat_with_database(request: ChatRequest) -> ChatResponse:

    timings = Timings()

    # Step 0: Input guardrail
    try:
        with timings.step("input_guard"):
            question = check_question(request.question)
    except GuardrailError as e:
        return _message(timings, "unsafe", request.question, str(e))

    # Step 1: Route the question
    with timings.step("router"):
        intent = classify_intent(question, schema_text).intent

    if intent == "greeting":
        return _message(timings, intent, question, GREETING_MESSAGE)

    if intent == "off_topic":
        return _message(timings, intent, question, OFF_TOPIC_MESSAGE)

    if intent == "unsafe":
        return _message(timings, intent, question, UNSAFE_MESSAGE)

    # Step 2: Generate SQL and check it
    with timings.step("generate_sql"):
        generation = generate_sql(
            question,
            schema_text
        )

    if not generation.can_answer:
        return _message(timings, "off_topic", question, CANNOT_ANSWER_MESSAGE)

    try:
        with timings.step("sql_guard"):
            sql = validate_sql(generation.sql, schema.table_names)
    except UnknownTableError:
        return _message(timings, "off_topic", question, CANNOT_ANSWER_MESSAGE)
    except GuardrailError as e:
        return _message(timings, "unsafe", question, f"{UNSAFE_MESSAGE} ({e})")

    # Step 3: Execute SQL (read-only transaction)
    with timings.step("execute_sql"):
        query = execute_sql(sql)

    # Step 4: Format the result
    if not query.rows:
        result = TextResult(answer=NO_DATA_MESSAGE)

    elif request.format == "table" or (
        request.format == "auto" and len(query.rows) > 1
    ):
        result = TableResult(**query.model_dump())

    else:
        records = [dict(zip(query.columns, row)) for row in query.rows]

        with timings.step("generate_answer"):
            answer = generate_answer(question, sql, records)

        result = TextResult(answer=answer)

    return _finish(
        timings,
        intent="data_question",
        question=question,
        sql=sql,
        result=result
    )
