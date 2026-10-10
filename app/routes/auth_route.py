import logging

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.dependencies import SESSION_COOKIE, current_user
from app.models.user_model import (
    EmailTaken,
    User,
    create_session,
    create_user,
    delete_session,
    get_credentials,
)
from app.services.auth_service import (
    DUMMY_HASH,
    MIN_PASSWORD_LENGTH,
    hash_password,
    is_valid_email,
    LOGIN_WINDOW,
    SIGNUP_LIMIT_PER_IP,
    SIGNUP_WINDOW,
    limiter,
    login_keys,
    new_session_token,
    normalize_email,
    verify_password,
)
from app.services.permissions import permissions_for
from app.views.auth_view import Credentials, UserInfo


def _info(user: User) -> UserInfo:
    return UserInfo(
        id=user.id,
        email=user.email,
        role=user.role,
        permissions=sorted(permissions_for(user.role)),
    )

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth")

_BAD_LOGIN = "That email and password don't match."


def _start_session(response: Response, user: User) -> None:
    token = new_session_token()
    create_session(user.id, token)

    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_days * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/signup", response_model=UserInfo, status_code=201)
def signup(credentials: Credentials, request: Request, response: Response):

    signup_key = f"signup:ip:{_client_ip(request)}"

    if limiter.count(signup_key) >= SIGNUP_LIMIT_PER_IP:
        raise HTTPException(
            status_code=429,
            detail="Too many sign-ups from this network. Try again later.",
        )

    limiter.record(signup_key, SIGNUP_WINDOW)

    email = normalize_email(credentials.email)

    if not is_valid_email(email):
        raise HTTPException(status_code=400, detail="Enter a valid email address.")

    if len(credentials.password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Use at least {MIN_PASSWORD_LENGTH} characters for your password.",
        )

    try:
        user = create_user(email, hash_password(credentials.password))
        _start_session(response, user)
    except EmailTaken:
        raise HTTPException(status_code=409, detail="An account with that email already exists.")
    except SQLAlchemyError:
        logger.exception("Sign-up failed")
        raise HTTPException(status_code=503, detail="Couldn't create the account right now, please try again.")

    return _info(user)


@router.post("/login", response_model=UserInfo)
def login(credentials: Credentials, request: Request, response: Response):

    email = normalize_email(credentials.email)
    keys = login_keys(_client_ip(request), email)

    if any(limiter.count(key) >= limit for key, limit in keys.items()):
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Wait a few minutes and try again.",
        )

    try:
        found = get_credentials(email)
    except SQLAlchemyError:
        logger.exception("Login lookup failed")
        raise HTTPException(status_code=503, detail="Couldn't sign in right now, please try again.")

    stored_hash = found[1] if found else DUMMY_HASH
    password_ok = verify_password(credentials.password, stored_hash)

    if not found or not password_ok:
        for key in keys:
            limiter.record(key, LOGIN_WINDOW)
        raise HTTPException(status_code=401, detail=_BAD_LOGIN)

    for key in list(keys)[:1]:  # a good login clears only this client's own counter
        limiter.clear(key)
    user = found[0]

    try:
        _start_session(response, user)
    except SQLAlchemyError:
        logger.exception("Could not create session")
        raise HTTPException(status_code=503, detail="Couldn't sign in right now, please try again.")

    return _info(user)


@router.post("/logout", status_code=204)
def logout(response: Response, session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):

    if session:
        try:
            delete_session(session)
        except SQLAlchemyError:
            logger.exception("Could not delete session")

    response.delete_cookie(SESSION_COOKIE, path="/")
    response.status_code = 204


@router.get("/me", response_model=UserInfo)
def me(user: User = Depends(current_user)):
    return _info(user)
