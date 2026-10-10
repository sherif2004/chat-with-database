from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.activity_model import ActivityEntry
from app.services.auth_service import MAX_PASSWORD_LENGTH


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class UserInfo(BaseModel):
    id: int
    email: str
    role: str = "user"
    permissions: list[str] = []


class AccountInfo(BaseModel):
    id: int
    email: str
    role: str
    created_at: datetime | None = None


class RoleChange(BaseModel):
    role: Literal["user", "supervisor", "admin"]


class ActivityPage(BaseModel):
    entries: list[ActivityEntry]
    has_more: bool
