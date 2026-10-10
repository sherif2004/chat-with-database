import { useEffect, useRef, useState } from "react";
import Icon from "./Icon";

const GROUPS = ["Today", "Yesterday", "Previous 7 days", "Earlier"];

function groupOf(isoDate) {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const time = new Date(isoDate).getTime();
  const day = 24 * 3600 * 1000;

  if (time >= startOfToday) return "Today";
  if (time >= startOfToday - day) return "Yesterday";
  if (time >= startOfToday - 7 * day) return "Previous 7 days";
  return "Earlier";
}

function Row({ conversation, active, locked, onSelect, onRename, onDelete }) {
  const [mode, setMode] = useState("idle"); // idle | renaming | confirming
  const [draft, setDraft] = useState(conversation.title);
  const inputRef = useRef(null);

  useEffect(() => {
    if (mode === "renaming") inputRef.current?.select();
  }, [mode]);

  function commitRename() {
    const title = draft.trim();
    if (title && title !== conversation.title) onRename(conversation.id, title);
    setMode("idle");
  }

  if (mode === "renaming") {
    return (
      <li className="rail-row rail-row-editing">
        <input
          ref={inputRef}
          className="rail-rename"
          value={draft}
          maxLength={120}
          aria-label="Conversation title"
          onChange={(event) => setDraft(event.target.value)}
          onBlur={commitRename}
          onKeyDown={(event) => {
            if (event.key === "Enter") commitRename();
            if (event.key === "Escape") {
              setDraft(conversation.title);
              setMode("idle");
            }
          }}
          autoFocus
        />
      </li>
    );
  }

  if (mode === "confirming") {
    return (
      <li className="rail-row rail-row-confirm">
        <span className="rail-confirm-text">Delete this chat?</span>
        <button
          type="button"
          className="text-button text-button-danger"
          onClick={() => onDelete(conversation.id)}
        >
          Delete
        </button>
        <button type="button" className="text-button" onClick={() => setMode("idle")}>
          Keep
        </button>
      </li>
    );
  }

  return (
    <li className={`rail-row ${active ? "rail-row-active" : ""}`}>
      <button
        type="button"
        className="rail-title"
        aria-current={active ? "true" : undefined}
        disabled={locked && !active}
        onClick={() => onSelect(conversation.id)}
        title={conversation.title}
      >
        {conversation.title}
      </button>
      <span className="rail-actions">
        <button
          type="button"
          className="icon-button"
          aria-label={`Rename ${conversation.title}`}
          onClick={() => {
            setDraft(conversation.title);
            setMode("renaming");
          }}
        >
          <Icon name="pencil" size={14} />
        </button>
        <button
          type="button"
          className="icon-button"
          aria-label={`Delete ${conversation.title}`}
          onClick={() => setMode("confirming")}
        >
          <Icon name="trash" size={14} />
        </button>
      </span>
    </li>
  );
}

export default function Rail({
  conversations,
  activeId,
  loading,
  locked,
  user,
  open,
  onClose,
  onNew,
  onSelect,
  onRename,
  onDelete,
  onSignOut,
}) {
  const grouped = GROUPS.map((name) => ({
    name,
    items: conversations.filter((conversation) => groupOf(conversation.updated_at) === name),
  })).filter((group) => group.items.length > 0);

  return (
    <>
      {open && <div className="scrim" onClick={onClose} aria-hidden="true" />}
      <aside className={`rail ${open ? "rail-open" : ""}`} aria-label="Conversations">
        <div className="rail-top">
          <button type="button" className="new-chat" onClick={onNew} disabled={locked}>
            <Icon name="plus" />
            New chat
          </button>
          <button
            type="button"
            className="icon-button rail-close"
            aria-label="Close conversations"
            onClick={onClose}
          >
            <Icon name="close" />
          </button>
        </div>

        <nav className="rail-list" aria-label="Past chats">
          {loading && conversations.length === 0 && (
            <p className="rail-empty">Loading chats…</p>
          )}
          {!loading && conversations.length === 0 && (
            <p className="rail-empty">Your chats will appear here.</p>
          )}
          {grouped.map((group) => (
            <section key={group.name}>
              <h2 className="rail-group">{group.name}</h2>
              <ul>
                {group.items.map((conversation) => (
                  <Row
                    key={conversation.id}
                    conversation={conversation}
                    active={conversation.id === activeId}
                    locked={locked}
                    onSelect={onSelect}
                    onRename={onRename}
                    onDelete={onDelete}
                  />
                ))}
              </ul>
            </section>
          ))}
        </nav>

        <div className="sidebar-account">
          <span className="sidebar-account-email" title={user.email}>
            {user.email}
          </span>
          <button type="button" className="sidebar-link-button" onClick={onSignOut}>
            Sign out
          </button>
        </div>
      </aside>
    </>
  );
}
