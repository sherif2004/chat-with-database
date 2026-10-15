"""Refuses connection targets on the server's own network.

A user-supplied host is a request the server makes on their behalf, so
without this check someone could point it at localhost, a cloud metadata
address or another internal service. Self-hosters whose databases live on
a private network turn it off with BLOCK_PRIVATE_HOSTS=false.
"""

import ipaddress
import os
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


def check_host(host: str | None) -> None:
    if not host or not settings.block_private_hosts:
        return

    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except (socket.gaierror, UnicodeError):
        # Fail closed: a name we cannot resolve here is not vouched for.
        raise PrivateHostBlocked(f"The host name '{host}' couldn't be found. Check the spelling.")

    if not all(_is_public(address) for address in addresses):
        raise PrivateHostBlocked(
            "That address is on a private network, which this server doesn't connect to. "
            "Use a publicly reachable host, or ask the administrator to allow private hosts."
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
    """Runs on every new pooled connection. check_host() looked the name up
    before connecting; this checks where the connection actually landed, so a
    name that resolves differently the second time (DNS rebinding) is caught."""

    if not settings.block_private_hosts:
        return

    address = _peer_address(dbapi_connection)
    if address is None:
        return  # driver doesn't expose it; check_host() was the only check

    try:
        public = _is_public(address)
    except ValueError:  # a unix socket path, not an IP
        public = False

    if not public:
        dbapi_connection.close()
        raise PrivateHostBlocked(
            "That connection ended up on a private network, which this server doesn't connect to."
        )
