import { useState } from "react";
import SchemaTree from "./SchemaTree";

export default function Sidebar({ connection, connecting, onConnect, workflow, onWorkflowChange }) {
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
        <div className="sidebar-heading">Database</div>

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

        <button
          type="button"
          className="sidebar-link-button"
          onClick={() => setFormOpen((open) => !open)}
        >
          {formOpen ? "Cancel" : "Connect a database"}
        </button>

        {formOpen && (
          <form className="connect-form" onSubmit={handleSubmit}>
            <input
              type="text"
              placeholder="postgresql://user:password@host:5432/dbname"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              disabled={connecting}
              autoFocus
            />
            <input
              type="text"
              placeholder="Label (optional)"
              value={label}
              onChange={(event) => setLabel(event.target.value)}
              disabled={connecting}
            />
            {formError && <div className="connect-error">{formError}</div>}
            <button type="submit" disabled={connecting || !url.trim()}>
              {connecting ? "Connecting…" : "Connect"}
            </button>
          </form>
        )}
      </div>

      <div className="sidebar-section">
        <div className="sidebar-heading">Workflow</div>

        <div className="workflow-options">
          <label className="workflow-option">
            <input
              type="radio"
              name="workflow"
              value="router"
              checked={workflow === "router"}
              onChange={() => onWorkflowChange("router")}
            />
            <span>
              <strong>With router</strong>
              <span className="workflow-option-note">
                Classifies intent first, uses few-shot examples. More accurate, more LLM calls.
              </span>
            </span>
          </label>

          <label className="workflow-option">
            <input
              type="radio"
              name="workflow"
              value="no_router"
              checked={workflow === "no_router"}
              onChange={() => onWorkflowChange("no_router")}
            />
            <span>
              <strong>No router (faster)</strong>
              <span className="workflow-option-note">
                One combined call classifies and generates SQL together, still using few-shot examples. One fewer LLM call than "with router".
              </span>
            </span>
          </label>
        </div>
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
