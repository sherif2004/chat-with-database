from typing import Literal

from pydantic import BaseModel

from app.services.llm_service import LIGHT_MODEL, ask_structured
from app.services.prompts import router_prompt
from app.views.chat_view import TokenUsage


class RouteDecision(BaseModel):
    intent: Literal["greeting", "data_question", "data_change", "off_topic", "unsafe"]
    reply: str | None = None


def classify_intent(
    question,
    schema_text,
    history: list[dict] | None = None,
    can_write: bool = False,
) -> tuple[RouteDecision, str, TokenUsage | None]:
    """A 4-way classification is an easy task compared to writing correct
    SQL, so this runs on LIGHT_MODEL."""

    prompt = router_prompt(question, schema_text, history or [], can_write)
    decision, usage = ask_structured(prompt, RouteDecision, max_output_tokens=200, model=LIGHT_MODEL)

    # Fail closed: an unusable routing answer is never sent to SQL.
    return decision or RouteDecision(intent="off_topic"), prompt, usage
