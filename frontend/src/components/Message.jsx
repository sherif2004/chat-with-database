import { memo, useId, useState } from "react";
import Icon from "./Icon";
import MessageDetails, { formatMs } from "./MessageDetails";
import ResultTable from "./ResultTable";

function answerText(response) {
  const result = response.result;
  if (result.type === "message") return result.message;
  return result.answer || "";
}

function Message({ role, question, response, error, isLast, onRegenerate, onEdit }) {
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
    <div className="message message-assistant">
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
          ) : (
            <p dir="auto">{result.message}</p>
          )}
        </div>

        <div className="message-meta">
          {response.cache_hit && <span className="message-cache-badge">Cached</span>}
          {totalMs != null && <span className="message-latency">{formatMs(totalMs)}</span>}
          <button type="button" className="text-button" onClick={copyAnswer}>
            {copied ? "Copied" : "Copy answer"}
          </button>
          {isLast && (
            <>
              <button type="button" className="text-button" onClick={onRegenerate}>
                <Icon name="refresh" size={14} />
                Regenerate
              </button>
              <button type="button" className="text-button" onClick={onEdit}>
                <Icon name="pencil" size={14} />
                Edit question
              </button>
            </>
          )}
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
