# Chat With Database

Ask questions in natural language about a Railway PostgreSQL database (Chinook). The question is converted to SQL, executed, and the result is answered in plain language.

## Structure (MVC)

```
app/
  main.py          FastAPI app
  config.py        environment settings
  models/          database access (engine, schema introspection, SQL execution)
  views/           request/response schemas
  controllers/     chat flow: question -> SQL -> result -> answer
  routes/          FastAPI endpoints
  services/        LLM calls (Azure OpenAI) and the intent router
  guardrails/      input check (prompt injection) and SQL check (read-only)
scripts/deploy.py  loads data/*.csv into the database
```

## Run

```
cp .env.example .env   # fill in values
pip install -r requirements.txt
uvicorn app.main:app --reload
```

`POST /chat` with `{"question": "Which artist has the most albums?"}`

## Flow

1. **Input guard** – length limit and prompt-injection patterns.
2. **Router** – classifies the question as `greeting`, `data_question`, `off_topic` or `unsafe`. Only `data_question` reaches SQL generation.
3. **SQL guard** – parses the generated SQL (sqlglot): one `SELECT` only, known tables only, no `pg_*`/`dblink`/`set_config`-style functions.
4. **Read-only execution** – runs in a read-only transaction with a statement timeout and a row cap, so writes fail even if a query slipped through.
5. **Formatting** – `format` in the request: `auto` (a single row is humanized, lists and rankings with several rows return a table), `text` or `table`.

Response `result` is one of `{"type": "message"}`, `{"type": "text"}` or `{"type": "table", "columns": [...], "rows": [...]}`.

Limits are set with `MAX_QUESTION_LENGTH`, `MAX_ROWS` and `STATEMENT_TIMEOUT_MS`. Run tests with `pytest`.
