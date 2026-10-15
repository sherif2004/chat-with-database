from fastapi import Cookie, Depends, HTTPException, Request

from app.accounts.users import User, get_user_by_token
from app.accounts.permissions import has_permission

SESSION_COOKIE = "session"


def current_user(session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> User:
    """Resolves the signed-in user from the session cookie. Every route that
    touches a user's data depends on this; identity never comes from the
    request body."""

    user = get_user_by_token(session) if session else None

    if user is None:
        raise HTTPException(status_code=401, detail="Please sign in to continue.")

    return user


def require_permission(permission: str):
    """Like current_user, but also refuses (403) a user whose role lacks the
    permission. The role is read from the database on every request, so a
    promotion or demotion applies immediately."""

    def dependency(user: User = Depends(current_user)) -> User:
        if not has_permission(user.role, permission):
            raise HTTPException(
                status_code=403, detail="You don't have permission to do that."
            )
        return user

    return dependency


def owner_key(user: User) -> str:
    """The key under which a user's history, saved connection and cached
    answers are stored. Prefixed so it can never match a row written before
    accounts existed, when clients chose their own session_id."""

    return f"u:{user.id}"


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
