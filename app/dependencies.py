from fastapi import Cookie, HTTPException

from app.models.user_model import User, get_user_by_token

SESSION_COOKIE = "session"


def current_user(session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> User:
    """Resolves the signed-in user from the session cookie. Every route that
    touches a user's data depends on this; identity never comes from the
    request body."""

    user = get_user_by_token(session) if session else None

    if user is None:
        raise HTTPException(status_code=401, detail="Please sign in to continue.")

    return user


def owner_key(user: User) -> str:
    """The key under which a user's history, saved connection and cached
    answers are stored. Prefixed so it can never match a row written before
    accounts existed, when clients chose their own session_id."""

    return f"u:{user.id}"
