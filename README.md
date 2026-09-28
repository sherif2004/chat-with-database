# Chat With Database

Ask questions in natural language about a PostgreSQL database (the demo uses Chinook, and you can connect your own from the UI). The question is converted to SQL, executed, and the result is answered in plain language.

The step-by-step path a message takes is in [docs/workflow.md](docs/workflow.md).

## Structure (MVC + graph)

```
app/
  main.py          FastAPI app
  config.py        environment settings
  graphs/          the chat pipeline as a LangGraph StateGraph:
                   chat_graph.py (nodes/edges, incl. the SQL retry loop),
                   chat_state.py (graph state shape)
  models/          data access: app database, chat history (the durable
                   conversation record), saved connections, workflow
                   setting, schema introspection, SQL execution, Qdrant
                   example store
  views/           request/response schemas
  controllers/     invokes the graph, turns the final state into a response
  routes/          FastAPI endpoints (chat, connections, settings)
  services/        Azure OpenAI calls (llm_service), all prompts (prompts.py),
                   the intent router, embeddings, few-shot example lookup,
                   the Redis response cache (cache_service.py)
  guardrails/      input check (prompt injection) and SQL check (read-only)
  timing.py        per-step timings returned with every response
docs/workflow.md   what happens to a message, step by step (with the graph diagram)
docker/            docker-compose.yml: runs Qdrant and Redis
scripts/deploy.py  loads data/*.csv into the database (needs scripts/requirements.txt)
```

## Run locally

```
cp .env.example .env   # fill in values
docker compose -f docker/docker-compose.yml up -d   # Qdrant + Redis
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

The pipeline is a LangGraph `StateGraph`, not hand-rolled branching. Full detail,
diagram and error table: [docs/workflow.md](docs/workflow.md).

1. **Input guard** – length limit and prompt-injection patterns.
2. **Answer cache (Redis)** – if the same question (case, punctuation and extra spaces ignored) was already asked in this session, the stored answer is returned from Redis. No LLM call, no SQL. The response has `cache_hit: true`. Entries expire after `CACHE_TTL_SECONDS`.
3. **Connection + history** – picks the session's database and loads the last 3 exchanges (run in parallel, since neither depends on the other) so follow-ups work.
4. **Router or no-router workflow** (chosen per session in the sidebar) – *with router*: a small LLM call classifies the message (`greeting`, `data_question`, `off_topic`, `unsafe`) and only `data_question` continues. *No router*: one combined call classifies and writes the SQL, one fewer round trip.
5. **Dynamic few-shot** – the question is embedded, and stored question→SQL pairs that are similar enough (found in Qdrant) are added to the SQL prompt.
6. **SQL guard** – parses the generated SQL (sqlglot): one `SELECT` only, known tables only, no `pg_*`/`dblink`/`set_config`-style functions.
7. **Read-only execution, with retry** – runs in a read-only transaction with a statement timeout and a row cap. If Postgres itself rejects the query (bad column, syntax slip the guard let through, ...), the error is fed back to the model and it gets up to 3 attempts total before falling back to a "can't answer" message — no more HTTP 500s on a bad query.
8. **Answer + learn** – the LLM writes a short answer from the first 20 rows. After the response is sent, in the background: the exchange is saved to `chat_history`, the response is cached in Redis, and a query that passed the guard and returned rows is saved as a few-shot example.

Response `result` is one of `{"type": "message", "message": "..."}` or
`{"type": "table", "queries": [{"sql", "columns", "rows", "truncated"}, ...], "answer": "..."}`.

Limits are set with `MAX_QUESTION_LENGTH`, `MAX_ROWS` and `STATEMENT_TIMEOUT_MS`.

## Azure OpenAI settings

```
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com
AZURE_OPENAI_DEPLOYMENT=<chat deployment name>
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=<embedding deployment name>
# optional
AZURE_OPENAI_API_VERSION=2025-03-01-preview
LLM_TIMEOUT_SECONDS=30
```

Use deployment names, not model names. The chat deployment must support structured (JSON schema) output, which the router and SQL generation use. If an Azure call fails or times out, `/chat` returns HTTP 503 with a readable message.

## Answer cache

Repeated questions are answered from Redis instead of calling the model. It is per
session, matches on the normalized question (word matching, not semantic), expires
after `CACHE_TTL_SECONDS` (default 3600s), and returns the earlier answer without
re-running the SQL, so numbers are as of when it was cached. `app.chat_history`
(Postgres) is the separate, durable conversation record — it never expires and
isn't the cache.

Run Redis locally with Docker:

```
docker compose -f docker/docker-compose.yml up -d
```

Or point `REDIS_URL` at any Redis instance. If Redis is unreachable, the app logs a
warning and every lookup is a miss — it never blocks a response.

## Few-shot examples

There is no seed data: the store starts empty and every new question that produces a working query (one that passed the SQL guard and returned rows) is saved with its SQL. Later, similar questions get those pairs in their prompt, so answers improve with use. Duplicates (same question or same SQL) are skipped, using Qdrant payload indexes on `question_key` and `sql_key`.

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
