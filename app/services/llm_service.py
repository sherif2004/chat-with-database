from typing import Literal, TypeVar

from openai import AzureOpenAI, OpenAIError
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.models.example_model import SimilarExample
from app.services.prompts import answer_prompt, route_and_sql_prompt, sql_prompt
from app.views.chat_view import TokenUsage

client = AzureOpenAI(
    api_key=settings.azure_openai_api_key,
    azure_endpoint=settings.azure_openai_endpoint,
    api_version=settings.azure_openai_api_version,
    timeout=settings.llm_timeout_seconds,
)

MODEL = settings.azure_openai_deployment

# The answer prompt gets at most this many rows; the rest only cost tokens.
ANSWER_ROW_LIMIT = 20

Output = TypeVar("Output", bound=BaseModel)


class LLMUnavailable(Exception):
    """The language model call failed (rate limit, timeout, outage...)."""


def _usage(response) -> TokenUsage | None:

    if response.usage is None:
        return None

    return TokenUsage(
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        total_tokens=response.usage.total_tokens,
    )


def ask_llm(prompt, max_output_tokens=None) -> tuple[str, TokenUsage | None]:
    """Free-text answer."""

    try:
        response = client.responses.create(
            model=MODEL,
            input=prompt,
            max_output_tokens=max_output_tokens
        )
    except OpenAIError as e:
        raise LLMUnavailable(str(e)) from e

    return response.output_text.strip(), _usage(response)


def ask_structured(
    prompt, output_type: type[Output], max_output_tokens=None
) -> tuple[Output | None, TokenUsage | None]:
    """Answer constrained to `output_type`'s JSON schema. The parsed value
    is None when the model refused or its output could not be parsed;
    callers treat that as "fail closed"."""

    try:
        response = client.responses.parse(
            model=MODEL,
            input=prompt,
            text_format=output_type,
            max_output_tokens=max_output_tokens
        )
    except OpenAIError as e:
        raise LLMUnavailable(str(e)) from e
    except ValidationError:
        return None, None

    return response.output_parsed, _usage(response)


class _SQLDraft(BaseModel):
    can_answer: bool
    sql: str | None = None
    cannot_answer_message: str | None = None
    clarification_question: str | None = None


class SQLGeneration(_SQLDraft):
    prompt: str = ""
    usage: TokenUsage | None = None


def generate_sql(
    question,
    schema_text,
    examples: list[SimilarExample] | None = None,
    history: list[dict] | None = None,
    previous_attempt: dict | None = None,
) -> SQLGeneration:
    """`previous_attempt`, when set, is {"sql", "error"} from a prior
    attempt that failed against the real database — used to retry with
    the failure fed back to the model."""

    prompt = sql_prompt(question, schema_text, examples or [], history or [], previous_attempt)
    draft, usage = ask_structured(prompt, _SQLDraft, max_output_tokens=1000)

    if draft is None or not draft.can_answer or not (draft.sql or "").strip():
        message = draft.cannot_answer_message if draft else None
        clarification = draft.clarification_question if draft else None
        return SQLGeneration(
            can_answer=False,
            cannot_answer_message=message or None,
            clarification_question=clarification or None,
            prompt=prompt,
            usage=usage,
        )

    return SQLGeneration(can_answer=True, sql=draft.sql.strip(), prompt=prompt, usage=usage)


def generate_answer(
    question,
    queries: list[dict]
) -> tuple[str, str, TokenUsage | None]:
    """`queries` is [{"sql", "rows"}, ...], one entry per executed
    statement; `rows` is trimmed to ANSWER_ROW_LIMIT here."""

    trimmed = [
        {"sql": q["sql"], "rows": q["rows"][:ANSWER_ROW_LIMIT], "total_rows": len(q["rows"])}
        for q in queries
    ]

    prompt = answer_prompt(question, trimmed)
    answer, usage = ask_llm(prompt, max_output_tokens=800)

    return answer, prompt, usage


class _RouteAndSqlDraft(BaseModel):
    intent: Literal[
        "greeting", "off_topic", "unsafe", "data_question",
        "cannot_answer", "needs_clarification"
    ]
    reply: str | None = None
    sql: str | None = None


class RouteAndSqlGeneration(_RouteAndSqlDraft):
    prompt: str = ""
    usage: TokenUsage | None = None


def generate_route_and_sql(
    question,
    schema_text,
    examples: list[SimilarExample] | None = None,
    history: list[dict] | None = None,
    previous_attempt: dict | None = None,
) -> RouteAndSqlGeneration:
    """Classify the question and, if it's a data question, generate its SQL,
    all in a single LLM call. Used by the "no router" workflow: faster
    (one fewer LLM round trip) than the router + generate_sql sequence,
    at the cost of folding the unsafe-question judgment into the same
    prompt as SQL generation instead of a dedicated call.

    `previous_attempt`, when set, is {"sql", "error"} from a prior attempt
    that failed against the real database.
    """

    prompt = route_and_sql_prompt(question, schema_text, examples or [], history or [], previous_attempt)
    draft, usage = ask_structured(prompt, _RouteAndSqlDraft, max_output_tokens=1000)

    # Fail closed: an unusable answer is never sent to SQL.
    if draft is None:
        return RouteAndSqlGeneration(intent="off_topic", prompt=prompt, usage=usage)

    if draft.intent == "data_question" and not (draft.sql or "").strip():
        draft.intent = "cannot_answer"

    return RouteAndSqlGeneration(**draft.model_dump(), prompt=prompt, usage=usage)
