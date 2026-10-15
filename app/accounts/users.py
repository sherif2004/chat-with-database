import logging
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.shared.database import app_engine, retry_on_disconnect, run_ddl
from app.shared.crypto import token_digest

logger = logging.getLogger(__name__)


class User(BaseModel):
    id: int
    email: str
    role: str = "user"
    created_at: datetime | None = None


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
        """
        ALTER TABLE app.users
        ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'user'
        CHECK (role IN ('user', 'supervisor', 'admin'))
        """,
    )


def _user(row) -> User:
    return User(id=row.id, email=row.email, role=row.role, created_at=row.created_at)


def create_user(email: str, password_hash: str, role: str = "user") -> User:

    def run():
        with app_engine.begin() as conn:
            row = conn.execute(
                text("""
                    INSERT INTO app.users (email, password_hash, role)
                    VALUES (:email, :password_hash, :role)
                    RETURNING id, email, role, created_at
                """),
                {"email": email, "password_hash": password_hash, "role": role},
            ).one()
            return _user(row)

    try:
        return retry_on_disconnect(run)
    except IntegrityError:
        raise EmailTaken()


def get_credentials(email: str) -> tuple[User, str] | None:

    def run():
        with app_engine.connect() as conn:
            row = conn.execute(
                text("SELECT id, email, role, created_at, password_hash FROM app.users WHERE email = :email"),
                {"email": email},
            ).first()
            return (_user(row), row.password_hash) if row else None

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
                    SELECT u.id, u.email, u.role, u.created_at
                    FROM app.user_sessions s
                    JOIN app.users u ON u.id = s.user_id
                    WHERE s.token_hash = :token_hash AND s.expires_at > now()
                """),
                {"token_hash": token_digest(token)},
            ).first()
            return _user(row) if row else None

    return retry_on_disconnect(run)


def delete_session(token: str) -> None:

    def run():
        with app_engine.begin() as conn:
            conn.execute(
                text("DELETE FROM app.user_sessions WHERE token_hash = :token_hash"),
                {"token_hash": token_digest(token)},
            )

    retry_on_disconnect(run)


def list_users() -> list[User]:

    def run():
        with app_engine.connect() as conn:
            result = conn.execute(
                text("SELECT id, email, role, created_at FROM app.users ORDER BY id")
            )
            return [_user(row) for row in result]

    return retry_on_disconnect(run)


def get_user(user_id: int) -> User | None:

    def run():
        with app_engine.connect() as conn:
            row = conn.execute(
                text("SELECT id, email, role, created_at FROM app.users WHERE id = :id"),
                {"id": user_id},
            ).first()
            return _user(row) if row else None

    return retry_on_disconnect(run)


class LastAdmin(Exception):
    pass


def set_role(user_id: int, role: str) -> User | None:
    """Changes a role and ends the user's sessions so it applies on their next
    login. Refuses to demote the last admin; the admin rows are locked so two
    concurrent demotions cannot both succeed."""

    def run():
        with app_engine.begin() as conn:
            admins = conn.execute(
                text("SELECT id FROM app.users WHERE role = 'admin' FOR UPDATE")
            ).scalars().all()

            if role != "admin" and admins == [user_id]:
                raise LastAdmin()

            row = conn.execute(
                text("""
                    UPDATE app.users SET role = :role WHERE id = :id
                    RETURNING id, email, role, created_at
                """),
                {"role": role, "id": user_id},
            ).first()

            if row:
                conn.execute(
                    text("DELETE FROM app.user_sessions WHERE user_id = :id"),
                    {"id": user_id},
                )

            return _user(row) if row else None

    return retry_on_disconnect(run)


def remove_user(user_id: int) -> bool:
    """Deletes the account, its sessions (by cascade), conversations, history
    and saved connection. Refuses to delete the last admin."""

    owner = f"u:{user_id}"

    def run():
        with app_engine.begin() as conn:
            admins = conn.execute(
                text("SELECT id FROM app.users WHERE role = 'admin' FOR UPDATE")
            ).scalars().all()

            if admins == [user_id]:
                raise LastAdmin()

            deleted = conn.execute(
                text("DELETE FROM app.users WHERE id = :id"), {"id": user_id}
            ).rowcount

            if deleted:
                conn.execute(text("DELETE FROM app.chat_history WHERE session_id = :o"), {"o": owner})
                conn.execute(text("DELETE FROM app.conversations WHERE owner = :o"), {"o": owner})

            return bool(deleted)

    return retry_on_disconnect(run)


def seed_admin(email: str, password_hash: str) -> None:
    """Creates the configured admin, or takes over the account if the email
    already exists. The configured password replaces the stored one and every
    existing session ends, so whoever registered the address first (before the
    operator) cannot keep access to it. Safe to run on every startup."""

    def run():
        with app_engine.begin() as conn:
            user_id = conn.execute(
                text("""
                    INSERT INTO app.users (email, password_hash, role)
                    VALUES (:email, :password_hash, 'admin')
                    ON CONFLICT (email) DO UPDATE SET
                        role = 'admin',
                        password_hash = EXCLUDED.password_hash
                    RETURNING id
                """),
                {"email": email, "password_hash": password_hash},
            ).scalar_one()

            conn.execute(
                text("DELETE FROM app.user_sessions WHERE user_id = :id"), {"id": user_id}
            )

    retry_on_disconnect(run)
