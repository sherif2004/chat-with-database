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
        <div className="bubble bubble-error">Something went wrong, try again.</div>
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
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      {result.columns.map((column) => (
                        <th key={column} dir="auto">
                          {column}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.rows.map((row, rowIndex) => (
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
              {result.truncated && <p className="truncated-note">Results truncated.</p>}
            </>
          ) : (
            <p dir="auto">{result.type === "message" ? result.message : result.answer}</p>
          )}
        </div>

        {hasDetails && (
          <div className="message-meta">
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
