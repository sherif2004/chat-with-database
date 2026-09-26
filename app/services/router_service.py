from typing import Literal

from pydantic import BaseModel

from app.services.llm_service import ask_structured
from app.services.prompts import router_prompt
from app.views.chat_view import TokenUsage


class RouteDecision(BaseModel):
    intent: Literal["greeting", "data_question", "off_topic", "unsafe"]
    reply: str | None = None


def classify_intent(
    question,
    schema_text,
    history: list[dict] | None = None
) -> tuple[RouteDecision, str, TokenUsage | None]:

    prompt = router_prompt(question, schema_text, history or [])
    decision, usage = ask_structured(prompt, RouteDecision, max_output_tokens=200)

    # Fail closed: an unusable routing answer is never sent to SQL.
    return decision or RouteDecision(intent="off_topic"), prompt, usage
