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

export function getHistory() {
  return request("/chat/history", undefined, "Failed to load history");
}

export function sendMessage(question) {
  return postJson("/chat", { question }, "Chat request failed");
}

export function getConnectionStatus() {
  return request("/connections/current", undefined, "Failed to load connection status");
}

export function connectDatabase(databaseUrl, label) {
  return postJson(
    "/connections",
    { database_url: databaseUrl, label: label || undefined },
    "Connection failed"
  );
}
