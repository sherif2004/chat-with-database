import json
import logging
import secrets
import time

import redis

from app.config import settings
from app.services.auth_service import token_digest
from app.services.cache_service import client

logger = logging.getLogger(__name__)

_PREFIX = "pending_change"

# Fallback when Redis is down: (payload, expires_at) per token digest.
_memory: dict[str, tuple[dict, float]] = {}


def store(payload: dict) -> str:
    """Remember a previewed change and return the one-time token the admin
    must send back to confirm it."""

    token = secrets.token_urlsafe(32)
    key = f"{_PREFIX}:{token_digest(token)}"
    ttl = settings.pending_change_ttl_seconds

    try:
        client.set(key, json.dumps(payload), ex=ttl)
    except redis.RedisError as e:
        logger.warning("Pending change kept in memory: %s", e)
        _memory[key] = (payload, time.monotonic() + ttl)

    return token


def take(token: str) -> dict | None:
    """Return and delete the change; a token works once, then never again."""

    key = f"{_PREFIX}:{token_digest(token)}"

    try:
        raw = client.getdel(key)
        if raw is not None:
            return json.loads(raw)
    except redis.RedisError as e:
        logger.warning("Pending change lookup fell back to memory: %s", e)

    payload, expires = _memory.pop(key, (None, 0.0))
    return payload if payload is not None and expires > time.monotonic() else None
