"""Refuses connection targets on the server's own network.

A user-supplied host is a request the server makes on their behalf, so
without this check someone could point it at localhost, a cloud metadata
address or another internal service. Self-hosters whose databases live on
a private network turn it off with BLOCK_PRIVATE_HOSTS=false.
"""

import ipaddress
import os
import socket

from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.dialects import HOST_PATTERN


class PrivateHostBlocked(SQLAlchemyError):
    """A SQLAlchemyError so a refusal raised while the pool opens a connection
    is handled like any other connection failure instead of becoming a 500."""


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%")[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    # is_global is false for private, loopback, link-local, reserved and
    # shared (100.64.0.0/10) ranges, which is stricter than is_private.
    return ip.is_global


def resolve_public(host: str) -> str:
    """Resolve `host` once and return an address that is safe to connect to.
    Every address the name resolves to must be public, or it is refused. A
    name that can't be resolved is refused too: we can't vouch for it."""

    try:
        addresses = [info[4][0] for info in socket.getaddrinfo(host, None)]
    except (socket.gaierror, UnicodeError):
        raise PrivateHostBlocked(f"The host name '{host}' couldn't be found. Check the spelling.")

    if not addresses or not all(_is_public(address) for address in addresses):
        raise PrivateHostBlocked(
            "That address is on a private network, which this server doesn't connect to. "
            "Use a publicly reachable host, or ask the administrator to allow private hosts."
        )

    return addresses[0]


def check_host(host: str | None) -> None:
    """Early, friendly refusal when the connect page is submitted."""

    if host and settings.block_private_hosts:
        resolve_public(host)


# The only keys the SQL Server dialect may put in its ODBC connection string.
# A fixed list means a hostile value can't add a second server or a failover
# partner, which the driver would also connect to.
_ODBC_KEYS = {"driver", "server", "database", "uid", "pwd", "encrypt", "trustservercertificate"}


class _Unpinnable(Exception):
    pass


def _odbc_pairs(text: str) -> list[tuple[str, str]]:
    """Split an ODBC connection string into (key, raw value) pairs. A value in
    braces may contain `;`, and `}}` inside braces is a literal brace."""

    pairs, i, n = [], 0, len(text)
    while i < n:
        equals = text.find("=", i)
        if equals == -1:
            if text[i:].strip(" ;"):
                raise _Unpinnable()
            break
        key, j = text[i:equals].strip(), equals + 1
        if j < n and text[j] == "{":
            k = j + 1
            while True:
                end = text.find("}", k)
                if end == -1:
                    raise _Unpinnable()
                if end + 1 < n and text[end + 1] == "}":
                    k = end + 2
                    continue
                break
            value, i = text[j:end + 1], end + 1
            if i < n and text[i] == ";":
                i += 1
        else:
            end = text.find(";", j)
            end = n if end == -1 else end
            value, i = text[j:end], end + 1
        pairs.append((key, value))
    return pairs


def _pin_odbc(connection_string: str) -> str:
    pairs = _odbc_pairs(connection_string)
    keys = [key.lower() for key, _ in pairs]

    if any(key not in _ODBC_KEYS for key in keys) or keys.count("server") != 1:
        raise _Unpinnable()

    rewritten = []
    for key, value in pairs:
        if key.lower() == "server":
            host, comma, port = value.strip("{} ").partition(",")
            if not HOST_PATTERN.match(host):
                raise _Unpinnable()
            value = resolve_public(host) + comma + port
        rewritten.append(f"{key}={value}")
    return ";".join(rewritten)


def pin_to_public_address(dialect, _record, cargs, cparams) -> None:
    """`do_connect` handler: runs for every new connection, resolves the host,
    vets the address, and hands the driver that address instead of the name.
    The driver therefore never resolves the name itself, so a DNS answer that
    changes between the check and the connection (DNS rebinding) has no effect,
    and a database that moves to a new address is picked up on the next
    connection instead of being stuck on an old one.

    Each driver takes its target differently, so each is handled explicitly:
    libpq (`hostaddr`, the name stays for TLS), pymysql (`host`), pyodbc (the
    `Server=` value of the connection string) and ClickHouse native (the DSN).
    Any other driver is refused while blocking is on, never let through."""

    if not settings.block_private_hosts:
        return

    try:
        host = cparams.get("host")

        if dialect.driver == "psycopg2" and isinstance(host, str) and host:
            cparams["hostaddr"] = resolve_public(host)
            return

        if dialect.driver == "pymysql" and isinstance(host, str) and host:
            cparams["host"] = resolve_public(host)
            return

        if dialect.driver == "pyodbc" and cargs and isinstance(cargs[0], str):
            cargs[0] = _pin_odbc(cargs[0])
            return

        if dialect.driver == "native" and cargs and isinstance(cargs[0], str):
            dsn = make_url(cargs[0])
            if dsn.host and HOST_PATTERN.match(dsn.host):
                cargs[0] = dsn.set(host=resolve_public(dsn.host)).render_as_string(hide_password=False)
                return
    except _Unpinnable:
        pass

    raise PrivateHostBlocked(
        "This server can't verify where that kind of connection goes, so it won't open it "
        "while private hosts are blocked. Ask the administrator to set BLOCK_PRIVATE_HOSTS=false "
        "if the database is trusted."
    )


def _peer_address(dbapi_connection) -> str | None:
    """The address the open connection is really talking to, or None when the
    driver doesn't expose its socket."""

    try:
        info = getattr(dbapi_connection, "info", None)  # psycopg2
        descriptor = getattr(info, "socket", None)
        if isinstance(descriptor, int):
            probe = socket.socket(fileno=os.dup(descriptor))
            try:
                return str(probe.getpeername()[0])
            finally:
                probe.close()

        sock = getattr(dbapi_connection, "_sock", None)  # pymysql
        if sock is not None:
            return str(sock.getpeername()[0])
    except (OSError, IndexError, TypeError):
        return None

    return None


def verify_peer(dbapi_connection, _record=None) -> None:
    """Second line of defence, on every new pooled connection: check where the
    connection actually landed. Registered first, so it runs before the
    dialect sends any query on the new connection."""

    if not settings.block_private_hosts:
        return

    address = _peer_address(dbapi_connection)
    if address is None:
        return  # driver doesn't expose its socket; pin_to_public_address() already fixed the address

    try:
        public = _is_public(address)
    except ValueError:  # a unix socket path, not an IP
        public = False

    if not public:
        dbapi_connection.close()
        raise PrivateHostBlocked(
            "That connection ended up on a private network, which this server doesn't connect to."
        )
