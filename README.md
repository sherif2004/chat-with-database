# Askbase — Chat With Database

Ask questions about a PostgreSQL database in plain language. Askbase turns each question into a safe, read-only SQL query, runs it, and answers in plain language, with the SQL and result table one click away. A demo database (Chinook) is included, and every user can connect their own.

## Contents

- [Features](#features)
- [Tech stack](#tech-stack)
- [How it works](#how-it-works)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Hybrid models](#hybrid-models)
- [Accounts and security](#accounts-and-security)
- [Conversations](#conversations)
- [API](#api)
- [Answer cache](#answer-cache)
- [Few-shot examples](#few-shot-examples)
- [Project structure](#project-structure)
- [Troubleshooting](#troubleshooting)

## Features

**Chat**
- Natural-language questions in, plain-language answers out, with follow-ups that remember the last few exchanges.
- A results table you can sort, copy, export to CSV, and (for a label plus a number) view as a bar chart.
- Staged progress while a question runs: reading, writing the query, running it, writing the answer.
- Regenerate an answer, edit your last question, and one-click follow-up suggestions.
- Starter questions written for the connected database.

**Conversations**
- Many chats per user, grouped by day, renamed or deleted from the sidebar.
- New chats are named automatically by a small language model.

**Your data**
- Sign up and log in; every user has their own history and their own connected database.
- Connect any PostgreSQL database from the UI (supervisors and admins). Its URL is stored encrypted.
- Three roles (user, supervisor, admin) with their own privileges, and a Users panel for supervisors and admins.

**Safety**
- Admins can change data through chat, but only after a preview and an explicit confirmation (see [Admin data changes](#admin-data-changes)).
- Prompt-injection input check, a SQL guard (one `SELECT`, known tables only), and read-only execution with a timeout and row cap.

**Interface**
- Light and dark mode, six page palettes and six main colors, chosen from an Appearance menu.
- Keyboard-accessible, with reduced-motion support.

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI, SQLAlchemy |
| Pipeline | LangGraph (`StateGraph`), sqlglot for SQL validation |
| Models | Azure OpenAI (a capable and a cheap chat deployment, plus embeddings) |
| Data | PostgreSQL (app tables and the demo database), Redis (answer cache), Qdrant (few-shot examples) |
| Frontend | React 18, Vite, plain CSS |

## How it works

Every message goes through a LangGraph pipeline:

1. **Input guard**: length limit and prompt-injection patterns.
2. **Answer cache (Redis)**: the same question (ignoring case, punctuation and extra spaces) asked by the same user is answered from Redis with no model call and no SQL. The response has `cache_hit: true`.
3. **Connection and history**: picks the user's database and loads the last 3 exchanges of the current conversation (in parallel), so follow-ups work.
4. **Router**: a small model classifies the message as `greeting`, `data_question`, `off_topic` or `unsafe` (and `data_change` for admins, which takes the preview-and-confirm path described under Admin data changes). Only data questions continue.
5. **Dynamic few-shot**: the question is embedded, and similar stored question and SQL pairs (from Qdrant) are added to the SQL prompt.
6. **SQL guard**: parses the generated SQL: one `SELECT` only, known tables only, no `pg_*`, `dblink` or `set_config`-style functions.
7. **Read-only execution with retry**: runs in a read-only transaction with a statement timeout and row cap. If Postgres rejects the query, the error is fed back to the model, for up to 3 attempts, before a "can't answer" message.
8. **Answer and learn**: the model writes a short answer from the first 20 rows. After the response is sent, in the background, the exchange is saved, the response is cached, and a query that passed the guard and returned rows is stored as a few-shot example.

For a new chat, a title is generated alongside steps 2 to 8, so it adds no waiting.

A response `result` is either `{"type": "message", "message": "..."}` `{"type": "table", "queries": [{"sql", "columns", "rows", "truncated"}, ...], "answer": "..."}`, or, for an admin's change preview, `{"type": "change", "message", "sql", "affected_rows", "token"}`.

## Getting started

### Prerequisites

- Python 3.10 or newer
- Node.js 18 or newer
- Docker (for Qdrant and Redis)
- A PostgreSQL database (a hosted one such as Supabase or Railway works)
- An Azure OpenAI resource with two chat deployments and one embedding deployment

### 1. Configure

```bash
cp .env.example .env
```

Fill in `.env`. At minimum: the Azure OpenAI values, `DATABASE_URL`, and `APP_SECRET_KEY` (needed to connect your own databases):

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 2. Start Qdrant and Redis

```bash
docker compose -f docker/docker-compose.yml up -d
```

### 3. Start the backend

One `requirements.txt` covers the API and the demo-data script.

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API runs at `http://localhost:8000` (interactive docs at `/docs`).

### 4. Load the demo data (optional)

`scripts/deploy.py` loads the Chinook CSVs from `data/` into the database in `DATABASE_URL`. It uses the same packages already installed in step 3:

```bash
python scripts/deploy.py
```

It replaces any existing tables named `Album`, `Artist`, `Customer`, `Employee`, `Genre`, `Invoice`, `InvoiceLine`, `MediaType`, `Playlist`, `PlaylistTrack` and `Track`.

### 5. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`, create an account, and ask a question. The frontend talks to the API at `http://localhost:8000` (set in `frontend/src/api.js`).

## Configuration

All settings are environment variables, read from `.env`.

| Variable | Required | Default | Description |
|---|---|---|---|
| `AZURE_OPENAI_API_KEY` | yes | | Azure OpenAI key |
| `AZURE_OPENAI_ENDPOINT` | yes | | `https://<resource>.openai.azure.com` |
| `AZURE_OPENAI_DEPLOYMENT` | yes | | Capable chat deployment, for example `gpt-4.1-mini` |
| `AZURE_OPENAI_DEPLOYMENT_LIGHT` | yes | | Cheap chat deployment, for example `gpt-4.1-nano` |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | yes | | Embedding deployment, for example `text-embedding-3-small` |
| `AZURE_OPENAI_API_VERSION` | no | `2025-03-01-preview` | API version |
| `LLM_TIMEOUT_SECONDS` | no | `30` | Per-call timeout |
| `DATABASE_URL` | yes | | PostgreSQL for the app tables and the demo data |
| `APP_SECRET_KEY` | for custom databases | | Encrypts saved database URLs |
| `SESSION_TTL_DAYS` | no | `14` | Login session lifetime |
| `COOKIE_SECURE` | no | `false` | Set `true` behind HTTPS |
| `CORS_ORIGINS` | no | `http://localhost:5173` | Comma-separated frontend origins |
| `MAX_QUESTION_LENGTH` | no | `500` | Longest accepted question |
| `MAX_ROWS` | no | `100` | Row cap per query |
| `STATEMENT_TIMEOUT_MS` | no | `10000` | Per-query timeout |
| `REDIS_URL` | no | `redis://localhost:6379/0` | Answer cache |
| `CACHE_TTL_SECONDS` | no | `3600` | How long cached answers live |
| `QDRANT_URL` | no | `http://localhost:6333` | Few-shot example store |
| `QDRANT_API_KEY` | no | | Only for Qdrant Cloud |
| `QDRANT_COLLECTION` | no | `chat_examples` | Collection name |
| `FEW_SHOT_MIN_SCORE` | no | `0.6` | Minimum similarity for an example to be used |

Use deployment names, not model names. Both chat deployments must support structured (JSON schema) output. If an Azure call fails or times out, the API returns HTTP 503 with a readable message.

## Hybrid models

Two chat deployments split the work by difficulty:

| Deployment | Used for |
|---|---|
| `AZURE_OPENAI_DEPLOYMENT` (capable) | Writing the SQL, writing the final answer, and follow-up suggestions |
| `AZURE_OPENAI_DEPLOYMENT_LIGHT` (cheap) | Classifying the message (router), naming new chats, and starter questions |

SQL needs real reasoning (joins, multi-statement decisions, schema disambiguation). Answers and follow-ups run on the capable model because answering in the question's language proved unreliable on a nano-class model: about 1 in 3 answers came back in the wrong language, even after prompt tuning. Naming and starters are short, low-risk tasks, so the cheap model handles them.

To use one model for everything, set both deployments to the same name.

## Accounts and security

Sign-up and login are built in and stored in the same Postgres database, in the `app` schema (`app.users`, `app.user_sessions`).

- Passwords are hashed with scrypt. Login sets an `httpOnly`, `SameSite=Lax` session cookie. Only a SHA-256 of the token is stored, so sessions can be revoked (logout deletes the row).
- Every chat, conversation and connection route requires the session. The user is read from the cookie, never from the request body, so one user cannot read another's history or database. History, saved connections and cached answers are keyed `u:<user id>`.
- Saved database URLs are encrypted at rest (Fernet) in `app.user_connections`. This needs `APP_SECRET_KEY`; without it, connecting a custom database is refused. The old plaintext `app.connections` table is no longer read and can be dropped.
- Login attempts are limited in Redis: 5 failures per 15 minutes per IP and email, 30 per IP, and 25 per email. Sign-ups are limited to 10 per hour per IP.
- State-changing requests from an origin that is not in `CORS_ORIGINS` are rejected.
- Chat history lives in `app.chat_history`, not in `public`, so it never leaks into the text-to-SQL schema.

### Roles

Every account has one role. Sign-up always creates a `user`; admins change roles from the **Users** panel (or `PATCH /admin/users/{id}/role`). The role is read from the database on every request, and changing it signs that user out.

| Permission | user | supervisor | admin |
|---|---|---|---|
| Chat, manage own conversations | yes | yes | yes |
| Connect a custom database | no (demo DB only) | yes | yes |
| List accounts, read other users' chats (read-only) | no | yes | yes |
| Change roles, delete accounts | no | no | yes |
| Change data in the connected database (preview, then confirm) | no | no | yes |

The role-to-permission map lives in `app/services/permissions.py`; routes ask for a permission with `require_permission("...")`. Set `ADMIN_EMAIL` and `ADMIN_PASSWORD` in `.env` to create the first admin on startup. If that email already has an account, it is promoted, its password is replaced by `ADMIN_PASSWORD`, and its sessions end. The last admin can't be demoted or deleted, and you can't change or delete your own account.

### Admin data changes

Chat stays read-only for everyone. An admin can also ask for a change in plain language ("delete customer 12"). The model writes one `INSERT`, `UPDATE` or `DELETE`; a separate write guard accepts only a single such statement on known `public` tables (`UPDATE` and `DELETE` need a `WHERE`, and the `app` schema is off limits). The statement is then run inside a transaction that is rolled back, and the chat shows the exact SQL and how many rows it would touch. Nothing is saved until the admin clicks **Confirm change** (`POST /chat/confirm-change`).

- The confirmation token is single-use, tied to that admin and expires after `PENDING_CHANGE_TTL_SECONDS` (300). The statement is re-validated, and the commit is refused if it touches a different number of rows than was shown.
- A change may touch at most `MAX_WRITE_ROWS` rows (100).
- Every committed change is recorded in `app.data_changes` (who, which database, the SQL, rows affected).
- This works on the shared demo database too, so a change there is seen by every user. Cached answers are cleared after a change.
- The connected database user must itself be allowed to write; the app cannot grant that.

Not built yet: email verification and password reset.

## Conversations

Each user has many conversations (`app.conversations`). History, follow-up context, regenerate and edit all work per conversation. A new chat gets a placeholder title from the first question, then a generated one from the small model. A title you set yourself is never overwritten.

`POST /chat/stream` does the same work as `POST /chat` and also sends progress as server-sent events: a `stage` event as each pipeline step starts, then one `done` (the same payload as `/chat`) or `error`. Send `replace_last: true` to regenerate or edit the newest exchange; it also skips the answer cache.

## API

All routes except sign-up and login need the session cookie.

| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/signup` | Create an account and sign in |
| `POST` | `/auth/login` | Sign in |
| `POST` | `/auth/logout` | Sign out |
| `GET` | `/auth/me` | The signed-in user, with role and permissions |
| `POST` | `/chat` | Ask a question and get the whole response |
| `POST` | `/chat/stream` | Ask a question, with stage events |
| `POST` | `/chat/confirm-change` | Apply a previewed data change (admin) |
| `GET` | `/conversations` | List conversations |
| `POST` | `/conversations` | Create an empty conversation |
| `PATCH` | `/conversations/{id}` | Rename |
| `DELETE` | `/conversations/{id}` | Delete, with its messages |
| `GET` | `/conversations/{id}/messages` | Messages in a conversation |
| `GET` | `/conversations/{id}/followups` | Suggested next questions |
| `POST` | `/connections` | Connect your own PostgreSQL database (supervisor, admin) |
| `GET` | `/connections/current` | The connected database and its schema |
| `GET` | `/connections/starters` | Starter questions for the connected schema |
| `GET` | `/admin/users` | List accounts (supervisor, admin) |
| `PATCH` | `/admin/users/{id}/role` | Change a role (admin) |
| `DELETE` | `/admin/users/{id}` | Delete an account and its data (admin) |
| `GET` | `/admin/users/{id}/conversations` | A user's conversations, read-only (supervisor, admin) |
| `GET` | `/admin/users/{id}/conversations/{cid}/messages` | Their messages, read-only (supervisor, admin) |

Example (after logging in and keeping the cookie):

```bash
curl -b cookies.txt -H "Content-Type: application/json" \
  -d '{"question": "Which artist has the most albums?"}' \
  http://localhost:8000/chat
```

## Answer cache

Repeated questions are answered from Redis instead of calling the model. The cache is per user, matches on the normalized question (word matching, not semantic), expires after `CACHE_TTL_SECONDS`, and returns the earlier answer without re-running the SQL, so numbers are as of when it was cached. `app.chat_history` (Postgres) is the separate, durable conversation record. It never expires and isn't the cache.

If Redis is unreachable, the app logs a warning and every lookup is a miss; it never blocks a response.

## Few-shot examples

There is no seed data. The store starts empty, and every question that produces a working query (one that passed the SQL guard and returned rows) is saved with its SQL. Later, similar questions get those pairs in their prompt, so answers improve with use. Duplicates (same question or same SQL) are skipped, using Qdrant payload indexes on `question_key` and `sql_key`.

Examples live in a Qdrant collection (`chat_examples`, cosine distance). It is created on startup and its vector size is detected from the embedding model. If you switch to a model with a different size, the app refuses to touch the existing collection and tells you to delete it so it can be rebuilt. Only examples with similarity of at least `FEW_SHOT_MIN_SCORE` go into the prompt (at most 20); if none qualify, the prompt has no examples.

Run Qdrant locally with Docker (data is kept in a volume), or use Qdrant Cloud and set `QDRANT_URL` and `QDRANT_API_KEY`. To stop the local services: `docker compose -f docker/docker-compose.yml down` (add `-v` to also delete the saved examples).

If Qdrant or embeddings are unreachable at startup, the app logs a warning and answers without examples.

## Project structure

```
app/
  main.py            FastAPI app, middleware, startup
  config.py          environment settings
  dependencies.py    signed-in user from the session cookie
  timing.py          per-step timings returned with every response
  graphs/            the chat pipeline (LangGraph StateGraph):
                     chat_graph.py (nodes, edges, SQL retry loop), chat_state.py
  models/            data access: users and sessions, conversations, chat
                     history, saved connections, schema introspection, SQL
                     execution, the Qdrant example store
  views/             request and response schemas
  controllers/       runs the graph and turns the final state into a response
  routes/            endpoints: auth, chat, conversations, connections, admin
  services/          LLM calls and prompts, intent router, chat titles,
                     starter and follow-up suggestions, embeddings, few-shot
                     lookup, Redis cache, password hashing and rate limits,
                     encryption of saved connection URLs, role permissions,
                     pending admin changes
  guardrails/        input check (prompt injection), SQL check (read-only) and
                     the admin write check
frontend/
  src/               React app: App.jsx, api.js, theme.js and components
                     (conversation rail, composer, results table, progress,
                     database drawer, users panel, appearance menu, sign-in screen)
  public/            favicon
data/                Chinook demo CSVs
docker/              docker-compose.yml: Qdrant and Redis
scripts/deploy.py    loads data/*.csv into the database
```

## Troubleshooting

- **"Saving a database connection needs APP_SECRET_KEY"**: set `APP_SECRET_KEY` in `.env` and restart the backend.
- **Sign-in works but the app shows a signed-out screen**: the browser must reach the API at the address set in `frontend/src/api.js`, and the address you open the frontend on must be listed in `CORS_ORIGINS`.
- **Answers are slow or skip examples**: check that Redis and Qdrant are running (`docker compose -f docker/docker-compose.yml ps`). The app still works without them, just without caching and examples.
- **HTTP 503 "language model is unavailable"**: an Azure OpenAI call failed or timed out; check the key, endpoint and deployment names.
