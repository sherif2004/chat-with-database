import { useEffect, useState } from "react";
import {
  AuthError,
  deleteUser,
  getUserConversations,
  getUserMessages,
  getUsers,
  setUserRole,
} from "../api";

const ROLES = ["user", "supervisor", "admin"];

export function can(user, permission) {
  return Boolean(user?.permissions?.includes(permission));
}

function ChatViewer({ account, onBack }) {
  const [conversations, setConversations] = useState(null);
  const [entries, setEntries] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getUserConversations(account.id).then(setConversations).catch((e) => setError(e.message));
  }, [account.id]);

  function open(conversationId) {
    setEntries(null);
    setError(null);
    getUserMessages(account.id, conversationId)
      .then(setEntries)
      .catch((e) => setError(e.message));
  }

  return (
    <div className="users-viewer">
      <button type="button" className="text-button" onClick={onBack}>
        ← Back to users
      </button>
      <h3 className="users-title">{account.email} · read-only</h3>
      {error && <div className="connect-error" role="alert">{error}</div>}
      {conversations && conversations.length === 0 && <p className="rail-empty">No chats yet.</p>}
      <ul className="users-chats">
        {conversations?.map((conversation) => (
          <li key={conversation.id}>
            <button type="button" className="sidebar-link-button" onClick={() => open(conversation.id)}>
              {conversation.title}
            </button>
          </li>
        ))}
      </ul>
      {entries?.map((entry, index) => (
        <div key={index} className="users-entry">
          <p><strong>{entry.question}</strong></p>
          <p>{entry.response?.result?.answer || entry.response?.result?.message}</p>
        </div>
      ))}
    </div>
  );
}

export default function UsersPanel({ me, onUnauthorized }) {
  const canWrite = can(me, "users:write");
  const [accounts, setAccounts] = useState(null);
  const [error, setError] = useState(null);
  const [viewing, setViewing] = useState(null);

  function handleError(e) {
    if (e instanceof AuthError) onUnauthorized();
    setError(e.message);
  }

  useEffect(() => {
    getUsers().then(setAccounts).catch(handleError);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function changeRole(account, role) {
    setError(null);
    try {
      const updated = await setUserRole(account.id, role);
      setAccounts((list) => list.map((a) => (a.id === updated.id ? updated : a)));
    } catch (e) {
      handleError(e);
    }
  }

  async function remove(account) {
    if (!window.confirm(`Delete ${account.email} and all of their chats?`)) return;
    setError(null);
    try {
      await deleteUser(account.id);
      setAccounts((list) => list.filter((a) => a.id !== account.id));
    } catch (e) {
      handleError(e);
    }
  }

  if (viewing) return <ChatViewer account={viewing} onBack={() => setViewing(null)} />;

  return (
    <div className="users-panel">
      <h3 className="users-title">Users</h3>
      {error && <div className="connect-error" role="alert">{error}</div>}
      {!accounts && !error && <p className="rail-empty">Loading…</p>}
      <ul className="users-list">
        {accounts?.map((account) => (
          <li key={account.id} className="users-row">
            <span className="users-email" title={account.email}>{account.email}</span>
            {canWrite && account.id !== me.id ? (
              <select
                aria-label={`Role for ${account.email}`}
                value={account.role}
                onChange={(event) => changeRole(account, event.target.value)}
              >
                {ROLES.map((role) => <option key={role} value={role}>{role}</option>)}
              </select>
            ) : (
              <span className="users-role">{account.role}</span>
            )}
            <button type="button" className="text-button" onClick={() => setViewing(account)}>
              View chats
            </button>
            {canWrite && account.id !== me.id && (
              <button type="button" className="text-button text-button-danger" onClick={() => remove(account)}>
                Delete
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
