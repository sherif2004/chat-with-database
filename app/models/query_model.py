from typing import Any

from pydantic import BaseModel
from sqlalchemy import text

from app.config import settings
from app.dialects import POSTGRES, Dialect
from app.models.database import retry_on_disconnect


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool = False


def execute_sql(sql, engine, dialect: Dialect = POSTGRES) -> QueryResult:
    """Run a query with a timeout, in a read-only session where the engine
    supports one.

    The SQL guard is the first line of defence; for engines that can refuse
    writes themselves (`dialect.read_only_enforced`) this is the second.
    `sql` is a single SELECT that already passed the guard.
    """

    def run():

        with engine.connect() as conn:

            if dialect is POSTGRES:
                conn = conn.execution_options(postgresql_readonly=True)

            dialect.prepare(conn)

            try:
                result = conn.execute(text(sql))
                columns = list(result.keys())
                rows = result.fetchmany(settings.max_rows + 1)
            finally:
                dialect.reset(conn)

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
