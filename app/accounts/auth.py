import base64
import hashlib
import hmac
import re
import secrets
import time

import redis

from app.shared.cache import client

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


def normalize_email(email: str) -> str:
    return email.strip().lower()


def is_valid_email(email: str) -> bool:
    return len(email) <= 254 and bool(_EMAIL_RE.match(email))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32
    )
    return "scrypt${}${}${}${}${}".format(
        _SCRYPT_N, _SCRYPT_R, _SCRYPT_P,
        base64.b64encode(salt).decode(), base64.b64encode(digest).decode(),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt_b64, digest_b64 = stored.split("$")
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.scrypt(
            password.encode(), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
    except (ValueError, TypeError):
        return False

    return hmac.compare_digest(actual, expected)


# Burned on unknown emails so a login attempt takes the same time whether or
# not the account exists.
DUMMY_HASH = hash_password("not-a-real-password")


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AttemptLimiter:
    """Counts attempts per key inside a fixed window. Backed by Redis so the
    counts survive restarts and are shared across workers; if Redis is down
    it falls back to per-process memory rather than failing open or closed."""

    def __init__(self):
        self._memory: dict[str, tuple[int, float]] = {}

    def _memory_count(self, key: str) -> int:
        count, expires = self._memory.get(key, (0, 0.0))
        if expires < time.monotonic():
            self._memory.pop(key, None)
            return 0
        return count

    def count(self, key: str) -> int:
        try:
            return int(client.get(f"auth_limit:{key}") or 0)
        except redis.RedisError:
            return self._memory_count(key)

    def record(self, key: str, window: int) -> None:
        try:
            redis_key = f"auth_limit:{key}"
            pipe = client.pipeline()
            pipe.incr(redis_key)
            pipe.expire(redis_key, window, nx=True)
            pipe.execute()
        except redis.RedisError:
            count = self._memory_count(key)
            _, expires = self._memory.get(key, (0, time.monotonic() + window))
            self._memory[key] = (count + 1, expires)

    def clear(self, key: str) -> None:
        self._memory.pop(key, None)
        try:
            client.delete(f"auth_limit:{key}")
        except redis.RedisError:
            pass


limiter = AttemptLimiter()

LOGIN_WINDOW = 15 * 60
LOGIN_LIMIT_PER_PAIR = 5      # one client guessing one account
LOGIN_LIMIT_PER_IP = 30       # one client spraying many accounts
LOGIN_LIMIT_PER_EMAIL = 25    # many clients guessing one account (high, so a
                              # stranger cannot easily lock someone out)
SIGNUP_WINDOW = 60 * 60
SIGNUP_LIMIT_PER_IP = 10


def login_keys(ip: str, email: str) -> dict[str, int]:
    return {
        f"login:pair:{ip}:{email}": LOGIN_LIMIT_PER_PAIR,
        f"login:ip:{ip}": LOGIN_LIMIT_PER_IP,
        f"login:email:{email}": LOGIN_LIMIT_PER_EMAIL,
    }
