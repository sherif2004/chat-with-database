const API_BASE = "http://localhost:8000";

export async function getHistory(sessionId) {
  const response = await fetch(
    `${API_BASE}/chat/history?session_id=${encodeURIComponent(sessionId)}`
  );

  if (!response.ok) {
    throw new Error(`Failed to load history: ${response.status}`);
  }

  return response.json();
}

export async function sendMessage(sessionId, question) {
  const response = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, session_id: sessionId }),
  });

  if (!response.ok) {
    throw new Error(`Chat request failed: ${response.status}`);
  }

  return response.json();
}

export async function getConnectionStatus(sessionId) {
  const response = await fetch(
    `${API_BASE}/connections/current?session_id=${encodeURIComponent(sessionId)}`
  );

  if (!response.ok) {
    throw new Error(`Failed to load connection status: ${response.status}`);
  }

  return response.json();
}

export async function connectDatabase(sessionId, databaseUrl, label) {
  const response = await fetch(`${API_BASE}/connections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      database_url: databaseUrl,
      label: label || undefined,
    }),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || `Connection failed: ${response.status}`);
  }

  return response.json();
}

export async function getWorkflow(sessionId) {
  const response = await fetch(
    `${API_BASE}/settings/workflow?session_id=${encodeURIComponent(sessionId)}`
  );

  if (!response.ok) {
    throw new Error(`Failed to load workflow setting: ${response.status}`);
  }

  return response.json();
}

export async function setWorkflow(sessionId, workflow) {
  const response = await fetch(`${API_BASE}/settings/workflow`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, workflow }),
  });

  if (!response.ok) {
    throw new Error(`Failed to update workflow setting: ${response.status}`);
  }

  return response.json();
}
