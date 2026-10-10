import logging
from datetime import date, datetime, timedelta, timezone

from pydantic import BaseModel
from sqlalchemy import text

from app.models.database import app_engine, retry_on_disconnect, run_ddl, run_or_log

logger = logging.getLogger(__name__)

EVENTS = (
    "signup",
    "login",
    "login_failed",
    "logout",
    "chat_viewed",
    "role_changed",
    "user_deleted",
    "data_changed",
)

_DETAIL_MAX = 300
_EMAIL_MAX = 254


class ActivityEntry(BaseModel):
    id: int
    at: datetime
    event: str
    actor_id: int | None
    actor_email: str | None
    target_id: int | None
    target_email: str | None
    detail: str | None
    ip: str | None


class DayCounts(BaseModel):
    day: date
    logins: int = 0
    failed: int = 0
    views: int = 0
    questions: int = 0


class ActivitySummary(BaseModel):
    days: list[DayCounts]
    logins: int
    failed_logins: int
    chat_views: int
    account_changes: int
    data_changes: int
    questions: int
    active_users: int


def ensure_activity_schema() -> None:
    run_ddl(
        "CREATE SCHEMA IF NOT EXISTS app",
        """
        CREATE TABLE IF NOT EXISTS app.activity_log (
            id BIGSERIAL PRIMARY KEY,
            at TIMESTAMPTZ NOT NULL DEFAULT now(),
            event TEXT NOT NULL,
            actor_id BIGINT,
            actor_email TEXT,
            target_id BIGINT,
            target_email TEXT,
            detail TEXT,
            ip TEXT
        )
        """,
        "CREATE INDEX IF NOT EXISTS activity_log_at_idx ON app.activity_log (at DESC)",
        "CREATE INDEX IF NOT EXISTS activity_log_event_idx ON app.activity_log (event, at DESC)",
    )


def record_activity(
    event: str,
    *,
    actor=None,
    actor_email: str | None = None,
    target=None,
    detail: str | None = None,
    ip: str | None = None,
) -> None:
    """Best-effort: a logging failure is reported but never breaks the action
    that triggered it. `actor` / `target` are User objects; `actor_email`
    covers an attempt by someone with no account (a failed sign-in)."""

    row = {
        "event": event,
        "actor_id": actor.id if actor else None,
        "actor_email": (actor.email if actor else actor_email or None),
        "target_id": target.id if target else None,
        "target_email": target.email if target else None,
        "detail": detail[:_DETAIL_MAX] if detail else None,
        "ip": ip,
    }
    if row["actor_email"]:
        row["actor_email"] = row["actor_email"][:_EMAIL_MAX]

    def run():
        with app_engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO app.activity_log
                        (event, actor_id, actor_email, target_id, target_email, detail, ip)
                    VALUES
                        (:event, :actor_id, :actor_email, :target_id, :target_email, :detail, :ip)
                """),
                row,
            )

    run_or_log(run, logger, "Could not record %s activity: %s", event)


def list_activity(
    events: list[str] | None, query: str | None, before_id: int | None, limit: int
) -> tuple[list[ActivityEntry], bool]:
    """Newest first. Returns the page and whether more (older) rows exist."""

    clauses, params = [], {"limit": limit + 1}

    if events:
        clauses.append("event = ANY(:events)")
        params["events"] = events
    if query:
        clauses.append(
            "(actor_email ILIKE :q OR target_email ILIKE :q OR detail ILIKE :q OR ip ILIKE :q)"
        )
        params["q"] = f"%{query.replace('%', '').replace('_', '')}%"
    if before_id:
        clauses.append("id < :before")
        params["before"] = before_id

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    def run():
        with app_engine.connect() as conn:
            rows = conn.execute(
                text(f"""
                    SELECT id, at, event, actor_id, actor_email, target_id,
                           target_email, detail, ip
                    FROM app.activity_log {where}
                    ORDER BY id DESC LIMIT :limit
                """),
                params,
            ).all()
            return [ActivityEntry(**dict(r._mapping)) for r in rows]

    rows = retry_on_disconnect(run)
    return rows[:limit], len(rows) > limit


def activity_summary(days: int = 14) -> ActivitySummary:
    """Per-day counts for the last `days` days (UTC) plus the last-7-day totals.
    Questions come from the chat history itself, so they cover the period
    before logging existed."""

    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days - 1)
    series = {start + timedelta(days=i): DayCounts(day=start + timedelta(days=i)) for i in range(days)}
    week_start = today - timedelta(days=6)

    def run():
        with app_engine.connect() as conn:
            events = conn.execute(
                text("""
                    SELECT (at AT TIME ZONE 'UTC')::date AS day, event, count(*) AS n
                    FROM app.activity_log
                    WHERE at >= :start AND event IN ('login', 'login_failed', 'chat_viewed')
                    GROUP BY 1, 2
                """),
                {"start": start},
            ).all()
            questions = conn.execute(
                text("""
                    SELECT (created_at AT TIME ZONE 'UTC')::date AS day, count(*) AS n
                    FROM app.chat_history WHERE created_at >= :start GROUP BY 1
                """),
                {"start": start},
            ).all()
            week = conn.execute(
                text("""
                    SELECT
                        count(*) FILTER (WHERE event = 'role_changed' OR event = 'user_deleted') AS changes,
                        count(*) FILTER (WHERE event = 'data_changed') AS data_changes
                    FROM app.activity_log WHERE at >= :week
                """),
                {"week": week_start},
            ).one()
            active = conn.execute(
                text("""
                    SELECT count(DISTINCT session_id) FROM app.chat_history
                    WHERE created_at >= :week
                """),
                {"week": week_start},
            ).scalar_one()
            return events, questions, week.changes, week.data_changes, active

    events, questions, changes, data_changes, active = retry_on_disconnect(run)

    key = {"login": "logins", "login_failed": "failed", "chat_viewed": "views"}
    for row in events:
        if row.day in series:
            setattr(series[row.day], key[row.event], row.n)
    for row in questions:
        if row.day in series:
            series[row.day].questions = row.n

    recent = [d for d in series.values() if d.day >= week_start]

    return ActivitySummary(
        days=list(series.values()),
        logins=sum(d.logins for d in recent),
        failed_logins=sum(d.failed for d in recent),
        chat_views=sum(d.views for d in recent),
        account_changes=changes,
        data_changes=data_changes,
        questions=sum(d.questions for d in recent),
        active_users=active,
    )
