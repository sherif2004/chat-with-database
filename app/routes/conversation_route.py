import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.controllers import chat_controller
from app.controllers.chat_controller import ConversationNotFound
from app.dependencies import current_user, owner_key
from app.models.connection_model import DatabaseConnectionError, get_or_default
from app.models.conversation_model import (
    create_conversation,
    delete_conversation,
    list_conversations,
    rename_conversation,
)
from app.models.history_model import get_recent_history
from app.models.user_model import User
from app.services.suggestion_service import follow_up_questions
from app.views.chat_view import HistoryEntry
from app.views.conversation_view import ConversationInfo, RenameRequest, Suggestions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations")

_NOT_FOUND = HTTPException(status_code=404, detail="Conversation not found.")


@router.get("", response_model=list[ConversationInfo])
def conversations(user: User = Depends(current_user)):
    return list_conversations(owner_key(user))


@router.post("", response_model=ConversationInfo, status_code=201)
def new_conversation(user: User = Depends(current_user)):
    return create_conversation(owner_key(user), "New chat")


@router.patch("/{conversation_id}", response_model=ConversationInfo)
def rename(conversation_id: int, request: RenameRequest, user: User = Depends(current_user)):

    title = " ".join(request.title.split())
    conversation = rename_conversation(owner_key(user), conversation_id, title) if title else None

    if conversation is None:
        raise _NOT_FOUND

    return conversation


@router.delete("/{conversation_id}", status_code=204)
def delete(conversation_id: int, user: User = Depends(current_user)):

    if not delete_conversation(owner_key(user), conversation_id):
        raise _NOT_FOUND


@router.get(
    "/{conversation_id}/messages",
    response_model=list[HistoryEntry],
    response_model_exclude_none=True,
)
def messages(conversation_id: int, user: User = Depends(current_user)):

    try:
        return chat_controller.get_chat_history(owner_key(user), conversation_id)
    except ConversationNotFound:
        raise _NOT_FOUND
    except SQLAlchemyError:
        logger.exception("Chat history read error")
        raise HTTPException(status_code=400, detail="Chat history read error.")


@router.get("/{conversation_id}/followups", response_model=Suggestions)
def followups(conversation_id: int, user: User = Depends(current_user)):
    """Suggested next questions for the latest answer. Generated on demand
    so the answer itself never waits for them."""

    owner = owner_key(user)

    try:
        rows = get_recent_history(owner, conversation_id, 1)
    except SQLAlchemyError:
        return Suggestions(suggestions=[])

    if not rows:
        return Suggestions(suggestions=[])

    last = rows[-1]
    response = last.response

    if response.get("intent") != "data_question":
        return Suggestions(suggestions=[])

    result = response.get("result") or {}
    answer = result.get("answer") or ""

    if not answer:
        return Suggestions(suggestions=[])

    try:
        schema_text = get_or_default(owner).schema_text
    except DatabaseConnectionError:
        return Suggestions(suggestions=[])

    return Suggestions(suggestions=follow_up_questions(schema_text, last.question, answer))
