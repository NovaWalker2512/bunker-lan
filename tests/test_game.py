
"""Тесты игрового движка «Бункер»."""

import pytest

from bunker.game.game import GameError, GameManager


def prepare_game(
    player_ids: list[str] | None = None,
) -> GameManager:
    """Создаёт партию и раскрывает характеристики первого раунда.

    Args:
        player_ids: Идентификаторы участников.

    Returns:
        Игровой движок в фазе голосования.
    """
    game = GameManager()
    players = player_ids or ["p1", "p2", "p3"]
    game.start(players)

    for player_id in players:
        game.reveal_attribute(player_id)

    return game


def test_game_requires_at_least_three_players():
    """Проверяет минимальное количество участников."""
    game = GameManager()

    with pytest.raises(GameError):
        game.start(["p1", "p2"])


def test_game_rejects_duplicate_player_ids():
    """Проверяет уникальность идентификаторов."""
    game = GameManager()

    with pytest.raises(GameError):
        game.start(["p1", "p1", "p2"])


def test_game_starts_in_reveal_phase():
    """Проверяет начальную фазу и скрытие характеристик."""
    game = GameManager()
    state = game.start(["p1", "p2", "p3"])

    assert state["phase"] == "reveal"
    assert state["category"] == "profession"
    assert len(state["players"]) == 3

    for player in state["players"]:
        assert player["cards"] == {}


def test_all_players_must_reveal_before_voting():
    """Проверяет переход к голосованию после раскрытия карт."""
    game = GameManager()
    game.start(["p1", "p2", "p3"])

    game.reveal_attribute("p1")
    game.reveal_attribute("p2")

    assert game.get_state()["phase"] == "reveal"

    state = game.reveal_attribute("p3")

    assert state["phase"] == "voting"

    for player in state["players"]:
        assert "Профессия" in player["cards"]


def test_player_cannot_reveal_same_card_twice():
    """Проверяет запрет повторного раскрытия."""
    game = GameManager()
    game.start(["p1", "p2", "p3"])
    game.reveal_attribute("p1")

    with pytest.raises(GameError):
        game.reveal_attribute("p1")


def test_player_cannot_vote_for_themselves():
    """Проверяет запрет голосования за себя."""
    game = prepare_game()

    with pytest.raises(GameError):
        game.cast_vote("p1", "p1")


def test_player_cannot_vote_twice():
    """Проверяет запрет повторного голоса."""
    game = prepare_game()
    game.cast_vote("p1", "p2")

    with pytest.raises(GameError):
        game.cast_vote("p1", "p3")


def test_game_finishes_when_bunker_is_full():
    """Проверяет завершение партии после исключения игрока."""
    game = prepare_game()

    game.cast_vote("p1", "p2")
    game.cast_vote("p2", "p1")
    state = game.cast_vote("p3", "p1")

    assert state["phase"] == "finished"
    assert state["active_player_ids"] == ["p2", "p3"]
    assert set(state["winners"]) == {"p2", "p3"}


def test_tie_starts_a_revote():
    """Проверяет переход к повторному голосованию."""
    game = prepare_game()

    game.cast_vote("p1", "p2")
    game.cast_vote("p2", "p3")
    state = game.cast_vote("p3", "p1")

    assert state["phase"] == "revote"
    assert set(state["tie_candidates"]) == {"p1", "p2", "p3"}


def test_revote_eliminates_one_of_the_tied_players():
    """Проверяет разрешение ничьей повторным голосованием."""
    game = prepare_game()

    game.cast_vote("p1", "p2")
    game.cast_vote("p2", "p3")
    game.cast_vote("p3", "p1")

    game.cast_vote("p1", "p2")
    game.cast_vote("p2", "p1")
    state = game.cast_vote("p3", "p1")

    assert state["phase"] == "finished"
    assert "p1" not in state["active_player_ids"]


def test_game_continues_with_another_round():
    """Проверяет продолжение игры, если мест ещё недостаточно."""
    game = GameManager(bunker_capacity=2)
    game.start(["p1", "p2", "p3", "p4"])

    for player_id in ["p1", "p2", "p3", "p4"]:
        game.reveal_attribute(player_id)

    game.cast_vote("p1", "p2")
    game.cast_vote("p2", "p1")
    game.cast_vote("p3", "p1")
    state = game.cast_vote("p4", "p1")

    assert state["phase"] == "reveal"
    assert state["round"] == 2
    assert state["active_player_ids"] == ["p2", "p3", "p4"]


def test_unknown_player_cannot_reveal():
    """Проверяет обработку действий неизвестного игрока."""
    game = GameManager()
    game.start(["p1", "p2", "p3"])

    with pytest.raises(GameError):
        game.reveal_attribute("unknown")


def test_invalid_bunker_capacity_is_rejected():
    """Проверяет допустимые значения вместимости."""
    with pytest.raises(ValueError):
        GameManager(bunker_capacity=0)

    with pytest.raises(ValueError):
        GameManager(bunker_capacity=8)

def test_history_records_reveals_and_elimination():
    """Проверяет запись раскрытия характеристик и исключения."""
    game = prepare_game()

    state = game.get_state()
    reveal_events = [
        event
        for event in state["history"]
        if event["type"] == "reveal"
    ]

    assert len(reveal_events) == 3
    assert all("player_id" in event for event in reveal_events)
    assert all("category" in event for event in reveal_events)
    assert all("value" in event for event in reveal_events)

    game.cast_vote("p1", "p2")
    game.cast_vote("p2", "p1")
    state = game.cast_vote("p3", "p1")

    elimination_events = [
        event
        for event in state["history"]
        if event["type"] == "elimination"
    ]

    assert len(elimination_events) == 1
    assert elimination_events[0]["player_id"] == "p1"
    assert elimination_events[0]["votes"] == 2

    assert any(
        event["type"] == "finished"
        for event in state["history"]
    )


def test_history_records_tie_before_revote():
    """Проверяет запись ничьей перед повторным голосованием."""
    game = prepare_game()

    game.cast_vote("p1", "p2")
    game.cast_vote("p2", "p3")
    state = game.cast_vote("p3", "p1")

    assert state["phase"] == "revote"

    tie_events = [
        event
        for event in state["history"]
        if event["type"] == "tie"
    ]

    assert len(tie_events) == 1
    assert set(tie_events[0]["player_ids"]) == {"p1", "p2", "p3"}
