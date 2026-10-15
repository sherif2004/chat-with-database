"""Refuses connection targets on the server's own network.

A user-supplied host is a request the server makes on their behalf, so
without this check someone could point it at localhost, a cloud metadata
address or another internal service. Self-hosters whose databases live on
a private network turn it off with BLOCK_PRIVATE_HOSTS=false.
"""

import ipaddress
import socket

from app.config import settings


class PrivateHostBlocked(Exception):
    pass


def check_host(host: str | None) -> None:
    if not host or not settings.block_private_hosts:
        return

    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except socket.gaierror:
        return  # unresolvable: the connection attempt will report it

    for address in addresses:
        ip = ipaddress.ip_address(address.split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified:
            raise PrivateHostBlocked(
                "That address is on a private network, which this server doesn't connect to. "
                "Use a publicly reachable host, or ask the administrator to allow private hosts."
            )
