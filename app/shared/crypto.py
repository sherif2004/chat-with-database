import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class SecretKeyMissing(Exception):
    """APP_SECRET_KEY is not configured, so secrets cannot be stored."""


def _fernet() -> Fernet:
    if not settings.app_secret_key:
        raise SecretKeyMissing(
            "Saving a database connection needs APP_SECRET_KEY to be set on the server."
        )

    digest = hashlib.sha256(settings.app_secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str | None:
    """None if the token was written with a different key or is corrupt."""

    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
