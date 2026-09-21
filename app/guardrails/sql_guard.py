import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from app.guardrails.errors import GuardrailError, UnknownTableError

# Anything that can write, change structure, or run commands.
_FORBIDDEN_NODES = tuple(
    getattr(exp, name)
    for name in (
        "Insert", "Update", "Delete", "Merge", "Drop", "Create", "Alter",
        "TruncateTable", "Command", "Copy", "Into", "Lock", "Set", "Grant",
        "Revoke", "Transaction", "Commit", "Rollback", "Use", "Pragma",
    )
    if hasattr(exp, name)
)

# Functions that read files, sleep, reach other servers or change settings.
_FORBIDDEN_FUNCTION_PREFIXES = ("pg_", "lo_", "dblink")
_FORBIDDEN_FUNCTIONS = {
    "set_config", "current_setting", "query_to_xml", "table_to_xml",
    "database_to_xml", "schema_to_xml", "cursor_to_xml", "txid_current",
    "nextval", "setval", "currval", "version",
}

_ALLOWED_SCHEMAS = {"", "public"}


def _function_name(func: exp.Expression) -> str:
    if isinstance(func, exp.Anonymous):
        return str(func.name).lower()
    return func.sql_name().lower()


def validate_sql(sql: str, allowed_tables: set[str]) -> str:
    """Accept only a single read-only SELECT over known tables."""

    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except SqlglotError:
        raise GuardrailError("The generated query could not be parsed.")

    if len(statements) != 1:
        raise GuardrailError("Exactly one SQL statement is allowed.")

    statement = statements[0]

    if not isinstance(statement, exp.Query):
        raise GuardrailError("Only SELECT queries are allowed.")

    for node in statement.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            raise GuardrailError("Only read-only SELECT queries are allowed.")

    cte_names = {cte.alias for cte in statement.find_all(exp.CTE)}

    for table in statement.find_all(exp.Table):
        if table.db not in _ALLOWED_SCHEMAS:
            raise GuardrailError("Access to that schema is not allowed.")

        if table.name not in allowed_tables and table.name not in cte_names:
            raise UnknownTableError(
                f"Unknown or disallowed table: {table.name or '<expression>'}."
            )

    for func in statement.find_all(exp.Func):
        name = _function_name(func)

        if name in _FORBIDDEN_FUNCTIONS or name.startswith(_FORBIDDEN_FUNCTION_PREFIXES):
            raise GuardrailError(f"The function {name} is not allowed.")

    return statement.sql(dialect="postgres")
