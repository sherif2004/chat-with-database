from pydantic import BaseModel, Field, model_validator

from app.models.schema_model import DatabaseSchema


class ConnectRequest(BaseModel):
    """Either a full `database_url`, or an `engine` plus separate fields."""

    database_url: str | None = None
    engine: str | None = None
    host: str = ""
    port: int | None = Field(default=None, ge=1, le=65535)
    database: str = ""
    username: str = ""
    password: str = ""
    label: str | None = None

    @model_validator(mode="after")
    def _needs_url_or_engine(self):
        if not (self.database_url and self.database_url.strip()) and not self.engine:
            raise ValueError("Give a connection URL, or choose a database type.")
        return self


class EngineInfo(BaseModel):
    key: str
    name: str
    default_port: int | None
    needs_host: bool
    installed: bool
    package: str
    read_only_enforced: bool
    supports_writes: bool


class EnginesResponse(BaseModel):
    engines: list[EngineInfo]


class ConnectionInfo(BaseModel):
    label: str
    is_default: bool
    engine: str = "PostgreSQL"
    read_only_enforced: bool = True
    schema_: DatabaseSchema = Field(alias="schema", serialization_alias="schema")
    error: str | None = None

    model_config = {"populate_by_name": True}


class TestResponse(BaseModel):
    ok: bool = True
    label: str
    engine: str
    table_count: int
    read_only_enforced: bool
