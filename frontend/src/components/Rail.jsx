import { memo, useEffect, useRef, useState } from "react";
import Icon from "./Icon";
import AppearanceMenu from "./AppearanceMenu";

const ROLE_LABEL = { user: "User", supervisor: "Supervisor", admin: "Admin" };

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
  const titleRef = useRef(null);
  const leftEditing = useRef(false);

  useEffect(() => {
    if (mode === "renaming") inputRef.current?.select();
    if (mode === "idle" && leftEditing.current) {
      leftEditing.current = false;
      titleRef.current?.focus();
    }
  }, [mode]);

  function setModeAndRestore(next) {
    if (next === "idle" && mode !== "idle") leftEditing.current = true;
    setMode(next);
  }

  function commitRename() {
    const title = draft.trim();
    if (title && title !== conversation.title) onRename(conversation.id, title);
    setModeAndRestore("idle");
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
              setModeAndRestore("idle");
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
        <button
          type="button"
          className="text-button"
          onClick={() => setModeAndRestore("idle")}
          autoFocus
        >
          Keep
        </button>
      </li>
    );
  }

  return (
    <li className={`rail-row ${active ? "rail-row-active" : ""}`}>
      <button
        ref={titleRef}
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

function Rail({
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
  view,
  adminItems,
  onNavigate,
}) {
  const grouped = GROUPS.map((name) => ({
    name,
    items: conversations.filter((conversation) => groupOf(conversation.updated_at) === name),
  })).filter((group) => group.items.length > 0);

  const closeRef = useRef(null);

  // On narrow screens the rail is a drawer: move focus into it when it opens.
  useEffect(() => {
    if (open) closeRef.current?.focus();
  }, [open]);

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
            ref={closeRef}
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

        {adminItems.length > 0 && (
          <nav className="rail-nav" aria-label="Administration">
            {adminItems.map((item) => (
              <button
                key={item.id}
                type="button"
                className="rail-nav-item"
                aria-current={view === item.id ? "page" : undefined}
                onClick={() => onNavigate(item.id)}
              >
                <Icon name={item.icon} size={16} />
                {item.label}
              </button>
            ))}
          </nav>
        )}

        <div className="sidebar-account">
          <span className="avatar" aria-hidden="true">
            {user.email.charAt(0).toUpperCase()}
          </span>
          <div className="account-text">
            <span className="account-email" title={user.email}>
              {user.email.split("@")[0]}
              {user.email.includes("@") && (
                <>
                  @<wbr />
                  {user.email.split("@").slice(1).join("@")}
                </>
              )}
            </span>
            <span className="account-role">{ROLE_LABEL[user.role] ?? user.role}</span>
          </div>
          <AppearanceMenu />
          <button
            type="button"
            className="icon-button"
            aria-label="Sign out"
            title="Sign out"
            onClick={onSignOut}
          >
            <Icon name="logout" size={18} />
          </button>
        </div>
      </aside>
    </>
  );
}

export default memo(Rail);
