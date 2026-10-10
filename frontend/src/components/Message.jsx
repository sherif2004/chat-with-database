import { memo, useId, useState } from "react";
import Icon from "./Icon";
import MessageDetails, { formatMs } from "./MessageDetails";
import ResultTable from "./ResultTable";
import { confirmChange } from "../api";

function answerText(response) {
  const result = response.result;
  if (result.type === "message" || result.type === "change") return result.message;
  return result.answer || "";
}

// An admin's previewed INSERT/UPDATE/DELETE. Nothing is saved until Confirm;
// a change loaded from history has no token and can only be asked for again.
function ChangePreview({ result }) {
  const [state, setState] = useState({ phase: result.token ? "idle" : "stale" });

  async function apply() {
    setState({ phase: "working" });
    try {
      const done = await confirmChange(result.token);
      setState({ phase: "done", message: done.message });
    } catch (error) {
      setState({ phase: "error", message: error.message });
    }
  }

  return (
    <>
      <p dir="auto">{result.message}</p>
      <pre className="change-sql"><code>{result.sql}</code></pre>

      {state.phase === "idle" && (
        <div className="change-actions">
          <button type="button" className="text-button text-button-danger" onClick={apply}>
            Confirm change
          </button>
          <button type="button" className="text-button" onClick={() => setState({ phase: "cancelled" })}>
            Cancel
          </button>
        </div>
      )}
      {state.phase === "working" && <p role="status">Applying…</p>}
      {state.phase === "done" && <p role="status"><strong>{state.message}</strong></p>}
      {state.phase === "cancelled" && <p role="status">Cancelled. Nothing was changed.</p>}
      {state.phase === "stale" && (
        <p role="status">This change isn't pending anymore. Ask again to redo it.</p>
      )}
      {state.phase === "error" && <p role="alert">{state.message}</p>}
    </>
  );
}

function Message({ role, question, response, error, fresh, isLast, onRegenerate, onEdit }) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const detailsId = useId();

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
        <div className="bubble bubble-error" role="alert">
          {typeof error === "string" ? error : "Something went wrong, try again."}
        </div>
      </div>
    );
  }

  const result = response.result;
  const totalMs = response.timings_ms?.total;
  const hasDetails = Boolean(response.timings_ms || response.debug);

  async function copyAnswer() {
    try {
      await navigator.clipboard.writeText(answerText(response));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard blocked; nothing to do.
    }
  }

  return (
    <div className={`message message-assistant${fresh ? " message-fresh" : ""}`}>
      <div className="message-assistant-column">
        <div className="bubble">
          {result.type === "table" ? (
            <>
              {result.answer && <p dir="auto">{result.answer}</p>}
              {result.queries.map((query, queryIndex) => (
                <ResultTable
                  key={queryIndex}
                  query={query}
                  label={
                    result.queries.length > 1
                      ? `Query ${queryIndex + 1} of ${result.queries.length}`
                      : null
                  }
                />
              ))}
            </>
          ) : result.type === "change" ? (
            <ChangePreview result={result} />
          ) : (
            <p dir="auto">{result.message}</p>
          )}
        </div>

        <div className="message-meta">
          <button type="button" className="text-button" onClick={copyAnswer}>
            <Icon name={copied ? "check" : "copy"} size={14} />
            {copied ? "Copied" : "Copy text"}
          </button>
          {isLast && (
            <>
              <button type="button" className="text-button" onClick={() => onRegenerate(question)}>
                <Icon name="refresh" size={14} />
                Regenerate
              </button>
              <button type="button" className="text-button" onClick={() => onEdit(question)}>
                <Icon name="pencil" size={14} />
                Edit question
              </button>
            </>
          )}
          {response.cache_hit && <span className="message-cache-badge">Cached</span>}
          {totalMs != null && <span className="message-latency">{formatMs(totalMs)}</span>}
          {hasDetails && (
            <button
              type="button"
              className="message-details-toggle"
              aria-expanded={detailsOpen}
              aria-controls={detailsId}
              onClick={() => setDetailsOpen((open) => !open)}
            >
              {detailsOpen ? "Hide details" : "Details"}
            </button>
          )}
        </div>

        <div id={detailsId}>
          {detailsOpen && <MessageDetails response={response} />}
        </div>
      </div>
    </div>
  );
}

export default memo(Message);
