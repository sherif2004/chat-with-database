from sqlalchemy import text

from app.models.database import engine


# ============================================================
# Validate SQL
# ============================================================

def validate_sql(sql):

    sql_clean = sql.strip().lower()

    # Must start with SELECT
    if not sql_clean.startswith("select"):
        raise ValueError(
            "Only SELECT queries are allowed."
        )

    forbidden = [
        "insert ",
        "update ",
        "delete ",
        "drop ",
        "alter ",
        "create ",
        "truncate ",
        "grant ",
        "revoke "
    ]

    for keyword in forbidden:

        if keyword in sql_clean:
            raise ValueError(
                f"Forbidden SQL operation detected: {keyword}"
            )

    return True


# ============================================================
# Execute SQL
# ============================================================

def execute_sql(sql):

    validate_sql(sql)

    with engine.connect() as conn:

        result = conn.execute(
            text(sql)
        )

        rows = result.mappings().all()

    return [dict(row) for row in rows]
