import json
import logging
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text

from app.models.database import app_engine, retry_on_disconnect

logger = logging.getLogger(__name__)


class HistoryRow(BaseModel):
    question: str
    response: dict
    created_at: datetime


def ensure_chat_history_schema() -> None:
    """Create the app.chat_history table if it doesn't exist yet.

    Called once at startup. Raises on failure; the caller decides whether
    that's fatal (it isn't — see app/main.py, which logs and continues).
    """

    def run():
        with app_engine.begin() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS app"))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS app.chat_history (
                    id BIGSERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    response JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS chat_history_session_id_created_at_idx
                ON app.chat_history (session_id, created_at)
            """))

    retry_on_disconnect(run)


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

    try:
        retry_on_disconnect(run)
    except SQLAlchemyError as e:
        logger.warning("Could not save chat history: %s", e)


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
            return [
                HistoryRow(
                    question=row.question,
                    response=row.response,
                    created_at=row.created_at
                )
                for row in result
            ]

    return retry_on_disconnect(run)


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
            rows = [
                HistoryRow(
                    question=row.question,
                    response=row.response,
                    created_at=row.created_at
                )
                for row in result
            ]
            return list(reversed(rows))

    return retry_on_disconnect(run)
