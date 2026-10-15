import logging

from sqlalchemy import text

from app.shared.database import app_engine, run_ddl, run_or_log

logger = logging.getLogger(__name__)


def ensure_audit_schema() -> None:
    run_ddl(
        "CREATE SCHEMA IF NOT EXISTS app",
        """
        CREATE TABLE IF NOT EXISTS app.data_changes (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            email TEXT NOT NULL,
            connection_label TEXT NOT NULL,
            sql TEXT NOT NULL,
            rows_affected INTEGER NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
    )


def record_change(user_id: int, email: str, connection_label: str, sql: str, rows: int) -> None:
    """Best-effort record of a committed admin change; the change itself is
    already saved, so a logging failure is reported but never undoes it."""

    def run():
        with app_engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO app.data_changes (user_id, email, connection_label, sql, rows_affected)
                    VALUES (:user_id, :email, :label, :sql, :rows)
                """),
                {"user_id": user_id, "email": email, "label": connection_label, "sql": sql, "rows": rows},
            )

    run_or_log(run, logger, "Could not record data change by user %s: %s", user_id)
