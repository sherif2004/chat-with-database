import { useState } from "react";
import SchemaTree from "./SchemaTree";

export default function DatabasePanel({ connection, connecting, onConnect, canConnect = true }) {
  const [formOpen, setFormOpen] = useState(false);
  const [url, setUrl] = useState("");
  const [label, setLabel] = useState("");
  const [formError, setFormError] = useState(null);

  async function handleSubmit(event) {
    event.preventDefault();

    const trimmedUrl = url.trim();
    if (!trimmedUrl || connecting) return;

    setFormError(null);

    try {
      await onConnect(trimmedUrl, label.trim());
      setUrl("");
      setLabel("");
      setFormOpen(false);
    } catch (error) {
      setFormError(error.message);
    }
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-section">
        <div className="sidebar-heading">Connected database</div>

        <div className="connection-status">
          <span
            className={`connection-dot ${
              connection?.error ? "connection-dot-error" : "connection-dot-ok"
            }`}
          />
          <div className="connection-text">
            <div className="connection-label">
              {connection ? connection.label : "Loading..."}
            </div>
            <div className="connection-sublabel">
              {connection?.error
                ? "Saved connection unreachable — using default data"
                : connection?.is_default
                ? "Default demo data"
                : "Custom connection"}
            </div>
          </div>
        </div>

        {!canConnect && (
          <p className="connection-sublabel">Your role can only use the demo database.</p>
        )}
        {canConnect && (
          <>
        <button
          type="button"
          className="sidebar-link-button"
          aria-expanded={formOpen}
          onClick={() => setFormOpen((open) => !open)}
        >
          {formOpen ? "Cancel" : "Connect a database"}
        </button>

        {formOpen && (
          <form className="connect-form" onSubmit={handleSubmit}>
            <input
              type="password"
              autoComplete="off"
              spellCheck={false}
              aria-label="Database connection URL"
              placeholder="postgresql://user:password@host:5432/dbname"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              disabled={connecting}
              autoFocus
            />
            <input
              type="text"
              aria-label="Connection label (optional)"
              placeholder="Label (optional)"
              value={label}
              onChange={(event) => setLabel(event.target.value)}
              disabled={connecting}
            />
            {formError && <div className="connect-error" role="alert">{formError}</div>}
            <button type="submit" disabled={connecting || !url.trim()}>
              {connecting ? "Connecting…" : "Connect"}
            </button>
          </form>
        )}
          </>
        )}
      </div>

      <div className="sidebar-section sidebar-section-schema">
        <div className="sidebar-heading">Schema</div>
        {connection ? (
          <SchemaTree tables={connection.schema.tables} />
        ) : (
          <div className="schema-empty">Loading schema...</div>
        )}
      </div>
    </aside>
  );
}
