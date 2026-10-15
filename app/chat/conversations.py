import logging
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import text

from app.shared.database import app_engine, retry_on_disconnect

logger = logging.getLogger(__name__)

TITLE_MAX_LENGTH = 80


class Conversation(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime


def _row(row) -> Conversation:
    return Conversation(
        id=row.id, title=row.title, created_at=row.created_at, updated_at=row.updated_at
    )


def title_from_question(question: str) -> str:
    title = " ".join(question.split())
    if len(title) > TITLE_MAX_LENGTH:
        title = title[: TITLE_MAX_LENGTH - 1].rstrip() + "…"
    return title or "New chat"


def create_conversation(owner: str, title: str) -> Conversation:

    def run():
        with app_engine.begin() as conn:
            return _row(conn.execute(
                text("""
                    INSERT INTO app.conversations (owner, title)
                    VALUES (:owner, :title)
                    RETURNING id, title, created_at, updated_at
                """),
                {"owner": owner, "title": title},
            ).one())

    return retry_on_disconnect(run)


def list_conversations(owner: str) -> list[Conversation]:

    def run():
        with app_engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT id, title, created_at, updated_at
                    FROM app.conversations
                    WHERE owner = :owner
                    ORDER BY updated_at DESC
                    LIMIT 500
                """),
                {"owner": owner},
            )
            return [_row(row) for row in result]

    return retry_on_disconnect(run)


def get_conversation(owner: str, conversation_id: int) -> Conversation | None:
    """Only ever returns a conversation the owner owns, so callers can use
    None as "not found" without leaking whether someone else's id exists."""

    def run():
        with app_engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT id, title, created_at, updated_at
                    FROM app.conversations
                    WHERE id = :id AND owner = :owner
                """),
                {"id": conversation_id, "owner": owner},
            ).first()
            return _row(row) if row else None

    return retry_on_disconnect(run)


def set_generated_title(
    owner: str, conversation_id: int, placeholder: str, title: str
) -> None:
    """Replace the placeholder title, but only if the user hasn't already
    renamed the chat in the meantime."""

    def run():
        with app_engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE app.conversations SET title = :title
                    WHERE id = :id AND owner = :owner AND title = :placeholder
                """),
                {"id": conversation_id, "owner": owner, "title": title, "placeholder": placeholder},
            )

    retry_on_disconnect(run)


def rename_conversation(owner: str, conversation_id: int, title: str) -> Conversation | None:

    def run():
        with app_engine.begin() as conn:
            row = conn.execute(
                text("""
                    UPDATE app.conversations SET title = :title
                    WHERE id = :id AND owner = :owner
                    RETURNING id, title, created_at, updated_at
                """),
                {"id": conversation_id, "owner": owner, "title": title},
            ).first()
            return _row(row) if row else None

    return retry_on_disconnect(run)


def delete_conversation(owner: str, conversation_id: int) -> bool:

    def run():
        with app_engine.begin() as conn:
            deleted = conn.execute(
                text("DELETE FROM app.conversations WHERE id = :id AND owner = :owner"),
                {"id": conversation_id, "owner": owner},
            ).rowcount
            if deleted:
                conn.execute(
                    text("""
                        DELETE FROM app.chat_history
                        WHERE session_id = :owner AND conversation_id = :id
                    """),
                    {"id": conversation_id, "owner": owner},
                )
            return bool(deleted)

    return retry_on_disconnect(run)
