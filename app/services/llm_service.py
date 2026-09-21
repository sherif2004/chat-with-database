import json

from openai import OpenAI

from app.config import (
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_DEPLOYMENT,
    AZURE_OPENAI_ENDPOINT,
)

# -------------------------
# Azure OpenAI
# -------------------------

client = OpenAI(
    api_key=AZURE_OPENAI_API_KEY,
    base_url=f"{AZURE_OPENAI_ENDPOINT}/openai/v1/"
)

MODEL = AZURE_OPENAI_DEPLOYMENT


# ============================================================
# Generate SQL
# ============================================================
def generate_sql(question, schema_text):

    prompt = f"""
You are a PostgreSQL SQL expert.

Convert the user's natural language question into
a PostgreSQL SELECT query.

DATABASE SCHEMA:

{schema_text}

IMPORTANT POSTGRESQL RULE:

Table and column names are CASE-SENSITIVE.

Always use DOUBLE QUOTES around every table name
and every column name exactly as they appear in
the database schema.

For example:

"Artist"
"ArtistId"
"Name"

Correct:

SELECT
    a."Name",
    COUNT(al."AlbumId") AS "AlbumCount"
FROM "Artist" AS a
JOIN "Album" AS al
    ON a."ArtistId" = al."ArtistId"
GROUP BY a."Name"
ORDER BY "AlbumCount" DESC
LIMIT 1;

Incorrect:

SELECT a.Name
FROM Artist a;

RULES:

1. Generate ONLY a SELECT query.
2. Do not generate INSERT.
3. Do not generate UPDATE.
4. Do not generate DELETE.
5. Do not generate DROP.
6. Do not generate ALTER.
7. Do not generate CREATE.
8. Do not invent tables.
9. Do not invent columns.
10. Use only tables and columns in the schema.
11. Use foreign keys to determine relationships.
12. Always double-quote table and column names.
13. Return ONLY SQL.
14. Do not use markdown.

USER QUESTION:

{question}
"""

    response = client.responses.create(
        model=MODEL,
        input=prompt
    )

    sql = response.output_text.strip()

    # Remove accidental markdown fences
    if sql.startswith("```"):
        sql = sql.replace("```sql", "")
        sql = sql.replace("```", "")
        sql = sql.strip()

    return sql


# ============================================================
# Generate Natural Language Answer
# ============================================================

def generate_answer(
    question,
    sql,
    database_result
):

    prompt = f"""
You are a data analyst.

The user asked:

{question}

The SQL query executed against the database was:

{sql}

The database returned:

{json.dumps(
    database_result,
    default=str,
    ensure_ascii=False
)}

Answer the user's question using ONLY
the database result.

Rules:

1. Do not invent information.
2. Do not make assumptions not supported by the result.
3. If the result is empty, clearly say that no matching
   data was found.
4. Give a concise and clear answer.
5. Do not mention internal SQL processing unless useful.
"""

    response = client.responses.create(
        model=MODEL,
        input=prompt
    )

    return response.output_text.strip()
