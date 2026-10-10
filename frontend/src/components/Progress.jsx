// Pipeline steps grouped into the four moments an analyst cares about.
const STAGES = [
  {
    key: "understand",
    label: "Reading your question",
    steps: ["input_guard", "cache_lookup", "resolve_connection", "load_history", "router"],
  },
  {
    key: "write",
    label: "Writing the query",
    steps: ["retrieve_examples", "generate_sql", "sql_guard"],
  },
  { key: "run", label: "Running it on your data", steps: ["execute_sql"] },
  { key: "answer", label: "Writing the answer", steps: ["generate_answer"] },
];

function stageIndex(step) {
  return STAGES.findIndex((stage) => stage.steps.includes(step));
}

export default function Progress({ step }) {
  const current = Math.max(stageIndex(step), 0);
  // Only stages already reached are shown, so we never promise a step
  // (like running a query) that a greeting or refusal will skip.
  const shown = STAGES.slice(0, current + 1);

  return (
    <div className="message message-assistant" role="status">
      <div className="bubble bubble-pending">
        <ol className="progress">
          {shown.map((stage, index) => (
            <li
              key={stage.key}
              className={index < current ? "progress-done" : "progress-active"}
            >
              <span className="progress-mark" aria-hidden="true" />
              {stage.label}
              {index === current ? "…" : ""}
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}
