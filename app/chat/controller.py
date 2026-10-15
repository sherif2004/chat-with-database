import logging
from concurrent.futures import ThreadPoolExecutor

from fastapi import BackgroundTasks
from pydantic import ValidationError

from app.chat.graph import chat_graph
from app.chat.conversations import (
    create_conversation,
    get_conversation,
    set_generated_title,
    title_from_question,
)
from app.chat.history import delete_last_exchange, get_history, save_message
from app.shared.cache import set_cached_response
from app.shared.llm import MODEL
from app.chat.respond.title import generate_title
from app.shared.timing import Timings
from app.chat.schemas import ChatRequest, ChatResponse, DebugInfo, HistoryEntry

logger = logging.getLogger(__name__)

PLACEHOLDER_TITLE = "New chat"
_TITLE_WAIT_SECONDS = 4

# Chat titles are written by the light model, in parallel with the answer.
_title_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="chat-title")


class ConversationNotFound(Exception):
    pass


def _finish(timings, background_tasks, session_id, conversation_id, debug, **fields):

    response = ChatResponse(
        timings_ms=timings.as_model(), debug=debug, conversation_id=conversation_id, **fields
    )

    logger.info(
        "intent=%s timings_ms=%s",
        response.intent,
        response.timings_ms
    )

    dumped = response.model_dump(mode="json")
    is_change = response.intent == "data_change"

    if is_change and dumped["result"].get("type") == "change":
        # The one-time token lives only in this response, not in history.
        dumped["result"]["token"] = None

    background_tasks.add_task(save_message, session_id, conversation_id, fields["question"], dumped)

    # Cache hits aren't re-cached — the entry that served this one is
    # already there and still fresh. A change is never cached: replaying one
    # must go back through preview and confirmation.
    if not fields.get("cache_hit") and not is_change:
        background_tasks.add_task(set_cached_response, session_id, fields["question"], dumped)

    return response


def _apply_title(title_future, placeholder, session_id, conversation_id) -> None:
    """Give a new chat its generated title; keep the placeholder if the
    model is slow, unavailable, or the user already renamed the chat."""

    if title_future is None:
        return

    try:
        title = title_future.result(timeout=_TITLE_WAIT_SECONDS)
    except Exception:
        logger.warning("Chat title not ready; keeping the placeholder")
        return

    if title:
        set_generated_title(session_id, conversation_id, placeholder, title)


def chat_with_database(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    session_id: str,
    timings: Timings | None = None,
    can_write: bool = False,
) -> ChatResponse:
    """`session_id` is the signed-in user's owner key (see dependencies.owner_key): the key under
    which history, the saved connection and cached answers are stored."""

    timings = timings or Timings()
    debug = DebugInfo(model=MODEL)

    placeholder = None  # set while this chat still needs a title

    if request.conversation_id is None:
        placeholder = title_from_question(request.question)
        conversation_id = create_conversation(session_id, placeholder).id
    else:
        conversation = get_conversation(session_id, request.conversation_id)
        if conversation is None:
            raise ConversationNotFound()
        conversation_id = conversation.id
        if conversation.title == PLACEHOLDER_TITLE:
            placeholder = PLACEHOLDER_TITLE
        if request.replace_last:
            delete_last_exchange(session_id, conversation_id)

    # Start naming the chat now so it finishes alongside the answer.
    title_future = (
        _title_pool.submit(generate_title, request.question) if placeholder else None
    )

    final_state = chat_graph.invoke(
        {
            "session_id": session_id,
            "conversation_id": conversation_id,
            "skip_cache": request.replace_last,
            "can_write": can_write,
            "raw_question": request.question,
        },
        config={
            "configurable": {
                "timings": timings,
                "debug": debug,
                "background_tasks": background_tasks,
                "session_data": {},
            }
        },
    )

    _apply_title(title_future, placeholder, session_id, conversation_id)

    if final_state.get("cache_hit"):
        cached = final_state["cached_response"]
        return _finish(
            timings,
            background_tasks,
            session_id,
            conversation_id,
            cached.debug,
            intent=cached.intent,
            question=final_state["question"],
            sql=cached.sql,
            result=cached.result,
            cache_hit=True,
        )

    return _finish(
        timings,
        background_tasks,
        session_id,
        conversation_id,
        debug,
        intent=final_state["intent"],
        question=final_state["question"],
        sql=final_state.get("statements"),
        result=final_state["result"],
    )


def get_chat_history(session_id: str, conversation_id: int) -> list[HistoryEntry]:

    if get_conversation(session_id, conversation_id) is None:
        raise ConversationNotFound()

    rows = get_history(session_id, conversation_id)

    entries = []

    for row in rows:
        try:
            entries.append(HistoryEntry(
                question=row.question,
                response=ChatResponse.model_validate(row.response),
                created_at=row.created_at
            ))
        except ValidationError:
            logger.warning("Skipping unparseable chat_history row for session %s", session_id)

    return entries
