import re

from app.config import settings
from app.guardrails.errors import GuardrailError

# Common prompt-injection phrasings. This is a cheap first line of defence;
# the router also classifies injection attempts as "unsafe".
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier)\s+(instructions|prompts?|rules)",
    r"disregard\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier|your)\s+(instructions|prompts?|rules)",
    r"forget\s+(all\s+|your\s+|the\s+)?(previous\s+|prior\s+)?(instructions|rules)",
    r"(reveal|show|print|repeat|display)\s+(me\s+)?(your\s+|the\s+)?(system\s+prompt|instructions|hidden\s+prompt)",
    r"you\s+are\s+now\s+(a|an|in)\b",
    r"\b(act|pretend)\s+(as|to\s+be)\b",
    r"\b(developer|jailbreak|dan)\s+mode\b",
    r"</?\s*(system|assistant|question)\s*>",
]

_compiled = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


def check_question(question: str) -> str:
    question = question.strip()

    if not question:
        raise GuardrailError("The question is empty.")

    if len(question) > settings.max_question_length:
        raise GuardrailError(
            f"The question is too long (max {settings.max_question_length} characters)."
        )

    for pattern in _compiled:
        if pattern.search(question):
            raise GuardrailError(
                "The question looks like an attempt to change my instructions."
            )

    return question
