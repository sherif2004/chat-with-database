# Multi-database connections — design

## Goal
Let a user connect and chat with any SQL database they own, not only PostgreSQL,
through the existing "connect your database" flow. Success: the same safe,
read-only pipeline (input guard, SQL guard, read-only execution with timeout
and row cap) works for each supported engine.

## Scope
- In: SQL databases reachable through a SQLAlchemy dialect + driver.
- Out: NoSQL (MongoDB, Redis, Elasticsearch). Separate sub-projects.
- Out (first version): admin data changes (preview/confirm) on non-Postgres
  engines; SQLite file paths typed by users (server filesystem exposure).

## Libraries
- SQLAlchemy: connect, introspect, execute.
- sqlglot: parse/validate in the engine's dialect.
- Optional driver extras per engine (pymysql, pyodbc, oracledb,
  snowflake-sqlalchemy, sqlalchemy-bigquery, clickhouse-sqlalchemy, ...).

## Architecture
A `Dialect` adapter registry (`app/dialects/`), keyed by SQLAlchemy driver name:
- `sqlglot_dialect`: name passed to `sqlglot.parse(read=...)` and `.sql(dialect=...)`.
- `readonly_and_timeout(conn)`: engine-specific read-only + statement timeout.
- `forbidden_functions`: engine-specific deny list.
- `default_schema` / `schemas`: what to introspect and allow in the guard.
- `prompt_hint`: short note for the SQL-writing prompt (e.g. `TOP` vs `LIMIT`).

Tiers:
1. Curated: Postgres, MySQL/MariaDB, SQL Server, Snowflake, BigQuery, ClickHouse.
   Full read-only + timeout enforcement, tested.
2. Generic fallback: any other installed SQLAlchemy driver. sqlglot dialect
   mapped from driver name or generic. SQL guard only; the UI warns the user to
   use read-only credentials.

`SessionConnection` carries its adapter. `sql_guard.validate_sql`,
`query_model.execute_sql`, `schema_model.get_database_schema` and the prompts
take it as a parameter instead of assuming Postgres. Postgres behaviour is
unchanged.

## Connect UX
`DatabasePanel.jsx`: engine dropdown + host/port/database/user/password, plus a
"paste a URL" option. The backend builds the URL with `URL.create(...)` so
special characters in passwords are safe. Storage stays encrypted per user.

## Safety
- Guard stays SELECT-only over known tables, parsed in the engine's dialect.
- Block connections to private/internal addresses (SSRF), configurable via
  settings for self-hosters.
- Driver allow-list check before `create_engine`; clear error if the driver
  package is not installed.

## Testing
- Unit tests per adapter: guard accept/reject cases, read-only/timeout SQL.
- Integration tests against MySQL and SQL Server containers added to
  `docker/docker-compose.yml`.
- Regression: existing Postgres tests unchanged and passing.

## Open items
None blocking. Oracle and the other warehouses start in the generic tier.
