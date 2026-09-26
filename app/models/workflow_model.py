import logging
from typing import Literal

from sqlalchemy import text

from app.models.database import app_engine, run_ddl, run_or_log

logger = logging.getLogger(__name__)

Workflow = Literal["router", "no_router"]

_DEFAULT_WORKFLOW: Workflow = "router"

# session_id -> workflow. Mirrors connection_model's cache: avoids a DB
# round trip on every chat message once a session's preference is known.
_cache: dict[str, Workflow] = {}


def ensure_workflow_schema() -> None:
    """Create the app.session_settings table if it doesn't exist yet."""

    run_ddl(
        "CREATE SCHEMA IF NOT EXISTS app",
        """
        CREATE TABLE IF NOT EXISTS app.session_settings (
            session_id TEXT PRIMARY KEY,
            workflow TEXT NOT NULL DEFAULT 'router',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
    )


def set_workflow(session_id: str, workflow: Workflow) -> None:

    _cache[session_id] = workflow

    def run():
        with app_engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO app.session_settings (session_id, workflow, updated_at)
                    VALUES (:session_id, :workflow, now())
                    ON CONFLICT (session_id) DO UPDATE SET
                        workflow = EXCLUDED.workflow,
                        updated_at = now()
                """),
                {"session_id": session_id, "workflow": workflow},
            )

    run_or_log(run, logger, "Could not save workflow preference for session %s: %s", session_id)


def get_workflow(session_id: str) -> Workflow:

    if session_id in _cache:
        return _cache[session_id]

    def run():
        with app_engine.connect() as conn:
            row = conn.execute(
                text("SELECT workflow FROM app.session_settings WHERE session_id = :session_id"),
                {"session_id": session_id},
            ).first()
            return row.workflow if row else None

    workflow = run_or_log(run, logger, "Could not read workflow preference for session %s: %s", session_id)

    resolved = workflow or _DEFAULT_WORKFLOW
    _cache[session_id] = resolved
    return resolved
