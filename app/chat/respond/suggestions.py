import hashlib
import json
import logging

import redis
from pydantic import BaseModel

from app.shared.cache import client
from app.shared.llm import LIGHT_MODEL, MODEL, LLMUnavailable, ask_structured
from app.chat.respond.prompts import followups_prompt, starters_prompt

logger = logging.getLogger(__name__)

_STARTERS_TTL_SECONDS = 24 * 3600
_MAX_SUGGESTION_LENGTH = 120

FALLBACK_STARTERS = [
    "What tables are in this database?",
    "How many rows does the biggest table have?",
    "Show me a sample of the data",
    "What can I ask about this data?",
]


class _Suggestions(BaseModel):
    questions: list[str]


def _clean(questions: list[str], limit: int) -> list[str]:
    seen, cleaned = set(), []
    for question in questions:
        question = " ".join(question.split())
        if question and len(question) <= _MAX_SUGGESTION_LENGTH and question.lower() not in seen:
            seen.add(question.lower())
            cleaned.append(question)
    return cleaned[:limit]


def starter_questions(schema_text: str) -> list[str]:
    """Starter questions for a schema, cached per schema for a day. Falls
    back to generic ones if the model is unavailable."""

    key = "starters:" + hashlib.sha256(schema_text.encode()).hexdigest()

    try:
        cached = client.get(key)
        if cached:
            return json.loads(cached)
    except redis.RedisError:
        pass

    try:
        result, _usage = ask_structured(
            starters_prompt(schema_text), _Suggestions, max_output_tokens=300, model=LIGHT_MODEL
        )
    except LLMUnavailable:
        return FALLBACK_STARTERS

    questions = _clean(result.questions, 4) if result else []
    if not questions:
        return FALLBACK_STARTERS

    try:
        client.set(key, json.dumps(questions), ex=_STARTERS_TTL_SECONDS)
    except redis.RedisError:
        pass

    return questions


def follow_up_questions(schema_text: str, question: str, answer: str) -> list[str]:
    try:
        result, _usage = ask_structured(
            followups_prompt(schema_text, question, answer),
            _Suggestions,
            max_output_tokens=250,
            # The cheap model often ignores the language rule (see the note
            # on generate_answer), so follow-ups run on the capable one.
            model=MODEL,
        )
    except LLMUnavailable:
        return []

    return _clean(result.questions, 3) if result else []
