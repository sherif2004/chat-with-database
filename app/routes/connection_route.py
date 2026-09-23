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


@router.post("/connections", response_model=ConnectionInfo, response_model_by_alias=True)
def create_connection(request: ConnectRequest):

    try:
        connection = connect(request.session_id, request.database_url, request.label)
    except DatabaseConnectionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ConnectionInfo(
        label=connection.label,
        is_default=connection.is_default,
        schema=connection.schema,
    )


@router.get("/connections/current", response_model=ConnectionInfo, response_model_by_alias=True)
def current_connection(session_id: str):

    try:
        connection = get_or_default(session_id)
        return ConnectionInfo(
            label=connection.label,
            is_default=connection.is_default,
            schema=connection.schema,
        )

    except DatabaseConnectionError as e:
        logger.warning("Saved connection unreachable for session %s: %s", session_id, e)

        default = get_default_connection()
        return ConnectionInfo(
            label=default.label,
            is_default=True,
            schema=default.schema,
            error=str(e),
        )
