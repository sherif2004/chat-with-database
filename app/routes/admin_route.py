import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.controllers import chat_controller
from app.controllers.chat_controller import ConversationNotFound
from app.dependencies import owner_key, require_permission
from app.models.connection_model import forget_connection
from app.models.conversation_model import list_conversations
from app.models.user_model import (
    LastAdmin,
    User,
    get_user,
    list_users,
    remove_user,
    set_role,
)
from app.views.auth_view import AccountInfo, RoleChange
from app.views.chat_view import HistoryEntry
from app.views.conversation_view import ConversationInfo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin")

_NO_USER = HTTPException(status_code=404, detail="User not found.")
_LAST_ADMIN = HTTPException(status_code=409, detail="There must be at least one admin.")


def _account(user: User) -> AccountInfo:
    return AccountInfo(id=user.id, email=user.email, role=user.role, created_at=user.created_at)


@router.get("/users", response_model=list[AccountInfo])
def users(_: User = Depends(require_permission("users:read"))):
    return [_account(user) for user in list_users()]


@router.patch("/users/{user_id}/role", response_model=AccountInfo)
def change_role(
    user_id: int,
    change: RoleChange,
    admin: User = Depends(require_permission("users:write")),
):

    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="You can't change your own role.")

    try:
        user = set_role(user_id, change.role)
    except LastAdmin:
        raise _LAST_ADMIN

    if user is None:
        raise _NO_USER

    logger.info("Admin %s set user %s to role %s", admin.id, user.id, user.role)
    return _account(user)


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, admin: User = Depends(require_permission("users:write"))):

    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="You can't delete your own account.")

    try:
        deleted = remove_user(user_id)
    except LastAdmin:
        raise _LAST_ADMIN

    if not deleted:
        raise _NO_USER

    forget_connection(f"u:{user_id}")
    logger.info("Admin %s deleted user %s", admin.id, user_id)


@router.get("/users/{user_id}/conversations", response_model=list[ConversationInfo])
def user_conversations(user_id: int, _: User = Depends(require_permission("conversation:read_any"))):

    target = get_user(user_id)

    if target is None:
        raise _NO_USER

    return list_conversations(owner_key(target))


@router.get(
    "/users/{user_id}/conversations/{conversation_id}/messages",
    response_model=list[HistoryEntry],
    response_model_exclude_none=True,
)
def user_messages(
    user_id: int,
    conversation_id: int,
    _: User = Depends(require_permission("conversation:read_any")),
):
    """Read-only: there is deliberately no write route for another user's chats."""

    target = get_user(user_id)

    if target is None:
        raise _NO_USER

    try:
        return chat_controller.get_chat_history(owner_key(target), conversation_id)
    except ConversationNotFound:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    except SQLAlchemyError:
        logger.exception("Chat history read error")
        raise HTTPException(status_code=400, detail="Chat history read error.")
