import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.exc import SQLAlchemyError

from app.chat import controller as chat_controller
from app.chat.controller import ConversationNotFound
from app.dependencies import client_ip, owner_key, require_permission
from app.databases.connection import forget_connection
from app.accounts.activity import (
    EVENTS,
    ActivitySummary,
    activity_summary,
    list_activity,
    record_activity,
)
from app.chat.conversations import get_conversation, list_conversations
from app.accounts.users import (
    LastAdmin,
    User,
    get_user,
    list_users,
    remove_user,
    set_role,
)
from app.api.schemas import AccountInfo, ActivityPage, RoleChange
from app.chat.schemas import HistoryEntry
from app.api.schemas import ConversationInfo

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
    request: Request,
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
    record_activity(
        "role_changed", actor=admin, target=user, detail=f"Now {user.role}", ip=client_ip(request)
    )
    return _account(user)


@router.delete("/users/{user_id}", status_code=204)
def delete_user(
    user_id: int, request: Request, admin: User = Depends(require_permission("users:write"))
):

    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="You can't delete your own account.")

    victim = get_user(user_id)

    try:
        deleted = remove_user(user_id)
    except LastAdmin:
        raise _LAST_ADMIN

    if not deleted:
        raise _NO_USER

    forget_connection(f"u:{user_id}")
    logger.info("Admin %s deleted user %s", admin.id, user_id)
    record_activity(
        "user_deleted",
        actor=admin,
        target=victim,
        detail=f"Deleted {victim.email}" if victim else None,
        ip=client_ip(request),
    )


@router.get("/users/{user_id}/conversations", response_model=list[ConversationInfo])
def user_conversations(
    user_id: int,
    request: Request,
    viewer: User = Depends(require_permission("conversation:read_any")),
):

    target = get_user(user_id)

    if target is None:
        raise _NO_USER

    record_activity(
        "chat_viewed", actor=viewer, target=target, detail="Browsed their conversation list",
        ip=client_ip(request),
    )

    return list_conversations(owner_key(target))


@router.get(
    "/users/{user_id}/conversations/{conversation_id}/messages",
    response_model=list[HistoryEntry],
    response_model_exclude_none=True,
)
def user_messages(
    user_id: int,
    conversation_id: int,
    request: Request,
    viewer: User = Depends(require_permission("conversation:read_any")),
):
    """Read-only: there is deliberately no write route for another user's chats."""

    target = get_user(user_id)

    if target is None:
        raise _NO_USER

    try:
        entries = chat_controller.get_chat_history(owner_key(target), conversation_id)
    except ConversationNotFound:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    except SQLAlchemyError:
        logger.exception("Chat history read error")
        raise HTTPException(status_code=400, detail="Chat history read error.")

    conversation = get_conversation(owner_key(target), conversation_id)
    record_activity(
        "chat_viewed",
        actor=viewer,
        target=target,
        detail=f"Opened \u201c{conversation.title}\u201d" if conversation else None,
        ip=client_ip(request),
    )

    return entries


@router.get("/activity", response_model=ActivityPage)
def activity(
    event: list[str] = Query(default=[]),
    q: str | None = Query(default=None, max_length=100),
    before: int | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    _: User = Depends(require_permission("activity:read")),
):

    events = [e for e in event if e in EVENTS]
    entries, has_more = list_activity(events or None, (q or "").strip() or None, before, limit)

    return ActivityPage(entries=entries, has_more=has_more)


@router.get("/activity/summary", response_model=ActivitySummary)
def activity_overview(_: User = Depends(require_permission("activity:read"))):
    return activity_summary()
