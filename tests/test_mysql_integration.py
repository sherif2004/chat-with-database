"""Runs against a real MySQL server. Skipped unless MYSQL_TEST_URL is set, e.g.

    docker run -d -e MYSQL_ROOT_PASSWORD=pw -e MYSQL_DATABASE=shop -p 33306:3306 mysql:8
    MYSQL_TEST_URL=mysql+pymysql://root:pw@127.0.0.1:33306/shop BLOCK_PRIVATE_HOSTS=false pytest
"""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.guardrails.sql_guard import validate_sql
from app.models import connection_model
from app.models.query_model import execute_sql

URL = os.environ.get("MYSQL_TEST_URL")
pytestmark = pytest.mark.skipif(not URL, reason="MYSQL_TEST_URL not set")


@pytest.fixture(scope="module")
def target():
    engine, dialect, schema, schema_name = connection_model._connect_and_introspect(URL)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS askbase_items (id INT PRIMARY KEY, name VARCHAR(20))"))
        conn.execute(text("REPLACE INTO askbase_items VALUES (1, 'a'), (2, 'b')"))
    schema, schema_name = connection_model._test_and_introspect(engine)
    yield engine, dialect, schema, schema_name
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS askbase_items"))
    engine.dispose()


def test_question_runs_end_to_end(target):
    engine, dialect, schema, schema_name = target
    [sql] = validate_sql("SELECT `name` FROM `askbase_items` ORDER BY `id`", schema.table_names, dialect, schema_name)
    assert execute_sql(sql, engine, dialect).rows == [["a"], ["b"]]


def test_engine_refuses_writes_and_resets_the_session(target):
    engine, dialect, *_ = target
    with pytest.raises(DBAPIError):
        execute_sql("INSERT INTO askbase_items VALUES (3, 'c')", engine, dialect)
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT @@session.transaction_read_only").scalar() == 0
