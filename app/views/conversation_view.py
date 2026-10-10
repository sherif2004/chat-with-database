from datetime import datetime

from pydantic import BaseModel, Field


class ConversationInfo(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime


class RenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class Suggestions(BaseModel):
    suggestions: list[str]
