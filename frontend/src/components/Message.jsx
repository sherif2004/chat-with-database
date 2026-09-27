import { useState } from "react";
import MessageDetails, { formatMs } from "./MessageDetails";

export default function Message({ role, question, response, error }) {
  const [detailsOpen, setDetailsOpen] = useState(false);

  if (role === "user") {
    return (
      <div className="message message-user">
        <div className="bubble" dir="auto">
          {question}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="message message-assistant">
        <div className="bubble bubble-error">
          {typeof error === "string" ? error : "Something went wrong, try again."}
        </div>
      </div>
    );
  }

  const result = response.result;
  const totalMs = response.timings_ms?.total;
  const hasDetails = Boolean(response.timings_ms || response.debug);

  return (
    <div className="message message-assistant">
      <div className="message-assistant-column">
        <div className="bubble">
          {result.type === "table" ? (
            <>
              {result.answer && (
                <p dir="auto">{result.answer}</p>
              )}
              {result.queries.map((query, queryIndex) => (
                <div key={queryIndex}>
                  {result.queries.length > 1 && (
                    <p className="query-label">Query {queryIndex + 1} of {result.queries.length}</p>
                  )}
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          {query.columns.map((column) => (
                            <th key={column} dir="auto">
                              {column}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {query.rows.map((row, rowIndex) => (
                          <tr key={rowIndex}>
                            {row.map((cell, cellIndex) => (
                              <td key={cellIndex} dir="auto">
                                {String(cell)}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {query.truncated && <p className="truncated-note">Results truncated.</p>}
                </div>
              ))}
            </>
          ) : (
            <p dir="auto">{result.type === "message" ? result.message : result.answer}</p>
          )}
        </div>

        {hasDetails && (
          <div className="message-meta">
            {response.cache_hit && <span className="message-cache-badge">Cached</span>}
            {totalMs != null && <span className="message-latency">{formatMs(totalMs)}</span>}
            <button
              type="button"
              className="message-details-toggle"
              onClick={() => setDetailsOpen((open) => !open)}
            >
              {detailsOpen ? "Hide details" : "Details"}
            </button>
          </div>
        )}

        {detailsOpen && <MessageDetails response={response} />}
      </div>
    </div>
  );
}
