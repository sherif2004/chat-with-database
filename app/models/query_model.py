from typing import Any

from pydantic import BaseModel
from sqlalchemy import text

from app.config import settings
from app.models.database import engine, retry_on_disconnect


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool = False


# ============================================================
# Execute SQL (read-only)
# ============================================================

def execute_sql(sql) -> QueryResult:
    """Run a query in a read-only transaction with a timeout.

    This is the last line of defence: even if a write got past the
    SQL guard, Postgres rejects it here. `sql` is a single SELECT that
    already passed the SQL guard, so the timeout can share its round trip.
    """

    def run():

        with engine.connect() as conn:

            conn = conn.execution_options(postgresql_readonly=True)

            result = conn.execute(text(
                f"SET LOCAL statement_timeout = {settings.statement_timeout_ms}; {sql}"
            ))

            columns = list(result.keys())

            rows = result.fetchmany(settings.max_rows + 1)

        return QueryResult(
            columns=columns,
            rows=[list(row) for row in rows[:settings.max_rows]],
            truncated=len(rows) > settings.max_rows
        )

    return retry_on_disconnect(run)
