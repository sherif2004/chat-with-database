import logging

from fastapi import APIRouter, HTTPException

from app.models.connection_model import (
    DatabaseConnectionError,
    connect,
    get_default_connection,
    get_or_default,
)
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
def create_connection(request: ConnectRequest):

    try:
        connection = connect(request.session_id, request.database_url, request.label)
    except DatabaseConnectionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _to_connection_info(connection)


@router.get("/connections/current", response_model=ConnectionInfo, response_model_by_alias=True)
def current_connection(session_id: str):

    try:
        return _to_connection_info(get_or_default(session_id))

    except DatabaseConnectionError as e:
        logger.warning("Saved connection unreachable for session %s: %s", session_id, e)
        return _to_connection_info(get_default_connection(), error=str(e))
