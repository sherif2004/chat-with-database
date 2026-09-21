class GuardrailError(Exception):
    """Raised when a question or a generated query violates a guardrail."""


class UnknownTableError(GuardrailError):
    """The query references a table that is not in the database schema."""
