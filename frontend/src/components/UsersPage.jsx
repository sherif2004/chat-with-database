import { useEffect, useState } from "react";
import {
  AuthError,
  deleteUser,
  getUserConversations,
  getUserMessages,
  getUsers,
  setUserRole,
} from "../api";
import { can } from "../permissions";
import Icon from "./Icon";
import Message from "./Message";
import PageHeader from "./PageHeader";

const ROLES = ["user", "supervisor", "admin"];
const ROLE_LABEL = { user: "User", supervisor: "Supervisor", admin: "Admin" };

const shortDate = (iso) =>
  new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });

/** Another user's chats, read-only. Opening one is recorded in the activity
 *  log, and the page says so rather than leaving it to be discovered. */
function ChatViewer({ account, onBack, onOpenRail, onFail }) {
  const [conversations, setConversations] = useState(null);
  const [activeId, setActiveId] = useState(null);
  const [entries, setEntries] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getUserConversations(account.id)
      .then(setConversations)
      .catch((e) => {
        onFail(e);
        setError(e.message);
      });
  }, [account.id, onFail]);

  function open(id) {
    setActiveId(id);
    setEntries(null);
    setError(null);
    getUserMessages(account.id, id)
      .then(setEntries)
      .catch((e) => {
        onFail(e);
        setError(e.message);
      });
  }

  return (
    <>
      <PageHeader title={account.email} onOpenRail={onOpenRail}>
        <button type="button" className="tool-button" onClick={onBack}>
          <Icon name="back" size={14} />
          All users
        </button>
      </PageHeader>

      <div className="page-body viewer">
        <p className="notice-line">
          <Icon name="eye" size={15} />
          Read-only. Opening someone's chats is recorded in the activity log.
        </p>

        {error && <div className="inline-error" role="alert">{error}</div>}

        <div className="viewer-grid">
          <nav className="viewer-list" aria-label={`Conversations of ${account.email}`}>
            {conversations === null && !error && <p className="empty-text">Loading…</p>}
            {conversations?.length === 0 && <p className="empty-text">No chats yet.</p>}
            <ul>
              {conversations?.map((conversation) => (
                <li key={conversation.id}>
                  <button
                    type="button"
                    className="viewer-item"
                    aria-current={conversation.id === activeId ? "true" : undefined}
                    onClick={() => open(conversation.id)}
                  >
                    <span className="viewer-item-title">{conversation.title}</span>
                    <span className="viewer-item-date">{shortDate(conversation.updated_at)}</span>
                  </button>
                </li>
              ))}
            </ul>
          </nav>

          <div className="viewer-thread" aria-live="polite">
            {activeId === null && conversations?.length > 0 && (
              <p className="empty-text">Choose a conversation to read it.</p>
            )}
            {activeId !== null && entries === null && !error && <p className="empty-text">Loading…</p>}
            {entries?.map((entry, index) => (
              <div key={index}>
                <Message role="user" question={entry.question} />
                <Message role="assistant" question={entry.question} response={entry.response} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}

export default function UsersPage({ me, onOpenRail, onUnauthorized }) {
  const canWrite = can(me, "users:write");
  const [accounts, setAccounts] = useState(null);
  const [error, setError] = useState(null);
  const [status, setStatus] = useState("");
  const [viewing, setViewing] = useState(null);
  const [confirming, setConfirming] = useState(null);

  function fail(e) {
    if (e instanceof AuthError) onUnauthorized();
  }

  function report(e) {
    fail(e);
    setError(e.message);
  }

  useEffect(() => {
    getUsers().then(setAccounts).catch(report);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function changeRole(account, role) {
    setError(null);
    try {
      const updated = await setUserRole(account.id, role);
      setAccounts((list) => list.map((a) => (a.id === updated.id ? updated : a)));
      setStatus(`${account.email} is now ${ROLE_LABEL[role].toLowerCase()}. They will be signed out.`);
    } catch (e) {
      report(e);
    }
  }

  async function remove(account) {
    setError(null);
    setConfirming(null);
    try {
      await deleteUser(account.id);
      setAccounts((list) => list.filter((a) => a.id !== account.id));
      setStatus(`Deleted ${account.email} and their chats.`);
    } catch (e) {
      report(e);
    }
  }

  if (viewing) {
    return (
      <ChatViewer
        account={viewing}
        onBack={() => setViewing(null)}
        onOpenRail={onOpenRail}
        onFail={fail}
      />
    );
  }

  return (
    <>
      <PageHeader title="Users" onOpenRail={onOpenRail} />

      <div className="page-body">
        <p className="page-lede">
          {accounts ? `${accounts.length} account${accounts.length === 1 ? "" : "s"}.` : "Loading accounts…"}{" "}
          {canWrite
            ? "Changing a role signs that person out so it applies on their next sign-in."
            : "You can read accounts and chats; only admins can change them."}
        </p>

        {error && <div className="inline-error" role="alert">{error}</div>}
        <p className="sr-only" role="status">{status}</p>
        {status && <p className="status-line" aria-hidden="true">{status}</p>}

        <div className="table-wrap">
          <table className="data-table users-table">
            <caption className="sr-only">Accounts</caption>
            <thead>
              <tr>
                <th scope="col">Account</th>
                <th scope="col">Role</th>
                <th scope="col">Joined</th>
                <th scope="col"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {accounts === null && !error &&
                [0, 1, 2].map((i) => (
                  <tr key={i} className="row-skeleton" aria-hidden="true">
                    <td colSpan={4}><span /></td>
                  </tr>
                ))}
              {accounts?.map((account) => {
                const isMe = account.id === me.id;
                return (
                  <tr key={account.id}>
                    <td className="cell-who" title={account.email}>
                      {account.email}
                      {isMe && <span className="you">You</span>}
                    </td>
                    <td>
                      {canWrite && !isMe ? (
                        <select
                          className="role-select"
                          aria-label={`Role for ${account.email}`}
                          value={account.role}
                          onChange={(event) => changeRole(account, event.target.value)}
                        >
                          {ROLES.map((role) => (
                            <option key={role} value={role}>{ROLE_LABEL[role]}</option>
                          ))}
                        </select>
                      ) : (
                        <span className="role-chip">{ROLE_LABEL[account.role]}</span>
                      )}
                    </td>
                    <td className="cell-when cell-joined">{account.created_at ? shortDate(account.created_at) : "-"}</td>
                    <td className={`cell-actions${confirming === account.id ? " confirming" : ""}`}>
                      <div className="actions">
                      {confirming === account.id ? (
                        <span className="confirm-inline">
                          Delete {account.email} and all their chats?
                          <button type="button" className="text-button text-button-danger" onClick={() => remove(account)}>
                            Delete
                          </button>
                          <button type="button" className="text-button" onClick={() => setConfirming(null)}>
                            Keep
                          </button>
                        </span>
                      ) : (
                        <>
                          <button type="button" className="text-button" onClick={() => setViewing(account)}>
                            <Icon name="eye" size={14} />
                            View chats
                          </button>
                          {canWrite && !isMe && (
                            <button
                              type="button"
                              className="text-button text-button-danger"
                              onClick={() => setConfirming(account.id)}
                            >
                              <Icon name="trash" size={14} />
                              Delete
                            </button>
                          )}
                        </>
                      )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
