# Message workflow

What happens to one message, from the browser to the answer on screen.

The pipeline is a [LangGraph](https://github.com/langchain-ai/langgraph) `StateGraph`
(`app/graphs/chat_graph.py`), not hand-rolled branching — each box below is one graph
node. `app/controllers/chat_controller.py` just invokes the graph and turns the final
state into a `ChatResponse`.

## Overview

```
Browser ──POST /chat──▶ route ──▶ controller ──▶ graph.invoke()
                                                       │
                                                  input_guard
                                                       │
                                                  cache_lookup (Redis)
                                          hit  │              │ miss
                                               ▼              ▼
                                       return stored  ┌───────┴───────┐
                                       answer          ▼               ▼
                                          resolve_connection      load_history
                                                       └───────┬───────┘
                                                        (parallel, join at)
                                                        route_after_context
                                                              │
                                                       classify_intent (LLM)
                                                  │ greeting/off_topic/unsafe
                                                  │  → reply, stop
                                                  ▼ data_question
                                           retrieve_examples (Qdrant)
                                                  ▼
                                           generate_sql (LLM call)   ◀───────────┐
                                             │ cannot answer → reply, stop        │
                                             ▼                                    │
                                        validate_sql                              │
                                             ▼                                    │
                                        execute_sql (read-only, Postgres)         │
                                  ok  │              │ DB rejects it              │
                                      ▼              ▼ (< SQL_MAX_ATTEMPTS)       │
                               generate_answer   retry: loop back to generate_sql ┘
                                  (LLM call)      the failed SQL + DB error included
                                      ▼              │ (attempts exhausted)
                               response returned      ▼
                                                   sql_failed → reply, stop

                          after the response is sent, in the background:
                            • save the exchange to app.chat_history
                            • cache the response in Redis
                            • remember question → SQL in Qdrant (if it returned rows)
```

Every step is timed (a retried step's duration accumulates across attempts). The
timings, prompts, token usage and examples used are returned in the response and
shown under **Details** in the UI.

## Steps in order

Code: `app/graphs/chat_graph.py` (nodes), `app/controllers/chat_controller.py`
(invokes the graph, builds the response).

| # | Step (graph node) | What it does | Can stop the request? |
|---|---|---|---|
| 1 | `input_guard` | Trims the text; rejects empty or too-long questions (`MAX_QUESTION_LENGTH`) and prompt-injection phrasings. | Yes → `unsafe` message |
| 2 | `cache_lookup` | Normalizes the question and looks it up in Redis, scoped to this session. | Yes → returns the stored answer, `cache_hit: true` |
| 3 | `resolve_connection` \| `load_history` | Run in parallel (both only need `session_id`): finds the target database (own saved connection or the `.env` default), and loads the last 3 exchanges so follow-ups like "just for Iron Maiden" work. | Connection failure → `connection_error` message |
| 4 | `classify_intent` | LLM call (`AZURE_OPENAI_DEPLOYMENT_LIGHT`): `greeting` / `off_topic` / `unsafe` / `data_question`. | First three → reply, stop |
| 5 | `retrieve_examples` | Embeds the question and fetches similar solved question→SQL pairs from Qdrant. | No |
| 6 | `generate_sql` | LLM call (`AZURE_OPENAI_DEPLOYMENT`, the capable model) that writes the SQL. Also the **retry target** — see below. | Can't answer / clarification needed → reply, stop |
| 7 | `validate_sql` | Parses the generated SQL with sqlglot: one or more `SELECT`s only, known tables only, no dangerous functions. | Yes → `unsafe` / can't-answer message (not retried — a guard rejection is a safety issue, not a fixable mistake) |
| 8 | `execute_sql` | Runs each statement in a read-only transaction with a statement timeout and a row cap (`MAX_ROWS`). | DB rejects it → retry (see below); exhausted → can't-answer message |
| 9 | `generate_answer` | LLM call (`AZURE_OPENAI_DEPLOYMENT`, the capable model) that writes a short answer in the question's language from the first 20 rows of each statement. | LLM down → HTTP 503 |
| 10 | *(controller)* `_finish` | Builds the response; schedules the background tasks below. | — |
| 11 | Background tasks | Saves the exchange to `chat_history`; caches the response in Redis; if a query returned rows, stores question → SQL in Qdrant as a future few-shot example. | Failures are logged, never shown |

## The SQL retry loop

`execute_sql` errors (a bad column, a syntax slip the guard let through, anything
Postgres itself rejects) are caught rather than left to propagate. The failing SQL
and the database's error message are fed back into the next `generate_sql` call, so
the model can fix its own mistake — up to `SQL_MAX_ATTEMPTS` (3) attempts total
before giving up with a normal "can't answer" message instead of an HTTP error.
A `validate_sql` (guardrail) rejection is **not** retried — that's a safety
judgment, not something feeding back the error would fix.

## Few-shot examples (Qdrant)

- **Retrieve:** the question is embedded and searched by cosine similarity; stored examples scoring at least `FEW_SHOT_MIN_SCORE` (0.6), at most 20, go into the prompt.
- **Learn:** after a successful answer with rows, the pair is saved in the background. A question or SQL that is already stored is skipped.
- If Qdrant or the embedding model is unreachable, the app answers without examples.

## The answer cache (Redis)

- Lives in Redis (`app/services/cache_service.py`), not in Postgres — a plain `GET`/`SET` on a hot key, not an indexed query.
- Key: `chat_cache:<session_id>:<normalized question>`. Case, punctuation and extra whitespace are ignored; it's word matching, not semantic.
- Expires after `CACHE_TTL_SECONDS` (default 3600) — unlike the table it replaced, entries don't live forever.
- A hit skips everything after `input_guard`: no LLM call, no SQL, no Qdrant. The stored SQL is **not** re-run, so the data in the answer is as of when it was first cached (or last refreshed).
- Every message, hit or miss, is still saved as a new row in `app.chat_history` — that table is the durable conversation record, not the cache.
- A Redis outage degrades to "always miss" — the cache never blocks a response.

## Where results come from: response shape

`intent` is `greeting`, `off_topic`, `unsafe`, `needs_clarification`, `data_question` or `connection_error`.
`result` is one of:
- `{"type": "message", "message": "..."}` — a fixed or translated reply
- `{"type": "table", "queries": [{"sql", "columns", "rows", "truncated"}, ...], "answer": "..."}` — one entry per SQL statement executed (usually one), plus one natural-language answer covering all of them

Also returned: `sql` (the executed statement(s)), `timings_ms`, `debug` (model, prompts, token usage, examples used) and `cache_hit`.

## Errors

| Situation | What the user sees |
|---|---|
| Empty, too long, or injection-like question | `unsafe` message from the input guard |
| Saved database unreachable | `connection_error` message; the default database is not silently used for the answer |
| Generated SQL isn't a safe read-only `SELECT` | `unsafe` message (not retried) |
| SQL references a table that doesn't exist | "the data doesn't contain the information" message (not retried) |
| SQL fails while running (bad column, syntax, ...) | Retried up to `SQL_MAX_ATTEMPTS` (3) with the error fed back to the model; a "can't answer" message only after all attempts fail |
| Azure OpenAI call fails or times out (`LLM_TIMEOUT_SECONDS`) | HTTP 503 with a "language model is unavailable" message; not saved, not cached |
| History or cache storage down | Logged; the chat keeps working without it |
| Model output can't be parsed | Treated as `off_topic` / can't answer — never sent to SQL |
