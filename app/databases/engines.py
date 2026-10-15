"""Per-engine behaviour for the databases a user can connect.

A `Dialect` holds everything that differs between engines: how to write the
URL, how to parse the SQL the model writes (sqlglot), which functions to
refuse, and how to ask the engine for a read-only, time-limited session.

Curated engines are tested and enforce what the engine allows. Any other
SQLAlchemy engine whose driver is installed works as a generic dialect: the
SQL guard still allows only SELECTs, but the engine itself is not asked to
refuse writes, so users are told to connect with a read-only account.
"""

import base64
import binascii
import json
import re
from dataclasses import dataclass, field
from importlib.util import find_spec
from typing import Callable

from sqlalchemy.engine import Connection, URL, make_url
from sqlalchemy.exc import ArgumentError

from app.config import settings


def _noop(conn: Connection) -> None:
    return None


def _postgres_prepare(conn: Connection) -> None:
    conn.exec_driver_sql(f"SET LOCAL statement_timeout = {int(settings.statement_timeout_ms)}")


def _mysql_prepare(conn: Connection) -> None:
    conn.exec_driver_sql("SET SESSION TRANSACTION READ ONLY")
    try:
        conn.exec_driver_sql(f"SET SESSION MAX_EXECUTION_TIME = {int(settings.statement_timeout_ms)}")
    except Exception:
        # MariaDB names this max_statement_time and counts in seconds.
        conn.exec_driver_sql(f"SET SESSION max_statement_time = {settings.statement_timeout_ms / 1000}")


def _mysql_reset(conn: Connection) -> None:
    conn.exec_driver_sql("SET SESSION TRANSACTION READ WRITE")


def _snowflake_prepare(conn: Connection) -> None:
    conn.exec_driver_sql(
        f"ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = {int(settings.statement_timeout_ms / 1000)}"
    )


def _mssql_prepare(conn: Connection) -> None:
    conn.exec_driver_sql(f"SET LOCK_TIMEOUT {int(settings.statement_timeout_ms)}")


def _clickhouse_prepare(conn: Connection) -> None:
    conn.exec_driver_sql(f"SET max_execution_time = {int(settings.statement_timeout_ms / 1000)}")


@dataclass(frozen=True)
class Dialect:
    key: str                      # id the UI sends, e.g. "mysql"
    name: str                     # shown to people and put in the SQL prompt
    backend: str                  # SQLAlchemy backend name, e.g. "mysql"
    driver: str                   # full SQLAlchemy drivername, e.g. "mysql+pymysql"
    module: str                   # importable module the driver needs
    package: str                  # pip package that provides it
    sqlglot: str | None           # sqlglot dialect name; None = generic SQL
    default_port: int | None = None
    curated: bool = False
    # What the engine itself refuses, not just the SQL guard.
    read_only_enforced: bool = False
    supports_writes: bool = False
    needs_host: bool = True
    # False when the "host" is an account or project id, not a network name.
    network_host: bool = True
    quote: str = '"'
    limit_hint: str = "add a LIMIT"
    forbidden_prefixes: tuple[str, ...] = ()
    forbidden_functions: frozenset[str] = frozenset()
    connect_args: dict = field(default_factory=dict)
    url_query: dict = field(default_factory=dict)
    # URL query options a user may set. Anything else is refused: driver
    # options can read local files, load certificates or redirect the host.
    allowed_query: frozenset[str] = frozenset()
    prepare: Callable[[Connection], None] = _noop
    reset: Callable[[Connection], None] = _noop

    @property
    def installed(self) -> bool:
        try:
            return find_spec(self.module) is not None
        except (ImportError, ValueError):
            return False

    @property
    def quote_rule(self) -> str:
        if self.quote == "`":
            return "Always wrap table and column names in backticks, exactly as they appear in the schema."
        if self.quote == "[":
            return "Always wrap table and column names in square brackets, exactly as they appear in the schema."
        return "Always wrap table and column names in double quotes, exactly as they appear in the schema."


POSTGRES = Dialect(
    key="postgresql", name="PostgreSQL", backend="postgresql", driver="postgresql+psycopg2",
    module="psycopg2", package="psycopg2-binary", sqlglot="postgres", default_port=5432,
    curated=True, read_only_enforced=True, supports_writes=True, limit_hint="add a LIMIT",
    forbidden_prefixes=(
        "pg_", "lo_", "dblink", "query_to_", "table_to_", "schema_to_", "database_to_", "cursor_to_",
    ),
    forbidden_functions=frozenset({
        "set_config", "current_setting", "ts_stat", "ts_rewrite", "txid_current", "nextval", "setval", "currval", "version",
    }),
    connect_args={"connect_timeout": 5},
    allowed_query=frozenset({"sslmode", "application_name"}),
    prepare=_postgres_prepare,
)

MYSQL = Dialect(
    key="mysql", name="MySQL / MariaDB", backend="mysql", driver="mysql+pymysql",
    module="pymysql", package="pymysql", sqlglot="mysql", default_port=3306,
    curated=True, read_only_enforced=True, quote="`", limit_hint="add a LIMIT",
    forbidden_functions=frozenset({
        "load_file", "sleep", "benchmark", "get_lock", "release_lock", "sys_exec", "sys_eval",
    }),
    connect_args={"connect_timeout": 5, "local_infile": False},
    allowed_query=frozenset({"charset"}),
    prepare=_mysql_prepare, reset=_mysql_reset,
)

MSSQL = Dialect(
    key="mssql", name="SQL Server", backend="mssql", driver="mssql+pyodbc",
    module="pyodbc", package="pyodbc", sqlglot="tsql", default_port=1433,
    curated=True, quote="[", limit_hint="use SELECT TOP n (there is no LIMIT)",
    forbidden_prefixes=("xp_", "sp_", "fn_"),
    forbidden_functions=frozenset({"openrowset", "openquery", "opendatasource"}),
    connect_args={"timeout": 5},
    url_query={"driver": "ODBC Driver 18 for SQL Server"},
    allowed_query=frozenset({"driver", "Encrypt", "TrustServerCertificate"}),
    prepare=_mssql_prepare,
)

SNOWFLAKE = Dialect(
    key="snowflake", name="Snowflake", backend="snowflake", driver="snowflake",
    module="snowflake.sqlalchemy", package="snowflake-sqlalchemy", sqlglot="snowflake",
    curated=True, network_host=False, limit_hint="add a LIMIT",
    allowed_query=frozenset({"warehouse", "role", "schema"}),
    prepare=_snowflake_prepare,
)

BIGQUERY = Dialect(
    key="bigquery", name="BigQuery", backend="bigquery", driver="bigquery",
    module="sqlalchemy_bigquery", package="sqlalchemy-bigquery", sqlglot="bigquery",
    curated=True, needs_host=False, network_host=False, quote="`", limit_hint="add a LIMIT",
    allowed_query=frozenset({"credentials_base64", "location"}),
)

CLICKHOUSE = Dialect(
    key="clickhouse", name="ClickHouse", backend="clickhouse", driver="clickhouse+native",
    module="clickhouse_sqlalchemy", package="clickhouse-sqlalchemy", sqlglot="clickhouse",
    default_port=9000, curated=True, limit_hint="add a LIMIT",
    forbidden_functions=frozenset({"file", "url", "s3", "hdfs", "remote", "mysql", "postgresql", "jdbc"}),
    allowed_query=frozenset({"secure", "verify"}),
    prepare=_clickhouse_prepare,
)

CURATED: tuple[Dialect, ...] = (POSTGRES, MYSQL, MSSQL, SNOWFLAKE, BIGQUERY, CLICKHOUSE)

# Network engines reachable by URL beyond the curated ones: SQLAlchemy backend
# name -> sqlglot dialect. This is an allowlist. Embedded engines (SQLite,
# DuckDB, Access, Firebird) are not here on purpose: their "host" is a file on
# the server, and anything not listed is refused rather than trusted.
_GENERIC_SQLGLOT = {
    "oracle": "oracle", "redshift": "redshift", "databricks": "databricks", "trino": "trino",
    "presto": "presto", "awsathena": "athena", "cockroachdb": "postgres", "starrocks": "starrocks",
    "doris": "doris", "hive": "hive", "impala": "hive", "spark": "spark", "teradata": "teradata",
    "db2": None, "hana": None, "vertica": None,
}

# File and URL readers a generic engine could expose through SQL.
_GENERIC_FORBIDDEN_FUNCTIONS = frozenset({
    "load_file", "read_csv", "read_csv_auto", "read_parquet", "read_json", "read_text",
    "read_blob", "glob", "httpfs", "external_query", "openrowset", "openquery",
})

_BY_BACKEND = {d.backend: d for d in CURATED}
_BY_KEY = {d.key: d for d in CURATED}


class UnsupportedDatabase(Exception):
    """The engine is blocked, or its driver package is not installed."""


def by_key(key: str) -> Dialect | None:
    return _BY_KEY.get(key)


# Host names, IPv4 and IPv6 literals. No spaces, slashes, commas, semicolons or `@`:
# those change what a URL or a driver connection string points at.
HOST_PATTERN = re.compile(r"^[A-Za-z0-9._:\-\[\]%]+$")

# A Snowflake account identifier, such as xy12345 or xy12345.eu-west-1.
_SNOWFLAKE_ACCOUNT = re.compile(r"^[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+)*$")

# Where a Google service-account key may fetch tokens from. A key can name any
# URL here, and the server would call it.
_GOOGLE_TOKEN_HOSTS = {"oauth2.googleapis.com", "accounts.google.com"}


def _check_snowflake(parsed: URL) -> None:
    """snowflake-sqlalchemy turns a bare account id into <id>.snowflakecomputing.com,
    but uses the typed host as is when there is a port or a snowflakecomputing.com
    in it. So only a bare account id is accepted."""

    host = parsed.host or ""
    if parsed.port is not None or "snowflakecomputing" in host.lower() or not _SNOWFLAKE_ACCOUNT.match(host):
        raise UnsupportedDatabase(
            "For Snowflake, enter only the account identifier (for example xy12345.eu-west-1), "
            "with no port and no snowflakecomputing.com."
        )


def _check_bigquery(parsed: URL) -> None:
    """A service-account key is a file of instructions the Google client follows,
    including where to send requests. Accept only an ordinary key that points at Google."""

    encoded = parsed.query.get("credentials_base64")
    if encoded is None:
        raise UnsupportedDatabase("BigQuery needs credentials_base64 (a base64 service-account key).")

    try:
        key = json.loads(base64.b64decode(str(encoded), validate=True))
    except (binascii.Error, ValueError, UnicodeDecodeError):
        raise UnsupportedDatabase("credentials_base64 isn't a base64-encoded service-account key.")

    token_host = ""
    if isinstance(key, dict) and isinstance(key.get("token_uri"), str):
        token_host = (key["token_uri"].split("://", 1)[-1].split("/", 1)[0]).lower()

    if (
        not isinstance(key, dict)
        or key.get("type") != "service_account"
        or token_host not in _GOOGLE_TOKEN_HOSTS
        or key.get("universe_domain", "googleapis.com") != "googleapis.com"
    ):
        raise UnsupportedDatabase("That isn't an ordinary Google service-account key.")


def _check_url(parsed: URL, dialect: Dialect) -> None:
    host = parsed.host or ""

    if dialect.needs_host and not host:
        raise UnsupportedDatabase("The connection URL needs a host (server address).")

    if host and not HOST_PATTERN.match(host):
        raise UnsupportedDatabase("The host should be a server name or IP address, with no spaces, slashes, commas or semicolons.")

    for key, value in parsed.query.items():
        if key not in dialect.allowed_query:
            allowed = ", ".join(sorted(dialect.allowed_query)) or "none"
            raise UnsupportedDatabase(
                f"The connection option '{key}' isn't allowed. Allowed options: {allowed}."
            )
        if key == "driver" and value not in ("ODBC Driver 17 for SQL Server", "ODBC Driver 18 for SQL Server"):
            raise UnsupportedDatabase("Only the Microsoft ODBC driver for SQL Server can be used.")

    if dialect.key == "snowflake":
        _check_snowflake(parsed)
    elif dialect.key == "bigquery":
        _check_bigquery(parsed)


def for_url(url: URL | str) -> Dialect:
    """The dialect for a connection URL, validated: curated if we know the
    engine, a generic one if it is on the network allowlist, otherwise refused."""

    try:
        parsed = make_url(url) if isinstance(url, str) else url
    except ArgumentError as e:
        raise UnsupportedDatabase(f"That doesn't look like a valid database URL: {e}")

    backend = parsed.get_backend_name()
    dialect = MYSQL if backend == "mariadb" else _BY_BACKEND.get(backend)

    if dialect is None:
        if backend not in _GENERIC_SQLGLOT:
            raise UnsupportedDatabase(
                f"'{backend}' isn't a supported database type. Embedded databases "
                "such as SQLite and DuckDB can't be opened from here, because they "
                "are files on the server."
            )
        driver_module = parsed.drivername.split("+")[-1] if "+" in parsed.drivername else backend
        dialect = Dialect(
            key=backend, name=backend.title(), backend=backend, driver=parsed.drivername,
            module=driver_module, package=driver_module, sqlglot=_GENERIC_SQLGLOT[backend],
            forbidden_functions=_GENERIC_FORBIDDEN_FUNCTIONS,
        )

    _check_url(parsed, dialect)
    return dialect


def build_url(dialect: Dialect, *, host: str, port: int | None, database: str,
              username: str, password: str) -> URL:
    """Build the URL from separate fields, so a password with `@` or `/` in it
    is escaped properly instead of breaking a hand-typed string."""

    return URL.create(
        drivername=dialect.driver,
        username=username or None,
        password=password or None,
        host=host or None,
        port=port or dialect.default_port,
        database=database or None,
        query=dict(dialect.url_query),
    )


def require_installed(dialect: Dialect) -> None:
    if not dialect.installed:
        raise UnsupportedDatabase(
            f"Support for {dialect.name} isn't installed on this server. "
            f"Ask the administrator to run: pip install {dialect.package}"
        )
