"""Refuses connection targets on the server's own network.

A user-supplied host is a request the server makes on their behalf, so
without this check someone could point it at localhost, a cloud metadata
address or another internal service. Self-hosters whose databases live on
a private network turn it off with BLOCK_PRIVATE_HOSTS=false.
"""

import ipaddress
import os
import re
import socket

from sqlalchemy.exc import SQLAlchemyError

from app.config import settings


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


_ODBC_SERVER = re.compile(r"(?i)(\bserver=)([^;,]*)")


def pin_to_public_address(dialect, _record, cargs, cparams) -> None:
    """`do_connect` handler: runs for every new connection, resolves the host,
    vets the address, and hands the driver that address instead of the name.
    The driver therefore never resolves the name itself, so a DNS answer that
    changes between the check and the connection (DNS rebinding) has no effect,
    and a database that moves to a new address is picked up on the next
    connection instead of being stuck on an old one.

    For libpq the name is kept (`host`) for TLS, and the address is added as
    `hostaddr`. Drivers whose host can't be located here are refused rather
    than let through unchecked."""

    if not settings.block_private_hosts:
        return

    host = cparams.get("host")
    if isinstance(host, str) and host:
        address = resolve_public(host)
        if dialect.driver == "psycopg2":
            cparams["hostaddr"] = address
        else:
            cparams["host"] = address
        return

    # pyodbc: the whole connection string is the first positional argument.
    if cargs and isinstance(cargs[0], str):
        match = _ODBC_SERVER.search(cargs[0])
        if match:
            address = resolve_public(match.group(2).strip().strip("{}"))
            cargs[0] = cargs[0][: match.start(2)] + address + cargs[0][match.end(2):]
            return

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
