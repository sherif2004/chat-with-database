import json
import logging
import queue
import threading

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import SQLAlchemyError

from app.controllers import chat_controller
from app.controllers.chat_controller import ConversationNotFound
from app.dependencies import current_user, owner_key, require_permission
from app.models.user_model import User
from app.services.llm_service import LLMUnavailable
from app.services.permissions import has_permission
from app.timing import Timings
from app.guardrails.errors import GuardrailError
from app.guardrails.sql_guard import validate_write_sql
from app.models.audit_model import record_change
from app.models.connection_model import DatabaseConnectionError, get_or_default
from app.models.history_model import save_message
from app.models.query_model import WriteRefused, commit_write
from app.services import pending_change_service
from app.services.cache_service import clear_cached_responses
from app.views.chat_view import (
    ChatRequest,
    ChatResponse,
    ConfirmChangeRequest,
    ConfirmChangeResponse,
    MessageResult,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_LLM_DOWN = "The language model is unavailable right now, please try again shortly."


@router.post("/chat", response_model=ChatResponse, response_model_exclude_none=True)
def chat(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(current_user),
):

    try:
        return chat_controller.chat_with_database(
            request,
            background_tasks,
            owner_key(user),
            can_write=has_permission(user.role, "data:write"),
        )

    except ConversationNotFound:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    except SQLAlchemyError:
        logger.exception("SQL execution error")
        raise HTTPException(status_code=400, detail="SQL execution error.")

    except LLMUnavailable:
        logger.exception("Language model call failed")
        raise HTTPException(status_code=503, detail=_LLM_DOWN)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/chat/stream")
def chat_stream(request: ChatRequest, user: User = Depends(current_user)):
    """Same work as POST /chat, but reports pipeline stages as they start
    (server-sent events: `stage`, then one `done` or `error`). The answer
    itself still arrives whole."""

    owner = owner_key(user)
    can_write = has_permission(user.role, "data:write")
    events: queue.Queue = queue.Queue()
    background_tasks = BackgroundTasks()

    def work():
        try:
            response = chat_controller.chat_with_database(
                request,
                background_tasks,
                owner,
                timings=Timings(on_step=lambda step: events.put(("stage", {"step": step}))),
                can_write=can_write,
            )
            events.put(("done", response.model_dump(mode="json", exclude_none=True)))
        except ConversationNotFound:
            events.put(("error", {"status": 404, "detail": "Conversation not found."}))
        except SQLAlchemyError:
            logger.exception("SQL execution error")
            events.put(("error", {"status": 400, "detail": "SQL execution error."}))
        except LLMUnavailable:
            logger.exception("Language model call failed")
            events.put(("error", {"status": 503, "detail": _LLM_DOWN}))
        except Exception:
            logger.exception("Chat stream failed")
            events.put(("error", {"status": 500, "detail": "Something went wrong, try again."}))
        finally:
            events.put(None)

    def stream():
        threading.Thread(target=work, daemon=True).start()
        while (item := events.get()) is not None:
            yield _sse(*item)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        background=background_tasks,
    )


@router.post("/chat/confirm-change", response_model=ConfirmChangeResponse)
def confirm_change(
    request: ConfirmChangeRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_permission("data:write")),
):
    """Commits a change previously previewed in chat. The token is single-use,
    belongs to the admin who received it, and expires; the statement is
    re-validated and must touch exactly the rows that were shown."""

    pending = pending_change_service.take(request.token)

    if pending is None:
        raise HTTPException(status_code=410, detail="That change expired or was already applied. Ask again.")

    owner = owner_key(user)

    if pending["owner"] != owner:
        raise HTTPException(status_code=403, detail="That change belongs to another account.")

    try:
        connection = get_or_default(owner)
    except DatabaseConnectionError as e:
        raise HTTPException(status_code=400, detail=f"Your connected database is unreachable: {e}")

    if connection.label != pending["connection_label"]:
        raise HTTPException(status_code=409, detail="The connected database changed. Ask again.")

    try:
        sql = validate_write_sql(pending["sql"], connection.schema.table_names)
        rows = commit_write(sql, connection.engine, pending["rows"])
    except GuardrailError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except WriteRefused:
        raise HTTPException(
            status_code=409,
            detail="The data changed since the preview, so nothing was saved. Ask again.",
        )
    except SQLAlchemyError as e:
        logger.exception("Confirmed change failed")
        reason = str(getattr(e, "orig", None) or e).strip().splitlines()[0]
        raise HTTPException(status_code=400, detail=f"The change failed and nothing was saved: {reason}")

    message = f"Done. {rows} row{'s' if rows != 1 else ''} changed."

    logger.info("User %s changed %s rows on %s: %s", user.id, rows, connection.label, sql)
    background_tasks.add_task(record_change, user.id, user.email, connection.label, sql, rows)
    # Answers cached before this change are stale: everyone's if the shared
    # demo database changed, otherwise just this admin's.
    background_tasks.add_task(clear_cached_responses, None if connection.is_default else owner)

    conversation_id = pending.get("conversation_id")
    if conversation_id is not None:
        saved = ChatResponse(
            intent="data_change",
            question=f"Confirmed: {pending['question']}",
            sql=[sql],
            result=MessageResult(message=message),
            conversation_id=conversation_id,
        )
        background_tasks.add_task(
            save_message, owner, conversation_id, saved.question, saved.model_dump(mode="json")
        )

    return ConfirmChangeResponse(message=message, affected_rows=rows)
