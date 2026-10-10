import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AuthError, getActivity, getActivitySummary } from "../api";
import Icon from "./Icon";
import PageHeader from "./PageHeader";

// One entry per logged event type: its filter label, the sentence-style
// label shown in the log, and the tone of its marker. Tone is never the only
// signal: every marker sits beside its label.
const EVENTS = {
  login: { filter: "Sign-ins", label: "Signed in", tone: "ok" },
  logout: { filter: null, label: "Signed out", tone: "quiet" },
  signup: { filter: null, label: "Created an account", tone: "ok" },
  login_failed: { filter: "Failed sign-ins", label: "Failed sign-in", tone: "bad" },
  chat_viewed: { filter: "Chats viewed", label: "Viewed someone's chat", tone: "info" },
  role_changed: { filter: "Account changes", label: "Changed a role", tone: "warn" },
  user_deleted: { filter: "Account changes", label: "Deleted an account", tone: "warn" },
  data_changed: { filter: "Data changes", label: "Changed data", tone: "warn" },
};

// Filters group event types; a filter can cover more than one.
const FILTERS = [
  { id: "all", label: "All activity", events: [], count: null },
  { id: "login", label: "Sign-ins", events: ["login"], count: "logins" },
  { id: "failed", label: "Failed sign-ins", events: ["login_failed"], count: "failed_logins" },
  { id: "views", label: "Chats viewed", events: ["chat_viewed"], count: "chat_views" },
  { id: "accounts", label: "Account changes", events: ["role_changed", "user_deleted"], count: "account_changes" },
  { id: "data", label: "Data changes", events: ["data_changed"], count: "data_changes" },
];

const MEASURES = [
  { id: "questions", label: "Questions", noun: "question" },
  { id: "logins", label: "Sign-ins", noun: "sign-in" },
  { id: "failed", label: "Failed sign-ins", noun: "failed sign-in" },
  { id: "views", label: "Chats viewed", noun: "chat view" },
];

const plural = (n, noun, many = `${noun}s`) => `${n.toLocaleString()} ${n === 1 ? noun : many}`;

function relativeTime(iso) {
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 45) return "Just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days} d ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

const fullTime = (iso) =>
  new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "medium" });

function DayChart({ days, measure }) {
  const [hover, setHover] = useState(null);
  const [W, setW] = useState(720);
  const boxRef = useRef(null);

  // Draw at the real width so type stays readable on a phone.
  useEffect(() => {
    const node = boxRef.current;
    if (!node) return;
    const observer = new ResizeObserver(([entry]) => {
      setW(Math.max(260, Math.round(entry.contentRect.width)));
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  const values = days.map((day) => day[measure.id]);
  const max = Math.max(...values, 1);
  const top = Math.ceil(max / 4) * 4 || 4; // headroom, and ticks on whole numbers
  const H = 156;
  const padL = 28;
  const padB = 24;
  const plotH = H - padB - 8;
  const step = (W - padL) / days.length;
  const barW = Math.min(26, Math.max(6, step - 8));
  const labelEvery = step >= 52 ? 1 : 2;

  const x = (i) => padL + i * step + (step - barW) / 2;
  const h = (v) => (v / top) * plotH;
  const ticks = [0, top / 2, top];

  const dayLabel = (iso, long) =>
    new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, long
      ? { weekday: "long", month: "short", day: "numeric" }
      : { month: "short", day: "numeric" });

  return (
    <div className="daychart" ref={boxRef}>
      <svg
        width={W}
        height={H}
        viewBox={`0 0 ${W} ${H}`}
        role="group"
        tabIndex={0}
        aria-label={`${measure.label} per day, last ${days.length} days. Use the left and right arrow keys to read each day.`}
        onMouseLeave={() => setHover(null)}
        onFocus={() => setHover((h) => (h === null ? days.length - 1 : h))}
        onBlur={() => setHover(null)}
        onKeyDown={(event) => {
          if (event.key === "ArrowLeft") setHover((h) => Math.max(0, (h ?? days.length) - 1));
          else if (event.key === "ArrowRight") setHover((h) => Math.min(days.length - 1, (h ?? -1) + 1));
          else if (event.key === "Home") setHover(0);
          else if (event.key === "End") setHover(days.length - 1);
          else if (event.key === "Escape") setHover(null);
          else return;
          event.preventDefault();
        }}
      >
        {ticks.map((tick) => (
          <g key={tick}>
            <line
              className="daychart-grid"
              x1={padL}
              x2={W}
              y1={8 + plotH - h(tick)}
              y2={8 + plotH - h(tick)}
            />
            <text className="daychart-tick" x={padL - 6} y={8 + plotH - h(tick) + 4} textAnchor="end">
              {tick}
            </text>
          </g>
        ))}
        {days.map((day, i) => {
          const v = values[i];
          const barH = v > 0 ? Math.max(h(v), 3) : 0;
          const active = hover === i;
          return (
            <g key={day.day} onMouseEnter={() => setHover(i)}>
              <rect className="daychart-hit" x={padL + i * step} y={0} width={step} height={H - padB} />
              {v > 0 && (
                <rect
                  className={`daychart-bar${active ? " daychart-bar-active" : ""}`}
                  x={x(i)}
                  y={8 + plotH - barH}
                  width={barW}
                  height={barH}
                  rx={3}
                />
              )}
              {(days.length - 1 - i) % labelEvery === 0 && (
                <text className="daychart-tick" x={x(i) + barW / 2} y={H - 6} textAnchor="middle">
                  {dayLabel(day.day)}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      {hover !== null && (
        <div
          className="daychart-tip"
          style={{
            left: `clamp(80px, ${padL + hover * step + step / 2}px, calc(100% - 80px))`,
          }}
          role="status"
        >
          <strong>{plural(values[hover], measure.noun)}</strong>
          <span>{dayLabel(days[hover].day, true)}</span>
        </div>
      )}
    </div>
  );
}

function EventCell({ event }) {
  const info = EVENTS[event] ?? { label: event, tone: "quiet" };
  return (
    <span className="ev">
      <span className={`ev-mark ev-${info.tone}`} aria-hidden="true">
        {info.tone === "bad" && <Icon name="alert" size={14} />}
      </span>
      {info.label}
    </span>
  );
}

function who(entry) {
  return entry.actor_email ?? "Unknown";
}

function detailOf(entry) {
  const parts = [];
  if (entry.target_email) parts.push(entry.target_email);
  if (entry.detail) parts.push(entry.detail);
  return parts;
}

export default function ActivityPage({ me, onOpenRail, onUnauthorized }) {
  const [summary, setSummary] = useState(null);
  const [entries, setEntries] = useState(null);
  const [hasMore, setHasMore] = useState(false);
  const [filterId, setFilterId] = useState("all");
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [measureId, setMeasureId] = useState("questions");
  const [error, setError] = useState(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [updatedAt, setUpdatedAt] = useState(null);
  const requestId = useRef(0);

  const filter = FILTERS.find((f) => f.id === filterId);
  const measure = MEASURES.find((m) => m.id === measureId);

  const handle = useCallback(
    (e) => {
      if (e instanceof AuthError) onUnauthorized();
      setError(e.message);
    },
    [onUnauthorized]
  );

  // Debounce the search box so typing does not fire a request per key.
  useEffect(() => {
    const timer = setTimeout(() => setSearch(query.trim()), 250);
    return () => clearTimeout(timer);
  }, [query]);

  const load = useCallback(() => {
    const id = ++requestId.current;
    setError(null);
    setEntries(null);
    Promise.all([
      getActivity({ events: filter.events, q: search }),
      getActivitySummary(),
    ])
      .then(([page, overview]) => {
        if (id !== requestId.current) return;
        setEntries(page.entries);
        setHasMore(page.has_more);
        setSummary(overview);
        setUpdatedAt(new Date());
      })
      .catch((e) => id === requestId.current && handle(e));
  }, [filter, search, handle]);

  useEffect(load, [load]);

  async function loadMore() {
    const last = entries[entries.length - 1];
    setLoadingMore(true);
    try {
      const page = await getActivity({ events: filter.events, q: search, before: last.id });
      setEntries((prev) => [...prev, ...page.entries]);
      setHasMore(page.has_more);
    } catch (e) {
      handle(e);
    } finally {
      setLoadingMore(false);
    }
  }

  const sentence = useMemo(() => {
    if (!summary) return "Loading the last 7 days…";
    return `In the last 7 days ${plural(summary.active_users, "person", "people")} asked ${plural(
      summary.questions,
      "question"
    )} and signed in ${plural(summary.logins, "time")}.`;
  }, [summary]);

  return (
    <>
      <PageHeader title="Activity" onOpenRail={onOpenRail}>
        {updatedAt && (
          <span className="page-stamp">
            Updated {updatedAt.toLocaleTimeString(undefined, { timeStyle: "short" })}
          </span>
        )}
        <button type="button" className="tool-button" onClick={load}>
          <Icon name="refresh" size={14} />
          Refresh
        </button>
      </PageHeader>

      <div className="page-body">
        <p className="page-lede" aria-live="polite">
          {sentence}
        </p>

        {error && <div className="inline-error" role="alert">{error}</div>}

        <section className="panel" aria-labelledby="chart-title">
          <div className="panel-head">
            <h2 id="chart-title" className="panel-title">
              {measure.label} per day
            </h2>
            <div className="segmented" role="radiogroup" aria-label="Measure">
              {MEASURES.map((m) => (
                <label key={m.id} className="segment">
                  <input
                    type="radio"
                    name="measure"
                    value={m.id}
                    checked={measureId === m.id}
                    onChange={() => setMeasureId(m.id)}
                  />
                  <span>{m.label}</span>
                </label>
              ))}
            </div>
          </div>
          {summary ? (
            <DayChart days={summary.days} measure={measure} />
          ) : (
            <div className="daychart-skeleton" aria-hidden="true" />
          )}
        </section>

        <section className="log" aria-labelledby="log-title">
          <h2 id="log-title" className="sr-only">Activity log</h2>
          <div className="log-tools">
            <div className="pills" role="group" aria-label="Filter by event, counts are for the last 7 days">
              {FILTERS.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  className="pill"
                  aria-pressed={filterId === f.id}
                  onClick={() => setFilterId(f.id)}
                >
                  {f.label}
                  {f.count && summary != null && (
                    <span className="pill-count" title="Last 7 days">{summary[f.count]}</span>
                  )}
                </button>
              ))}
            </div>
            <label className="search">
              <Icon name="search" size={15} />
              <span className="sr-only">Search the log</span>
              <input
                type="search"
                placeholder="Search by email, detail or address"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
          </div>

          <p className="log-note">Counts on the filters cover the last 7 days. The list shows everything, newest first.</p>

          <div className="table-wrap">
            <table className="data-table activity-table">
              <caption className="sr-only">
                Activity log, newest first. Times are shown in your time zone.
              </caption>
              <thead>
                <tr>
                  <th scope="col">When</th>
                  <th scope="col">Event</th>
                  <th scope="col">Who</th>
                  <th scope="col">Details</th>
                  <th scope="col">Address</th>
                </tr>
              </thead>
              <tbody>
                {entries === null && !error &&
                  [0, 1, 2, 3, 4].map((i) => (
                    <tr key={i} className="row-skeleton" aria-hidden="true">
                      <td colSpan={5}><span /></td>
                    </tr>
                  ))}
                {entries?.map((entry) => (
                  <tr key={entry.id} className={entry.event === "login_failed" ? "row-flag" : undefined}>
                    <td className="cell-when cell-time">
                      <time dateTime={entry.at} title={fullTime(entry.at)}>
                        {relativeTime(entry.at)}
                      </time>
                    </td>
                    <td className="cell-event"><EventCell event={entry.event} /></td>
                    <td className="cell-who" title={who(entry)}>
                      {who(entry)}
                      {entry.actor_id === me.id && <span className="you">You</span>}
                    </td>
                    <td className="cell-detail">
                      {detailOf(entry).map((part, i) => (
                        <span key={i} title={part}>{part}</span>
                      ))}
                    </td>
                    <td className="cell-ip">{entry.ip ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            {entries?.length === 0 && (
              <div className="empty-state">
                <p className="empty-title">Nothing logged here yet</p>
                <p className="empty-text">
                  {search || filterId !== "all"
                    ? "No events match this filter. Try All activity or a different search."
                    : "Events appear as people sign in, view chats and change accounts."}
                </p>
              </div>
            )}
          </div>

          {hasMore && (
            <button type="button" className="tool-button load-more" onClick={loadMore} disabled={loadingMore}>
              {loadingMore ? "Loading…" : "Show older activity"}
            </button>
          )}
        </section>
      </div>
    </>
  );
}
