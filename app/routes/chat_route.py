import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.controllers import chat_controller
from app.services.llm_service import LLMUnavailable
from app.views.chat_view import ChatRequest, ChatResponse, HistoryEntry

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/chat", response_model=ChatResponse, response_model_exclude_none=True)
def chat(request: ChatRequest, background_tasks: BackgroundTasks):

    try:
        return chat_controller.chat_with_database(request, background_tasks)

    except SQLAlchemyError:
        logger.exception("SQL execution error")
        raise HTTPException(status_code=400, detail="SQL execution error.")

    except LLMUnavailable:
        logger.exception("Language model call failed")
        raise HTTPException(
            status_code=503,
            detail="The language model is unavailable right now, please try again shortly."
        )


@router.get("/chat/history", response_model=list[HistoryEntry])
def chat_history(session_id: str):

    try:
        return chat_controller.get_chat_history(session_id)

    except SQLAlchemyError:
        logger.exception("Chat history read error")
        raise HTTPException(status_code=400, detail="Chat history read error.")
