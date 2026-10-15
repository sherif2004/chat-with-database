import { useEffect, useMemo, useRef, useState } from "react";
import { AuthError, connectDatabase, getEngines, testConnection } from "../api";
import Icon from "./Icon";
import PageHeader from "./PageHeader";

/** What the form asks for, per engine. The server owns which engines exist
 *  and whether they are installed; this only decides how to ask. */
const LAYOUT = {
  postgresql: {
    example: "postgresql://user:password@host:5432/dbname",
    database: "Database name",
  },
  mysql: {
    example: "mysql+pymysql://user:password@host:3306/dbname",
    database: "Database name",
  },
  mssql: {
    example: "mssql+pyodbc://user:password@host:1433/dbname?driver=ODBC+Driver+18+for+SQL+Server",
    database: "Database name",
  },
  clickhouse: {
    example: "clickhouse+native://user:password@host:9000/dbname",
    database: "Database name",
  },
  snowflake: {
    example: "snowflake://user:password@account/database/schema?warehouse=WAREHOUSE",
    host: "Account identifier",
    hostHint: "For example xy12345.eu-west-1",
    database: "Database name",
    noPort: true,
  },
  bigquery: {
    example: "bigquery://project-id/dataset?credentials_base64=…",
    urlOnly: "BigQuery connects with a service-account key, so it needs a connection URL.",
  },
  other: {
    example: "dialect+driver://user:password@host:port/dbname",
    urlOnly: "Paste a SQLAlchemy connection URL for any other SQL database.",
  },
};

const OTHER = { key: "other", name: "Other SQL database", installed: true, read_only_enforced: false };

const EMPTY = { host: "", port: "", database: "", username: "", password: "" };

/** Turns a driver's raw message into what went wrong and what to try next. */
function explain(message) {
  const text = message || "";
  const rules = [
    [/private network/i, "This server can't reach private addresses.", "Use a publicly reachable host, or ask the administrator to allow private hosts."],
    [/isn't installed|pip install/i, "This database type isn't installed on the server.", text],
    [/password authentication failed|access denied|login failed|authentication failed|invalid (user|credentials)/i, "The server rejected the username or password.", "Check both, and that the account may sign in from this server."],
    [/could not translate host|name or service not known|getaddrinfo|unknown mysql server host|nodename nor servname|not known/i, "That host name couldn't be found.", "Check the spelling of the host."],
    [/timed? ?out|timeout|connection refused|can't connect|could not connect|no route/i, "The server didn't answer.", "Check the host and port, and that its firewall or allow-list admits this server."],
    [/does not exist|unknown database|cannot open database/i, "That database name doesn't exist on the server.", "Check the database name."],
    [/valid database url|could not parse|invalid url|no such module|can't load plugin/i, "That connection URL isn't valid.", "Check it against the example under the field."],
  ];
  for (const [pattern, what, next] of rules) {
    if (pattern.test(text)) return { what, next, detail: text === next ? "" : text };
  }
  return { what: "Couldn't connect to that database.", next: "", detail: text };
}

function EngineOption({ engine, selected, onSelect }) {
  const unavailable = !engine.installed;
  return (
    <label className={`engine-option${unavailable ? " engine-option-off" : ""}`}>
      <input
        type="radio"
        name="engine"
        value={engine.key}
        checked={selected}
        onChange={() => onSelect(engine.key)}
      />
      <span className="engine-option-body">
        <span className="engine-option-name">{engine.name}</span>
        {unavailable && <span className="engine-option-note">Not installed</span>}
      </span>
      <span className="engine-option-check" aria-hidden="true">
        <Icon name="check" size={14} />
      </span>
    </label>
  );
}

export default function ConnectPage({ onOpenRail, onBack, onConnect, onUnauthorized }) {
  const [engines, setEngines] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [engineKey, setEngineKey] = useState("postgresql");
  const [mode, setMode] = useState("details");
  const [fields, setFields] = useState(EMPTY);
  const [url, setUrl] = useState("");
  const [label, setLabel] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [check, setCheck] = useState({ state: "idle" });
  const [saving, setSaving] = useState(false);
  const resultRef = useRef(null);

  useEffect(() => {
    getEngines()
      .then((data) => setEngines(data.engines))
      .catch((e) => {
        if (e instanceof AuthError) onUnauthorized();
        else setLoadError(e.message);
      });
  }, [onUnauthorized]);

  const all = useMemo(() => [...(engines || []), OTHER], [engines]);
  const engine = all.find((e) => e.key === engineKey) || OTHER;
  const layout = LAYOUT[engine.key] || LAYOUT.other;
  const urlMode = Boolean(layout.urlOnly) || mode === "url";
  const busy = check.state === "testing" || saving;

  const ready = urlMode
    ? url.trim().length > 0
    : (engine.needs_host === false || fields.host.trim()) && fields.username.trim();

  function reset() {
    setCheck({ state: "idle" });
  }

  function chooseEngine(key) {
    setEngineKey(key);
    setFields((f) => ({ ...f, port: "" }));
    reset();
  }

  function setField(name, value) {
    setFields((f) => ({ ...f, [name]: value }));
    reset();
  }

  function payload() {
    const named = label.trim() ? { label: label.trim() } : {};
    if (urlMode) return { database_url: url.trim(), ...named };
    return {
      engine: engine.key,
      host: fields.host,
      port: fields.port ? Number(fields.port) : undefined,
      database: fields.database,
      username: fields.username,
      password: fields.password,
      ...named,
    };
  }

  async function run(action) {
    if (!ready || busy) return;

    try {
      await action();
    } catch (error) {
      if (error instanceof AuthError) return onUnauthorized();
      setSaving(false);
      setCheck({ state: "error", ...explain(error.message) });
    }
  }

  const handleTest = () =>
    run(async () => {
      setCheck({ state: "testing" });
      const result = await testConnection(payload());
      setCheck({ state: "ok", ...result });
    });

  const handleSubmit = (event) => {
    event.preventDefault();
    run(async () => {
      setSaving(true);
      await onConnect(payload());
    });
  };

  useEffect(() => {
    if (check.state === "ok" || check.state === "error") resultRef.current?.focus();
  }, [check]);

  const warnReadOnly = engine.installed && !engine.read_only_enforced;

  return (
    <>
      <PageHeader title="Connect a database" onOpenRail={onOpenRail}>
        <button type="button" className="tool-button" onClick={onBack}>
          <Icon name="back" size={14} />
          Back to chat
        </button>
      </PageHeader>

      <form className="page-body connect-page" onSubmit={handleSubmit} noValidate>
        <p className="page-lede">
          Choose the kind of database, say how to reach it, and test it before you switch.
          Questions only ever run read-only SELECT queries, and your password is encrypted
          before it is saved.
        </p>

        {loadError && <div className="inline-error" role="alert">{loadError}</div>}

        <fieldset className="connect-section" disabled={busy}>
          <legend className="connect-heading">Database type</legend>
          <div className="engine-grid" role="radiogroup" aria-label="Database type">
            {all.map((e) => (
              <EngineOption key={e.key} engine={e} selected={e.key === engineKey} onSelect={chooseEngine} />
            ))}
          </div>
          {!engines && !loadError && <p className="connect-hint">Loading database types…</p>}
        </fieldset>

        {warnReadOnly && (
          <p className="notice-line notice-warn">
            <Icon name="alert" size={15} />
            <span>
              {engine.key === "other" ? "This kind of database" : engine.name} can't be switched
              to read-only from here. Askbase still only sends SELECT queries, but connect with
              an account that has read-only permission.
            </span>
          </p>
        )}

        {!engine.installed && (
          <div className="inline-error" role="alert">
            {engine.name} isn't installed on this server. Ask the administrator to run{" "}
            <code>pip install {engine.package}</code>.
          </div>
        )}

        <fieldset className="connect-section" disabled={busy || !engine.installed}>
          <div className="connect-section-head">
            <legend className="connect-heading">Connection</legend>
            {!layout.urlOnly && (
              <div className="segmented connect-mode" role="radiogroup" aria-label="How to enter the connection">
                {[["details", "Fill in details"], ["url", "Paste a URL"]].map(([id, text]) => (
                  <label key={id} className="segment">
                    <input
                      type="radio"
                      name="mode"
                      checked={mode === id}
                      onChange={() => {
                        setMode(id);
                        reset();
                      }}
                    />
                    <span>{text}</span>
                  </label>
                ))}
              </div>
            )}
          </div>

          {layout.urlOnly && <p className="connect-hint">{layout.urlOnly}</p>}

          {urlMode ? (
            <label className="field">
              <span className="field-label">Connection URL</span>
              <input
                type={showPassword ? "text" : "password"}
                className="field-mono"
                autoComplete="off"
                spellCheck={false}
                value={url}
                placeholder={layout.example}
                onChange={(e) => {
                  setUrl(e.target.value);
                  reset();
                }}
              />
              <span className="field-hint">
                Looks like <code>{layout.example}</code>. Hidden while you type, because it
                holds the password.{" "}
                <button type="button" className="text-button" onClick={() => setShowPassword((v) => !v)}>
                  {showPassword ? "Hide" : "Show"}
                </button>
              </span>
            </label>
          ) : (
            <div className="field-grid">
              <label className={`field field-host${layout.noPort ? " field-wide" : ""}`}>
                <span className="field-label">{layout.host || "Host"}</span>
                <input
                  type="text"
                  autoComplete="off"
                  spellCheck={false}
                  value={fields.host}
                  placeholder={layout.host ? "" : "db.example.com"}
                  onChange={(e) => setField("host", e.target.value)}
                />
                {layout.hostHint && <span className="field-hint">{layout.hostHint}</span>}
              </label>

              {!layout.noPort && (
                <label className="field field-port">
                  <span className="field-label">Port</span>
                  <input
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    autoComplete="off"
                    value={fields.port}
                    placeholder={engine.default_port ? String(engine.default_port) : ""}
                    onChange={(e) => setField("port", e.target.value.replace(/\D/g, ""))}
                  />
                </label>
              )}

              <label className="field field-wide">
                <span className="field-label">{layout.database || "Database name"}</span>
                <input
                  type="text"
                  autoComplete="off"
                  spellCheck={false}
                  value={fields.database}
                  onChange={(e) => setField("database", e.target.value)}
                />
              </label>

              <label className="field">
                <span className="field-label">Username</span>
                <input
                  type="text"
                  autoComplete="off"
                  spellCheck={false}
                  value={fields.username}
                  onChange={(e) => setField("username", e.target.value)}
                />
              </label>

              <label className="field">
                <span className="field-label">Password</span>
                <span className="field-password">
                  <input
                    type={showPassword ? "text" : "password"}
                    autoComplete="new-password"
                    value={fields.password}
                    onChange={(e) => setField("password", e.target.value)}
                  />
                  <button
                    type="button"
                    className="icon-button"
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    aria-pressed={showPassword}
                    onClick={() => setShowPassword((v) => !v)}
                  >
                    <Icon name="eye" size={16} />
                  </button>
                </span>
              </label>
            </div>
          )}

          <label className="field field-label-row">
            <span className="field-label">
              Name <span className="field-optional">(optional)</span>
            </span>
            <input
              type="text"
              autoComplete="off"
              value={label}
              placeholder="How it appears in the sidebar"
              onChange={(e) => setLabel(e.target.value)}
            />
          </label>
        </fieldset>

        <div className="connect-result" aria-live="polite">
          {check.state === "testing" && <p className="status-line">Testing the connection…</p>}

          {check.state === "ok" && (
            <div className="result result-ok" tabIndex={-1} ref={resultRef}>
              <Icon name="check" size={16} />
              <p>
                <strong>Reached {check.label}.</strong> Found {check.table_count}{" "}
                {check.table_count === 1 ? "table" : "tables"}.
                {check.table_count === 0 && " The account may not be allowed to see any."}
              </p>
            </div>
          )}

          {check.state === "error" && (
            <div className="result result-error" role="alert" tabIndex={-1} ref={resultRef}>
              <Icon name="alert" size={16} />
              <div>
                <p>
                  <strong>{check.what}</strong> {check.next}
                </p>
                {check.detail && <p className="result-detail">{check.detail}</p>}
              </div>
            </div>
          )}
        </div>

        <div className="connect-actions">
          <button type="submit" className="action-primary" disabled={!ready || busy || !engine.installed}>
            {saving ? "Connecting…" : "Connect and switch"}
          </button>
          <button
            type="button"
            className="action-secondary"
            disabled={!ready || busy || !engine.installed}
            onClick={handleTest}
          >
            Test connection
          </button>
        </div>
      </form>
    </>
  );
}
