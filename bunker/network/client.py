import socket

from bunker.network.protocol import decode_message, encode_message


def send_request(
    host: str,
    port: int,
    message: dict,
    timeout: float = 2.0,
) -> dict:
    """Send one request and receive one response.

    Args:
        host: Server IP address or hostname.
        port: Server TCP port.
        message: Request dictionary.
        timeout: Maximum wait time for socket operations in seconds.

    Returns:
        The decoded server response.

    Raises:
        OSError: If connection or data transfer fails.
        ValueError: If the received response has an invalid format.
    """
    with socket.create_connection((host, port), timeout=timeout) as connection:
        connection.sendall(encode_message(message))

        with connection.makefile("rb") as stream:
            response_data = stream.readline()

        if not response_data:
            raise ConnectionError("Server closed the connection.")

        return decode_message(response_data)
