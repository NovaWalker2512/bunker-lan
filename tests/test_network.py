from bunker.network.client import send_request
from bunker.network.server import BunkerServer


def test_server_answers_ping():
    server = BunkerServer(host="127.0.0.1", port=0)
    server.start()

    try:
        host, port = server.address

        response = send_request(
            host,
            port,
            {"type": "ping", "message": "hello"},
        )

        assert response == {"type": "pong", "message": "hello"}
    finally:
        server.stop()


def test_server_rejects_unknown_message_type():
    server = BunkerServer(host="127.0.0.1", port=0)
    server.start()

    try:
        host, port = server.address

        response = send_request(
            host,
            port,
            {"type": "unknown"},
        )

        assert response["type"] == "error"
        assert "unknown" in response["message"]
    finally:
        server.stop()
