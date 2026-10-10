import logging
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.models.database import app_engine, retry_on_disconnect, run_ddl
from app.services.auth_service import token_digest

logger = logging.getLogger(__name__)


class User(BaseModel):
    id: int
    email: str


class EmailTaken(Exception):
    pass


def ensure_users_schema() -> None:
    run_ddl(
        "CREATE SCHEMA IF NOT EXISTS app",
        """
        CREATE TABLE IF NOT EXISTS app.users (
            id BIGSERIAL PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS app.user_sessions (
            token_hash TEXT PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES app.users(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at TIMESTAMPTZ NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS user_sessions_user_id_idx ON app.user_sessions (user_id)",
    )


def create_user(email: str, password_hash: str) -> User:

    def run():
        with app_engine.begin() as conn:
            row = conn.execute(
                text("""
                    INSERT INTO app.users (email, password_hash)
                    VALUES (:email, :password_hash)
                    RETURNING id, email
                """),
                {"email": email, "password_hash": password_hash},
            ).one()
            return User(id=row.id, email=row.email)

    try:
        return retry_on_disconnect(run)
    except IntegrityError:
        raise EmailTaken()


def get_credentials(email: str) -> tuple[User, str] | None:

    def run():
        with app_engine.connect() as conn:
            row = conn.execute(
                text("SELECT id, email, password_hash FROM app.users WHERE email = :email"),
                {"email": email},
            ).first()
            return (User(id=row.id, email=row.email), row.password_hash) if row else None

    return retry_on_disconnect(run)


def create_session(user_id: int, token: str) -> None:
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.session_ttl_days)

    def run():
        with app_engine.begin() as conn:
            conn.execute(
                text("DELETE FROM app.user_sessions WHERE expires_at < now()")
            )
            conn.execute(
                text("""
                    INSERT INTO app.user_sessions (token_hash, user_id, expires_at)
                    VALUES (:token_hash, :user_id, :expires_at)
                """),
                {"token_hash": token_digest(token), "user_id": user_id, "expires_at": expires_at},
            )

    retry_on_disconnect(run)


def get_user_by_token(token: str) -> User | None:

    def run():
        with app_engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT u.id, u.email
                    FROM app.user_sessions s
                    JOIN app.users u ON u.id = s.user_id
                    WHERE s.token_hash = :token_hash AND s.expires_at > now()
                """),
                {"token_hash": token_digest(token)},
            ).first()
            return User(id=row.id, email=row.email) if row else None

    return retry_on_disconnect(run)


def delete_session(token: str) -> None:

    def run():
        with app_engine.begin() as conn:
            conn.execute(
                text("DELETE FROM app.user_sessions WHERE token_hash = :token_hash"),
                {"token_hash": token_digest(token)},
            )

    retry_on_disconnect(run)
