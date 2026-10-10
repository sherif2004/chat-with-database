import logging

from fastapi import BackgroundTasks
from pydantic import ValidationError

from app.graphs.chat_graph import chat_graph
from app.models.conversation_model import (
    create_conversation,
    get_conversation,
    rename_conversation,
    title_from_question,
)
from app.models.history_model import delete_last_exchange, get_history, save_message
from app.services.cache_service import set_cached_response
from app.services.llm_service import MODEL
from app.timing import Timings
from app.views.chat_view import ChatRequest, ChatResponse, DebugInfo, HistoryEntry

logger = logging.getLogger(__name__)


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
    background_tasks.add_task(save_message, session_id, conversation_id, fields["question"], dumped)

    # Cache hits aren't re-cached — the entry that served this one is
    # already there and still fresh.
    if not fields.get("cache_hit"):
        background_tasks.add_task(set_cached_response, session_id, fields["question"], dumped)

    return response


def chat_with_database(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    session_id: str,
    timings: Timings | None = None,
) -> ChatResponse:
    """`session_id` is the signed-in user's owner key (see dependencies.owner_key): the key under
    which history, the saved connection and cached answers are stored."""

    timings = timings or Timings()
    debug = DebugInfo(model=MODEL)

    if request.conversation_id is None:
        conversation_id = create_conversation(
            session_id, title_from_question(request.question)
        ).id
    else:
        conversation = get_conversation(session_id, request.conversation_id)
        if conversation is None:
            raise ConversationNotFound()
        conversation_id = conversation.id
        if conversation.title == "New chat":
            rename_conversation(session_id, conversation_id, title_from_question(request.question))
        if request.replace_last:
            delete_last_exchange(session_id, conversation_id)

    final_state = chat_graph.invoke(
        {
            "session_id": session_id,
            "conversation_id": conversation_id,
            "skip_cache": request.replace_last,
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
