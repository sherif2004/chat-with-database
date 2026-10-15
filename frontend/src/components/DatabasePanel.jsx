import SchemaTree from "./SchemaTree";

export default function DatabasePanel({ connection, onOpenConnect, canConnect = true }) {
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
                : `${connection?.engine ?? "Custom"} connection`}
            </div>
          </div>
        </div>

        {connection && !connection.error && !connection.read_only_enforced && (
          <p className="connection-sublabel">
            This engine can't be set to read-only here. Use a read-only account.
          </p>
        )}

        {!canConnect && (
          <p className="connection-sublabel">Your role can only use the demo database.</p>
        )}
        {canConnect && (
          <button type="button" className="sidebar-link-button" onClick={onOpenConnect}>
            {connection?.is_default ? "Connect a database" : "Change database"}
          </button>
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
