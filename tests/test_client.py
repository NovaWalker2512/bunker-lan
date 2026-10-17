import queue

import pytest

from bunker.network.client import BunkerClient, send_request
from bunker.network.server import BunkerServer


def test_client_receives_ping_response():
    """Проверяет получение ответа на ping."""
    server = BunkerServer()
    client = BunkerClient()
    server.start()

    try:
        host, port = server.address
        client.connect(host, port)
        client.send({"type": "ping", "message": "Привет"})

        response = client.receive(timeout=2)

        assert response == {
            "type": "pong",
            "message": "Привет",
        }
    finally:
        client.close()
        server.stop()


def test_client_receives_welcome_and_lobby_state():
    """Проверяет получение данных после входа в комнату."""
    server = BunkerServer()
    client = BunkerClient()
    server.start()

    try:
        host, port = server.address
        client.connect(host, port)
        client.send({"type": "join", "nickname": "Мира"})

        welcome = client.receive(timeout=2)
        state = client.receive(timeout=2)

        assert welcome["type"] == "welcome"
        assert welcome["player_id"]
        assert state["type"] == "lobby_state"
        assert state["players"][0]["nickname"] == "Мира"
    finally:
        client.close()
        server.stop()


def test_client_cannot_send_without_connection():
    """Проверяет запрет отправки без подключения."""
    client = BunkerClient()

    with pytest.raises(RuntimeError):
        client.send({"type": "ping"})


def test_client_rejects_invalid_port():
    """Проверяет обработку некорректного номера порта."""
    client = BunkerClient()

    with pytest.raises(ValueError):
        client.connect("127.0.0.1", 70000)


def test_receive_times_out_without_messages():
    """Проверяет тайм-аут при отсутствии сообщений."""
    client = BunkerClient()

    with pytest.raises(queue.Empty):
        client.receive(timeout=0.01)


def test_send_request_remains_compatible():
    """Проверяет совместимость прежней функции запроса."""
    server = BunkerServer()
    server.start()

    try:
        host, port = server.address
        response = send_request(
            host,
            port,
            {"type": "ping", "message": "Проверка"},
        )

        assert response["type"] == "pong"
        assert response["message"] == "Проверка"
    finally:
        server.stop()
