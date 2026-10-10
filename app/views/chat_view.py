from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from app.timing import StepTimings


class ChatRequest(BaseModel):
    question: str
    conversation_id: int | None = None
    # Regenerate / edit-last: drop the newest exchange first and skip the answer cache.
    replace_last: bool = False


class MessageResult(BaseModel):
    type: Literal["message"] = "message"
    message: str


class QueryTable(BaseModel):
    sql: str
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool = False


class TableResult(BaseModel):
    """One or more queries run for a single question, each with its own
    SQL and rows, plus one natural-language answer covering all of them."""

    type: Literal["table"] = "table"
    queries: list[QueryTable]
    answer: str | None = None


class ChangeResult(BaseModel):
    """A previewed INSERT/UPDATE/DELETE awaiting an admin's confirmation.
    `token` is absent once the preview is stored in history: it only works
    once and expires, so an old chat never offers a stale Confirm."""

    type: Literal["change"] = "change"
    message: str
    sql: str
    affected_rows: int
    token: str | None = None


Result = Annotated[
    MessageResult | TableResult | ChangeResult,
    Field(discriminator="type")
]


class ExampleUsed(BaseModel):
    question: str
    sql: str
    score: float


class TokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int


class DebugInfo(BaseModel):
    model: str
    prompts: dict[str, str] = Field(default_factory=dict)
    token_usage: dict[str, TokenUsage] = Field(default_factory=dict)
    examples: list[ExampleUsed] = Field(default_factory=list)


class ChatResponse(BaseModel):
    intent: Literal[
        "greeting", "off_topic", "unsafe", "data_question",
        "connection_error", "needs_clarification", "data_change"
    ]
    question: str
    sql: list[str] | None = None
    result: Result
    timings_ms: StepTimings = StepTimings()
    debug: DebugInfo | None = None
    cache_hit: bool = False
    conversation_id: int | None = None


class HistoryEntry(BaseModel):
    question: str
    response: ChatResponse
    created_at: datetime


class ConfirmChangeRequest(BaseModel):
    token: str


class ConfirmChangeResponse(BaseModel):
    message: str
    affected_rows: int
