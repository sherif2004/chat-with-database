const API_BASE = "http://localhost:8000";

async function request(path, options, action) {
  const response = await fetch(`${API_BASE}${path}`, options);

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || `${action}: ${response.status}`);
  }

  return response.json();
}

export function getHistory(sessionId) {
  return request(
    `/chat/history?session_id=${encodeURIComponent(sessionId)}`,
    undefined,
    "Failed to load history"
  );
}

export function sendMessage(sessionId, question) {
  return request(
    "/chat",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, session_id: sessionId }),
    },
    "Chat request failed"
  );
}

export function getConnectionStatus(sessionId) {
  return request(
    `/connections/current?session_id=${encodeURIComponent(sessionId)}`,
    undefined,
    "Failed to load connection status"
  );
}

export function connectDatabase(sessionId, databaseUrl, label) {
  return request(
    "/connections",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        database_url: databaseUrl,
        label: label || undefined,
      }),
    },
    "Connection failed"
  );
}
