import logging

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import current_user, owner_key, require_permission
from app.models.user_model import User
from app.services.crypto_service import SecretKeyMissing
from app.models.connection_model import (
    DatabaseConnectionError,
    connect,
    get_default_connection,
    get_or_default,
)
from app.services.suggestion_service import FALLBACK_STARTERS, starter_questions
from app.views.conversation_view import Suggestions
from app.views.connection_view import ConnectionInfo, ConnectRequest

logger = logging.getLogger(__name__)

router = APIRouter()


def _to_connection_info(connection, error: str | None = None) -> ConnectionInfo:
    return ConnectionInfo(
        label=connection.label,
        is_default=connection.is_default,
        schema=connection.schema,
        error=error,
    )


@router.post("/connections", response_model=ConnectionInfo, response_model_by_alias=True)
def create_connection(
    request: ConnectRequest, user: User = Depends(require_permission("connection:write"))
):

    try:
        connection = connect(owner_key(user), request.database_url, request.label)
    except DatabaseConnectionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SecretKeyMissing as e:
        raise HTTPException(status_code=503, detail=str(e))

    return _to_connection_info(connection)


@router.get("/connections/current", response_model=ConnectionInfo, response_model_by_alias=True)
def current_connection(user: User = Depends(current_user)):

    session_id = owner_key(user)

    try:
        return _to_connection_info(get_or_default(session_id))

    except DatabaseConnectionError as e:
        logger.warning("Saved connection unreachable for session %s: %s", session_id, e)
        return _to_connection_info(get_default_connection(), error=str(e))


@router.get("/connections/starters", response_model=Suggestions)
def starters(user: User = Depends(current_user)):
    """Starter questions for the empty chat, written for the connected schema."""

    try:
        schema_text = get_or_default(owner_key(user)).schema_text
    except DatabaseConnectionError:
        return Suggestions(suggestions=FALLBACK_STARTERS)

    return Suggestions(suggestions=starter_questions(schema_text))
