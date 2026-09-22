from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError

from app.config import settings

# PostgreSQL (Supabase). No pool_pre_ping: it costs a round trip on every
# checkout. Stale connections are recycled and retried instead (see below).
engine = create_engine(
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
