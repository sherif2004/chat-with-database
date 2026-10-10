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
        CREATE TABLE IF NOT EXISTS app.conversations (
            id BIGSERIAL PRIMARY KEY,
            owner TEXT NOT NULL,
            title TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS conversations_owner_updated_idx ON app.conversations (owner, updated_at DESC)",
        "ALTER TABLE app.chat_history ADD COLUMN IF NOT EXISTS conversation_id BIGINT",
        """
        CREATE INDEX IF NOT EXISTS chat_history_conversation_idx
        ON app.chat_history (conversation_id, created_at)
        """,
        # question_key backed the exact-match response cache, now moved to
        # Redis (see app/services/cache_service.py) — drop the leftover
        # column/index so chat_history is purely the conversation record.
        "DROP INDEX IF EXISTS app.chat_history_session_id_question_key_idx",
        "ALTER TABLE app.chat_history DROP COLUMN IF EXISTS question_key",
    )


def save_message(session_id: str, conversation_id: int, question: str, response: dict) -> None:
    """Persist one exchange. Never raises: a storage problem must not
    break the chat response, which has already been sent by the time
    this runs as a background task."""

    def run():
        with app_engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO app.chat_history (session_id, conversation_id, question, response)
                    VALUES (:session_id, :conversation_id, :question, CAST(:response AS JSONB))
                """),
                {
                    "session_id": session_id,
                    "conversation_id": conversation_id,
                    "question": question,
                    "response": json.dumps(response),
                }
            )
            conn.execute(
                text("UPDATE app.conversations SET updated_at = now() WHERE id = :id AND owner = :owner"),
                {"id": conversation_id, "owner": session_id},
            )

    run_or_log(run, logger, "Could not save chat history: %s")


def get_history(session_id: str, conversation_id: int) -> list[HistoryRow]:

    def run():
        with app_engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT question, response, created_at
                    FROM app.chat_history
                    WHERE session_id = :session_id AND conversation_id = :conversation_id
                    ORDER BY created_at ASC
                """),
                {"session_id": session_id, "conversation_id": conversation_id}
            )
            return [_to_history_row(row) for row in result]

    return retry_on_disconnect(run)


def get_recent_history(session_id: str, conversation_id: int | None, limit: int) -> list[HistoryRow]:
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
                    WHERE session_id = :session_id AND conversation_id = :conversation_id
                    ORDER BY created_at DESC
                    LIMIT :limit
                """),
                {"session_id": session_id, "conversation_id": conversation_id, "limit": limit}
            )
            return list(reversed([_to_history_row(row) for row in result]))

    return retry_on_disconnect(run)


def delete_last_exchange(session_id: str, conversation_id: int) -> None:
    """Drop the newest exchange of a conversation — used when the user
    regenerates an answer or edits their last question."""

    def run():
        with app_engine.begin() as conn:
            conn.execute(
                text("""
                    DELETE FROM app.chat_history
                    WHERE id = (
                        SELECT id FROM app.chat_history
                        WHERE session_id = :session_id AND conversation_id = :conversation_id
                        ORDER BY created_at DESC, id DESC
                        LIMIT 1
                    )
                """),
                {"session_id": session_id, "conversation_id": conversation_id},
            )

    retry_on_disconnect(run)
