import logging

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import current_user, owner_key, require_permission
from app.models.user_model import User
from app.services.crypto_service import SecretKeyMissing
from app.dialects import CURATED, UnsupportedDatabase, build_url, by_key, require_installed
from app.models.connection_model import (
    DatabaseConnectionError,
    check_connection,
    connect,
    get_default_connection,
    get_or_default,
)
from app.services.suggestion_service import FALLBACK_STARTERS, starter_questions
from app.views.conversation_view import Suggestions
from app.views.connection_view import (
    ConnectionInfo,
    ConnectRequest,
    EngineInfo,
    EnginesResponse,
    TestResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _to_connection_info(connection, error: str | None = None) -> ConnectionInfo:
    return ConnectionInfo(
        label=connection.label,
        is_default=connection.is_default,
        engine=connection.dialect.name,
        read_only_enforced=connection.dialect.read_only_enforced,
        schema=connection.schema,
        error=error,
    )


def _url_from_request(request: ConnectRequest):
    """The URL to connect to: the pasted one, or one built from the fields."""

    if request.database_url and request.database_url.strip():
        return request.database_url.strip()

    dialect = by_key(request.engine or "")
    if dialect is None:
        raise DatabaseConnectionError("Choose a database type, or paste a connection URL.")

    try:
        require_installed(dialect)
    except UnsupportedDatabase as e:
        raise DatabaseConnectionError(str(e))

    if dialect.needs_host and not request.host.strip():
        raise DatabaseConnectionError("Enter the host (server address) of the database.")

    return build_url(
        dialect,
        host=request.host.strip(),
        port=request.port,
        database=request.database.strip(),
        username=request.username.strip(),
        password=request.password,
    )


@router.get("/connections/engines", response_model=EnginesResponse)
def list_engines(user: User = Depends(require_permission("connection:write"))):
    return EnginesResponse(
        engines=[
            EngineInfo(
                key=d.key,
                name=d.name,
                default_port=d.default_port,
                needs_host=d.needs_host,
                installed=d.installed,
                package=d.package,
                read_only_enforced=d.read_only_enforced,
                supports_writes=d.supports_writes,
            )
            for d in CURATED
        ]
    )


@router.post("/connections/test", response_model=TestResponse)
def test_connection_route(
    request: ConnectRequest, user: User = Depends(require_permission("connection:write"))
):
    """Try a connection without saving it."""

    try:
        result = check_connection(_url_from_request(request))
    except DatabaseConnectionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return TestResponse(
        label=result.label,
        engine=result.dialect.name,
        table_count=result.table_count,
        read_only_enforced=result.dialect.read_only_enforced,
    )


@router.post("/connections", response_model=ConnectionInfo, response_model_by_alias=True)
def create_connection(
    request: ConnectRequest, user: User = Depends(require_permission("connection:write"))
):

    try:
        connection = connect(owner_key(user), _url_from_request(request), request.label)
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
