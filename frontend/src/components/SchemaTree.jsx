import { useMemo, useState } from "react";

function matches(table, query) {
  if (!query) return true;
  const q = query.toLowerCase();
  if (table.name.toLowerCase().includes(q)) return true;
  return table.columns.some((column) => column.name.toLowerCase().includes(q));
}

export default function SchemaTree({ tables }) {
  const [filter, setFilter] = useState("");
  const [expanded, setExpanded] = useState(() => new Set());

  const visibleTables = useMemo(
    () => tables.filter((table) => matches(table, filter)),
    [tables, filter]
  );

  function toggle(name) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
  }

  return (
    <div className="schema-tree">
      <input
        type="text"
        className="schema-filter"
        placeholder="Filter tables or columns..."
        value={filter}
        onChange={(event) => setFilter(event.target.value)}
      />

      {tables.length === 0 && (
        <div className="schema-empty">No tables found.</div>
      )}

      {tables.length > 0 && visibleTables.length === 0 && (
        <div className="schema-empty">No matches for "{filter}".</div>
      )}

      <ul className="schema-table-list">
        {visibleTables.map((table) => {
          const isOpen = expanded.has(table.name) || Boolean(filter);

          return (
            <li key={table.name} className="schema-table">
              <button
                type="button"
                className="schema-table-header"
                onClick={() => toggle(table.name)}
              >
                <span className={`schema-caret ${isOpen ? "schema-caret-open" : ""}`}>
                  ▸
                </span>
                <span className="schema-table-name">{table.name}</span>
                <span className="schema-column-count">{table.columns.length}</span>
              </button>

              {isOpen && (
                <ul className="schema-column-list">
                  {table.columns.map((column) => {
                    const isPrimaryKey = table.primary_key.includes(column.name);
                    const foreignKey = table.foreign_keys.find((fk) =>
                      fk.columns.includes(column.name)
                    );

                    return (
                      <li key={column.name} className="schema-column">
                        <span className="schema-column-name">{column.name}</span>
                        <span className="schema-column-type">{column.type}</span>
                        {isPrimaryKey && <span className="schema-badge schema-badge-pk">PK</span>}
                        {foreignKey && (
                          <span className="schema-badge schema-badge-fk">
                            FK → {foreignKey.references_table}
                          </span>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
