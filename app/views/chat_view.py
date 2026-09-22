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


class ChatResponse(BaseModel):
    intent: Literal["greeting", "off_topic", "unsafe", "data_question"]
    question: str
    sql: str | None = None
    result: Result
    timings_ms: StepTimings = StepTimings()


class HistoryEntry(BaseModel):
    question: str
    response: ChatResponse
    created_at: datetime
