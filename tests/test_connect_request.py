import pytest
from pydantic import ValidationError

from app.views.connection_view import ConnectRequest


def make(**kw):
    return ConnectRequest(**kw)


def test_fields_are_trimmed_but_the_password_is_not():
    request = make(engine="mysql", host="  db.example.com ", username=" u ", password=" p ", label="  ")
    assert request.host == "db.example.com" and request.username == "u"
    assert request.password == " p "
    assert request.label is None


@pytest.mark.parametrize("kw", [
    dict(),                                                           # neither
    dict(engine="mysql", host="h", database_url="postgresql://u:p@h/db"),  # both
    dict(database_url="postgresql://u:p@h/db", host="h"),            # url plus fields
    dict(engine="oracle", host="h"),                                  # not a form engine
    dict(engine="mysql"),                                             # host missing
    dict(engine="mysql", host="db/evil"),
    dict(engine="mysql", host="a,b"),
    dict(engine="mysql", host="user@host"),
    dict(engine="mysql", host="h", port=0),
    dict(engine="mysql", host="h", port=70000),
    dict(engine="mysql", host="h", database="x" * 129),
    dict(engine="mysql", host="h", username="u\nDROP"),
    dict(engine="mysql", host="h", password="a\x00b"),
    dict(engine="mysql", host="h", unexpected="x"),
    dict(database_url="not a url"),
    dict(database_url="postgresql://u:p@h/db\nDROP"),
    dict(database_url="postgresql://u:p@h/" + "d" * 2100),
    dict(database_url="postgresql://u:p@h/db", label="x" * 81),
])
def test_bad_requests_are_rejected(kw):
    with pytest.raises(ValidationError):
        make(**kw)


@pytest.mark.parametrize("kw", [
    dict(engine="postgresql", host="db.example.com", port=5432, database="d", username="u", password="p"),
    dict(engine="snowflake", host="xy12345.eu-west-1", username="u"),
    dict(engine="mysql", host="2001:db8::1", username="u"),
    dict(database_url="postgresql://u:p@h/db", label="Prod replica"),
])
def test_good_requests_pass(kw):
    make(**kw)
