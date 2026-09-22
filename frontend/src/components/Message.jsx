export default function Message({ role, question, response, error }) {
  if (role === "user") {
    return (
      <div className="message message-user">
        <div className="bubble">{question}</div>
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

  return (
    <div className="message message-assistant">
      <div className="bubble">
        {result.type === "table" ? (
          <>
            {result.answer && <p>{result.answer}</p>}
            <table>
              <thead>
                <tr>
                  {result.columns.map((column) => (
                    <th key={column}>{column}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.rows.map((row, rowIndex) => (
                  <tr key={rowIndex}>
                    {row.map((cell, cellIndex) => (
                      <td key={cellIndex}>{String(cell)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            {result.truncated && <p className="truncated-note">Results truncated.</p>}
          </>
        ) : (
          <p>{result.type === "message" ? result.message : result.answer}</p>
        )}
      </div>
    </div>
  );
}
