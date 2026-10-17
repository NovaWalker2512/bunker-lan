import socket
import threading

from bunker.network.protocol import ProtocolError, decode_message, encode_message


class BunkerServer:
    """TCP server for the Bunker LAN messaging prototype."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> None:
        """Initialize the server configuration.

        Args:
            host: Local interface address to bind to.
            port: Port to listen on. Zero selects an available port.
        """
        self.host = host
        self.port = port
        self._server_socket: socket.socket | None = None
        self._accept_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._clients: set[socket.socket] = set()
        self._clients_lock = threading.Lock()

    @property
    def address(self) -> tuple[str, int]:
        """Return the actual listening address.

        Returns:
            A tuple containing the bound host and port.

        Raises:
            RuntimeError: If the server has not been started.
        """
        if self._server_socket is None:
            raise RuntimeError("Server is not running.")

        host, port = self._server_socket.getsockname()[:2]
        return host, port

    def start(self) -> None:
        """Start listening for TCP connections.

        Raises:
            OSError: If the socket cannot be created or bound.
            RuntimeError: If the server is already running.
        """
        if self._accept_thread is not None:
            if self._accept_thread.is_alive():
                raise RuntimeError("Server is already running.")

        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
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
            name="bunker-server-accept",
            daemon=True,
        )
        self._accept_thread.start()

    def stop(self) -> None:
        """Stop the server and close active client connections."""
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
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1)

        self._accept_thread = None

    def _accept_connections(self) -> None:
        """Accept clients and start a handler for each connection."""
        server_socket = self._server_socket

        while server_socket is not None and not self._stop_event.is_set():
            try:
                connection, _ = server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            with self._clients_lock:
                self._clients.add(connection)

            threading.Thread(
                target=self._handle_client,
                args=(connection,),
                name="bunker-client-handler",
                daemon=True,
            ).start()

    def _handle_client(self, connection: socket.socket) -> None:
        """Receive messages and send responses to one client.

        Args:
            connection: An established TCP connection.
        """
        try:
            with connection.makefile("rb") as stream:
                for raw_message in stream:
                    try:
                        request = decode_message(raw_message)
                    except ProtocolError as exc:
                        response = {
                            "type": "error",
                            "message": str(exc),
                        }
                    else:
                        response = self._build_response(request)

                    connection.sendall(encode_message(response))
        except OSError:
            pass
        finally:
            with self._clients_lock:
                self._clients.discard(connection)
            connection.close()

    @staticmethod
    def _build_response(request: dict) -> dict:
        """Build a response to a valid request.

        Args:
            request: A decoded request message.

        Returns:
            A pong response or an error response.
        """
        if request["type"] == "ping":
            return {
                "type": "pong",
                "message": request.get("message", ""),
            }

        return {
            "type": "error",
            "message": f"Unsupported message type: {request['type']}",
        }
