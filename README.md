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
docker/            docker-compose.yml: runs Qdrant
scripts/deploy.py  loads data/*.csv into the database (needs scripts/requirements.txt)
```

## Run locally

```
cp .env.example .env   # fill in values
docker compose -f docker/docker-compose.yml up -d   # Qdrant
pip install -r requirements.txt
uvicorn app.main:app --reload
```

`POST /chat` with `{"question": "Which artist has the most albums?", "session_id": "<any client-generated id>"}`

## Frontend (UI + chat history)

```
cd frontend
npm install
npm run dev
```

Opens a React chat UI at `http://localhost:5173`, talking to the backend at
`http://localhost:8000`. Each browser gets an anonymous `session_id`
(stored in `localStorage`) — chat history is persisted server-side, in a
separate `app.chat_history` table (not `public`, so it never leaks into the
text-to-SQL schema), and restored on reload.

## Flow

1. **Input guard** – length limit and prompt-injection patterns.
2. **Router** – (runs in parallel with the example lookup) classifies the question as `greeting`, `data_question`, `off_topic` or `unsafe`. Only `data_question` reaches SQL generation.
3. **Dynamic few-shot** – the question is embedded, and stored question→SQL pairs that are similar enough (found in Qdrant) are added to the SQL prompt.
4. **SQL guard** – parses the generated SQL (sqlglot): one `SELECT` only, known tables only, no `pg_*`/`dblink`/`set_config`-style functions.
5. **Read-only execution** – runs in a read-only transaction with a statement timeout and a row cap, so writes fail even if a query slipped through.
6. **Learn + format** – a query that passed the guard and returned rows is saved as an example after the response is sent, so the store grows from real usage without slowing the answer. A query with no rows returns a `message`/`text` result saying so; a query with rows always returns a `table` result carrying both the raw `columns`/`rows` and an LLM-generated `answer` string together.

Response `result` is one of `{"type": "message"}`, `{"type": "text"}` or `{"type": "table", "columns": [...], "rows": [...], "answer": "..."}`.

Limits are set with `MAX_QUESTION_LENGTH`, `MAX_ROWS` and `STATEMENT_TIMEOUT_MS`.

## Few-shot examples

There is no seed data: the store starts empty and every new question that produces a working query (one that passed the SQL guard and returned rows) is saved with its SQL. Later, similar questions get those pairs in their prompt, so answers improve with use. Duplicates (same question or same SQL) are skipped.

Stored in a **Qdrant** collection (`chat_examples`, cosine distance). The collection is created on startup and its vector size is detected from the embedding model, so nothing else needs configuring. If you switch to a model with a different size, the app refuses to touch the existing collection and tells you to delete it so it can be rebuilt.

Run Qdrant locally with Docker (data is kept in a volume):

```
docker compose -f docker/docker-compose.yml up -d
```

Stop it with `docker compose -f docker/docker-compose.yml down` (add `-v` to also delete the saved examples).

or use Qdrant Cloud and set `QDRANT_URL` and `QDRANT_API_KEY` in `.env` (the default URL is `http://localhost:6333`). Needs an Azure OpenAI **embedding** deployment:

```
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small
```

If Qdrant or embedding is unreachable at startup, the app logs a warning and answers without examples. Only examples whose similarity to the question is at least `FEW_SHOT_MIN_SCORE` (0.6) go into the prompt (at most 20, as a safety ceiling); if none qualify, the prompt gets no examples.
