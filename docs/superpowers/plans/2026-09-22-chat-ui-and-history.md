# Chat UI and Persisted Chat History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a React chat UI for `POST /chat`, and persist every exchange server-side so a browser session's conversation survives a reload.

**Architecture:** Chat history is stored in a new `app.chat_history` table in the *same* Postgres database the app already queries, but in a separate `app` schema so it never appears in the `public`-schema introspection used for text-to-SQL. A background task (mirroring the existing few-shot `remember()` pattern) writes each exchange after the response is sent. A new `GET /chat/history` endpoint replays it back. A Vite + React frontend in `frontend/` talks to the existing FastAPI backend over CORS.

**Tech Stack:** FastAPI, SQLAlchemy (existing `engine`), Postgres JSONB, React 18 + Vite (frontend, new).

**Spec:** `docs/superpowers/specs/2026-09-22-chat-ui-and-history-design.md`

## Global Constraints

- Chat history table lives in schema `app`, never `public` (`public` is what `get_database_schema()` introspects for text-to-SQL — leaking the log table there risks the LLM generating SQL against it).
- History persistence must be best-effort: any storage failure is logged and swallowed, never breaks the chat response (same guarantee `remember()` already gives few-shot examples).
- No authentication. Sessions are anonymous, identified by a client-generated `session_id` string.
- `response` is stored as the full `ChatResponse` JSON, not a re-derived shape — the history endpoint replays it straight into the same Pydantic model the UI already renders.
- No test framework exists in this repo (no `tests/` directory, no pytest in `requirements.txt`). Verification steps in this plan are manual (`curl`, `python -c`, browser) — do not introduce pytest as a side effect of this plan.
- Frontend: no build/deploy tooling beyond Vite's dev server (`npm run dev`). Production bundling is out of scope.

---

## File Structure

**Backend (modify existing MVC layout):**
- Create: `app/models/history_model.py` — schema/table creation, insert, select.
- Modify: `app/views/chat_view.py` — `session_id` on `ChatRequest`, new `HistoryEntry` model.
- Modify: `app/controllers/chat_controller.py` — persist in background task, `get_chat_history()`.
- Modify: `app/routes/chat_route.py` — `GET /chat/history`.
- Modify: `app/main.py` — create history schema at startup, add CORS middleware.

**Frontend (new `frontend/` directory, Vite + React, not part of the Python app):**
- Create: `frontend/package.json`, `frontend/vite.config.js`, `frontend/index.html`
- Create: `frontend/src/main.jsx` — React entry point.
- Create: `frontend/src/api.js` — `getHistory(sessionId)`, `sendMessage(sessionId, question)`.
- Create: `frontend/src/session.js` — `getSessionId()` (localStorage-backed).
- Create: `frontend/src/App.jsx` — chat state, input box, message list.
- Create: `frontend/src/components/Message.jsx` — renders one exchange by `result.type`.
- Create: `frontend/src/index.css` — minimal chat styling.

---

### Task 1: Chat history storage model

**Files:**
- Create: `app/models/history_model.py`
- Test: manual, via `python -c` (see Step 4/6 below)

**Interfaces:**
- Consumes: `app.models.database.engine`, `app.models.database.retry_on_disconnect` (both existing).
- Produces:
  - `ensure_chat_history_schema() -> None`
  - `save_message(session_id: str, question: str, response: dict) -> None`
  - `HistoryRow` (pydantic model: `question: str`, `response: dict`, `created_at: datetime`)
  - `get_history(session_id: str) -> list[HistoryRow]`

- [ ] **Step 1: Write `app/models/history_model.py`**

```python
import json
import logging
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text

from app.models.database import engine, retry_on_disconnect

logger = logging.getLogger(__name__)


class HistoryRow(BaseModel):
    question: str
    response: dict
    created_at: datetime


def ensure_chat_history_schema() -> None:
    """Create the app.chat_history table if it doesn't exist yet.

    Called once at startup. Raises on failure; the caller decides whether
    that's fatal (it isn't — see app/main.py, which logs and continues).
    """

    def run():
        with engine.begin() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS app"))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS app.chat_history (
                    id BIGSERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    response JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS chat_history_session_id_created_at_idx
                ON app.chat_history (session_id, created_at)
            """))

    retry_on_disconnect(run)


def save_message(session_id: str, question: str, response: dict) -> None:
    """Persist one exchange. Never raises: a storage problem must not
    break the chat response, which has already been sent by the time
    this runs as a background task."""

    def run():
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO app.chat_history (session_id, question, response)
                    VALUES (:session_id, :question, CAST(:response AS JSONB))
                """),
                {
                    "session_id": session_id,
                    "question": question,
                    "response": json.dumps(response),
                }
            )

    try:
        retry_on_disconnect(run)
    except SQLAlchemyError as e:
        logger.warning("Could not save chat history: %s", e)


def get_history(session_id: str) -> list[HistoryRow]:

    def run():
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT question, response, created_at
                    FROM app.chat_history
                    WHERE session_id = :session_id
                    ORDER BY created_at ASC
                """),
                {"session_id": session_id}
            )
            return [
                HistoryRow(
                    question=row.question,
                    response=row.response,
                    created_at=row.created_at
                )
                for row in result
            ]

    return retry_on_disconnect(run)
```

- [ ] **Step 2: Verify the module imports cleanly**

Run: `python -c "import app.models.history_model"` from the repo root.
Expected: no output, exit code 0.

- [ ] **Step 3: Manually create the schema against the configured database**

Run:
```bash
python -c "
from app.models.history_model import ensure_chat_history_schema
ensure_chat_history_schema()
print('ok')
"
```
Expected: prints `ok`. If it fails, check `DATABASE_URL` in `.env` — this needs a live Postgres connection (same one the rest of the app already uses).

- [ ] **Step 4: Manually verify insert + read round-trip**

Run:
```bash
python -c "
from app.models.history_model import save_message, get_history

save_message('test-session', 'How many artists are there?', {
    'intent': 'data_question',
    'question': 'How many artists are there?',
    'sql': 'SELECT COUNT(*) FROM artist',
    'result': {'type': 'text', 'answer': '275 artists.'},
    'timings_ms': {},
})

rows = get_history('test-session')
assert len(rows) == 1
assert rows[0].question == 'How many artists are there?'
assert rows[0].response['result']['answer'] == '275 artists.'
print('ok', rows[0].created_at)
"
```
Expected: prints `ok <timestamp>`.

- [ ] **Step 5: Clean up the test row**

Run:
```bash
python -c "
from sqlalchemy import text
from app.models.database import engine
with engine.begin() as conn:
    conn.execute(text(\"DELETE FROM app.chat_history WHERE session_id = 'test-session'\"))
print('cleaned')
"
```
Expected: prints `cleaned`.

- [ ] **Step 6: Commit**

```bash
git add app/models/history_model.py
git commit -m "Add chat_history storage model in a dedicated app schema

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: `session_id` on requests, `HistoryEntry` response model

**Files:**
- Modify: `app/views/chat_view.py`

**Interfaces:**
- Consumes: nothing new (pure schema addition).
- Produces:
  - `ChatRequest.session_id: str` (required, `min_length=1`)
  - `HistoryEntry` (pydantic model: `question: str`, `response: ChatResponse`, `created_at: datetime`)

- [ ] **Step 1: Add `session_id` to `ChatRequest` and add `HistoryEntry`**

In `app/views/chat_view.py`, add the `datetime` import and `Field` (already imported), then:

```python
from datetime import datetime
```

Change:

```python
class ChatRequest(BaseModel):
    question: str
    # auto: single values are humanized, lists/rankings come back as a table
    # text: always humanize the result / table: always return a table
    format: Literal["auto", "text", "table"] = "auto"
```

to:

```python
class ChatRequest(BaseModel):
    question: str
    session_id: str = Field(min_length=1)
    # auto: single values are humanized, lists/rankings come back as a table
    # text: always humanize the result / table: always return a table
    format: Literal["auto", "text", "table"] = "auto"
```

Add at the end of the file, after `ChatResponse`:

```python
class HistoryEntry(BaseModel):
    question: str
    response: ChatResponse
    created_at: datetime
```

- [ ] **Step 2: Verify the module imports and `ChatRequest` requires `session_id`**

Run:
```bash
python -c "
from app.views.chat_view import ChatRequest
try:
    ChatRequest(question='hi')
    print('FAIL: should have required session_id')
except Exception:
    print('ok: session_id required')
print(ChatRequest(question='hi', session_id='abc'))
"
```
Expected: prints `ok: session_id required` followed by the constructed request.

- [ ] **Step 3: Commit**

```bash
git add app/views/chat_view.py
git commit -m "Add session_id to ChatRequest and HistoryEntry response model

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Persist exchanges from the controller; add `get_chat_history`

**Files:**
- Modify: `app/controllers/chat_controller.py`

**Interfaces:**
- Consumes: `app.models.history_model.save_message`, `app.models.history_model.get_history`, `app.views.chat_view.HistoryEntry`, `app.views.chat_view.ChatResponse`.
- Produces: `get_chat_history(session_id: str) -> list[HistoryEntry]`, used by the route in Task 4. `chat_with_database` now persists every exchange (all four intents) via `background_tasks`.

- [ ] **Step 1: Import the new model and view pieces**

In `app/controllers/chat_controller.py`, add to the imports:

```python
from app.models.history_model import get_history, save_message
```

and add `HistoryEntry` to the existing `from app.views.chat_view import (...)` block:

```python
from app.views.chat_view import (
    ChatRequest,
    ChatResponse,
    HistoryEntry,
    MessageResult,
    TableResult,
    TextResult,
)
```

- [ ] **Step 2: Persist every response, not just successful data questions**

The cleanest place is `_finish`, since every return path in `chat_with_database` funnels through it (directly or via `_message`) and it already has the built `response` and `timings`. Change `_finish` to also take `background_tasks` and the current `question`/`session_id`, and schedule the save there:

```python
def _finish(timings, background_tasks, session_id, question, **fields):

    response = ChatResponse(timings_ms=timings.as_model(), **fields)

    logger.info(
        "intent=%s timings_ms=%s",
        response.intent,
        response.timings_ms
    )

    background_tasks.add_task(
        save_message, session_id, question, response.model_dump(mode="json")
    )

    return response


def _message(timings, background_tasks, session_id, intent, question, message):

    return _finish(
        timings,
        background_tasks,
        session_id,
        question,
        intent=intent,
        question=question,
        result=MessageResult(message=message)
    )
```

Note `response.model_dump(mode="json")`: this serializes `datetime`/etc. to JSON-safe types before `save_message` hands the dict to `json.dumps`.

- [ ] **Step 3: Update every call site in `chat_with_database` to pass `background_tasks` and `session_id`**

```python
def chat_with_database(
    request: ChatRequest,
    background_tasks: BackgroundTasks
) -> ChatResponse:

    timings = Timings()
    session_id = request.session_id

    # Step 0: Input guardrail
    try:
        with timings.step("input_guard"):
            question = check_question(request.question)
    except GuardrailError as e:
        return _message(timings, background_tasks, session_id, "unsafe", request.question, str(e))

    # Step 1: Route the question, while looking up similar examples in parallel
    router_call = _executor.submit(
        _timed, timings, "router", classify_intent, question, schema_text
    )
    examples_call = _executor.submit(
        _timed, timings, "retrieve_examples", find_similar, question
    )

    intent = router_call.result().intent

    if intent == "greeting":
        return _message(timings, background_tasks, session_id, intent, question, GREETING_MESSAGE)

    if intent == "off_topic":
        return _message(timings, background_tasks, session_id, intent, question, OFF_TOPIC_MESSAGE)

    if intent == "unsafe":
        return _message(timings, background_tasks, session_id, intent, question, UNSAFE_MESSAGE)

    # Step 2: Similar solved examples (dynamic few-shot)
    examples, question_vector = examples_call.result()

    # Step 3: Generate SQL and check it
    with timings.step("generate_sql"):
        generation = generate_sql(
            question,
            schema_text,
            examples
        )

    if not generation.can_answer:
        return _message(timings, background_tasks, session_id, "off_topic", question, CANNOT_ANSWER_MESSAGE)

    try:
        with timings.step("sql_guard"):
            sql = validate_sql(generation.sql, schema.table_names)
    except UnknownTableError:
        return _message(timings, background_tasks, session_id, "off_topic", question, CANNOT_ANSWER_MESSAGE)
    except GuardrailError as e:
        return _message(timings, background_tasks, session_id, "unsafe", question, f"{UNSAFE_MESSAGE} ({e})")

    # Step 4: Execute SQL (read-only transaction)
    with timings.step("execute_sql"):
        query = execute_sql(sql)

    # Step 5: Learn from the chat (after the response is sent): the pair
    # passed the guard, ran, and returned rows
    if query.rows:
        background_tasks.add_task(remember, question, sql, question_vector)

    # Step 6: Format the result — return both the raw table and an
    # LLM-generated natural-language answer together
    if not query.rows:
        result = TextResult(answer=NO_DATA_MESSAGE)

    else:
        records = [dict(zip(query.columns, row)) for row in query.rows]

        with timings.step("generate_answer"):
            answer = generate_answer(question, sql, records)

        result = TableResult(**query.model_dump(), answer=answer)

    return _finish(
        timings,
        background_tasks,
        session_id,
        question,
        intent="data_question",
        question=question,
        sql=sql,
        result=result
    )
```

- [ ] **Step 4: Add `get_chat_history`**

At the end of `app/controllers/chat_controller.py`:

```python
def get_chat_history(session_id: str) -> list[HistoryEntry]:

    rows = get_history(session_id)

    return [
        HistoryEntry(
            question=row.question,
            response=ChatResponse.model_validate(row.response),
            created_at=row.created_at
        )
        for row in rows
    ]
```

- [ ] **Step 5: Verify the module imports cleanly**

Run: `python -c "import app.controllers.chat_controller"`
Expected: no output, exit code 0.

- [ ] **Step 6: Commit**

```bash
git add app/controllers/chat_controller.py
git commit -m "Persist every chat exchange and add get_chat_history

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: `GET /chat/history` route, startup schema creation, CORS

**Files:**
- Modify: `app/routes/chat_route.py`
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `app.controllers.chat_controller.get_chat_history`, `app.models.history_model.ensure_chat_history_schema`.
- Produces: `GET /chat/history?session_id=...` → `list[HistoryEntry]`. App now accepts cross-origin requests from `http://localhost:5173`.

- [ ] **Step 1: Add the history route**

In `app/routes/chat_route.py`:

```python
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.controllers import chat_controller
from app.views.chat_view import ChatRequest, ChatResponse, HistoryEntry

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/chat", response_model=ChatResponse, response_model_exclude_none=True)
def chat(request: ChatRequest, background_tasks: BackgroundTasks):

    try:
        return chat_controller.chat_with_database(request, background_tasks)

    except SQLAlchemyError:
        logger.exception("SQL execution error")
        raise HTTPException(status_code=400, detail="SQL execution error.")


@router.get("/chat/history", response_model=list[HistoryEntry])
def chat_history(session_id: str):

    return chat_controller.get_chat_history(session_id)
```

- [ ] **Step 2: Create the history schema at startup and enable CORS**

In `app/main.py`:

```python
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.controllers import chat_controller
from app.models.history_model import ensure_chat_history_schema
from app.routes import chat_route
from app.services import example_service

logging.basicConfig(level=logging.INFO)
for name in ("httpx", "httpx2"):
    logging.getLogger(name).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    chat_controller.load_schema()
    example_service.load_examples()

    try:
        ensure_chat_history_schema()
    except Exception as e:
        logger.warning("Chat history storage is off: %s", e)

    yield


app = FastAPI(title="Chat With Database", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_route.router)
```

- [ ] **Step 3: Start the app and verify both endpoints manually**

Run: `uvicorn app.main:app --reload` (needs `docker compose -f docker/docker-compose.yml up -d` for Qdrant, per the README, and a working `.env`).

In another terminal:
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "How many artists are there?", "session_id": "manual-test"}' | python -m json.tool

curl -s "http://localhost:8000/chat/history?session_id=manual-test" | python -m json.tool
```
Expected: the first call returns a `ChatResponse` with `result.type == "table"` and a non-null `result.answer`; the second call returns a one-element list whose `response` matches the first call's body.

- [ ] **Step 4: Clean up the manual-test row**

```bash
python -c "
from sqlalchemy import text
from app.models.database import engine
with engine.begin() as conn:
    conn.execute(text(\"DELETE FROM app.chat_history WHERE session_id = 'manual-test'\"))
print('cleaned')
"
```

- [ ] **Step 5: Commit**

```bash
git add app/routes/chat_route.py app/main.py
git commit -m "Add GET /chat/history endpoint, startup schema creation, and CORS

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Frontend scaffold — Vite + React, API client, session id

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/main.jsx`
- Create: `frontend/src/session.js`
- Create: `frontend/src/api.js`
- Create: `frontend/.gitignore`

**Interfaces:**
- Produces:
  - `getSessionId(): string` (from `session.js`)
  - `getHistory(sessionId: string): Promise<Array<{question: string, response: object, created_at: string}>>`
  - `sendMessage(sessionId: string, question: string): Promise<object>` (the `ChatResponse` JSON)
  - Both `api.js` functions call `http://localhost:8000` — used by Task 6's `App.jsx`.

- [ ] **Step 1: `frontend/package.json`**

```json
{
  "name": "chat-with-database-frontend",
  "private": true,
  "version": "0.0.1",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.1",
    "vite": "^5.4.0"
  }
}
```

- [ ] **Step 2: `frontend/vite.config.js`**

```javascript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
});
```

- [ ] **Step 3: `frontend/index.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Chat With Database</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

- [ ] **Step 4: `frontend/src/session.js`**

```javascript
const STORAGE_KEY = "chat_session_id";

export function getSessionId() {
  let sessionId = localStorage.getItem(STORAGE_KEY);

  if (!sessionId) {
    sessionId = crypto.randomUUID();
    localStorage.setItem(STORAGE_KEY, sessionId);
  }

  return sessionId;
}
```

- [ ] **Step 5: `frontend/src/api.js`**

```javascript
const API_BASE = "http://localhost:8000";

export async function getHistory(sessionId) {
  const response = await fetch(
    `${API_BASE}/chat/history?session_id=${encodeURIComponent(sessionId)}`
  );

  if (!response.ok) {
    throw new Error(`Failed to load history: ${response.status}`);
  }

  return response.json();
}

export async function sendMessage(sessionId, question) {
  const response = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, session_id: sessionId }),
  });

  if (!response.ok) {
    throw new Error(`Chat request failed: ${response.status}`);
  }

  return response.json();
}
```

- [ ] **Step 6: `frontend/src/main.jsx`** (minimal placeholder — `App.jsx` arrives in Task 6)

```jsx
import React from "react";
import ReactDOM from "react-dom/client";
import "./index.css";

function App() {
  return <div>Loading chat UI...</div>;
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

- [ ] **Step 7: `frontend/src/index.css`** (empty placeholder — filled in Task 7)

```css
body {
  margin: 0;
}
```

- [ ] **Step 8: `frontend/.gitignore`**

```
node_modules
dist
```

- [ ] **Step 9: Install dependencies and verify the dev server boots**

Run:
```bash
cd frontend
npm install
npm run dev
```
Expected: Vite prints a local URL (e.g. `http://localhost:5173/`); opening it in a browser shows "Loading chat UI...". Stop the dev server (Ctrl+C) once confirmed.

- [ ] **Step 10: Commit**

```bash
cd ..
git add frontend/package.json frontend/vite.config.js frontend/index.html \
        frontend/src/main.jsx frontend/src/session.js frontend/src/api.js \
        frontend/src/index.css frontend/.gitignore
git commit -m "Scaffold Vite + React frontend with API client and session id

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

(`node_modules` and `package-lock.json` are excluded/handled by `.gitignore`; `package-lock.json` itself should be committed if `npm install` generated one — check `git status` and add it if present, since lockfiles are meant to be tracked.)

---

### Task 6: Chat UI — message list, input, result rendering

**Files:**
- Create: `frontend/src/components/Message.jsx`
- Modify: `frontend/src/main.jsx` (replace placeholder with the real `App`)
- Create: `frontend/src/App.jsx`

**Interfaces:**
- Consumes: `getSessionId` (`session.js`), `getHistory`/`sendMessage` (`api.js`), both from Task 5.
- Produces: rendered chat UI. No further tasks depend on this one's exports — it's the leaf of the tree.

- [ ] **Step 1: `frontend/src/components/Message.jsx`**

```jsx
export default function Message({ role, question, response, error }) {
  if (role === "user") {
    return (
      <div className="message message-user">
        <div className="bubble">{question}</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="message message-assistant">
        <div className="bubble bubble-error">Something went wrong, try again.</div>
      </div>
    );
  }

  const result = response.result;

  return (
    <div className="message message-assistant">
      <div className="bubble">
        {result.type === "table" ? (
          <>
            {result.answer && <p>{result.answer}</p>}
            <table>
              <thead>
                <tr>
                  {result.columns.map((column) => (
                    <th key={column}>{column}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.rows.map((row, rowIndex) => (
                  <tr key={rowIndex}>
                    {row.map((cell, cellIndex) => (
                      <td key={cellIndex}>{String(cell)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            {result.truncated && <p className="truncated-note">Results truncated.</p>}
          </>
        ) : (
          <p>{result.type === "message" ? result.message : result.answer}</p>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: `frontend/src/App.jsx`**

```jsx
import { useEffect, useRef, useState } from "react";
import { getHistory, sendMessage } from "./api";
import { getSessionId } from "./session";
import Message from "./components/Message";

export default function App() {
  const [sessionId] = useState(getSessionId);
  const [exchanges, setExchanges] = useState([]);
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    getHistory(sessionId)
      .then((entries) => {
        setExchanges(
          entries.map((entry) => ({
            question: entry.question,
            response: entry.response,
            error: false,
          }))
        );
      })
      .catch(() => {
        // No history yet, or the store is unreachable — start with an empty chat.
      });
  }, [sessionId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [exchanges, sending]);

  async function handleSubmit(event) {
    event.preventDefault();

    const trimmed = question.trim();
    if (!trimmed || sending) return;

    setQuestion("");
    setSending(true);

    try {
      const response = await sendMessage(sessionId, trimmed);
      setExchanges((prev) => [...prev, { question: trimmed, response, error: false }]);
    } catch {
      setExchanges((prev) => [...prev, { question: trimmed, response: null, error: true }]);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="chat">
      <header className="chat-header">Chat With Database</header>

      <div className="chat-messages">
        {exchanges.map((exchange, index) => (
          <div key={index}>
            <Message role="user" question={exchange.question} />
            <Message
              role="assistant"
              response={exchange.response}
              error={exchange.error}
            />
          </div>
        ))}
        {sending && (
          <div className="message message-assistant">
            <div className="bubble bubble-pending">Thinking…</div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form className="chat-input" onSubmit={handleSubmit}>
        <input
          type="text"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask a question about the data..."
          disabled={sending}
        />
        <button type="submit" disabled={sending}>
          Send
        </button>
      </form>
    </div>
  );
}
```

- [ ] **Step 3: Wire `App` into `frontend/src/main.jsx`**

```jsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

- [ ] **Step 4: Manual verification against the running backend**

With the backend running (`uvicorn app.main:app --reload`, from Task 4) and Qdrant up:

Run: `cd frontend && npm run dev`, open the printed URL.

Verify in the browser:
- Type "How many artists are there?" and submit — a table with the `answer` text appears.
- Reload the page — the same exchange is still there (loaded from `/chat/history`).
- Open the same URL in an incognito window — it starts empty (different `session_id`).
- Open browser dev tools → Application → Local Storage — confirm a `chat_session_id` key exists.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.jsx frontend/src/main.jsx frontend/src/components/Message.jsx
git commit -m "Add chat UI: message list, input, per-result-type rendering

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: Styling and final end-to-end pass

**Files:**
- Modify: `frontend/src/index.css`
- Modify: `README.md`

**Interfaces:**
- Consumes: class names already used in `Message.jsx`/`App.jsx` (Task 6): `chat`, `chat-header`, `chat-messages`, `chat-input`, `message`, `message-user`, `message-assistant`, `bubble`, `bubble-error`, `bubble-pending`, `truncated-note`.
- Produces: nothing further downstream — this is the last task.

- [ ] **Step 1: `frontend/src/index.css`**

```css
* {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: system-ui, -apple-system, sans-serif;
  background: #f5f5f7;
}

.chat {
  display: flex;
  flex-direction: column;
  height: 100vh;
  max-width: 720px;
  margin: 0 auto;
  background: #fff;
  border-left: 1px solid #e0e0e0;
  border-right: 1px solid #e0e0e0;
}

.chat-header {
  padding: 16px;
  font-weight: 600;
  border-bottom: 1px solid #e0e0e0;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.message {
  display: flex;
}

.message-user {
  justify-content: flex-end;
}

.message-assistant {
  justify-content: flex-start;
}

.bubble {
  max-width: 85%;
  padding: 10px 14px;
  border-radius: 12px;
  background: #eef1f5;
}

.message-user .bubble {
  background: #0a84ff;
  color: #fff;
}

.bubble-error {
  background: #ffe5e5;
  color: #a30000;
}

.bubble-pending {
  color: #666;
  font-style: italic;
}

.truncated-note {
  color: #888;
  font-size: 0.85em;
}

table {
  border-collapse: collapse;
  margin-top: 8px;
  width: 100%;
}

th, td {
  border: 1px solid #d0d0d0;
  padding: 4px 8px;
  text-align: left;
  font-size: 0.9em;
}

.chat-input {
  display: flex;
  gap: 8px;
  padding: 16px;
  border-top: 1px solid #e0e0e0;
}

.chat-input input {
  flex: 1;
  padding: 10px 12px;
  border: 1px solid #d0d0d0;
  border-radius: 8px;
  font-size: 1em;
}

.chat-input button {
  padding: 10px 16px;
  border: none;
  border-radius: 8px;
  background: #0a84ff;
  color: #fff;
  font-size: 1em;
  cursor: pointer;
}

.chat-input button:disabled {
  background: #a0c8f0;
  cursor: default;
}
```

- [ ] **Step 2: Document the new pieces in `README.md`**

Add a new section after the existing "Run locally" section:

```markdown
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
```

- [ ] **Step 3: Full end-to-end manual pass**

With Qdrant, the backend (`uvicorn app.main:app --reload`), and the frontend (`npm run dev`, from `frontend/`) all running:

- Ask a data question with multiple rows (e.g. "List the top 5 selling artists") — confirm the table renders with borders/readable spacing, and the `answer` text appears above it.
- Ask a greeting ("hi") — confirm it renders as plain text, and shows up in `/chat/history` too (not just `data_question`s).
- Ask an off-topic question — same check.
- Reload — confirm all of the above are restored in order.
- Resize the browser window narrow — confirm the layout doesn't break (fixed max-width column, no horizontal scroll of the page itself; the table may scroll within its bubble, which is acceptable).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/index.css README.md
git commit -m "Style the chat UI and document the frontend in the README

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Self-Review Notes

- **Spec coverage:** storage location/rationale → Task 1; `session_id` request field + `HistoryEntry` → Task 2; background persistence for all four intents + history retrieval → Task 3; `GET /chat/history`, startup schema creation, CORS → Task 4; frontend scaffold/session/API client → Task 5; message list/input/per-type rendering → Task 6; styling + README + full manual pass → Task 7. All spec sections have a task.
- **Placeholder scan:** no TBD/TODO; every step has literal code or an exact command.
- **Type consistency:** `HistoryRow` (model layer, `response: dict`) vs `HistoryEntry` (view layer, `response: ChatResponse`) are intentionally different — the controller's `get_chat_history` is exactly the seam that converts one to the other via `ChatResponse.model_validate`. `save_message`'s `response: dict` parameter matches `response.model_dump(mode="json")` at its one call site in Task 3.
