import pytest

from bunker.game.room import RoomError, RoomManager


def create_ready_room() -> RoomManager:
    """Create a room with three ready players."""
    room = RoomManager(max_players=4)

    room.add_player("p1", "Ulyana")
    room.add_player("p2", "Alex")
    room.add_player("p3", "Mira")

    for player_id in ("p1", "p2", "p3"):
        room.set_ready(player_id, True)

    return room


def test_first_player_becomes_host():
    room = RoomManager()

    host = room.add_player("p1", "Ulyana")
    guest = room.add_player("p2", "Alex")

    assert host["is_host"] is True
    assert guest["is_host"] is False


def test_duplicate_nickname_is_rejected():
    room = RoomManager()

    room.add_player("p1", "Ulyana")

    with pytest.raises(RoomError):
        room.add_player("p2", "ulyana")


def test_full_room_rejects_new_player():
    room = RoomManager(max_players=3)

    room.add_player("p1", "Ulyana")
    room.add_player("p2", "Alex")
    room.add_player("p3", "Mira")

    with pytest.raises(RoomError):
        room.add_player("p4", "Ivan")


def test_game_starts_when_everyone_is_ready():
    room = create_ready_room()

    state = room.start_game("p1")

    assert state["started"] is True
    assert len(state["players"]) == 3


def test_non_host_cannot_start_game():
    room = create_ready_room()

    with pytest.raises(RoomError):
        room.start_game("p2")


def test_game_cannot_start_before_everyone_is_ready():
    room = RoomManager()

    room.add_player("p1", "Ulyana")
    room.add_player("p2", "Alex")
    room.add_player("p3", "Mira")

    room.set_ready("p1", True)
    room.set_ready("p2", True)

    with pytest.raises(RoomError):
        room.start_game("p1")


def test_host_status_transfers_after_host_leaves():
    room = RoomManager()

    room.add_player("p1", "Ulyana")
    room.add_player("p2", "Alex")

    room.remove_player("p1")

    state = room.get_lobby_state()

    assert state["host_id"] == "p2"
    assert state["players"][0]["is_host"] is True


def test_invalid_player_limits_are_rejected():
    with pytest.raises(ValueError):
        RoomManager(max_players=2)

    with pytest.raises(ValueError):
        RoomManager(max_players=5, min_players=6)


def test_cannot_add_player_after_game_starts():
    room = create_ready_room()
    room.start_game("p1")

    with pytest.raises(RoomError):
        room.add_player("p4", "Ivan")
