# Chat UI and persisted chat history

## Problem

The app currently exposes only a `POST /chat` JSON API. There is no UI to use
it from, and no history: every question is answered and then forgotten
(aside from the unrelated Qdrant few-shot example store, which exists to
improve SQL generation, not to let a user see their past conversation).

We want:

1. A web UI to chat with the database.
2. Chat history persisted server-side and restorable per browser session.

## Non-goals

- No authentication/login. Sessions are anonymous, identified by a
  client-generated id.
- No multi-device sync, no cross-session history merging.
- No editing/deleting past messages, no pagination UI (history is small
  enough per session to load in one shot).

## Storage: `app.chat_history`

The database the app talks to (`DATABASE_URL`) is also the database the
text-to-SQL flow queries and introspects (`get_database_schema()`, scoped to
the `public` schema). Chat history must never show up in that introspection
— otherwise the LLM could see its own log table and try to generate SQL
against it.

So chat history lives in the **same Postgres database, in a separate
schema** called `app`:

```sql
CREATE SCHEMA IF NOT EXISTS app;

CREATE TABLE IF NOT EXISTS app.chat_history (
    id          BIGSERIAL PRIMARY KEY,
    session_id  TEXT NOT NULL,
    question    TEXT NOT NULL,
    response    JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chat_history_session_id_created_at_idx
    ON app.chat_history (session_id, created_at);
```

`response` stores the full `ChatResponse` JSON exactly as returned to the
client (intent, question, sql, result, timings). This avoids duplicating the
`Result` union's shape in a second table/schema — the history endpoint can
just replay stored JSON back into the same Pydantic models the UI already
knows how to render.

Schema/table creation happens once at startup (`app.main.lifespan`), mirroring
how `chat_controller.load_schema()` and `example_service.load_examples()`
already behave: best-effort, logged and non-fatal on failure. If it fails,
the app still serves chat, just without persistence for that run.

## Backend changes

### `app/models/history_model.py` (new)

- `ensure_chat_history_schema()` — runs the `CREATE SCHEMA`/`CREATE TABLE`
  DDL above, called from the lifespan startup hook.
- `save_message(session_id: str, question: str, response: ChatResponse)` —
  inserts one row.
- `get_history(session_id: str) -> list[HistoryEntry]` — selects all rows for
  a session ordered by `created_at ASC`.

Uses the existing `engine` from `app.models.database` — no new connection or
credentials.

### `app/views/chat_view.py`

- `ChatRequest` gains `session_id: str` (required — the UI always sends
  one).
- New `HistoryEntry` model: `{question: str, response: ChatResponse,
  created_at: datetime}` for the history endpoint's response list.

### `app/controllers/chat_controller.py`

- `chat_with_database` accepts the already-required `session_id` from the
  request.
- After `_finish(...)` builds the response, add a background task (same
  `background_tasks.add_task` mechanism already used for `remember`) that
  calls `save_message(session_id, question, response)`. This covers every
  branch (greeting/off_topic/unsafe/data_question) so the full conversation
  is logged, not just successful data questions.
- New function `get_chat_history(session_id: str) -> list[HistoryEntry]`
  thin wrapper around the model function, for the route to call.

### `app/routes/chat_route.py`

- New `GET /chat/history` endpoint, query param `session_id`, returns
  `list[HistoryEntry]`.

### `app/main.py`

- Startup (`lifespan`): call `ensure_chat_history_schema()` in a
  try/except, logging a warning on failure (matches the Qdrant
  unreachable-at-startup behavior described in the README).
- Add `CORSMiddleware` allowing the Vite dev origin (`http://localhost:5173`
  by default, overridable later if needed) so the frontend dev server can
  call the API directly.

## Frontend: `frontend/` (new, Vite + React)

Minimal single-page chat app, no routing, no state library beyond React's
built-in state.

- **Session id**: on first load, read `chat_session_id` from
  `localStorage`; if absent, generate one (`crypto.randomUUID()`) and store
  it.
- **Hydration**: on mount, `GET /chat/history?session_id=...` and render
  the returned entries as the initial message list.
- **Sending a message**: input box + send button/Enter key. `POST /chat`
  with `{question, session_id}`. While in flight, show a lightweight
  loading indicator on the pending assistant bubble. On success, append the
  question (user bubble) and the response (assistant bubble) to local
  state — no need to re-fetch history.
- **Rendering a result** (`result.type`):
  - `message` / `text` → the `message`/`answer` string as plain text.
  - `table` → an HTML `<table>` built from `columns`/`rows`, with the
    `answer` text (now always present alongside table results, per the
    earlier backend change) shown above the table.
- **Error handling**: a failed request shows an inline error bubble
  ("Something went wrong, try again") and does not corrupt the message
  list.

No build/deploy tooling beyond Vite's defaults (`npm run dev` for local
development). Production bundling/serving is out of scope for this spec —
can be revisited if/when the app needs to be deployed as one unit.

## Data flow summary

1. Page loads → read/create `session_id` → `GET /chat/history` → render
   past messages.
2. User submits a question → `POST /chat {question, session_id}` → existing
   guardrail/router/SQL/execute/format pipeline runs unchanged → response
   returned to the UI → **in parallel**, a background task persists
   `{session_id, question, response}` to `app.chat_history`.
3. New tab/reload with the same browser → same `session_id` from
   `localStorage` → history restored.

## Testing

Manual, since this is UI + integration work without existing test
infrastructure to extend:

- Two different browser profiles (or one normal + one incognito) produce
  independent histories.
- A question that returns rows renders both the table and the `answer`
  text.
- A greeting/off-topic/unsafe question still shows up in history (not just
  `data_question`s).
- Reloading the page restores the prior conversation for that session.
- Stopping Postgres (or breaking `DATABASE_URL` temporarily) still lets
  chat work — history just silently fails to save, matching the
  Qdrant-unreachable behavior.
