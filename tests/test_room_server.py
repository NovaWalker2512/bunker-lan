import socket

from bunker.network.protocol import decode_message, encode_message
from bunker.network.server import BunkerServer


def test_join_receives_welcome_and_lobby_state():
    server = BunkerServer()
    server.start()

    try:
        with socket.create_connection(
            server.address,
            timeout=2,
        ) as connection:
            connection.settimeout(2)

            with connection.makefile("rb") as stream:
                connection.sendall(
                    encode_message(
                        {
                            "type": "join",
                            "nickname": "Mira",
                        }
                    )
                )

                welcome = decode_message(stream.readline())
                state = decode_message(stream.readline())

                assert welcome["type"] == "welcome"
                assert welcome["player_id"]
                assert state["type"] == "lobby_state"
                assert len(state["players"]) == 1
                assert state["players"][0]["nickname"] == "Mira"
                assert state["players"][0]["is_host"] is True
    finally:
        server.stop()


def test_ready_request_requires_joining_first():
    server = BunkerServer()
    server.start()

    try:
        with socket.create_connection(
            server.address,
            timeout=2,
        ) as connection:
            connection.settimeout(2)

            with connection.makefile("rb") as stream:
                connection.sendall(
                    encode_message(
                        {
                            "type": "ready",
                            "ready": True,
                        }
                    )
                )

                response = decode_message(stream.readline())

                assert response["type"] == "error"
                assert "Join the room" in response["message"]
    finally:
        server.stop()


def test_duplicate_nickname_is_rejected_by_server():
    server = BunkerServer()
    server.start()

    try:
        with socket.create_connection(
            server.address,
            timeout=2,
        ) as first:
            first.settimeout(2)

            with first.makefile("rb") as first_stream:
                first.sendall(
                    encode_message(
                        {
                            "type": "join",
                            "nickname": "Mira",
                        }
                    )
                )

                welcome = decode_message(first_stream.readline())
                state = decode_message(first_stream.readline())

                assert welcome["type"] == "welcome"
                assert state["type"] == "lobby_state"

                with socket.create_connection(
                    server.address,
                    timeout=2,
                ) as second:
                    second.settimeout(2)

                    with second.makefile("rb") as second_stream:
                        second.sendall(
                            encode_message(
                                {
                                    "type": "join",
                                    "nickname": "mira",
                                }
                            )
                        )

                        response = decode_message(second_stream.readline())

                        assert response["type"] == "error"
                        assert "nickname" in response["message"]
    finally:
        server.stop()
