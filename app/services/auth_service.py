import base64
import hashlib
import hmac
import re
import secrets
import time
from collections import defaultdict, deque

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


class LoginThrottle:
    """Allows `limit` failed attempts per key within `window` seconds.
    In-memory, so it resets on restart and is per-process — enough to stop
    casual guessing; put a shared limiter in front for multi-worker deploys."""

    def __init__(self, limit: int = 5, window: int = 15 * 60):
        self.limit = limit
        self.window = window
        self._failures: dict[str, deque] = defaultdict(deque)

    def _prune(self, key: str) -> deque:
        failures = self._failures[key]
        cutoff = time.monotonic() - self.window
        while failures and failures[0] < cutoff:
            failures.popleft()
        return failures

    def blocked(self, key: str) -> bool:
        return len(self._prune(key)) >= self.limit

    def record_failure(self, key: str) -> None:
        self._prune(key).append(time.monotonic())

    def clear(self, key: str) -> None:
        self._failures.pop(key, None)


login_throttle = LoginThrottle()
