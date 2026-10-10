from pydantic import BaseModel, Field

from app.services.auth_service import MAX_PASSWORD_LENGTH


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class UserInfo(BaseModel):
    id: int
    email: str
