"""Turns query results into a written answer."""

from app.chat.respond.prompts import answer_prompt
from app.shared.llm import MODEL, TokenUsage, ask_llm

# The answer prompt gets at most this many rows; the rest only cost tokens.
ANSWER_ROW_LIMIT = 20


def generate_answer(
    question,
    queries: list[dict]
) -> tuple[str, str, TokenUsage | None]:
    """`queries` is [{"sql", "rows"}, ...], one entry per executed
    statement; `rows` is trimmed to ANSWER_ROW_LIMIT here.

    Summarizing rows into a sentence looks easy, but LIGHT_MODEL proved
    unreliable at the one rule that matters most here — answering in the
    question's language (verified: ~1 in 3 answers came back in the wrong
    language, reproducibly, across unrelated questions, even after
    strengthening the prompt). Runs on MODEL instead.
    """

    trimmed = [
        {"sql": q["sql"], "rows": q["rows"][:ANSWER_ROW_LIMIT], "total_rows": len(q["rows"])}
        for q in queries
    ]

    prompt = answer_prompt(question, trimmed)
    answer, usage = ask_llm(prompt, max_output_tokens=800, model=MODEL)

    return answer, prompt, usage
