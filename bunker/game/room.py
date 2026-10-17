from dataclasses import dataclass
from threading import RLock


class RoomError(ValueError):
    """Raised when a room operation violates its rules."""


@dataclass
class Player:
    """Represent a player connected to a game room."""

    player_id: str
    nickname: str
    is_host: bool = False
    ready: bool = False

    def to_dict(self) -> dict[str, str | bool]:
        """Convert the player into a serializable dictionary.

        Returns:
            A dictionary containing public player information.
        """
        return {
            "player_id": self.player_id,
            "nickname": self.nickname,
            "is_host": self.is_host,
            "ready": self.ready,
        }


class RoomManager:
    """Manage players and readiness in a Bunker LAN room."""

    def __init__(
        self,
        max_players: int = 8,
        min_players: int = 3,
    ) -> None:
        """Initialize a room.

        Args:
            max_players: Maximum number of players, from 3 to 8.
            min_players: Minimum number required to start a game.

        Raises:
            ValueError: If the player limits are invalid.
        """
        if (
            not isinstance(max_players, int)
            or isinstance(max_players, bool)
            or not 3 <= max_players <= 8
        ):
            raise ValueError("Maximum players must be between 3 and 8.")

        if (
            not isinstance(min_players, int)
            or isinstance(min_players, bool)
            or not 2 <= min_players <= max_players
        ):
            raise ValueError("Minimum players must be between 2 and max_players.")

        self.max_players = max_players
        self.min_players = min_players
        self._players: dict[str, Player] = {}
        self._host_id: str | None = None
        self._started = False
        self._lock = RLock()

    def add_player(
        self,
        player_id: str,
        nickname: str,
    ) -> dict[str, str | bool]:
        """Add a player to the room.

        Args:
            player_id: Unique identifier assigned by the server.
            nickname: Display name chosen by the player.

        Returns:
            Public information about the added player.

        Raises:
            RoomError: If the player cannot join the room.
        """
        if not isinstance(player_id, str) or not player_id.strip():
            raise RoomError("Player ID cannot be empty.")

        if not isinstance(nickname, str):
            raise RoomError("Nickname must be a string.")

        player_id = player_id.strip()
        nickname = nickname.strip()

        if not nickname or len(nickname) > 20:
            raise RoomError("Nickname must contain 1 to 20 characters.")

        with self._lock:
            if self._started:
                raise RoomError("The game has already started.")

            if player_id in self._players:
                raise RoomError("This player is already in the room.")

            if any(
                player.nickname.casefold() == nickname.casefold()
                for player in self._players.values()
            ):
                raise RoomError("This nickname is already taken.")

            if len(self._players) >= self.max_players:
                raise RoomError("The room is full.")

            is_host = self._host_id is None
            player = Player(
                player_id=player_id,
                nickname=nickname,
                is_host=is_host,
            )

            self._players[player_id] = player

            if is_host:
                self._host_id = player_id

            return player.to_dict()

    def remove_player(self, player_id: str) -> None:
        """Remove a player and transfer host status if necessary.

        Args:
            player_id: Identifier of the player to remove.

        Raises:
            RoomError: If the player is not in the room.
        """
        with self._lock:
            if player_id not in self._players:
                raise RoomError("Player is not in the room.")

            del self._players[player_id]

            if player_id == self._host_id:
                self._host_id = next(iter(self._players), None)

            for current_id, player in self._players.items():
                player.is_host = current_id == self._host_id

            if not self._players:
                self._started = False

    def set_ready(
        self,
        player_id: str,
        ready: bool,
    ) -> dict[str, str | bool]:
        """Change a player's readiness status.

        Args:
            player_id: Identifier of the player.
            ready: Whether the player is ready to start.

        Returns:
            Updated public information about the player.

        Raises:
            RoomError: If the player or requested status is invalid.
        """
        if not isinstance(ready, bool):
            raise RoomError("Ready status must be a boolean.")

        with self._lock:
            if self._started:
                raise RoomError("The game has already started.")

            player = self._players.get(player_id)

            if player is None:
                raise RoomError("Player is not in the room.")

            player.ready = ready
            return player.to_dict()

    def start_game(self, player_id: str) -> dict:
        """Start the game if the host and all players are ready.

        Args:
            player_id: Identifier of the player requesting the start.

        Returns:
            A snapshot of the room state after starting.

        Raises:
            RoomError: If the requester is not the host or
                the room is not ready to start.
        """
        with self._lock:
            if player_id != self._host_id:
                raise RoomError("Only the host can start the game.")

            if self._started:
                raise RoomError("The game has already started.")

            if len(self._players) < self.min_players:
                raise RoomError("Not enough players to start.")

            if not all(player.ready for player in self._players.values()):
                raise RoomError("All players must be ready.")

            self._started = True
            return self.get_lobby_state()

    def get_lobby_state(self) -> dict:
        """Return a snapshot of the public room state.

        Returns:
            A dictionary containing players, limits, host and game status.
        """
        with self._lock:
            return {
                "type": "lobby_state",
                "host_id": self._host_id,
                "max_players": self.max_players,
                "min_players": self.min_players,
                "started": self._started,
                "players": [player.to_dict() for player in self._players.values()],
            }
