from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from app.timing import StepTimings


class ChatRequest(BaseModel):
    question: str
    session_id: str = Field(min_length=1)


class MessageResult(BaseModel):
    type: Literal["message"] = "message"
    message: str


class TextResult(BaseModel):
    type: Literal["text"] = "text"
    answer: str


class TableResult(BaseModel):
    type: Literal["table"] = "table"
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool = False
    answer: str | None = None


Result = Annotated[
    MessageResult | TextResult | TableResult,
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
    workflow: Literal["router", "no_router"] = "router"
    prompts: dict[str, str] = Field(default_factory=dict)
    token_usage: dict[str, TokenUsage] = Field(default_factory=dict)
    examples: list[ExampleUsed] = Field(default_factory=list)


class ChatResponse(BaseModel):
    intent: Literal["greeting", "off_topic", "unsafe", "data_question", "connection_error"]
    question: str
    sql: str | None = None
    result: Result
    timings_ms: StepTimings = StepTimings()
    debug: DebugInfo | None = None


class HistoryEntry(BaseModel):
    question: str
    response: ChatResponse
    created_at: datetime
