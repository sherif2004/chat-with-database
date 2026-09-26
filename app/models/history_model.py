import json
import logging
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import text

from app.models.database import app_engine, retry_on_disconnect, run_ddl, run_or_log

logger = logging.getLogger(__name__)


class HistoryRow(BaseModel):
    question: str
    response: dict
    created_at: datetime


def _to_history_row(row) -> HistoryRow:
    return HistoryRow(question=row.question, response=row.response, created_at=row.created_at)


def ensure_chat_history_schema() -> None:
    """Create the app.chat_history table if it doesn't exist yet.

    Called once at startup. Raises on failure; the caller decides whether
    that's fatal (it isn't — see app/main.py, which logs and continues).
    """

    run_ddl(
        "CREATE SCHEMA IF NOT EXISTS app",
        """
        CREATE TABLE IF NOT EXISTS app.chat_history (
            id BIGSERIAL PRIMARY KEY,
            session_id TEXT NOT NULL,
            question TEXT NOT NULL,
            response JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS chat_history_session_id_created_at_idx
        ON app.chat_history (session_id, created_at)
        """,
        """
        CREATE INDEX IF NOT EXISTS chat_history_session_id_question_idx
        ON app.chat_history (session_id, lower(question), created_at DESC)
        """,
    )


def save_message(session_id: str, question: str, response: dict) -> None:
    """Persist one exchange. Never raises: a storage problem must not
    break the chat response, which has already been sent by the time
    this runs as a background task."""

    def run():
        with app_engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO app.chat_history (session_id, question, response)
                    VALUES (:session_id, :question, CAST(:response AS JSONB))
                """),
                {
                    "session_id": session_id,
                    "question": question,
                    "response": json.dumps(response),
                }
            )

    run_or_log(run, logger, "Could not save chat history: %s")


def get_history(session_id: str) -> list[HistoryRow]:

    def run():
        with app_engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT question, response, created_at
                    FROM app.chat_history
                    WHERE session_id = :session_id
                    ORDER BY created_at ASC
                """),
                {"session_id": session_id}
            )
            return [_to_history_row(row) for row in result]

    return retry_on_disconnect(run)


def get_cached_response(session_id: str, question: str) -> dict | None:
    """Exact-match cache lookup: the response of the most recent identical
    question asked in this session, or None on a miss.

    Matching is a plain case-insensitive string comparison (no embeddings,
    no fuzzy matching) — a deliberate word-for-word match, not semantic
    similarity like find_similar() uses for few-shot examples.
    """

    def run():
        with app_engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT response
                    FROM app.chat_history
                    WHERE session_id = :session_id
                      AND lower(question) = lower(:question)
                    ORDER BY created_at DESC
                    LIMIT 1
                """),
                {"session_id": session_id, "question": question}
            )
            row = result.first()
            return row.response if row else None

    return run_or_log(run, logger, "Could not look up cached response: %s")


def get_recent_history(session_id: str, limit: int) -> list[HistoryRow]:
    """Last `limit` exchanges, oldest first. Unlike get_history(), this
    fetches only `limit` rows from the database instead of the whole
    session — used to feed a prompt, where the cost must not grow with
    how long the conversation has been going."""

    def run():
        with app_engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT question, response, created_at
                    FROM app.chat_history
                    WHERE session_id = :session_id
                    ORDER BY created_at DESC
                    LIMIT :limit
                """),
                {"session_id": session_id, "limit": limit}
            )
            return list(reversed([_to_history_row(row) for row in result]))

    return retry_on_disconnect(run)
