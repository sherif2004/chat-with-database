import logging
from dataclasses import dataclass

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.exc import SQLAlchemyError

from app.databases.engines import POSTGRES, Dialect, UnsupportedDatabase, for_url, require_installed
from app.databases.network_guard import PrivateHostBlocked, check_host, pin_to_public_address, verify_peer
from app.shared.database import app_engine, run_ddl, run_or_log
from app.databases.schema import DatabaseSchema, default_schema_name, get_database_schema, schema_to_text
from app.shared.crypto import SecretKeyMissing, decrypt, encrypt

logger = logging.getLogger(__name__)

class DatabaseConnectionError(Exception):
    """A user-supplied database URL was invalid or could not be reached."""


@dataclass
class SessionConnection:
    engine: Engine
    schema: DatabaseSchema
    schema_text: str
    label: str
    is_default: bool
    dialect: Dialect = POSTGRES
    schema_name: str | None = "public"


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


def _label_for(database_url: str | URL) -> str:
    url = make_url(database_url) if isinstance(database_url, str) else database_url
    host = url.host or "localhost"
    database = url.database or ""
    return f"{host}/{database}" if database else host


def _build_engine(database_url: str | URL) -> tuple[Engine, Dialect]:
    try:
        url = make_url(database_url) if isinstance(database_url, str) else database_url
        dialect = for_url(url)
        require_installed(dialect)
        if dialect.network_host:
            check_host(url.host)
    except (UnsupportedDatabase, PrivateHostBlocked) as e:
        raise DatabaseConnectionError(str(e))
    except Exception as e:
        raise DatabaseConnectionError(f"That doesn't look like a valid database URL: {e}")

    try:
        engine = create_engine(url, pool_recycle=300, connect_args=dict(dialect.connect_args))
        if dialect.network_host:
            event.listen(engine, "do_connect", pin_to_public_address)
            event.listen(engine, "connect", verify_peer, insert=True)
    except Exception as e:
        raise DatabaseConnectionError(f"Could not set up that connection: {e}")

    return engine, dialect


def _test_and_introspect(engine: Engine) -> tuple[DatabaseSchema, str | None]:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        schema_name = default_schema_name(engine)
        return get_database_schema(engine, schema_name), schema_name

    except SQLAlchemyError as e:
        engine.dispose()
        raise DatabaseConnectionError(f"Could not connect to that database: {getattr(e, "orig", None) or e}")


def _connect_and_introspect(database_url: str | URL) -> tuple[Engine, Dialect, DatabaseSchema, str | None]:
    engine, dialect = _build_engine(database_url)
    schema, schema_name = _test_and_introspect(engine)
    return engine, dialect, schema, schema_name


def _make_connection(
    engine: Engine, dialect: Dialect, schema: DatabaseSchema, schema_name: str | None, label: str
) -> SessionConnection:
    return SessionConnection(
        engine=engine,
        schema=schema,
        schema_text=schema_to_text(schema),
        label=label,
        is_default=False,
        dialect=dialect,
        schema_name=schema_name,
    )


@dataclass
class ConnectionCheck:
    label: str
    dialect: Dialect
    table_count: int


def check_connection(database_url: str | URL) -> ConnectionCheck:
    """Try a connection without saving it, so the UI can say whether it works."""

    engine, dialect, schema, _schema_name = _connect_and_introspect(database_url)
    try:
        return ConnectionCheck(_label_for(database_url), dialect, len(schema.tables))
    finally:
        engine.dispose()


def ensure_connections_schema() -> None:
    """Create the app.user_connections table if it doesn't exist yet.

    `session_id` holds the signed-in user's id. URLs are stored encrypted
    (see crypto_service); the older plaintext app.connections table is no
    longer read."""

    run_ddl(
        "CREATE SCHEMA IF NOT EXISTS app",
        """
        CREATE TABLE IF NOT EXISTS app.user_connections (
            session_id TEXT PRIMARY KEY,
            database_url_encrypted TEXT NOT NULL,
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


def _save_connection_row(session_id: str, encrypted_url: str, label: str) -> None:

    def run():
        with app_engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO app.user_connections (session_id, database_url_encrypted, label, updated_at)
                    VALUES (:session_id, :database_url, :label, now())
                    ON CONFLICT (session_id) DO UPDATE SET
                        database_url_encrypted = EXCLUDED.database_url_encrypted,
                        label = EXCLUDED.label,
                        updated_at = now()
                """),
                {"session_id": session_id, "database_url": encrypted_url, "label": label},
            )

    run_or_log(run, logger, "Could not save connection for session %s: %s", session_id)


def _load_saved_url(session_id: str) -> str | None:

    def run():
        with app_engine.connect() as conn:
            row = conn.execute(
                text("SELECT database_url_encrypted FROM app.user_connections WHERE session_id = :session_id"),
                {"session_id": session_id},
            ).first()
            return row.database_url_encrypted if row else None

    encrypted = run_or_log(run, logger, "Could not read saved connection for session %s: %s", session_id)

    if encrypted is None:
        return None

    try:
        url = decrypt(encrypted)
    except SecretKeyMissing:
        logger.warning("APP_SECRET_KEY is not set; ignoring saved connection for session %s", session_id)
        return None

    if url is None:
        logger.warning("Saved connection for session %s could not be decrypted", session_id)

    return url


def connect(session_id: str, database_url: str | URL, label: str | None = None) -> SessionConnection:
    """Connect a session to a new database, replacing any existing one."""

    url_text = database_url if isinstance(database_url, str) else database_url.render_as_string(hide_password=False)
    encrypted_url = encrypt(url_text)  # fails fast if APP_SECRET_KEY is unset

    engine, dialect, schema, schema_name = _connect_and_introspect(database_url)
    resolved_label = label or _label_for(database_url)

    old = _cache.get(session_id)
    if old is not None:
        old.engine.dispose()

    connection = _make_connection(engine, dialect, schema, schema_name, resolved_label)
    _cache[session_id] = connection
    _save_connection_row(session_id, encrypted_url, resolved_label)

    return connection


def forget_connection(session_id: str) -> None:
    """Drop a session's saved connection (used when its account is deleted)."""

    old = _cache.pop(session_id, None)
    if old is not None:
        old.engine.dispose()

    def run():
        with app_engine.begin() as conn:
            conn.execute(
                text("DELETE FROM app.user_connections WHERE session_id = :session_id"),
                {"session_id": session_id},
            )

    run_or_log(run, logger, "Could not delete connection for session %s: %s", session_id)


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

    engine, dialect, schema, schema_name = _connect_and_introspect(saved_url)
    connection = _make_connection(engine, dialect, schema, schema_name, _label_for(saved_url))

    _cache[session_id] = connection
    return connection
