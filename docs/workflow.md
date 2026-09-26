# Message workflow

What happens to one message, from the browser to the answer on screen.

## Overview

```
Browser ──POST /chat──▶ route ──▶ controller ──▶ input guard
                                                     │
                                                     ▼
                                            cache lookup (Postgres)
                                          hit │              │ miss
                                              ▼              ▼
                                      return stored     resolve connection
                                      answer            load recent history
                                                             │
                                          ┌──────────────────┴──────────────────┐
                                          ▼ workflow = router                   ▼ workflow = no_router
                                   router (LLM call)                    retrieve examples (Qdrant)
                                     │ greeting / off_topic / unsafe             │
                                     │  → reply, stop                            ▼
                                     ▼ data_question                    route + generate SQL (one LLM call)
                              retrieve examples (Qdrant)                  │ greeting / off_topic / unsafe /
                                     ▼                                    │ cannot_answer → reply, stop
                              generate SQL (LLM call)                     ▼ data_question
                                     │ cannot answer → reply, stop        │
                                     └──────────────────┬─────────────────┘
                                                        ▼
                                                    SQL guard
                                                        ▼
                                              execute (read-only, Postgres)
                                                        ▼
                                          generate answer (LLM call)
                                                        ▼
                                  response returned ── then, in the background:
                                                       • save the exchange to chat_history
                                                       • remember question → SQL in Qdrant
```

Every step is timed. The timings, prompts, token usage and examples used are
returned in the response and shown under **Details** in the UI.

## Steps in order

Code: `app/controllers/chat_controller.py` (`chat_with_database`).

| # | Step | What it does | Code | Can stop the request? |
|---|---|---|---|---|
| 1 | **Input guard** | Trims the text; rejects empty or too-long questions (`MAX_QUESTION_LENGTH`) and prompt-injection phrasings. | `guardrails/input_guard.py` | Yes → `unsafe` message |
| 2 | **Cache lookup** | Normalizes the question (lowercase, no punctuation, single spaces) and looks for the same question in this session's `app.chat_history`. | `models/history_model.py` `get_cached_response` | Yes → returns the stored answer, `cache_hit: true` |
| 3 | **Resolve connection** | Finds the database this session is connected to: its own saved connection, or the default from `.env`. | `models/connection_model.py` `get_or_default` | Yes → `connection_error` message |
| 4 | **Load history** | Last 3 exchanges (question, answer, SQL) so follow-ups like "just for Iron Maiden" work. | `chat_controller._recent_history` | No |
| 5 | **Workflow** | Router or no-router path, chosen per session in the sidebar (see below). | `models/workflow_model.py` | — |
| 6 | **SQL guard** | Parses the generated SQL with sqlglot: one `SELECT` only, known tables only, no dangerous functions. | `guardrails/sql_guard.py` | Yes → `unsafe` / can't-answer message |
| 7 | **Execute SQL** | Runs it in a read-only transaction with a statement timeout and a row cap (`MAX_ROWS`). | `models/query_model.py` | SQL error → HTTP 400 |
| 8 | **Generate answer** | The LLM writes a short answer in the question's language from the first 20 rows. | `services/llm_service.py` `generate_answer` | LLM down → HTTP 503 |
| 9 | **Respond** | Returns the table (if rows) and the answer text. | `_finish` | — |
| 10 | **Background tasks** | Saves the exchange to `chat_history`; if the query returned rows, stores question → SQL in Qdrant as a future few-shot example. | `save_message`, `example_service.remember` | Failures are logged, never shown |

## The two workflows

Chosen per session with the **Workflow** radio buttons in the sidebar.

**With router** (default, `_chat_with_router`)
1. Router LLM call classifies the message: `greeting`, `off_topic`, `unsafe` or `data_question`. The first three return a reply in the user's language and stop.
2. Only for `data_question`: retrieve few-shot examples from Qdrant.
3. Generate SQL (LLM call). If the model says the data can't answer it, return that message.

**No router** (`_chat_without_router`)
1. Retrieve few-shot examples from Qdrant (always, since the intent isn't known yet).
2. One LLM call classifies *and* generates SQL together (`greeting`, `off_topic`, `unsafe`, `cannot_answer` or `data_question`).

Both continue with SQL guard → execute → generate answer. No-router saves one LLM
round trip but folds the safety judgment into the SQL prompt.

## Few-shot examples (Qdrant)

- **Retrieve:** the question is embedded and searched by cosine similarity; stored examples scoring at least `FEW_SHOT_MIN_SCORE` (0.6), at most 20, go into the prompt.
- **Learn:** after a successful answer with rows, the pair is saved in the background. A question or SQL that is already stored is skipped.
- If Qdrant or the embedding model is unreachable, the app answers without examples.

## The answer cache

- Lives in the `app.chat_history` table (Postgres), not in memory. Survives restarts.
- Scoped to one `session_id` (a random id kept in the browser's `localStorage`).
- Matches on the normalized question, so `Top 5 artists?` and `top 5  artists` are the same. It is word matching, not semantic.
- A hit skips everything after the input guard: no LLM call, no SQL, no Qdrant. The stored SQL is **not** re-run, so the data in the answer is as of the first time it was asked.
- Every message, hit or miss, is saved as a new history row.

## Where results come from: response shape

`intent` is `greeting`, `off_topic`, `unsafe`, `data_question` or `connection_error`.
`result` is one of:
- `{"type": "message", "message": "..."}` — a fixed or translated reply
- `{"type": "text", "answer": "..."}` — data question with no rows
- `{"type": "table", "columns": [...], "rows": [...], "answer": "..."}` — data question with rows

Also returned: `sql`, `timings_ms`, `debug` (model, workflow, prompts, token usage,
examples used) and `cache_hit`.

## Errors

| Situation | What the user sees |
|---|---|
| Empty, too long, or injection-like question | `unsafe` message from the input guard |
| Saved database unreachable | `connection_error` message; the default database is not silently used for the answer |
| Generated SQL isn't a safe read-only `SELECT` | `unsafe` message |
| SQL references a table that doesn't exist | "the data doesn't contain the information" message |
| SQL fails while running | HTTP 400, "Something went wrong" |
| Azure OpenAI call fails or times out (`LLM_TIMEOUT_SECONDS`) | HTTP 503 with a "language model is unavailable" message; not saved, not cached |
| History, cache, or settings storage down | Logged; the chat keeps working without it |
| Model output can't be parsed | Treated as `off_topic` / can't answer — never sent to SQL |
