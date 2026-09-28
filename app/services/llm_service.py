from typing import TypeVar

from openai import AzureOpenAI, OpenAIError
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.models.example_model import SimilarExample
from app.services.prompts import answer_prompt, sql_prompt
from app.views.chat_view import TokenUsage

client = AzureOpenAI(
    api_key=settings.azure_openai_api_key,
    azure_endpoint=settings.azure_openai_endpoint,
    api_version=settings.azure_openai_api_version,
    timeout=settings.llm_timeout_seconds,
)

MODEL = settings.azure_openai_deployment
LIGHT_MODEL = settings.azure_openai_deployment_light

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


def ask_llm(prompt, max_output_tokens=None, model=MODEL) -> tuple[str, TokenUsage | None]:
    """Free-text answer."""

    try:
        response = client.responses.create(
            model=model,
            input=prompt,
            max_output_tokens=max_output_tokens
        )
    except OpenAIError as e:
        raise LLMUnavailable(str(e)) from e

    return response.output_text.strip(), _usage(response)


def ask_structured(
    prompt, output_type: type[Output], max_output_tokens=None, model=MODEL
) -> tuple[Output | None, TokenUsage | None]:
    """Answer constrained to `output_type`'s JSON schema. The parsed value
    is None when the model refused or its output could not be parsed;
    callers treat that as "fail closed"."""

    try:
        response = client.responses.parse(
            model=model,
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
    statement; `rows` is trimmed to ANSWER_ROW_LIMIT here.

    Summarizing rows into a sentence looks easy, but LIGHT_MODEL proved
    unreliable at the one rule that matters most here — answering in the
    question's language (verified: ~1 in 3 answers came back in the wrong
    language, reproducibly, across unrelated questions, even after
    strengthening the prompt). Runs on MODEL instead.
    """

    trimmed = [
        {"sql": q["sql"], "rows": q["rows"][:ANSWER_ROW_LIMIT], "total_rows": len(q["rows"])}
        for q in queries
    ]

    prompt = answer_prompt(question, trimmed)
    answer, usage = ask_llm(prompt, max_output_tokens=800, model=MODEL)

    return answer, prompt, usage
