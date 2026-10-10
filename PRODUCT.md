# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Analysts (role: user)** ask plain-language questions about a PostgreSQL database and read the answers, SQL and result tables. They are not necessarily technical.
- **Supervisors** do the same, may connect their own database, and may read other users' chats (read-only).
- **Admins** do everything above, manage accounts and roles, and may change data through chat after a preview and an explicit confirmation. Admins also need an activity dashboard (confirmed in session): both an audit view (who signed in, failed sign-ins, who viewed whose chats, role and account changes) and a usage view (how the app is used over time).

## Product Purpose

Askbase turns a question into a safe, read-only SQL query, runs it, and answers in plain language, with the SQL and result table one click away. Success: a non-technical person gets a correct answer fast and can see how it was produced. For admins, success also means being able to answer "who did what, and when" without opening the database.

## Positioning

Every answer shows its work (SQL and table) and every privileged action leaves a trace: chat stays read-only, changes are previewed and confirmed, and other people's chats can only be viewed, never edited.

## Operating Context

Single web app: FastAPI backend, React frontend (plain CSS), PostgreSQL, Redis, Qdrant. Sessions use httpOnly cookies. Three roles: user, supervisor, admin.

## Capabilities and Constraints

- Roles and permissions are defined in `app/services/permissions.py`; the backend is the authority and the UI only hides what a role cannot use.
- Event types to log and show (confirmed): sign-ins and sign-outs, failed sign-ins, chats viewed by another user, account and role changes. Admin data changes are already recorded in `app.data_changes`.
- UX improvement scope (confirmed): chat screen and results, sidebar and navigation. The existing brand look (see `.impeccable/design.json`) stays; this refines it.
- Undecided: retention period for activity logs; sign-in screen and mobile/accessibility passes were not selected for this round.

## Evidence on Hand

Real data only. There are no customer testimonials, benchmarks or usage numbers; the dashboard must show real logged events and never invented figures.

## Product Principles

1. Show the work: answers, SQL and audit trails are visible, not hidden.
2. Read-only by default; anything that changes data or accounts needs a role and leaves a record.
3. Plain language over jargon for analysts; precise detail for admins.
4. The backend decides permissions; the interface never implies access a role lacks.
