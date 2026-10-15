const API_BASE = "http://localhost:8000";

export class AuthError extends Error {}

async function request(path, options = {}, action) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    credentials: "include",
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const message = body?.detail || `${action}: ${response.status}`;
    // 401 on a data call means the session expired; auth calls report their
    // own 401 ("wrong password") as a plain error.
    if (response.status === 401 && !path.startsWith("/auth/")) {
      throw new AuthError(message);
    }
    throw new Error(message);
  }

  return response.status === 204 ? null : response.json();
}

function postJson(path, payload, action) {
  return request(
    path,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    action
  );
}

export function getCurrentUser() {
  return request("/auth/me", undefined, "Failed to load account");
}

export function signUp(email, password) {
  return postJson("/auth/signup", { email, password }, "Sign up failed");
}

export function logIn(email, password) {
  return postJson("/auth/login", { email, password }, "Log in failed");
}

export function logOut() {
  return request("/auth/logout", { method: "POST" }, "Log out failed");
}

export function getConversations() {
  return request("/conversations", undefined, "Failed to load conversations");
}

export function getMessages(conversationId) {
  return request(
    `/conversations/${conversationId}/messages`,
    undefined,
    "Failed to load conversation"
  );
}

export function renameConversation(conversationId, title) {
  return request(
    `/conversations/${conversationId}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    },
    "Rename failed"
  );
}

export function deleteConversation(conversationId) {
  return request(
    `/conversations/${conversationId}`,
    { method: "DELETE" },
    "Delete failed"
  );
}

export function getFollowups(conversationId) {
  return request(
    `/conversations/${conversationId}/followups`,
    undefined,
    "Failed to load suggestions"
  );
}

export function getStarters() {
  return request("/connections/starters", undefined, "Failed to load suggestions");
}

/**
 * Sends a question and reports pipeline stages as they start.
 * Resolves with the final chat response; rejects on failure, or with an
 * AbortError when `signal` is aborted.
 */
export async function streamChat(
  question,
  { conversationId, replaceLast = false, signal, onStage }
) {
  const response = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      conversation_id: conversationId ?? undefined,
      replace_last: replaceLast,
    }),
    signal,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const message = body?.detail || `Chat request failed: ${response.status}`;
    throw response.status === 401 ? new AuthError(message) : new Error(message);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop();

    for (const raw of events) {
      const name = /^event: (.+)$/m.exec(raw)?.[1];
      const data = /^data: (.+)$/m.exec(raw)?.[1];
      if (!name || !data) continue;

      const payload = JSON.parse(data);
      if (name === "stage") onStage?.(payload.step);
      else if (name === "done") result = payload;
      else if (name === "error") throw new Error(payload.detail);
    }
  }

  if (!result) throw new Error("The connection closed before an answer arrived.");
  return result;
}

export function getConnectionStatus() {
  return request("/connections/current", undefined, "Failed to load connection status");
}

export function getEngines() {
  return request("/connections/engines", undefined, "Failed to load database types");
}

/** `payload` is either { database_url } or { engine, host, port, database, username, password }. */
export function testConnection(payload) {
  return postJson("/connections/test", payload, "Connection test failed");
}

export function connectDatabase(payload) {
  return postJson("/connections", payload, "Connection failed");
}

export function getUsers() {
  return request("/admin/users", undefined, "Failed to load users");
}

export function setUserRole(userId, role) {
  return request(
    `/admin/users/${userId}/role`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role }),
    },
    "Couldn't change the role"
  );
}

export function deleteUser(userId) {
  return request(`/admin/users/${userId}`, { method: "DELETE" }, "Couldn't delete the user");
}

export function getUserConversations(userId) {
  return request(
    `/admin/users/${userId}/conversations`,
    undefined,
    "Failed to load their chats"
  );
}

export function getUserMessages(userId, conversationId) {
  return request(
    `/admin/users/${userId}/conversations/${conversationId}/messages`,
    undefined,
    "Failed to load the chat"
  );
}

export function confirmChange(token) {
  return postJson("/chat/confirm-change", { token }, "Couldn't apply the change");
}

export function getActivity({ events = [], q = "", before } = {}) {
  const params = new URLSearchParams();
  events.forEach((event) => params.append("event", event));
  if (q) params.set("q", q);
  if (before) params.set("before", String(before));
  const query = params.toString();
  return request(`/admin/activity${query ? `?${query}` : ""}`, undefined, "Failed to load activity");
}

export function getActivitySummary() {
  return request("/admin/activity/summary", undefined, "Failed to load the summary");
}
