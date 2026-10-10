from typing import Any

from pydantic import BaseModel
from sqlalchemy import text

from app.config import settings
from app.models.database import retry_on_disconnect


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool = False


def execute_sql(sql, engine) -> QueryResult:
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


class WriteRefused(Exception):
    """A change that must not be committed (too many rows, or the row count
    differs from what the admin was shown)."""


def dry_run_write(sql, engine) -> int:
    """Run an INSERT/UPDATE/DELETE inside a transaction, count the rows it
    touches, and roll back. Nothing is saved."""

    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            conn.execute(text(f"SET LOCAL statement_timeout = {settings.statement_timeout_ms}"))
            return conn.execute(text(sql)).rowcount
        finally:
            transaction.rollback()


def commit_write(sql, engine, expected_rows: int) -> int:
    """Run the change for real, committing only if it touches exactly the
    number of rows the admin confirmed. Never retried: a retry after a lost
    connection could apply it twice."""

    with engine.begin() as conn:
        conn.execute(text(f"SET LOCAL statement_timeout = {settings.statement_timeout_ms}"))
        rows = conn.execute(text(sql)).rowcount

        if rows != expected_rows or rows > settings.max_write_rows:
            raise WriteRefused()  # leaving the block rolls back

        return rows
