import re


def normalize_text(text: str) -> str:
    """Lowercase, drop punctuation and collapse whitespace for comparisons."""

    text = re.sub(r"[^\w\s]", " ", text.lower())

    return " ".join(text.split())
