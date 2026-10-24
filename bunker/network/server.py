import socket
import threading
import uuid

from bunker.game.game import GameError, GameManager

from bunker.game.room import RoomError, RoomManager
from bunker.network.protocol import (
    ProtocolError,
    decode_message,
    encode_message,
)


class BunkerServer:
    """Manage TCP connections and a shared game lobby."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        max_players: int = 8,
        min_players: int = 3,
    ) -> None:
        """Initialize the server and its room.

        Args:
            host: Network interface address to listen on.
            port: TCP port; zero selects an available port.
            max_players: Maximum number of players in the room.
            min_players: Minimum number required to start.
        """
        self.host = host
        self.port = port
        self.room = RoomManager(max_players, min_players)
        self.game: GameManager | None = None

        self._server_socket = None
        self._accept_thread = None
        self._stop_event = threading.Event()

        self._clients = set()
        self._client_players = {}
        self._send_locks = {}
        self._clients_lock = threading.Lock()
        self._state_lock = threading.RLock()

    @property
    def address(self) -> tuple[str, int]:
        """Return the actual listening address.

        Returns:
            A tuple containing the bound host and port.

        Raises:
            RuntimeError: If the server is not running.
        """
        if self._server_socket is None:
            raise RuntimeError("Server is not running.")

        host, port = self._server_socket.getsockname()[:2]
        return host, port

    def start(self) -> None:
        """Start accepting incoming TCP connections.

        Raises:
            RuntimeError: If the server is already running.
            OSError: If the listening socket cannot be created.
        """
        if self._accept_thread is not None and self._accept_thread.is_alive():
            raise RuntimeError("Server is already running.")

        server_socket = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM,
        )

        try:
            server_socket.setsockopt(
                socket.SOL_SOCKET,
                socket.SO_REUSEADDR,
                1,
            )
            server_socket.bind((self.host, self.port))
            server_socket.listen()
            server_socket.settimeout(0.2)
        except OSError:
            server_socket.close()
            raise

        self._server_socket = server_socket
        self._stop_event.clear()

        self._accept_thread = threading.Thread(
            target=self._accept_connections,
            args=(server_socket,),
            daemon=True,
        )
        self._accept_thread.start()

    def stop(self) -> None:
        """Stop the server and close connected clients."""
        self._stop_event.set()

        server_socket = self._server_socket
        self._server_socket = None

        if server_socket is not None:
            server_socket.close()

        with self._clients_lock:
            clients = list(self._clients)

        for connection in clients:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            finally:
                connection.close()

        thread = self._accept_thread
        if thread is not None:
            thread.join(timeout=1)

        self._accept_thread = None

    def _accept_connections(
        self,
        server_socket: socket.socket,
    ) -> None:
        """Accept clients and start their message handlers.

        Args:
            server_socket: The listening TCP socket.
        """
        while not self._stop_event.is_set():
            try:
                connection, _ = server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            with self._clients_lock:
                self._clients.add(connection)
                self._send_locks[connection] = threading.Lock()

            threading.Thread(
                target=self._handle_client,
                args=(connection,),
                daemon=True,
            ).start()

    def _send_to_client(
        self,
        connection: socket.socket,
        message: dict,
    ) -> bool:
        """Send one JSON message to a connected client.

        Args:
            connection: Client socket.
            message: Message dictionary.

        Returns:
            True if sending succeeded, otherwise False.
        """
        with self._clients_lock:
            send_lock = self._send_locks.get(connection)

        if send_lock is None:
            return False

        try:
            payload = encode_message(message)
            with send_lock:
                connection.sendall(payload)
            return True
        except (OSError, ProtocolError):
            return False

    def _broadcast_lobby_state(self) -> None:
        """Send the current public room state to every client."""
        if self._stop_event.is_set():
            return

        state = self.room.get_lobby_state()

        with self._clients_lock:
            clients = list(self._clients)

        for connection in clients:
            self._send_to_client(connection, state)

    def _broadcast_game_state(self) -> None:
        """Отправляет состояние игровой партии всем подключённым клиентам."""
        if self._stop_event.is_set() or self.game is None:
            return

        state = self.game.get_state()

        with self._clients_lock:
            clients = list(self._clients)

        for connection in clients:
            self._send_to_client(connection, state)

    def _handle_client(self, connection: socket.socket) -> None:
        """Read and process messages from one client.

        Args:
            connection: An established client socket.
        """
        try:
            with connection.makefile("rb") as stream:
                for raw_message in stream:
                    try:
                        request = decode_message(raw_message)
                    except ProtocolError as exc:
                        self._send_to_client(
                            connection,
                            {
                                "type": "error",
                                "message": str(exc),
                            },
                        )
                        continue

                    if not self._process_message(connection, request):
                        break
        except (OSError, ValueError):
            pass
        finally:
            self._remove_client(connection)
            connection.close()

    def _process_message(
        self,
        connection: socket.socket,
        request: dict,
    ) -> bool:
        """Process a client request.

        Args:
            connection: Socket that sent the request.
            request: Decoded JSON message.

        Returns:
            False if the client should disconnect, otherwise True.
        """
        message_type = request["type"]

        if message_type == "ping":
            self._send_to_client(
                connection,
                {
                    "type": "pong",
                    "message": request.get("message", ""),
                },
            )
            return True

        if message_type == "join":
            return self._join_client(connection, request)

        if message_type == "ready":
            with self._state_lock:
                player_id = self._get_player_id(connection)

                if player_id is None:
                    self._send_error(
                        connection,
                        "Join the room before sending actions.",
                    )
                    return True

                try:
                    self.room.set_ready(
                        player_id,
                        request.get("ready"),
                    )
                except RoomError as exc:
                    self._send_error(connection, str(exc))
                    return True

                self._broadcast_lobby_state()
            return True

        if message_type == "start":
            with self._state_lock:
                player_id = self._get_player_id(connection)

                if player_id is None:
                    self._send_error(
                        connection,
                        "Сначала необходимо присоединиться к комнате.",
                    )
                    return True

                current_state = self.room.get_lobby_state()

                if len(current_state["players"]) < 3:
                    self._send_error(
                        connection,
                        "Для начала партии необходимо минимум 3 игрока.",
                    )
                    return True

                try:
                    lobby_state = self.room.start_game(player_id)

                    game = GameManager(bunker_capacity=2)
                    game.start(
                        [
                            player["player_id"]
                            for player in lobby_state["players"]
                        ]
                    )
                except (RoomError, GameError) as exc:
                    self._send_error(connection, str(exc))
                    return True

                self.game = game
                self._broadcast_game_state()

            return True

        if message_type == "reveal":
            with self._state_lock:
                player_id = self._get_player_id(connection)

                if player_id is None:
                    self._send_error(
                        connection,
                        "Сначала необходимо присоединиться к комнате.",
                    )
                    return True

                if self.game is None:
                    self._send_error(
                        connection,
                        "Партия ещё не началась.",
                    )
                    return True

                try:
                    self.game.reveal_attribute(player_id)
                except GameError as exc:
                    self._send_error(connection, str(exc))
                    return True

                self._broadcast_game_state()

            return True

        if message_type == "vote":
            with self._state_lock:
                player_id = self._get_player_id(connection)

                if player_id is None:
                    self._send_error(
                        connection,
                        "Сначала необходимо присоединиться к комнате.",
                    )
                    return True

                if self.game is None:
                    self._send_error(
                        connection,
                        "Партия ещё не началась.",
                    )
                    return True

                target_id = request.get("target_id")

                try:
                    self.game.cast_vote(player_id, target_id)
                except GameError as exc:
                    self._send_error(connection, str(exc))
                    return True

                self._broadcast_game_state()

            return True

        if message_type == "leave":
            self._send_to_client(connection, {"type": "left"})
            return False

        self._send_error(
            connection,
            f"Unsupported message type: {message_type}",
        )
        return True

    def _join_client(
        self,
        connection: socket.socket,
        request: dict,
    ) -> bool:
        """Register a client and notify all room participants.

        Args:
            connection: Socket requesting to join.
            request: Join request containing the nickname.

        Returns:
            True to keep the connection open.
        """
        with self._state_lock:
            if self._get_player_id(connection) is not None:
                self._send_error(
                    connection,
                    "This connection has already joined.",
                )
                return True

            nickname = request.get("nickname")

            if not isinstance(nickname, str):
                self._send_error(
                    connection,
                    "Nickname must be a string.",
                )
                return True

            player_id = uuid.uuid4().hex

            try:
                player = self.room.add_player(
                    player_id,
                    nickname,
                )
            except RoomError as exc:
                self._send_error(connection, str(exc))
                return True

            with self._clients_lock:
                self._client_players[connection] = player_id

            self._send_to_client(
                connection,
                {
                    "type": "welcome",
                    "player_id": player_id,
                    "host_id": (player_id if player["is_host"] else None),
                },
            )
            self._broadcast_lobby_state()

        return True

    def _get_player_id(
        self,
        connection: socket.socket,
    ) -> str | None:
        """Find the player associated with a connection.

        Args:
            connection: Client socket.

        Returns:
            Player ID or None if the client has not joined.
        """
        with self._clients_lock:
            return self._client_players.get(connection)

    def _send_error(
        self,
        connection: socket.socket,
        message: str,
    ) -> None:
        """Send a structured error message to a client.

        Args:
            connection: Client socket.
            message: Human-readable error description.
        """
        self._send_to_client(
            connection,
            {
                "type": "error",
                "message": message,
            },
        )

    def _remove_client(
        self,
        connection: socket.socket,
    ) -> None:
        """Remove a disconnected client and update the lobby."""
        with self._state_lock:
            with self._clients_lock:
                self._clients.discard(connection)
                self._send_locks.pop(connection, None)
                player_id = self._client_players.pop(
                    connection,
                    None,
                )

            if player_id is not None:
                try:
                    self.room.remove_player(player_id)
                except RoomError:
                    pass

                self._broadcast_lobby_state()
