const STEP_LABELS = {
  input_guard: "Input guard",
  resolve_connection: "Resolve connection",
  router: "Router",
  retrieve_examples: "Retrieve examples",
  generate_sql: "Generate SQL",
  route_and_generate_sql: "Route + generate SQL",
  sql_guard: "SQL guard",
  execute_sql: "Execute SQL",
  generate_answer: "Generate answer",
};

const WORKFLOW_LABELS = {
  router: "With router",
  no_router: "No router (merged call)",
};

export function formatMs(ms) {
  if (ms == null) return null;
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${Math.round(ms)}ms`;
}

function formatTokens(usage) {
  if (!usage) return null;
  return `${usage.input_tokens} in / ${usage.output_tokens} out`;
}

export default function MessageDetails({ response }) {
  const { intent, sql, timings_ms: timings, debug } = response;

  const timingEntries = Object.entries(timings || {}).filter(
    ([step, ms]) => step !== "total" && ms != null
  );
  const totalMs = timings?.total;
  const tokenUsage = debug?.token_usage || {};
  const totalUsage = Object.values(tokenUsage).reduce(
    (sum, usage) => ({
      input_tokens: sum.input_tokens + (usage?.input_tokens || 0),
      output_tokens: sum.output_tokens + (usage?.output_tokens || 0),
    }),
    { input_tokens: 0, output_tokens: 0 }
  );
  const hasTotalUsage = totalUsage.input_tokens > 0 || totalUsage.output_tokens > 0;

  return (
    <div className="details-panel">
      {(timingEntries.length > 0 || totalMs != null) && (
        <div className="details-section">
          <div className="details-heading">Timings</div>
          <ul className="details-timings">
            {timingEntries.map(([step, ms]) => {
              const usage = tokenUsage[step];
              return (
                <li key={step}>
                  <span>{STEP_LABELS[step] || step}</span>
                  <span>
                    {formatMs(ms)}
                    {usage && (
                      <span className="details-tokens"> · {formatTokens(usage)}</span>
                    )}
                  </span>
                </li>
              );
            })}
            {totalMs != null && (
              <li className="details-timings-total">
                <span>Total</span>
                <span>
                  {formatMs(totalMs)}
                  {hasTotalUsage && (
                    <span className="details-tokens"> · {formatTokens(totalUsage)}</span>
                  )}
                </span>
              </li>
            )}
          </ul>
        </div>
      )}

      <div className="details-section">
        <div className="details-heading">Routing</div>
        <div className="details-row">
          Intent: <code>{intent}</code>
        </div>
        {debug?.model && (
          <div className="details-row">
            Model: <code>{debug.model}</code>
          </div>
        )}
        {debug?.workflow && (
          <div className="details-row">
            Workflow: <code>{WORKFLOW_LABELS[debug.workflow] || debug.workflow}</code>
          </div>
        )}
      </div>

      {sql && (
        <div className="details-section">
          <div className="details-heading">SQL</div>
          <pre className="details-code">{sql}</pre>
        </div>
      )}

      {debug?.examples?.length > 0 && (
        <div className="details-section">
          <div className="details-heading">Few-shot examples used</div>
          {debug.examples.map((example, index) => (
            <div key={index} className="details-example">
              <div className="details-example-score">score {example.score.toFixed(2)}</div>
              <div>{example.question}</div>
              <pre className="details-code">{example.sql}</pre>
            </div>
          ))}
        </div>
      )}

      {debug?.prompts && Object.keys(debug.prompts).length > 0 && (
        <div className="details-section">
          <div className="details-heading">Prompts</div>
          {Object.entries(debug.prompts).map(([name, prompt]) => (
            <details key={name} className="details-prompt">
              <summary>{STEP_LABELS[name] || name}</summary>
              <pre className="details-code">{prompt}</pre>
            </details>
          ))}
        </div>
      )}
    </div>
  );
}
