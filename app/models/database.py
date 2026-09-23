from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError

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
