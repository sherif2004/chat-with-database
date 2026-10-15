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
import ConnectPage from "./components/ConnectPage";
import DatabasePanel from "./components/DatabasePanel";
import Icon from "./components/Icon";
import Message from "./components/Message";
import Progress, { stageKeyFor } from "./components/Progress";
import Rail from "./components/Rail";
import ActivityPage from "./components/ActivityPage";
import UsersPage from "./components/UsersPage";
import { can } from "./permissions";

// The product name shown in the browser tab; change it here and in index.html.
const APP_NAME = "Askbase";

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

  useEffect(() => {
    if (user !== undefined) return;
    document.title = APP_NAME;
  }, [user]);

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
  const [starters, setStarters] = useState(null);
  const [followups, setFollowups] = useState([]);
  const [railOpen, setRailOpen] = useState(false);
  const [dbOpen, setDbOpen] = useState(false);
  const [view, setView] = useState("chat"); // chat | users | activity | connect

  const bottomRef = useRef(null);
  const composerRef = useRef(null);
  const dbButtonRef = useRef(null);
  const menuButtonRef = useRef(null);
  const shellRef = useRef(null);
  const sendRef = useRef(null);
  const skipRailFocus = useRef(false);
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

  const closeRail = useCallback(() => setRailOpen(false), []);
  const closeDatabase = useCallback(() => setDbOpen(false), []);

  useEffect(() => {
    if (!railOpen && !dbOpen) return;

    function onKeyDown(event) {
      if (event.key !== "Escape") return;
      if (dbOpen) closeDatabase();
      else closeRail();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [railOpen, dbOpen, closeRail, closeDatabase]);

  // Give focus back to whatever opened a drawer once it closes. This waits
  // for the effect below to clear `inert`, which blocks focus while set.
  const wasRailOpen = useRef(false);
  const wasDbOpen = useRef(false);
  useEffect(() => {
    if (wasRailOpen.current && !railOpen && !skipRailFocus.current) {
      menuButtonRef.current?.focus();
    }
    skipRailFocus.current = false;
    if (wasDbOpen.current && !dbOpen) dbButtonRef.current?.focus();
    wasRailOpen.current = railOpen;
    wasDbOpen.current = dbOpen;
  }, [railOpen, dbOpen]);

  // While a drawer is open the rest of the page is inert, so Tab and
  // screen-reader navigation stay inside it.
  useEffect(() => {
    const shell = shellRef.current;
    if (!shell) return;

    const main = shell.querySelectorAll(".chat, .page");
    const rail = shell.querySelector(".rail");
    const narrow = window.matchMedia("(max-width: 900px)").matches;

    main.forEach((node) => {
      node.inert = dbOpen || (railOpen && narrow);
    });
    rail.inert = dbOpen;

    return () => {
      main.forEach((node) => {
        node.inert = false;
      });
      rail.inert = false;
    };
  }, [railOpen, dbOpen, view]);

  const adminItems = [
    can(user, "users:read") && { id: "users", label: "Users", icon: "users" },
    can(user, "activity:read") && { id: "activity", label: "Activity", icon: "activity" },
  ].filter(Boolean);

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
          item.id === itemId ? { ...item, response, pending: false, fresh: true } : item
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

  sendRef.current = send;

  const startNewChat = useCallback(() => {
    setActiveId(null);
    activeRef.current = null;
    setTimeline([]);
    setFollowups([]);
    setEditing(false);
    setQuestion("");
    skipRailFocus.current = true; // the composer takes focus instead
    setRailOpen(false);
    composerRef.current?.focus();
  }, []);

  const startEditing = useCallback((text) => {
    setQuestion(text);
    setEditing(true);
    composerRef.current?.focus();
  }, []);

  const regenerate = useCallback(
    (text) => sendRef.current(text, { replaceLast: true }),
    []
  );

  const handleRename = useCallback(async (id, title) => {
    setConversations((prev) =>
      prev.map((conversation) => (conversation.id === id ? { ...conversation, title } : conversation))
    );
    try {
      await renameConversation(id, title);
    } catch (error) {
      fail(error);
      getConversations().then(setConversations).catch(fail);
    }
  }, [fail]);

  const handleDelete = useCallback(
    async (id) => {
      try {
        await deleteConversation(id);
        setConversations((prev) => prev.filter((conversation) => conversation.id !== id));
        if (id === activeRef.current) startNewChat();
      } catch (error) {
        fail(error);
      }
    },
    [fail, startNewChat]
  );

  async function handleConnect(payload) {
    const info = await connectDatabase(payload);
    setConnection(info);
    setTimeline((prev) => [
      ...prev,
      { id: newId(), type: "notice", text: `Switched to ${info.label}` },
    ]);
    setView("chat");
  }

  const handleSignOut = useCallback(async () => {
    try {
      await logOut();
    } finally {
      onSignedOut();
    }
  }, [onSignedOut]);

  const activeConversation = conversations.find((c) => c.id === activeId);

  // The tab shows the open chat's title (and that it is working), then the name.
  const tabTitle = activeConversation?.title;
  useEffect(() => {
    const base = tabTitle ? `${tabTitle} · ${APP_NAME}` : APP_NAME;
    document.title = sending ? `Working… · ${base}` : base;
  }, [tabTitle, sending]);
  const showEmpty = timeline.length === 0 && !sending && !messagesLoading;

  return (
    <div className="app-shell" ref={shellRef}>
      <Rail
        conversations={conversations}
        activeId={view === "chat" ? activeId : null}
        loading={conversationsLoading}
        locked={sending}
        user={user}
        open={railOpen}
        onClose={closeRail}
        onNew={() => {
          setView("chat");
          startNewChat();
        }}
        onSelect={(id) => {
          setView("chat");
          openConversation(id);
        }}
        onRename={handleRename}
        onDelete={handleDelete}
        onSignOut={handleSignOut}
        view={view}
        adminItems={adminItems}
        onNavigate={(id) => {
          setView(id);
          setRailOpen(false);
        }}
      />

      <main
        className="chat"
        hidden={view !== "chat"}
        data-stage={sending ? stageKeyFor(stage) : undefined}
      >
        <header className="chat-bar">
          <button
            ref={menuButtonRef}
            type="button"
            className="icon-button chat-menu"
            aria-label="Open conversations"
            aria-expanded={railOpen}
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
            aria-expanded={dbOpen}
            aria-label={`Connected database: ${connection?.label ?? "loading"}`}
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
            <div className="skeleton">
              <span className="sr-only">Loading conversation…</span>
              <span className="skeleton-bubble skeleton-right" aria-hidden="true" />
              <span className="skeleton-bubble" aria-hidden="true" />
              <span className="skeleton-bubble skeleton-right skeleton-short" aria-hidden="true" />
            </div>
          )}

          {showEmpty && (
            <div className="chat-empty">
              <h2 className="chat-empty-title">Ask anything about your data</h2>
              <p className="chat-empty-subtitle">
                Ask in plain language. You'll get an answer first, and can open the details to see exactly how it was found.
              </p>
              <div className="starters" role="group" aria-label="Example questions">
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
                    question={item.question}
                    response={item.response}
                    error={item.error}
                    fresh={item.fresh}
                    isLast={item.id === lastExchange?.id && !sending && !item.error}
                    onRegenerate={regenerate}
                    onEdit={startEditing}
                  />
                )}
              </div>
            )
          )}

          {followups.length > 0 && !sending && (
            <div className="followups" role="group" aria-label="Suggested follow-up questions">
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

      {view !== "chat" && (
        <main className="page">
          {view === "users" && (
            <UsersPage
              me={user}
              onOpenRail={() => setRailOpen(true)}
              onUnauthorized={onSignedOut}
            />
          )}
          {view === "connect" && (
            <ConnectPage
              onOpenRail={() => setRailOpen(true)}
              onBack={() => setView("chat")}
              onConnect={handleConnect}
              onUnauthorized={onSignedOut}
            />
          )}
          {view === "activity" && (
            <ActivityPage
              me={user}
              onOpenRail={() => setRailOpen(true)}
              onUnauthorized={onSignedOut}
            />
          )}
        </main>
      )}

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
              onOpenConnect={() => {
                closeDatabase();
                setView("connect");
              }}
              canConnect={can(user, "connection:write")}
            />
          </div>
        </>
      )}
    </div>
  );
}
