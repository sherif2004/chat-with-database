"""Asks the model to write SQL for a question."""

from pydantic import BaseModel

from app.chat.generate.example_store import SimilarExample
from app.chat.generate.prompts import sql_prompt, write_sql_prompt
from app.databases.engines import POSTGRES, Dialect
from app.shared.llm import TokenUsage, ask_structured


class _SQLDraft(BaseModel):
    can_answer: bool
    sql: str | None = None
    cannot_answer_message: str | None = None
    clarification_question: str | None = None


class SQLGeneration(_SQLDraft):
    prompt: str = ""
    usage: TokenUsage | None = None


def _generate(prompt: str) -> SQLGeneration:
    """Asks the model and fails closed: anything but a usable statement
    becomes a "can't answer" result carrying the model's explanation."""

    draft, usage = ask_structured(prompt, _SQLDraft, max_output_tokens=1000)

    if draft is None or not draft.can_answer or not (draft.sql or "").strip():
        return SQLGeneration(
            can_answer=False,
            cannot_answer_message=(draft.cannot_answer_message if draft else None) or None,
            clarification_question=(draft.clarification_question if draft else None) or None,
            prompt=prompt,
            usage=usage,
        )

    return SQLGeneration(can_answer=True, sql=draft.sql.strip(), prompt=prompt, usage=usage)


def generate_sql(
    question,
    schema_text,
    examples: list[SimilarExample] | None = None,
    history: list[dict] | None = None,
    previous_attempt: dict | None = None,
    dialect: Dialect = POSTGRES,
) -> SQLGeneration:
    """`previous_attempt`, when set, is {"sql", "error"} from a prior
    attempt that failed against the real database — used to retry with
    the failure fed back to the model."""

    prompt = sql_prompt(question, schema_text, examples or [], history or [], previous_attempt, dialect)
    return _generate(prompt)


def generate_write_sql(question, schema_text, history: list[dict] | None = None) -> SQLGeneration:
    """One INSERT/UPDATE/DELETE for an admin's request. Only ever previewed
    here; nothing runs until it is confirmed."""

    return _generate(write_sql_prompt(question, schema_text, history or []))
