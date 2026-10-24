
"""Интеграционные тесты игрового сервера."""

import queue
import time
from typing import Callable

from bunker.network.client import BunkerClient
from bunker.network.server import BunkerServer


def wait_for_message(
    client: BunkerClient,
    condition: Callable[[dict], bool],
    timeout: float = 3.0,
) -> dict:
    """Ожидает сообщение, удовлетворяющее условию.

    Args:
        client: Подключённый сетевой клиент.
        condition: Функция проверки полученного сообщения.
        timeout: Максимальное время ожидания в секундах.

    Returns:
        Первое сообщение, удовлетворяющее условию.

    Raises:
        AssertionError: Если нужное сообщение не поступило вовремя.
    """
    deadline = time.monotonic() + timeout

    while True:
        remaining = deadline - time.monotonic()

        if remaining <= 0:
            raise AssertionError(
                "Не получено ожидаемое сообщение от сервера."
            )

        try:
            message = client.receive(timeout=remaining)
        except queue.Empty as exc:
            raise AssertionError(
                "Истекло время ожидания сообщения."
            ) from exc

        if condition(message):
            return message


def test_server_runs_game_and_finishes_voting():
    """Проверяет начало партии, раскрытие и голосование."""
    server = BunkerServer(host="127.0.0.1", port=0)
    clients = []
    player_ids = []

    server.start()

    try:
        host, port = server.address

        for nickname in ("Анна", "Борис", "Вера"):
            client = BunkerClient()
            clients.append(client)
            client.connect(host, port)
            client.send(
                {
                    "type": "join",
                    "nickname": nickname,
                }
            )

            welcome = wait_for_message(
                client,
                lambda message: message.get("type") == "welcome",
            )
            player_ids.append(welcome["player_id"])

            wait_for_message(
                client,
                lambda message: message.get("type") == "lobby_state",
            )

        for client in clients:
            client.send(
                {
                    "type": "ready",
                    "ready": True,
                }
            )

        wait_for_message(
            clients[0],
            lambda message: (
                message.get("type") == "lobby_state"
                and len(message.get("players", [])) == 3
                and all(
                    player["ready"]
                    for player in message["players"]
                )
            ),
        )

        clients[0].send({"type": "start"})

        initial_state = wait_for_message(
            clients[0],
            lambda message: message.get("type") == "game_state",
        )

        assert initial_state["phase"] == "reveal"

        for client in clients:
            client.send({"type": "reveal"})

        wait_for_message(
            clients[0],
            lambda message: (
                message.get("type") == "game_state"
                and message.get("phase") == "voting"
            ),
        )

        clients[0].send(
            {
                "type": "vote",
                "target_id": player_ids[1],
            }
        )
        clients[1].send(
            {
                "type": "vote",
                "target_id": player_ids[0],
            }
        )
        clients[2].send(
            {
                "type": "vote",
                "target_id": player_ids[0],
            }
        )

        final_state = wait_for_message(
            clients[0],
            lambda message: (
                message.get("type") == "game_state"
                and message.get("phase") == "finished"
            ),
        )

        assert set(final_state["winners"]) == {
            player_ids[1],
            player_ids[2],
        }

    finally:
        for client in clients:
            client.close()

        server.stop()


def test_reveal_before_game_start_is_rejected():
    """Проверяет запрет раскрытия до начала партии."""
    server = BunkerServer(host="127.0.0.1", port=0)
    client = BunkerClient()

    server.start()

    try:
        host, port = server.address
        client.connect(host, port)
        client.send(
            {
                "type": "join",
                "nickname": "Анна",
            }
        )

        wait_for_message(
            client,
            lambda message: message.get("type") == "welcome",
        )

        wait_for_message(
            client,
            lambda message: message.get("type") == "lobby_state",
        )

        client.send({"type": "reveal"})

        error = wait_for_message(
            client,
            lambda message: message.get("type") == "error",
        )

        assert "не началась" in error["message"]

    finally:
        client.close()
        server.stop()
