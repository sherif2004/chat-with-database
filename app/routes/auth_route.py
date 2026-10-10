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
    login_throttle,
    new_session_token,
    normalize_email,
    verify_password,
)
from app.views.auth_view import Credentials, UserInfo

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


def _throttle_key(request: Request, email: str) -> str:
    client = request.client.host if request.client else "unknown"
    return f"{client}:{email}"


@router.post("/signup", response_model=UserInfo, status_code=201)
def signup(credentials: Credentials, response: Response):

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

    return UserInfo(id=user.id, email=user.email)


@router.post("/login", response_model=UserInfo)
def login(credentials: Credentials, request: Request, response: Response):

    email = normalize_email(credentials.email)
    key = _throttle_key(request, email)

    if login_throttle.blocked(key):
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
        login_throttle.record_failure(key)
        raise HTTPException(status_code=401, detail=_BAD_LOGIN)

    login_throttle.clear(key)
    user = found[0]

    try:
        _start_session(response, user)
    except SQLAlchemyError:
        logger.exception("Could not create session")
        raise HTTPException(status_code=503, detail="Couldn't sign in right now, please try again.")

    return UserInfo(id=user.id, email=user.email)


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
    return UserInfo(id=user.id, email=user.email)
