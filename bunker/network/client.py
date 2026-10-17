
import queue
import socket
import threading
from typing import Any

from bunker.network.protocol import (
    ProtocolError,
    decode_message,
    encode_message,
)


class BunkerClient:
    """Управляет постоянным TCP-соединением с игровым сервером."""

    def __init__(self) -> None:
        """Создаёт клиент без установленного соединения."""
        self._socket: socket.socket | None = None
        self._receiver_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._messages: queue.Queue[dict[str, Any]] = queue.Queue()
        self._send_lock = threading.Lock()

    @property
    def connected(self) -> bool:
        """Возвращает True, если клиент считает соединение активным."""
        return (
            self._socket is not None
            and not self._stop_event.is_set()
        )

    def connect(
        self,
        host: str,
        port: int,
        timeout: float = 3.0,
    ) -> None:
        """Подключается к серверу и запускает приём сообщений.

        Args:
            host: IP-адрес или имя сервера.
            port: TCP-порт сервера.
            timeout: Максимальное время установления соединения.

        Raises:
            OSError: Если подключение не удалось.
            RuntimeError: Если клиент уже подключён.
            ValueError: Если параметры подключения некорректны.
        """
        if self._socket is not None:
            raise RuntimeError("Клиент уже подключён.")

        if not 1 <= port <= 65535:
            raise ValueError("Порт должен быть от 1 до 65535.")

        if timeout <= 0:
            raise ValueError("Время ожидания должно быть положительным.")

        connection = socket.create_connection(
            (host, port),
            timeout=timeout,
        )
        connection.settimeout(None)

        self._stop_event.clear()
        self._socket = connection

        self._receiver_thread = threading.Thread(
            target=self._receive_messages,
            args=(connection,),
            name="bunker-client-receiver",
            daemon=True,
        )
        self._receiver_thread.start()

    def send(self, message: dict[str, Any]) -> None:
        """Отправляет JSON-сообщение серверу.

        Args:
            message: Словарь с типом сообщения и его данными.

        Raises:
            RuntimeError: Если клиент не подключён.
            ProtocolError: Если сообщение нельзя сериализовать.
            OSError: Если отправка завершилась ошибкой.
        """
        connection = self._socket

        if connection is None or self._stop_event.is_set():
            raise RuntimeError("Клиент не подключён.")

        payload = encode_message(message)

        with self._send_lock:
            connection.sendall(payload)

    def receive(self, timeout: float | None = None) -> dict[str, Any]:
        """Возвращает следующее сообщение из входящей очереди.

        Args:
            timeout: Максимальное ожидание в секундах.
                None означает ожидание без ограничения времени.

        Returns:
            Полученное сообщение в виде словаря.

        Raises:
            queue.Empty: Если сообщение не поступило вовремя.
        """
        return self._messages.get(timeout=timeout)

    def _receive_messages(self, connection: socket.socket) -> None:
        """Принимает сообщения сервера в фоновом потоке.

        Args:
            connection: Сокет установленного соединения.
        """
        buffer = bytearray()

        while not self._stop_event.is_set():
            try:
                chunk = connection.recv(4096)
            except OSError:
                if not self._stop_event.is_set():
                    self._messages.put(
                        {
                            "type": "disconnected",
                            "message": "Соединение с сервером прервано.",
                        }
                    )
                break

            if not chunk:
                if not self._stop_event.is_set():
                    self._messages.put(
                        {
                            "type": "disconnected",
                            "message": "Сервер закрыл соединение.",
                        }
                    )
                break

            buffer.extend(chunk)

            while b"\n" in buffer:
                raw_message, _, remainder = buffer.partition(b"\n")
                buffer = bytearray(remainder)

                if not raw_message.strip():
                    continue

                try:
                    message = decode_message(bytes(raw_message))
                except ProtocolError as exc:

                    self._messages.put(
                        {
                            "type": "client_error",
                            "message": str(exc),
                        }
                    )
                    continue

                self._messages.put(message)

    def close(self) -> None:
        """Закрывает соединение и останавливает поток приёма."""
        self._stop_event.set()

        connection = self._socket
        self._socket = None

        if connection is not None:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            finally:
                connection.close()

        thread = self._receiver_thread

        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1)

        self._receiver_thread = None


def send_request(
    host: str,
    port: int,
    message: dict[str, Any],
    timeout: float = 2.0,
) -> dict[str, Any]:
    """Отправляет один запрос и получает один ответ.

    Функция сохранена для совместимости с существующими тестами.

    Args:
        host: IP-адрес или имя сервера.
        port: TCP-порт сервера.
        message: Словарь с запросом.
        timeout: Максимальное время ожидания ответа.

    Returns:
        Словарь с ответом сервера.

    Raises:
        OSError: Если подключение или передача данных не удались.
        queue.Empty: Если ответ не поступил вовремя.
        ProtocolError: Если сообщение имеет неверный формат.
    """
    client = BunkerClient()

    try:
        client.connect(host, port, timeout=timeout)
        client.send(message)
        return client.receive(timeout=timeout)
    finally:
        client.close()
