# Askbase: developer onboarding

Askbase lets people ask questions about a SQL database in plain language. The backend turns each question into a safe, read-only SQL query, runs it, and explains the result.

## 1. Run it (about 5 minutes)

```bash
cp .env.example .env                                  # add your Azure OpenAI settings
docker compose -f docker/docker-compose.yml up -d     # Qdrant + Redis
pip install -r requirements.txt
uvicorn app.main:app --reload                         # API on :8000
cd frontend && npm install && npm run dev             # UI
```

Check it works:
- [ ] The UI loads and you can sign in.
- [ ] Asking a question returns a table and an answer.
- [ ] The app still works if Redis or Qdrant are stopped. It only loses caching and examples.

The README has the full configuration table and troubleshooting.

## 2. What happens to one question

`app/chat/graph.py` wires the whole flow (a LangGraph graph). Its stages are grouped into four phases, each with its own folder under `app/chat/`: **understand**, **generate**, **execute**, **respond**. In order:

| # | Stage (node) | What it does |
|---|--------------|--------------|
| 1 | `input_guard` | Rejects empty, oversized or unsafe input |
| 2 | `cache_lookup` | Returns a cached answer if the same question was asked before |
| 3 | `resolve_connection`, `load_history` | Finds the user's database and the last few messages |
| 4 | `classify_intent` | Greeting, data question, data change, or off-topic |
| 5 | `retrieve_examples` | Finds similar past questions in Qdrant to guide the LLM |
| 6 | `generate_sql` | LLM writes SQL using the engine's dialect rules |
| 7 | `validate_sql` | `sql_guard` parses the SQL and allows only SELECTs on known tables |
| 8 | `execute_sql` | Runs it in a read-only session, retrying up to 3 times on errors |
| 9 | `generate_write`, `validate_write`, `preview_write` | The change path (PostgreSQL only): preview first, user confirms |
| 10 | `generate_answer` | Turns the rows into a written answer |

## 3. Where things are

| Folder | Role |
|--------|------|
| `app/chat/graph.py` | The flow in one file. Start here. |
| `app/chat/understand/` | Phase 1: input check, cache, history, intent (steps 1 to 4) |
| `app/chat/generate/` | Phase 2: similar examples, prompts, SQL generation (steps 5 and 6) |
| `app/chat/execute/` | Phase 3: SQL safety check, run, change preview (steps 7 to 9) |
| `app/chat/respond/` | Phase 4: the answer, chat titles, suggested questions (step 10) |
| `app/databases/` | Connected databases: engine rules, network guard, connections, schema, queries |
| `app/accounts/` | Users, sessions, passwords, permissions, activity log |
| `app/api/` | HTTP endpoints and their request/response schemas |
| `app/shared/` | Cache, LLM client, encryption, timings |
| `frontend/src/components/` | React UI (`ConnectPage.jsx` is the connect-a-database screen) |
| `docker/` | Local Qdrant and Redis |
| `docs/` | Pipeline diagrams (`pipeline.html`) |

## 4. Common tasks

- **Add a database engine:** add a `Dialect` entry in `app/databases/engines.py` (URL allowlist, read-only setup, quoting, LIMIT style). Add its driver to `requirements.txt`.
- **Change what the LLM is told:** `app/chat/generate/prompts.py` (SQL), `app/chat/understand/prompts.py` (intent), `app/chat/respond/prompts.py` (answers).
- **Add a pipeline stage:** write the node in the phase folder's `nodes.py` and wire it in `build_chat_graph()` in `app/chat/graph.py`.
- **Change a safety rule:** `app/chat/execute/sql_guard.py`. Keep it fail-closed.

## 5. Rules that matter

- Connected databases are queried read-only. Where the engine cannot enforce that, the UI warns the user.
- Private and internal network addresses are blocked unless `BLOCK_PRIVATE_HOSTS=false`.
- Data changes through chat are PostgreSQL-only and need an explicit confirm.
- Never log connection strings or passwords.
- The repo has no automated tests right now. Check changes by running the app and asking a real question.

## 6. Known limits

- Only PostgreSQL and MySQL have been tested against live servers. SQL Server, Snowflake, BigQuery, ClickHouse and the generic engines are untested live.
- SQLite, DuckDB and NoSQL databases are not supported.
- Most generic engines are refused while `BLOCK_PRIVATE_HOSTS=true`.
