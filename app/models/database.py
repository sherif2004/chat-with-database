import logging

from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from app.config import settings

# PostgreSQL (Supabase). No pool_pre_ping: it costs a round trip on every
# checkout. Stale connections are recycled and retried instead (see below).
#
# This engine is reserved for the app's own bookkeeping (chat history,
# saved connections) — never for a user-supplied database. See
# app/models/connection_model.py for the per-session target engines that
# a "connect to my database" request creates.
app_engine = create_engine(
    settings.database_url,
    pool_recycle=300
)


def retry_on_disconnect(operation):
    """Run `operation()`, retrying once if the pooled connection had been dropped."""

    try:
        return operation()

    except DBAPIError as e:
        if not e.connection_invalidated:
            raise

        return operation()


def run_ddl(*statements: str) -> None:
    """Run DDL statements against app_engine in one transaction, retrying
    once on a dropped connection. Used by each subsystem's ensure_*_schema()
    so a missing table only disables that one subsystem, not the others."""

    def run():
        with app_engine.begin() as conn:
            for statement in statements:
                conn.execute(text(statement))

    retry_on_disconnect(run)


def run_or_log(operation, logger: logging.Logger, message: str, *args) -> None:
    """Run `operation()` via retry_on_disconnect; on failure, log a warning
    and return None instead of raising.

    Shared by every best-effort read/write in the app's own bookkeeping
    tables (chat history, saved connections, workflow settings) — a storage
    hiccup there must degrade gracefully, not break the request that
    triggered it.
    """

    try:
        return retry_on_disconnect(operation)
    except SQLAlchemyError as e:
        logger.warning(message, *args, e)
        return None
