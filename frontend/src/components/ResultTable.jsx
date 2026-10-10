import { useMemo, useState } from "react";
import Icon from "./Icon";

const COLLAPSED_ROWS = 10;
const CHART_MAX_ROWS = 30;

const isNumber = (value) => typeof value === "number" && Number.isFinite(value);

function compare(a, b) {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  if (isNumber(a) && isNumber(b)) return a - b;
  return String(a).localeCompare(String(b), undefined, { numeric: true });
}

function toCsv(columns, rows) {
  const escape = (value) => {
    const text = value == null ? "" : String(value);
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  return [columns, ...rows].map((row) => row.map(escape).join(",")).join("\n");
}

function toTsv(columns, rows) {
  return [columns, ...rows]
    .map((row) => row.map((cell) => (cell == null ? "" : String(cell))).join("\t"))
    .join("\n");
}

function BarChart({ labels, values, labelName, valueName }) {
  const max = Math.max(...values, 0) || 1;
  return (
    <ul className="chart" aria-label={`${valueName} by ${labelName}`}>
      {labels.map((label, index) => (
        <li key={index} className="chart-row">
          <span className="chart-label" title={String(label)}>
            {String(label)}
          </span>
          <span className="chart-track">
            <span
              className="chart-bar"
              style={{ width: `${Math.max((values[index] / max) * 100, 1)}%` }}
            />
          </span>
          <span className="chart-value">{values[index].toLocaleString()}</span>
        </li>
      ))}
    </ul>
  );
}

export default function ResultTable({ query, label }) {
  const { columns, rows, truncated } = query;
  const [sort, setSort] = useState(null); // { index, direction }
  const [showAll, setShowAll] = useState(false);
  const [view, setView] = useState("table");
  const [copied, setCopied] = useState(false);

  const numericColumns = useMemo(
    () =>
      columns.map((_, index) => {
        const cells = rows.map((row) => row[index]).filter((cell) => cell != null);
        return cells.length > 0 && cells.every(isNumber);
      }),
    [columns, rows]
  );

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const direction = sort.direction === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => direction * compare(a[sort.index], b[sort.index]));
  }, [rows, sort]);

  // A chart makes sense for "a label, then a number" with a few rows.
  const chartValueIndex = numericColumns.findIndex(
    (numeric, index) => index > 0 && numeric
  );
  const canChart =
    !numericColumns[0] &&
    chartValueIndex > 0 &&
    rows.length >= 2 &&
    rows.length <= CHART_MAX_ROWS;

  const visible = showAll ? sorted : sorted.slice(0, COLLAPSED_ROWS);
  const hiddenCount = sorted.length - visible.length;

  function toggleSort(index) {
    setSort((current) => {
      if (!current || current.index !== index) return { index, direction: "asc" };
      if (current.direction === "asc") return { index, direction: "desc" };
      return null;
    });
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(toTsv(columns, sorted));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard blocked; the CSV download is still available.
    }
  }

  function download() {
    const blob = new Blob([toCsv(columns, sorted)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "result.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="result">
      {label && <p className="query-label">{label}</p>}

      {view === "chart" && canChart ? (
        <BarChart
          labels={sorted.map((row) => row[0])}
          values={sorted.map((row) => Number(row[chartValueIndex]))}
          labelName={columns[0]}
          valueName={columns[chartValueIndex]}
        />
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                {columns.map((column, index) => {
                  const active = sort?.index === index;
                  return (
                    <th
                      key={column + index}
                      dir="auto"
                      className={numericColumns[index] ? "cell-number" : undefined}
                      aria-sort={
                        active ? (sort.direction === "asc" ? "ascending" : "descending") : "none"
                      }
                    >
                      <button
                        type="button"
                        className="sort-button"
                        onClick={() => toggleSort(index)}
                      >
                        {column}
                        <span className="sort-mark" aria-hidden="true">
                          {active && <Icon name={sort.direction === "asc" ? "up" : "down"} size={12} />}
                        </span>
                      </button>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {visible.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {row.map((cell, cellIndex) => (
                    <td
                      key={cellIndex}
                      dir="auto"
                      className={numericColumns[cellIndex] ? "cell-number" : undefined}
                    >
                      {cell == null ? "—" : String(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {hiddenCount > 0 && view === "table" && (
        <button type="button" className="text-button" onClick={() => setShowAll(true)}>
          Show all {sorted.length} rows
        </button>
      )}
      {showAll && sorted.length > COLLAPSED_ROWS && view === "table" && (
        <button type="button" className="text-button" onClick={() => setShowAll(false)}>
          Show fewer rows
        </button>
      )}
      {truncated && <p className="truncated-note">Results truncated.</p>}

      <div className="result-tools">
        {canChart && (
          <button
            type="button"
            className="tool-button"
            onClick={() => setView(view === "table" ? "chart" : "table")}
          >
            <Icon name={view === "table" ? "chart" : "table"} />
            {view === "table" ? "Chart" : "Table"}
          </button>
        )}
        <button type="button" className="tool-button" onClick={copy}>
          <Icon name={copied ? "check" : "copy"} />
          {copied ? "Copied" : "Copy"}
        </button>
        <button type="button" className="tool-button" onClick={download}>
          <Icon name="download" />
          CSV
        </button>
      </div>
    </div>
  );
}
