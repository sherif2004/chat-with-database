from app.models.query_model import execute_sql
from app.models.schema_model import get_database_schema, schema_to_text
from app.services.llm_service import generate_answer, generate_sql

schema_text = None


def load_schema():

    global schema_text

    schema = get_database_schema()

    schema_text = schema_to_text(schema)


# ============================================================
# Chat With Database
# ============================================================

def chat_with_database(question):

    # Step 1: Generate SQL
    sql = generate_sql(
        question,
        schema_text
    )

    # Step 2: Execute SQL
    result = execute_sql(sql)

    # Step 3: Generate answer
    answer = generate_answer(
        question,
        sql,
        result
    )

    return {
        "question": question,
        "sql": sql,
        "answer": answer
    }
