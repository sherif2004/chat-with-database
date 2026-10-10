import { useEffect, useRef, useState } from "react";
import {
  AuthError,
  connectDatabase,
  getConnectionStatus,
  getCurrentUser,
  getHistory,
  logOut,
  sendMessage,
} from "./api";
import AuthScreen from "./components/AuthScreen";
import Message from "./components/Message";
import Sidebar from "./components/Sidebar";

let nextId = 0;
const newId = () => ++nextId;

export default function App() {
  // undefined = checking the session, null = signed out.
  const [user, setUser] = useState(undefined);

  useEffect(() => {
    getCurrentUser()
      .then(setUser)
      .catch(() => setUser(null));
  }, []);

  if (user === undefined) {
    return <div className="auth-loading" role="status">Loading…</div>;
  }

  if (user === null) {
    return <AuthScreen onAuthenticated={setUser} />;
  }

  return <ChatApp user={user} onSignedOut={() => setUser(null)} />;
}

function ChatApp({ user, onSignedOut }) {
  const [timeline, setTimeline] = useState([]);
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const [connection, setConnection] = useState(null);
  const [connecting, setConnecting] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    getHistory()
      .then((entries) => {
        setTimeline(
          entries.map((entry) => ({
            id: newId(),
            type: "exchange",
            question: entry.question,
            response: entry.response,
            error: false,
          }))
        );
      })
      .catch((error) => {
        if (error instanceof AuthError) onSignedOut();
        // Otherwise: no history yet, or the store is unreachable — start empty.
      });

    getConnectionStatus()
      .then(setConnection)
      .catch((error) => {
        if (error instanceof AuthError) onSignedOut();
        // Otherwise the sidebar just shows "Loading..." until this succeeds.
      });
  }, []);

  useEffect(() => {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    bottomRef.current?.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth" });
  }, [timeline, sending]);

  async function handleSubmit(event) {
    event.preventDefault();

    const trimmed = question.trim();
    if (!trimmed || sending) return;

    setQuestion("");
    setSending(true);

    try {
      const response = await sendMessage(trimmed);
      setTimeline((prev) => [
        ...prev,
        { id: newId(), type: "exchange", question: trimmed, response, error: false },
      ]);
    } catch (error) {
      if (error instanceof AuthError) {
        onSignedOut();
        return;
      }
      setTimeline((prev) => [
        ...prev,
        {
          id: newId(),
          type: "exchange",
          question: trimmed,
          response: null,
          error: error.message || true,
        },
      ]);
    } finally {
      setSending(false);
    }
  }

  async function handleConnect(databaseUrl, label) {
    setConnecting(true);

    try {
      const info = await connectDatabase(databaseUrl, label);
      setConnection(info);
      setTimeline((prev) => [
        ...prev,
        { id: newId(), type: "notice", text: `Switched to ${info.label}` },
      ]);
    } finally {
      setConnecting(false);
    }
  }

  async function handleSignOut() {
    try {
      await logOut();
    } finally {
      onSignedOut();
    }
  }

  return (
    <div className="app-shell">
      <Sidebar
        user={user}
        onSignOut={handleSignOut}
        connection={connection}
        connecting={connecting}
        onConnect={handleConnect}
      />

      <div className="chat">
        <main className="chat-main">
        <header>
          <h1 className="chat-header">Chat With Database</h1>
        </header>

        <div
          className="chat-messages"
          role="log"
          aria-live="polite"
          aria-label="Conversation"
        >
          {timeline.length === 0 && !sending && (
            <div className="chat-empty">
              <div className="chat-empty-title">Ask me anything about your data</div>
              <div className="chat-empty-subtitle">
                Try a question like "how many users signed up last month?"
              </div>
            </div>
          )}
          {timeline.map((item) =>
            item.type === "notice" ? (
              <div key={item.id} className="chat-notice">
                {item.text}
              </div>
            ) : (
              <div key={item.id}>
                <Message role="user" question={item.question} />
                <Message role="assistant" response={item.response} error={item.error} />
              </div>
            )
          )}
          {sending && (
            <div className="message message-assistant">
              <div className="bubble bubble-pending">
                <span className="sr-only">Working on your answer…</span>
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
            aria-label="Your question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ask a question about the data..."
            readOnly={sending}
            aria-busy={sending}
          />
          <button type="submit" disabled={sending}>
            Send
          </button>
        </form>
        </main>
      </div>
    </div>
  );
}
