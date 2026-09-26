import logging
from dataclasses import dataclass

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError

from app.models.database import app_engine, run_ddl, run_or_log
from app.models.schema_model import DatabaseSchema, get_database_schema, schema_to_text

logger = logging.getLogger(__name__)

# Phase 1: Postgres only. The SQL guard and prompt generation are written
# against Postgres semantics — supporting other dialects needs guardrail
# changes and is tracked as a follow-up, not attempted here.
_ALLOWED_DRIVERNAMES = {"postgresql", "postgresql+psycopg2", "postgresql+psycopg"}

_CONNECT_TIMEOUT_SECONDS = 5


class DatabaseConnectionError(Exception):
    """A user-supplied database URL was invalid or could not be reached."""


@dataclass
class SessionConnection:
    engine: Engine
    schema: DatabaseSchema
    schema_text: str
    label: str
    is_default: bool


# session_id -> SessionConnection, for sessions that connected their own DB.
_cache: dict[str, SessionConnection] = {}

# Sessions confirmed to have no saved connection, so get_or_default() can
# skip the app.connections round trip on every subsequent chat message.
# Cleared implicitly on process restart; connect() makes it irrelevant for
# a session by putting it in _cache instead.
_no_saved_connection: set[str] = set()

# Computed once at startup from settings.database_url; used by any session
# that hasn't connected a database of its own.
_default_connection: SessionConnection | None = None


def _label_for(database_url: str) -> str:
    url = make_url(database_url)
    host = url.host or "localhost"
    database = url.database or ""
    return f"{host}/{database}" if database else host


def _build_engine(database_url: str) -> Engine:
    try:
        url = make_url(database_url)
    except Exception as e:
        raise DatabaseConnectionError(f"That doesn't look like a valid database URL: {e}")

    if url.drivername not in _ALLOWED_DRIVERNAMES:
        raise DatabaseConnectionError(
            "Only PostgreSQL connections are supported right now "
            "(a postgresql:// URL)."
        )

    return create_engine(
        database_url,
        pool_recycle=300,
        connect_args={"connect_timeout": _CONNECT_TIMEOUT_SECONDS},
    )


def _test_and_introspect(engine: Engine) -> DatabaseSchema:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        return get_database_schema(engine)

    except SQLAlchemyError as e:
        engine.dispose()
        raise DatabaseConnectionError(f"Could not connect to that database: {e.orig or e}")


def _connect_and_introspect(database_url: str) -> tuple[Engine, DatabaseSchema]:
    engine = _build_engine(database_url)
    return engine, _test_and_introspect(engine)


def _make_connection(engine: Engine, schema: DatabaseSchema, label: str) -> SessionConnection:
    return SessionConnection(
        engine=engine,
        schema=schema,
        schema_text=schema_to_text(schema),
        label=label,
        is_default=False,
    )


def ensure_connections_schema() -> None:
    """Create the app.connections table if it doesn't exist yet."""

    run_ddl(
        "CREATE SCHEMA IF NOT EXISTS app",
        """
        CREATE TABLE IF NOT EXISTS app.connections (
            session_id TEXT PRIMARY KEY,
            database_url TEXT NOT NULL,
            label TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
    )


def init_default_connection() -> None:
    """Introspect the default (.env) database once at startup."""

    global _default_connection

    schema = get_database_schema(app_engine)

    _default_connection = SessionConnection(
        engine=app_engine,
        schema=schema,
        schema_text=schema_to_text(schema),
        label=_label_for(str(app_engine.url)),
        is_default=True,
    )


def get_default_connection() -> SessionConnection:
    assert _default_connection is not None, "init_default_connection() was not called"
    return _default_connection


def _save_connection_row(session_id: str, database_url: str, label: str) -> None:

    def run():
        with app_engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO app.connections (session_id, database_url, label, updated_at)
                    VALUES (:session_id, :database_url, :label, now())
                    ON CONFLICT (session_id) DO UPDATE SET
                        database_url = EXCLUDED.database_url,
                        label = EXCLUDED.label,
                        updated_at = now()
                """),
                {"session_id": session_id, "database_url": database_url, "label": label},
            )

    run_or_log(run, logger, "Could not save connection for session %s: %s", session_id)


def _load_saved_url(session_id: str) -> str | None:

    def run():
        with app_engine.connect() as conn:
            row = conn.execute(
                text("SELECT database_url FROM app.connections WHERE session_id = :session_id"),
                {"session_id": session_id},
            ).first()
            return row.database_url if row else None

    return run_or_log(run, logger, "Could not read saved connection for session %s: %s", session_id)


def connect(session_id: str, database_url: str, label: str | None = None) -> SessionConnection:
    """Connect a session to a new database, replacing any existing one."""

    engine, schema = _connect_and_introspect(database_url)
    resolved_label = label or _label_for(database_url)

    old = _cache.get(session_id)
    if old is not None:
        old.engine.dispose()

    connection = _make_connection(engine, schema, resolved_label)
    _cache[session_id] = connection
    _save_connection_row(session_id, database_url, resolved_label)

    return connection


def get_or_default(session_id: str) -> SessionConnection:
    """Return the session's connection, lazily reconnecting from a saved
    row if needed, otherwise the default (.env) connection.

    Raises DatabaseConnectionError if the session has a saved connection
    that can no longer be reached — callers decide how to surface that.
    """

    cached = _cache.get(session_id)
    if cached is not None:
        return cached

    if session_id in _no_saved_connection:
        return get_default_connection()

    saved_url = _load_saved_url(session_id)
    if saved_url is None:
        _no_saved_connection.add(session_id)
        return get_default_connection()

    engine, schema = _connect_and_introspect(saved_url)
    connection = _make_connection(engine, schema, _label_for(saved_url))

    _cache[session_id] = connection
    return connection
