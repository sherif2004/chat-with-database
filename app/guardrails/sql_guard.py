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

# Upper bound on how many SELECTs one question may run, so a question that
# genuinely needs several independent result sets is still cheap and fast.
MAX_STATEMENTS = 5


def _function_name(func: exp.Expression) -> str:
    if isinstance(func, exp.Anonymous):
        return str(func.name).lower()
    return func.sql_name().lower()


def _validate_statement(statement, allowed_tables: set[str]) -> str:

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


def validate_sql(sql: str, allowed_tables: set[str]) -> list[str]:
    """Accept only read-only SELECTs over known tables, one or several
    (up to MAX_STATEMENTS), and return each validated statement."""

    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except SqlglotError:
        raise GuardrailError("The generated query could not be parsed.")

    if not statements:
        raise GuardrailError("At least one SQL statement is required.")

    if len(statements) > MAX_STATEMENTS:
        raise GuardrailError(f"At most {MAX_STATEMENTS} SQL statements are allowed.")

    return [_validate_statement(statement, allowed_tables) for statement in statements]
