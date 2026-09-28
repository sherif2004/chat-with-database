import logging

from fastapi import BackgroundTasks
from pydantic import ValidationError

from app.graphs.chat_graph import chat_graph
from app.models.history_model import get_history, save_message
from app.services.cache_service import set_cached_response
from app.services.llm_service import MODEL
from app.timing import Timings
from app.views.chat_view import ChatRequest, ChatResponse, DebugInfo, HistoryEntry

logger = logging.getLogger(__name__)


def _finish(timings, background_tasks, session_id, debug, **fields):

    response = ChatResponse(timings_ms=timings.as_model(), debug=debug, **fields)

    logger.info(
        "intent=%s timings_ms=%s",
        response.intent,
        response.timings_ms
    )

    dumped = response.model_dump(mode="json")
    background_tasks.add_task(save_message, session_id, fields["question"], dumped)

    # Cache hits aren't re-cached — the entry that served this one is
    # already there and still fresh.
    if not fields.get("cache_hit"):
        background_tasks.add_task(set_cached_response, session_id, fields["question"], dumped)

    return response


def chat_with_database(
    request: ChatRequest,
    background_tasks: BackgroundTasks
) -> ChatResponse:

    timings = Timings()
    session_id = request.session_id
    debug = DebugInfo(model=MODEL)

    final_state = chat_graph.invoke(
        {"session_id": session_id, "raw_question": request.question},
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
        debug,
        intent=final_state["intent"],
        question=final_state["question"],
        sql=final_state.get("statements"),
        result=final_state["result"],
    )


def get_chat_history(session_id: str) -> list[HistoryEntry]:

    rows = get_history(session_id)

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
