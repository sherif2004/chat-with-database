from pydantic import BaseModel, Field

from app.models.schema_model import DatabaseSchema


class ConnectRequest(BaseModel):
    session_id: str = Field(min_length=1)
    database_url: str = Field(min_length=1)
    label: str | None = None


class ConnectionInfo(BaseModel):
    label: str
    is_default: bool
    schema_: DatabaseSchema = Field(alias="schema", serialization_alias="schema")
    error: str | None = None

    model_config = {"populate_by_name": True}
