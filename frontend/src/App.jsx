import { useEffect, useRef, useState } from "react";
import { getHistory, sendMessage } from "./api";
import { getSessionId } from "./session";
import Message from "./components/Message";

export default function App() {
  const [sessionId] = useState(getSessionId);
  const [exchanges, setExchanges] = useState([]);
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    getHistory(sessionId)
      .then((entries) => {
        setExchanges(
          entries.map((entry) => ({
            question: entry.question,
            response: entry.response,
            error: false,
          }))
        );
      })
      .catch(() => {
        // No history yet, or the store is unreachable — start with an empty chat.
      });
  }, [sessionId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [exchanges, sending]);

  async function handleSubmit(event) {
    event.preventDefault();

    const trimmed = question.trim();
    if (!trimmed || sending) return;

    setQuestion("");
    setSending(true);

    try {
      const response = await sendMessage(sessionId, trimmed);
      setExchanges((prev) => [...prev, { question: trimmed, response, error: false }]);
    } catch {
      setExchanges((prev) => [...prev, { question: trimmed, response: null, error: true }]);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="chat">
      <header className="chat-header">Chat With Database</header>

      <div className="chat-messages">
        {exchanges.map((exchange, index) => (
          <div key={index}>
            <Message role="user" question={exchange.question} />
            <Message
              role="assistant"
              response={exchange.response}
              error={exchange.error}
            />
          </div>
        ))}
        {sending && (
          <div className="message message-assistant">
            <div className="bubble bubble-pending">Thinking…</div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form className="chat-input" onSubmit={handleSubmit}>
        <input
          type="text"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask a question about the data..."
          disabled={sending}
        />
        <button type="submit" disabled={sending}>
          Send
        </button>
      </form>
    </div>
  );
}
