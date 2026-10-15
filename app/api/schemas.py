"""Request and response models for the HTTP API."""

import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from app.accounts.activity import ActivityEntry
from app.accounts.auth import MAX_PASSWORD_LENGTH
from app.databases.engines import HOST_PATTERN, by_key
from app.databases.schema import DatabaseSchema


# --- Accounts ---


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


# --- Conversations ---


class ConversationInfo(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime


class RenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class Suggestions(BaseModel):
    suggestions: list[str]


# --- Connecting a database ---


_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _no_control_characters(value: str, what: str) -> str:
    if _CONTROL.search(value):
        raise ValueError(f"The {what} can't contain line breaks or control characters.")
    return value


Text = Annotated[str, StringConstraints(strip_whitespace=True)]


class ConnectRequest(BaseModel):
    """What a person typed into the connect page, checked before anything
    touches the network. Either a full `database_url`, or an `engine` with
    separate fields, never both."""

    model_config = ConfigDict(extra="forbid")

    database_url: Text | None = Field(default=None, max_length=2048)
    engine: Text | None = Field(default=None, max_length=32)
    host: Text = Field(default="", max_length=253)
    port: int | None = Field(default=None, ge=1, le=65535)
    database: Text = Field(default="", max_length=128)
    username: Text = Field(default="", max_length=128)
    # Not stripped: a password may legitimately start or end with a space.
    password: str = Field(default="", max_length=256)
    label: Text | None = Field(default=None, max_length=80)

    @field_validator("database_url")
    @classmethod
    def _url_is_well_formed(cls, value):
        if not value:
            return None
        _no_control_characters(value, "connection URL")
        if "://" not in value:
            raise ValueError("That doesn't look like a connection URL. It should start with something like postgresql://")
        try:
            make_url(value)
        except ArgumentError:
            raise ValueError("That connection URL can't be read. Check it against the example under the field.")
        return value

    @field_validator("engine")
    @classmethod
    def _engine_is_known(cls, value):
        if not value:
            return None
        if by_key(value) is None:
            raise ValueError("Choose one of the listed database types, or paste a connection URL.")
        return value

    @field_validator("host")
    @classmethod
    def _host_is_a_host(cls, value):
        if value and not HOST_PATTERN.match(value):
            raise ValueError("The host should be a server name or IP address, with no spaces, slashes or commas.")
        return value

    @field_validator("database", "username")
    @classmethod
    def _plain_text(cls, value, info):
        return _no_control_characters(value, info.field_name)

    @field_validator("password")
    @classmethod
    def _password_has_no_nul(cls, value):
        if "\x00" in value:
            raise ValueError("The password can't contain a null character.")
        return value

    @field_validator("label")
    @classmethod
    def _label_is_plain(cls, value):
        if not value:
            return None
        return _no_control_characters(value, "name")

    @model_validator(mode="after")
    def _one_way_of_connecting(self):
        has_url = bool(self.database_url)
        has_fields = bool(self.engine)

        if not has_url and not has_fields:
            raise ValueError("Choose a database type, or paste a connection URL.")

        if has_url and has_fields:
            raise ValueError("Give either a connection URL or a database type with its details, not both.")

        if has_url:
            if any((self.host, self.port, self.database, self.username, self.password)):
                raise ValueError("A connection URL already holds the details. Clear the other fields or the URL.")
            return self

        dialect = by_key(self.engine)
        if dialect.needs_host and not self.host:
            raise ValueError("Enter the host (server address) of the database.")

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
    __test__ = False  # not a pytest class

    ok: bool = True
    label: str
    engine: str
    table_count: int
    read_only_enforced: bool
