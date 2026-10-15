import pytest

from app.dialects import MYSQL, MSSQL, POSTGRES, UnsupportedDatabase, build_url, by_key, for_url
from app.guardrails.errors import GuardrailError
from app.guardrails.sql_guard import validate_sql


def test_curated_engines_resolve_from_urls():
    assert for_url("postgresql://u:p@h/db") is POSTGRES
    assert for_url("mysql+pymysql://u:p@h/db") is MYSQL
    assert for_url("mariadb+pymysql://u:p@h/db") is MYSQL
    assert for_url("mssql+pyodbc://u:p@h/db") is MSSQL


def test_other_engines_get_a_generic_dialect():
    dialect = for_url("oracle+oracledb://u:p@h/svc")
    assert dialect.sqlglot == "oracle"
    assert not dialect.curated and not dialect.read_only_enforced


@pytest.mark.parametrize("url", [
    "sqlite:////etc/passwd",
    "duckdb:////etc/passwd",
    "firebird://u:p@h/db",
    "access+pyodbc:///?odbc_connect=x",
])
def test_embedded_and_unlisted_engines_are_refused(url):
    with pytest.raises(UnsupportedDatabase):
        for_url(url)


@pytest.mark.parametrize("url", [
    "mysql+pymysql://u:p@h/db?local_infile=1",
    "mysql+pymysql://u:p@h/db?ssl_ca=/etc/passwd",
    "mysql+pymysql://u:p@h/db?read_default_file=/etc/passwd",
    "postgresql://u:p@h/db?sslrootcert=/etc/passwd",
    "postgresql://u:p@h/db?host=127.0.0.1",
    "postgresql://u:p@h/db?service=x",
    "mssql+pyodbc://u:p@h/db?odbc_connect=DRIVER%3D%7Bx%7D",
    "mssql+pyodbc://u:p@h/db?driver=/tmp/evil.so",
    "oracle+oracledb://u:p@h/svc?wallet_location=/tmp",
])
def test_unlisted_driver_options_are_refused(url):
    with pytest.raises(UnsupportedDatabase):
        for_url(url)


@pytest.mark.parametrize("url", [
    "postgresql://u:p@a,b/db",
    "postgresql://u:p@/db",
    "mysql+pymysql://u:p@/var/run/mysqld.sock/db",
])
def test_odd_hosts_are_refused(url):
    with pytest.raises(UnsupportedDatabase):
        for_url(url)


def test_allowed_options_pass():
    for_url("postgresql://u:p@h/db?sslmode=require")
    for_url("mssql+pyodbc://u:p@h/db?driver=ODBC+Driver+17+for+SQL+Server&Encrypt=yes")
    for_url("snowflake://u:p@acct/db/schema?warehouse=W")


def test_mysql_never_loads_local_files():
    assert MYSQL.connect_args["local_infile"] is False


def test_build_url_escapes_the_password():
    url = build_url(by_key("mysql"), host="h", port=None, database="d", username="u", password="p@ss/w:rd")
    assert url.password == "p@ss/w:rd"
    assert url.port == 3306
    assert "p@ss/w:rd" not in url.render_as_string()


@pytest.mark.parametrize("dialect,schema,sql", [
    (MYSQL, "shop", "SELECT `a` FROM `t` LIMIT 5"),
    (MSSQL, "dbo", "SELECT TOP 5 [a] FROM [t]"),
    (POSTGRES, "public", 'SELECT "a" FROM "t" LIMIT 5'),
])
def test_select_is_accepted_in_each_dialect(dialect, schema, sql):
    assert validate_sql(sql, {"t"}, dialect, schema) == [sql]


@pytest.mark.parametrize("dialect,schema,sql", [
    (MYSQL, "shop", "DELETE FROM t"),
    (MYSQL, "shop", "SELECT SLEEP(5) FROM t"),
    (MYSQL, "shop", "SELECT * FROM other.t"),
    (MYSQL, "shop", "SELECT * FROM secret"),
    (MSSQL, "dbo", "SELECT * FROM t; DROP TABLE t"),
    (MSSQL, "dbo", "EXEC xp_cmdshell 'dir'"),
    (POSTGRES, "public", "SELECT pg_sleep(5)"),
])
def test_unsafe_sql_is_refused(dialect, schema, sql):
    with pytest.raises(GuardrailError):
        validate_sql(sql, {"t"}, dialect, schema)
