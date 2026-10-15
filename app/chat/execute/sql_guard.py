import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from app.databases.engines import POSTGRES, Dialect
from app.chat.errors import GuardrailError, UnknownTableError
from app.config import MAX_STATEMENTS

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


# Upper bound on how many SELECTs one question may run, so a question that
# genuinely needs several independent result sets is still cheap and fast.


def _function_name(func: exp.Expression) -> str:
    if isinstance(func, exp.Anonymous):
        return str(func.name).lower()
    return func.sql_name().lower()


def _check_tables_and_functions(
    statement, allowed_tables: set[str], dialect: Dialect, schema_name: str | None
) -> None:

    allowed_schemas = {"", schema_name or ""}

    cte_names = {cte.alias for cte in statement.find_all(exp.CTE)}

    for table in statement.find_all(exp.Table):
        # A three-part name (otherdb.dbo.t) reaches another database on the
        # same server, which the table-name check below would not notice.
        if table.catalog:
            raise GuardrailError("Access to another database is not allowed.")

        if table.db not in allowed_schemas:
            raise GuardrailError("Access to that schema is not allowed.")

        if table.name not in allowed_tables and table.name not in cte_names:
            raise UnknownTableError(
                f"Unknown or disallowed table: {table.name or '<expression>'}."
            )

    for func in statement.find_all(exp.Func):
        name = _function_name(func)

        if name in dialect.forbidden_functions or name.startswith(dialect.forbidden_prefixes):
            raise GuardrailError(f"The function {name} is not allowed.")


def _validate_statement(
    statement, allowed_tables: set[str], dialect: Dialect, schema_name: str | None
) -> str:

    if not isinstance(statement, exp.Query):
        raise GuardrailError("Only SELECT queries are allowed.")

    for node in statement.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            raise GuardrailError("Only read-only SELECT queries are allowed.")

    _check_tables_and_functions(statement, allowed_tables, dialect, schema_name)

    # Optimizer hints can override the statement timeout, so they are dropped.
    for hint in list(statement.find_all(exp.Hint)):
        hint.pop()

    # Comments carry nothing the answer needs, and a driver may treat some as
    # executable (MySQL /*! ... */, optimizer hints), so none reach the database.
    return statement.sql(dialect=dialect.sqlglot, comments=False)


def validate_sql(
    sql: str,
    allowed_tables: set[str],
    dialect: Dialect = POSTGRES,
    schema_name: str | None = "public",
) -> list[str]:
    """Accept only read-only SELECTs over known tables, one or several
    (up to MAX_STATEMENTS), and return each validated statement."""

    try:
        statements = [s for s in sqlglot.parse(sql, read=dialect.sqlglot) if s is not None]
    except SqlglotError:
        raise GuardrailError("The generated query could not be parsed.")

    if not statements:
        raise GuardrailError("At least one SQL statement is required.")

    if len(statements) > MAX_STATEMENTS:
        raise GuardrailError(f"At most {MAX_STATEMENTS} SQL statements are allowed.")

    return [_validate_statement(statement, allowed_tables, dialect, schema_name) for statement in statements]


_WRITE_NODES = tuple(getattr(exp, name) for name in ("Insert", "Update", "Delete"))
_FORBIDDEN_IN_WRITE = tuple(n for n in _FORBIDDEN_NODES if n not in _WRITE_NODES)


def validate_write_sql(sql: str, allowed_tables: set[str]) -> str:  # PostgreSQL only
    """Accept exactly one INSERT, UPDATE or DELETE over known tables in the
    public schema and return it normalized. UPDATE and DELETE need a WHERE.
    Only reachable by roles holding data:write; the read path above never
    accepts any of this."""

    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except SqlglotError:
        raise GuardrailError("The generated change could not be parsed.")

    if len(statements) != 1:
        raise GuardrailError("Exactly one statement is allowed.")

    statement = statements[0]

    if not isinstance(statement, _WRITE_NODES):
        raise GuardrailError("Only INSERT, UPDATE or DELETE statements are allowed.")

    # A second write hidden in a CTE or subquery would slip past the check above.
    if sum(isinstance(node, _WRITE_NODES) for node in statement.walk()) != 1:
        raise GuardrailError("Only one INSERT, UPDATE or DELETE is allowed.")

    for node in statement.walk():
        if isinstance(node, _FORBIDDEN_IN_WRITE):
            raise GuardrailError("That statement type is not allowed.")

    if isinstance(statement, (exp.Update, exp.Delete)) and not statement.args.get("where"):
        raise GuardrailError("UPDATE and DELETE must have a WHERE clause.")

    _check_tables_and_functions(statement, allowed_tables, POSTGRES, "public")

    return statement.sql(dialect="postgres")
