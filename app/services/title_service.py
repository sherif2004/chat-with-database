import logging
import re

from pydantic import BaseModel

from app.services.llm_service import LIGHT_MODEL, LLMUnavailable, ask_structured
from app.services.prompts import title_prompt

logger = logging.getLogger(__name__)

MAX_TITLE_LENGTH = 60


class _Title(BaseModel):
    title: str


def _clean(title: str) -> str | None:
    title = " ".join(title.split()).strip(" \"'`“”‘’.!?:;,-")
    title = re.sub(r"^(title|عنوان)\s*[:：]\s*", "", title, flags=re.IGNORECASE)

    if not title:
        return None

    if len(title) > MAX_TITLE_LENGTH:
        title = title[: MAX_TITLE_LENGTH - 1].rstrip() + "…"

    return title


def generate_title(question: str) -> str | None:
    """A short topic title for a new chat, or None if the model is
    unavailable or gives nothing usable (the caller keeps its placeholder).

    A naming task is easy, so it runs on the light model (the cheap half of
    the hybrid setup). That model is weaker at keeping to the question's
    language, so a title can occasionally come back in the wrong one.
    """

    try:
        result, _usage = ask_structured(
            title_prompt(question), _Title, max_output_tokens=40, model=LIGHT_MODEL
        )
    except LLMUnavailable:
        logger.warning("Chat title generation skipped: model unavailable")
        return None

    return _clean(result.title) if result else None
