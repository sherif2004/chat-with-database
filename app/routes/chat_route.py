import json
import logging
import queue
import threading

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import SQLAlchemyError

from app.controllers import chat_controller
from app.controllers.chat_controller import ConversationNotFound
from app.dependencies import current_user, owner_key
from app.models.user_model import User
from app.services.llm_service import LLMUnavailable
from app.timing import Timings
from app.views.chat_view import ChatRequest, ChatResponse

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
        return chat_controller.chat_with_database(request, background_tasks, owner_key(user))

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
    events: queue.Queue = queue.Queue()
    background_tasks = BackgroundTasks()

    def work():
        try:
            response = chat_controller.chat_with_database(
                request,
                background_tasks,
                owner,
                timings=Timings(on_step=lambda step: events.put(("stage", {"step": step}))),
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
