import { useCallback, useEffect, useRef, useState } from "react";
import {
  AuthError,
  connectDatabase,
  deleteConversation,
  getConnectionStatus,
  getConversations,
  getCurrentUser,
  getFollowups,
  getMessages,
  getStarters,
  logOut,
  renameConversation,
  streamChat,
} from "./api";
import AuthScreen from "./components/AuthScreen";
import Composer from "./components/Composer";
import DatabasePanel from "./components/DatabasePanel";
import Icon from "./components/Icon";
import Message from "./components/Message";
import Progress from "./components/Progress";
import Rail from "./components/Rail";

let nextId = 0;
const newId = () => ++nextId;

const prefersReducedMotion = () =>
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

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

function entriesToTimeline(entries) {
  return entries.map((entry) => ({
    id: newId(),
    type: "exchange",
    question: entry.question,
    response: entry.response,
    error: false,
  }));
}

function ChatApp({ user, onSignedOut }) {
  const [conversations, setConversations] = useState([]);
  const [conversationsLoading, setConversationsLoading] = useState(true);
  const [activeId, setActiveId] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [question, setQuestion] = useState("");
  const [editing, setEditing] = useState(false);
  const [sending, setSending] = useState(false);
  const [stage, setStage] = useState(null);
  const [connection, setConnection] = useState(null);
  const [connecting, setConnecting] = useState(false);
  const [starters, setStarters] = useState(null);
  const [followups, setFollowups] = useState([]);
  const [railOpen, setRailOpen] = useState(false);
  const [dbOpen, setDbOpen] = useState(false);

  const bottomRef = useRef(null);
  const composerRef = useRef(null);
  const dbButtonRef = useRef(null);
  const abortRef = useRef(null);
  const activeRef = useRef(null);

  const fail = useCallback(
    (error) => {
      if (error instanceof AuthError) onSignedOut();
    },
    [onSignedOut]
  );

  useEffect(() => {
    activeRef.current = activeId;
  }, [activeId]);

  const openConversation = useCallback(
    (id) => {
      setActiveId(id);
      activeRef.current = id;
      setTimeline([]);
      setFollowups([]);
      setEditing(false);
      setQuestion("");
      setRailOpen(false);
      setMessagesLoading(true);

      getMessages(id)
        .then((entries) => {
          if (activeRef.current === id) setTimeline(entriesToTimeline(entries));
        })
        .catch((error) => {
          fail(error);
          if (activeRef.current === id) {
            setTimeline([
              { id: newId(), type: "notice", text: "Couldn't load this chat. Try again." },
            ]);
          }
        })
        .finally(() => {
          if (activeRef.current === id) setMessagesLoading(false);
        });
    },
    [fail]
  );

  // First load: conversations, the connected database, and the latest chat.
  useEffect(() => {
    getConversations()
      .then((list) => {
        setConversations(list);
        if (list.length > 0) openConversation(list[0].id);
      })
      .catch(fail)
      .finally(() => setConversationsLoading(false));

    getConnectionStatus().then(setConnection).catch(fail);
  }, [fail, openConversation]);

  // Starter questions follow the connected schema.
  const connectionLabel = connection?.label;
  useEffect(() => {
    if (!connectionLabel) return;
    setStarters(null);
    getStarters()
      .then((result) => setStarters(result.suggestions))
      .catch((error) => {
        fail(error);
        setStarters([]);
      });
  }, [connectionLabel, fail]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({
      behavior: prefersReducedMotion() ? "auto" : "smooth",
    });
  }, [timeline, sending, stage, followups]);

  useEffect(() => {
    function onKeyDown(event) {
      if (event.key !== "Escape") return;
      setRailOpen(false);
      setDbOpen(false);
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  const lastExchange = [...timeline].reverse().find((item) => item.type === "exchange");

  async function send(text, { replaceLast = false } = {}) {
    const trimmed = text.trim();
    if (!trimmed || sending) return;

    const itemId = newId();
    const controller = new AbortController();
    abortRef.current = controller;

    setQuestion("");
    setEditing(false);
    setFollowups([]);
    setStage(null);
    setSending(true);
    setTimeline((prev) => {
      let base = prev;
      if (replaceLast) {
        const index = prev.map((item) => item.type).lastIndexOf("exchange");
        if (index >= 0) base = prev.filter((_, i) => i !== index);
      }
      return [
        ...base,
        { id: itemId, type: "exchange", question: trimmed, response: null, error: false, pending: true },
      ];
    });

    try {
      const response = await streamChat(trimmed, {
        conversationId: activeId,
        replaceLast,
        signal: controller.signal,
        onStage: setStage,
      });

      setTimeline((prev) =>
        prev.map((item) =>
          item.id === itemId ? { ...item, response, pending: false } : item
        )
      );

      const conversationId = response.conversation_id;
      setActiveId(conversationId);
      activeRef.current = conversationId;
      getConversations().then(setConversations).catch(fail);

      if (response.intent === "data_question" && response.result.type === "table") {
        getFollowups(conversationId)
          .then((result) => {
            if (activeRef.current === conversationId) setFollowups(result.suggestions);
          })
          .catch(() => {});
      }
    } catch (error) {
      if (error.name === "AbortError") {
        // Stopped by the user: take the question back so it can be reworded.
        setTimeline((prev) => prev.filter((item) => item.id !== itemId));
        setQuestion(trimmed);
        return;
      }
      if (error instanceof AuthError) {
        onSignedOut();
        return;
      }
      setTimeline((prev) =>
        prev.map((item) =>
          item.id === itemId
            ? { ...item, pending: false, error: error.message || true }
            : item
        )
      );
    } finally {
      abortRef.current = null;
      setSending(false);
      setStage(null);
    }
  }

  function startNewChat() {
    setActiveId(null);
    activeRef.current = null;
    setTimeline([]);
    setFollowups([]);
    setEditing(false);
    setQuestion("");
    setRailOpen(false);
    composerRef.current?.focus();
  }

  function startEditing() {
    if (!lastExchange) return;
    setQuestion(lastExchange.question);
    setEditing(true);
    composerRef.current?.focus();
  }

  async function handleRename(id, title) {
    setConversations((prev) =>
      prev.map((conversation) => (conversation.id === id ? { ...conversation, title } : conversation))
    );
    try {
      await renameConversation(id, title);
    } catch (error) {
      fail(error);
      getConversations().then(setConversations).catch(fail);
    }
  }

  async function handleDelete(id) {
    try {
      await deleteConversation(id);
      setConversations((prev) => prev.filter((conversation) => conversation.id !== id));
      if (id === activeRef.current) startNewChat();
    } catch (error) {
      fail(error);
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

  function closeDatabase() {
    setDbOpen(false);
    dbButtonRef.current?.focus();
  }

  const activeConversation = conversations.find((c) => c.id === activeId);
  const showEmpty = timeline.length === 0 && !sending && !messagesLoading;

  return (
    <div className="app-shell">
      <Rail
        conversations={conversations}
        activeId={activeId}
        loading={conversationsLoading}
        locked={sending}
        user={user}
        open={railOpen}
        onClose={() => setRailOpen(false)}
        onNew={startNewChat}
        onSelect={openConversation}
        onRename={handleRename}
        onDelete={handleDelete}
        onSignOut={handleSignOut}
      />

      <main className="chat">
        <header className="chat-bar">
          <button
            type="button"
            className="icon-button chat-menu"
            aria-label="Open conversations"
            onClick={() => setRailOpen(true)}
          >
            <Icon name="menu" size={20} />
          </button>
          <h1 className="chat-title">{activeConversation?.title || "New chat"}</h1>
          <button
            type="button"
            ref={dbButtonRef}
            className="db-button"
            onClick={() => setDbOpen(true)}
            aria-haspopup="dialog"
          >
            <span
              className={`connection-dot ${
                connection?.error ? "connection-dot-error" : "connection-dot-ok"
              }`}
              aria-hidden="true"
            />
            <Icon name="database" />
            <span className="db-button-label">{connection?.label ?? "Database"}</span>
          </button>
        </header>

        <div
          className="chat-messages"
          role="log"
          aria-live="polite"
          aria-label="Conversation"
        >
          {messagesLoading && (
            <div className="skeleton" aria-hidden="true">
              <span className="skeleton-bubble skeleton-right" />
              <span className="skeleton-bubble" />
              <span className="skeleton-bubble skeleton-right skeleton-short" />
            </div>
          )}

          {showEmpty && (
            <div className="chat-empty">
              <h2 className="chat-empty-title">Ask anything about your data</h2>
              <p className="chat-empty-subtitle">
                Ask in plain language. You'll get an answer first, and can open the details to see exactly how it was found.
              </p>
              <div className="starters" aria-label="Example questions">
                {starters === null && (
                  <>
                    <span className="starter starter-skeleton" />
                    <span className="starter starter-skeleton" />
                    <span className="starter starter-skeleton" />
                  </>
                )}
                {starters?.map((starter) => (
                  <button
                    key={starter}
                    type="button"
                    className="starter"
                    onClick={() => send(starter)}
                  >
                    {starter}
                  </button>
                ))}
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
                {item.pending ? (
                  <Progress step={stage} />
                ) : (
                  <Message
                    role="assistant"
                    response={item.response}
                    error={item.error}
                    isLast={item.id === lastExchange?.id && !sending && !item.error}
                    onRegenerate={() => send(item.question, { replaceLast: true })}
                    onEdit={startEditing}
                  />
                )}
              </div>
            )
          )}

          {followups.length > 0 && !sending && (
            <div className="followups" aria-label="Suggested follow-up questions">
              {followups.map((followup) => (
                <button
                  key={followup}
                  type="button"
                  className="starter"
                  onClick={() => send(followup)}
                >
                  {followup}
                </button>
              ))}
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <Composer
          value={question}
          onChange={setQuestion}
          onSend={() => send(question, { replaceLast: editing })}
          onStop={() => abortRef.current?.abort()}
          sending={sending}
          editing={editing}
          onCancelEdit={() => {
            setEditing(false);
            setQuestion("");
          }}
          inputRef={composerRef}
        />
      </main>

      {dbOpen && (
        <>
          <div className="scrim" onClick={closeDatabase} aria-hidden="true" />
          <div className="drawer" role="dialog" aria-modal="true" aria-label="Connected database">
            <button
              type="button"
              className="icon-button drawer-close"
              aria-label="Close database panel"
              onClick={closeDatabase}
              autoFocus
            >
              <Icon name="close" />
            </button>
            <DatabasePanel
              connection={connection}
              connecting={connecting}
              onConnect={handleConnect}
            />
          </div>
        </>
      )}
    </div>
  );
}
