
"""Игровой движок кооперативной игры «Бункер»."""

from collections import Counter
from random import Random
from threading import RLock

from bunker.game.cards import (
    CARD_DECK,
    CATEGORIES,
    CATEGORY_LABELS,
    create_character,
)


class GameError(ValueError):
    """Ошибка при нарушении правил игровой партии."""


class GameManager:
    """Управляет раундами, характеристиками и голосованием."""

    def __init__(
        self,
        bunker_capacity: int = 2,
        rng: Random | None = None,
    ) -> None:
        """Создаёт игровой движок.

        Args:
            bunker_capacity: Количество мест в бункере.
            rng: Необязательный генератор случайных чисел.

        Raises:
            ValueError: Если вместимость бункера некорректна.
        """
        if (
            not isinstance(bunker_capacity, int)
            or isinstance(bunker_capacity, bool)
            or not 1 <= bunker_capacity <= 7
        ):
            raise ValueError(
                "Вместимость бункера должна быть от 1 до 7."
            )

        self.bunker_capacity = bunker_capacity
        self._rng = rng if rng is not None else Random()
        self._lock = RLock()

        self._players: list[str] = []
        self._characters: dict[str, dict[str, str]] = {}
        self._revealed: set[tuple[str, str]] = set()
        self._eliminated: set[str] = set()

        self._votes: dict[str, str] = {}
        self._tie_candidates: list[str] = []
        self._winners: list[str] = []

        self._round_index = 0
        self._phase = "waiting"

    def start(self, player_ids: list[str]) -> dict:
        """Создаёт персонажей и запускает первую фазу партии.

        Args:
            player_ids: Уникальные идентификаторы игроков.

        Returns:
            Начальное публичное состояние игры.

        Raises:
            GameError: Если состав игроков некорректен или
                партия уже запущена.
        """
        with self._lock:
            if self._phase != "waiting":
                raise GameError("Партия уже была запущена.")

            if not isinstance(player_ids, (list, tuple)):
                raise GameError("Ожидается список игроков.")

            if not 3 <= len(player_ids) <= 8:
                raise GameError(
                    "В партии должно быть от 3 до 8 игроков."
                )

            if any(
                not isinstance(player_id, str)
                or not player_id.strip()
                for player_id in player_ids
            ):
                raise GameError(
                    "Идентификаторы игроков не должны быть пустыми."
                )

            normalized_ids = [
                player_id.strip() for player_id in player_ids
            ]

            if len(set(normalized_ids)) != len(normalized_ids):
                raise GameError(
                    "Идентификаторы игроков должны быть уникальными."
                )

            if self.bunker_capacity >= len(normalized_ids):
                raise GameError(
                    "Игроков должно быть больше, чем мест в бункере."
                )

            self._players = normalized_ids
            self._characters = {
                player_id: create_character(self._rng)
                for player_id in self._players
            }
            self._phase = "reveal"

            return self.get_state()

    def reveal_attribute(self, player_id: str) -> dict:
        """Раскрывает характеристику игрока текущего раунда.

        Args:
            player_id: Идентификатор раскрывающего игрока.

        Returns:
            Обновлённое публичное состояние игры.

        Raises:
            GameError: Если сейчас нельзя раскрывать характеристики
                или игрок не может выполнить действие.
        """
        with self._lock:
            if self._phase != "reveal":
                raise GameError(
                    "Сейчас раскрывать характеристики нельзя."
                )

            self._ensure_active_player(player_id)

            category = CATEGORIES[
                self._round_index % len(CATEGORIES)
            ]
            card_key = (player_id, category)

            if card_key in self._revealed:
                raise GameError(
                    "Эта характеристика уже раскрыта."
                )

            self._revealed.add(card_key)

            active_players = self._active_players()

            if all(
                (active_id, category) in self._revealed
                for active_id in active_players
            ):
                self._phase = "voting"

            return self.get_state()

    def cast_vote(
        self,
        voter_id: str,
        target_id: str,
    ) -> dict:
        """Принимает голос игрока за исключение участника.

        Args:
            voter_id: Идентификатор голосующего.
            target_id: Идентификатор выбранного игрока.

        Returns:
            Обновлённое состояние партии после голосования.

        Raises:
            GameError: Если голосование неактивно, участник
                не может голосовать или цель выбрана неверно.
        """
        with self._lock:
            if self._phase not in ("voting", "revote"):
                raise GameError(
                    "Сейчас голосование не проводится."
                )

            self._ensure_active_player(voter_id)
            self._ensure_active_player(target_id)

            if voter_id == target_id:
                raise GameError("Нельзя голосовать за себя.")

            if voter_id in self._votes:
                raise GameError(
                    "Вы уже проголосовали в этом голосовании."
                )

            if (
                self._phase == "revote"
                and target_id not in self._tie_candidates
            ):
                raise GameError(
                    "При повторном голосовании можно выбрать "
                    "только одного из лидеров."
                )

            self._votes[voter_id] = target_id

            if all(
                player_id in self._votes
                for player_id in self._active_players()
            ):
                self._resolve_votes()

            return self.get_state()

    def get_state(self) -> dict:
        """Возвращает публичное состояние партии.

        Скрытые характеристики не передаются до их раскрытия.

        Returns:
            Словарь с фазой, раундом, игроками, раскрытыми
            характеристиками, кандидатами на исключение и победителями.
        """
        with self._lock:
            category = CATEGORIES[
                self._round_index % len(CATEGORIES)
            ]

            players = []

            for player_id in self._players:
                revealed_cards = {
                    CATEGORY_LABELS[card_category]:
                    self._characters[player_id][card_category]
                    for card_category in CATEGORIES
                    if (player_id, card_category) in self._revealed
                }

                players.append(
                    {
                        "player_id": player_id,
                        "eliminated": player_id in self._eliminated,
                        "cards": revealed_cards,
                    }
                )

            return {
                "type": "game_state",
                "phase": self._phase,
                "round": self._round_index + 1,
                "category": category,
                "category_label": CATEGORY_LABELS[category],
                "bunker_capacity": self.bunker_capacity,
                "active_player_ids": self._active_players(),
                "players": players,
                "votes_received": len(self._votes),
                "tie_candidates": list(self._tie_candidates),
                "winners": list(self._winners),
            }

    def _ensure_active_player(self, player_id: str) -> None:
        """Проверяет, что игрок участвует в партии.

        Args:
            player_id: Идентификатор игрока.

        Raises:
            GameError: Если игрок отсутствует или уже исключён.
        """
        if (
            player_id not in self._players
            or player_id in self._eliminated
        ):
            raise GameError(
                "Игрок не участвует в текущей партии."
            )

    def _active_players(self) -> list[str]:
        """Возвращает список игроков, оставшихся в партии.

        Returns:
            Идентификаторы действующих игроков в порядке подключения.
        """
        return [
            player_id
            for player_id in self._players
            if player_id not in self._eliminated
        ]

    def _resolve_votes(self) -> None:
        """Подсчитывает голоса и выполняет исключение игрока."""
        counts = Counter(self._votes.values())
        highest_score = max(counts.values())

        candidates = [
            player_id
            for player_id, score in counts.items()
            if score == highest_score
        ]

        if len(candidates) > 1 and self._phase != "revote":
            self._tie_candidates = candidates
            self._votes.clear()
            self._phase = "revote"
            return

        eliminated_id = self._rng.choice(candidates)
        self._eliminated.add(eliminated_id)

        self._votes.clear()
        self._tie_candidates.clear()

        active_players = self._active_players()

        if len(active_players) <= self.bunker_capacity:
            self._phase = "finished"
            self._winners = active_players
            return

        self._round_index = (
            self._round_index + 1
        ) % len(CATEGORIES)
        self._phase = "reveal"
