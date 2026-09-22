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
