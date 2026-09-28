import logging
from contextlib import contextmanager
from urllib.parse import quote

from langgraph.checkpoint.postgres import PostgresSaver

from app.config import settings

logger = logging.getLogger(__name__)


def _with_app_schema_search_path(url: str) -> str:
    """PostgresSaver creates its tables (checkpoints, checkpoint_blobs, ...)
    with unqualified names in whatever schema is first on the connection's
    search_path. Point that at "app" — the same schema chat_history,
    connections and workflow settings already use — so they don't land in
    "public" and pollute get_database_schema()'s introspection (that's
    hardcoded to "public", since it's what describes the user's actual
    data; see app/models/schema_model.py)."""

    options = quote("-c search_path=app,public")
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}options={options}"


@contextmanager
def open_checkpointer():
    """Open the checkpointer's own Postgres connection for the app's
    lifetime, create its tables if missing, and yield it — or yield None
    if it can't be reached, so a storage hiccup here degrades to
    "no mid-turn crash recovery" instead of failing app startup.

    Reuses the same database as the app's own bookkeeping (chat history,
    saved connections); the checkpointer manages its own tables there.
    """

    conn_cm = PostgresSaver.from_conn_string(_with_app_schema_search_path(settings.database_url))

    try:
        checkpointer = conn_cm.__enter__()
        checkpointer.setup()
    except Exception as e:
        logger.warning("Graph checkpointing is off: %s", e)
        yield None
        return

    try:
        yield checkpointer
    finally:
        conn_cm.__exit__(None, None, None)
