import json
import logging

import redis

from app.config import settings
from app.utils import normalize_text

logger = logging.getLogger(__name__)

client = redis.Redis.from_url(settings.redis_url, decode_responses=True)

_KEY_PREFIX = "chat_cache"


def _key(session_id: str, question: str) -> str | None:
    """None when the question normalizes to nothing (matches the exact-match
    semantics the old DB cache had: an empty key is never cached)."""

    question_key = normalize_text(question)
    return f"{_KEY_PREFIX}:{session_id}:{question_key}" if question_key else None


def get_cached_response(session_id: str, question: str) -> dict | None:
    """Exact-match cache lookup, or None on a miss or a Redis hiccup — a
    cache failure must never break the chat, only skip the shortcut."""

    key = _key(session_id, question)
    if key is None:
        return None

    try:
        raw = client.get(key)
    except redis.RedisError as e:
        logger.warning("Cache lookup skipped: %s", e)
        return None

    return json.loads(raw) if raw is not None else None


def set_cached_response(session_id: str, question: str, response: dict) -> None:
    """Best-effort write, run as a background task after the response is
    already sent — never lets a storage problem affect the request."""

    key = _key(session_id, question)
    if key is None:
        return

    try:
        client.set(key, json.dumps(response), ex=settings.cache_ttl_seconds)
    except redis.RedisError as e:
        logger.warning("Could not cache response: %s", e)
