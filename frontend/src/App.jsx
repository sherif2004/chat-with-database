import { useEffect, useRef, useState } from "react";
import {
  connectDatabase,
  getConnectionStatus,
  getHistory,
  getWorkflow,
  sendMessage,
  setWorkflow as setWorkflowSetting,
} from "./api";
import { getSessionId } from "./session";
import Message from "./components/Message";
import Sidebar from "./components/Sidebar";

export default function App() {
  const [sessionId] = useState(getSessionId);
  const [timeline, setTimeline] = useState([]);
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const [connection, setConnection] = useState(null);
  const [connecting, setConnecting] = useState(false);
  const [workflow, setWorkflow] = useState("router");
  const bottomRef = useRef(null);

  useEffect(() => {
    getHistory(sessionId)
      .then((entries) => {
        setTimeline(
          entries.map((entry) => ({
            type: "exchange",
            question: entry.question,
            response: entry.response,
            error: false,
          }))
        );
      })
      .catch(() => {
        // No history yet, or the store is unreachable — start with an empty chat.
      });

    getConnectionStatus(sessionId)
      .then(setConnection)
      .catch(() => {
        // Sidebar just shows "Loading..." until this succeeds on retry.
      });

    getWorkflow(sessionId)
      .then((info) => setWorkflow(info.workflow))
      .catch(() => {
        // Falls back to the "router" default already in state.
      });
  }, [sessionId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [timeline, sending]);

  async function handleSubmit(event) {
    event.preventDefault();

    const trimmed = question.trim();
    if (!trimmed || sending) return;

    setQuestion("");
    setSending(true);

    try {
      const response = await sendMessage(sessionId, trimmed);
      setTimeline((prev) => [
        ...prev,
        { type: "exchange", question: trimmed, response, error: false },
      ]);
    } catch {
      setTimeline((prev) => [
        ...prev,
        { type: "exchange", question: trimmed, response: null, error: true },
      ]);
    } finally {
      setSending(false);
    }
  }

  async function handleConnect(databaseUrl, label) {
    setConnecting(true);

    try {
      const info = await connectDatabase(sessionId, databaseUrl, label);
      setConnection(info);
      setTimeline((prev) => [
        ...prev,
        { type: "notice", text: `Switched to ${info.label}` },
      ]);
    } finally {
      setConnecting(false);
    }
  }

  async function handleWorkflowChange(next) {
    const previous = workflow;
    setWorkflow(next);

    try {
      await setWorkflowSetting(sessionId, next);
    } catch {
      // The backend resolves workflow per session from stored state, not
      // from the chat request itself — if the update didn't take, revert
      // so the UI doesn't show a choice that isn't actually active.
      setWorkflow(previous);
    }
  }

  return (
    <div className="app-shell">
      <Sidebar
        connection={connection}
        connecting={connecting}
        onConnect={handleConnect}
        workflow={workflow}
        onWorkflowChange={handleWorkflowChange}
      />

      <div className="chat">
        <header className="chat-header">Chat With Database</header>

        <div className="chat-messages">
          {timeline.length === 0 && !sending && (
            <div className="chat-empty">
              <div className="chat-empty-title">Ask me anything about your data</div>
              <div className="chat-empty-subtitle">
                Try a question like "how many users signed up last month?"
              </div>
            </div>
          )}
          {timeline.map((item, index) =>
            item.type === "notice" ? (
              <div key={index} className="chat-notice">
                {item.text}
              </div>
            ) : (
              <div key={index}>
                <Message role="user" question={item.question} />
                <Message role="assistant" response={item.response} error={item.error} />
              </div>
            )
          )}
          {sending && (
            <div className="message message-assistant">
              <div className="bubble bubble-pending">
                <span className="typing-dot" />
                <span className="typing-dot" />
                <span className="typing-dot" />
              </div>
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
    </div>
  );
}
