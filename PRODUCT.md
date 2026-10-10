# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Non-technical analysts who need answers from a PostgreSQL database without writing SQL. They ask questions in plain language and expect a plain-language answer they can trust.

## Product Purpose

Chat With Database turns a natural-language question into SQL, runs it read-only against PostgreSQL, and answers in plain language. The demo uses the Chinook database; users can connect their own database from the UI. Success: an analyst gets a correct answer, and can see how it was reached, without SQL knowledge.

## Positioning

- Transparent pipeline: the response exposes generated SQL, result tables, per-step timings, cache hits and retries alongside the answer.
- Safety guardrails: input check for prompt injection, SQL guard (single SELECT, known tables only), read-only execution with timeout and row cap.
- Learns from usage: successful queries are stored as few-shot examples for later questions.
- Bring your own database: connections are managed from the UI.

## Operating Context

- Chat UI with per-browser anonymous session_id; history persisted server-side and restored on reload.
- Follow-up questions use the last 3 exchanges.
- Sidebar shows connections and schema tree.
- Responses are either a message or a table result (queries with columns, rows, truncated flag) plus an answer.
- Backend: FastAPI + LangGraph, Azure OpenAI, Qdrant, Redis.

## Capabilities and Constraints

- Frontend is React + Vite (`frontend/`); stack stays as is.
- Router classifies messages: greeting, data_question, off_topic, unsafe; only data questions run SQL.
- Results capped by MAX_ROWS; the answer is written from the first 20 rows.
- SQL errors are retried up to 3 attempts before a "can't answer" message.

## Evidence on Hand

Chinook demo data in `data/*.csv`, schema diagram `docs/Schema.jpg`, pipeline docs in `docs/workflow.md`. No testimonials, customers or benchmarks exist; do not fabricate them.

## Product Principles

1. Trust through visibility: show how an answer was produced, but keep the plain-language answer first for non-technical readers.
2. Safe by default: never imply write access; make guardrail refusals clear and calm.
3. Plain language over jargon: SQL and timings are available detail, not the headline.
4. Honest failure: when the system cannot answer, say so rather than guess.
