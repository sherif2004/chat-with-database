import pytest

from app.config import settings
from app.dialects import network
from app.dialects.network import PrivateHostBlocked, check_host


@pytest.fixture(autouse=True)
def blocking(monkeypatch):
    monkeypatch.setattr(settings, "block_private_hosts", True)


@pytest.mark.parametrize("host", [
    "127.0.0.1", "10.0.0.5", "192.168.1.9", "169.254.169.254", "100.64.0.1", "::1", "::ffff:10.0.0.1",
])
def test_non_public_addresses_are_blocked(host):
    with pytest.raises(PrivateHostBlocked):
        check_host(host)


def test_unresolvable_host_fails_closed(monkeypatch):
    def fail(*args, **kwargs):
        raise network.socket.gaierror("nope")

    monkeypatch.setattr(network.socket, "getaddrinfo", fail)
    with pytest.raises(PrivateHostBlocked):
        check_host("does-not-exist.invalid")


def test_public_address_is_allowed():
    check_host("8.8.8.8")


def test_check_can_be_turned_off(monkeypatch):
    monkeypatch.setattr(settings, "block_private_hosts", False)
    check_host("127.0.0.1")


class _FakeConnection:
    """Stands in for a pymysql connection: it exposes the socket as `_sock`."""

    def __init__(self, sock):
        self._sock = sock
        self.closed = False

    def close(self):
        self.closed = True


def _loopback_pair():
    import socket

    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    client = socket.create_connection(server.getsockname())
    return server, client


def test_peer_on_a_private_address_is_refused_and_closed():
    server, client = _loopback_pair()
    try:
        connection = _FakeConnection(client)
        with pytest.raises(PrivateHostBlocked):
            network.verify_peer(connection)
        assert connection.closed
    finally:
        client.close()
        server.close()


def test_peer_check_is_skipped_when_blocking_is_off(monkeypatch):
    monkeypatch.setattr(settings, "block_private_hosts", False)
    server, client = _loopback_pair()
    try:
        network.verify_peer(_FakeConnection(client))
    finally:
        client.close()
        server.close()


def test_drivers_that_hide_their_socket_are_not_blocked():
    network.verify_peer(object())
