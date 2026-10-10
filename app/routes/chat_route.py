import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.controllers import chat_controller
from app.dependencies import current_user, owner_key
from app.models.user_model import User
from app.services.llm_service import LLMUnavailable
from app.views.chat_view import ChatRequest, ChatResponse, HistoryEntry

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/chat", response_model=ChatResponse, response_model_exclude_none=True)
def chat(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(current_user),
):

    try:
        return chat_controller.chat_with_database(request, background_tasks, owner_key(user))

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
def chat_history(user: User = Depends(current_user)):

    try:
        return chat_controller.get_chat_history(owner_key(user))

    except SQLAlchemyError:
        logger.exception("Chat history read error")
        raise HTTPException(status_code=400, detail="Chat history read error.")
