"""Phase 2, generate: find similar past questions and have the model write SQL."""

from app.chat.common import (
    CANNOT_ANSWER_MESSAGE,
    CANNOT_CHANGE_MESSAGE,
    get_connection,
    deps,
    message_state,
    record_usage,
)
from app.chat.generate.examples import find_similar
from app.chat.generate.sql import generate_sql, generate_write_sql
from app.chat.schemas import ExampleUsed
from app.chat.state import GraphState


def retrieve_examples_node(state: GraphState, config) -> dict:

    timings, debug, _bg = deps(config)

    with timings.step("retrieve_examples"):
        examples, question_vector = find_similar(state["question"])

    debug.examples = [
        ExampleUsed(question=e.example.question, sql=e.example.sql, score=e.score)
        for e in examples
    ]

    return {"examples": examples, "question_vector": question_vector}


def generate_sql_node(state: GraphState, config) -> dict:
    """Generates SQL for the question. Also the retry target: when
    `sql_error` is set (a previous statement was rejected by the
    database), that failure is fed back to the model so it can fix its
    own mistake instead of repeating it.
    """

    timings, debug, _bg = deps(config)
    connection = get_connection(config)

    previous_attempt = None
    if state.get("sql_error"):
        previous_attempt = {"sql": state.get("sql"), "error": state["sql_error"]}

    with timings.step("generate_sql"):
        generation = generate_sql(
            state["question"],
            connection.schema_text,
            state.get("examples"),
            state.get("history"),
            previous_attempt=previous_attempt,
            dialect=connection.dialect,
        )
    debug.prompts["generate_sql"] = generation.prompt
    record_usage(debug, "generate_sql", generation.usage)

    if generation.clarification_question:
        return message_state("needs_clarification", generation.clarification_question)
    if not generation.can_answer:
        return message_state("off_topic", generation.cannot_answer_message or CANNOT_ANSWER_MESSAGE)

    return {"sql": generation.sql, "intent": "data_question"}


def generate_write_node(state: GraphState, config) -> dict:

    timings, debug, _bg = deps(config)
    connection = get_connection(config)

    with timings.step("generate_sql"):
        generation = generate_write_sql(
            state["question"], connection.schema_text, state.get("history")
        )
    debug.prompts["generate_write_sql"] = generation.prompt
    record_usage(debug, "generate_write_sql", generation.usage)

    if generation.clarification_question:
        return message_state("needs_clarification", generation.clarification_question)
    if not generation.can_answer:
        return message_state("off_topic", generation.cannot_answer_message or CANNOT_CHANGE_MESSAGE)

    return {"sql": generation.sql}
