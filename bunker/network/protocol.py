import json
from typing import Any


class ProtocolError(ValueError):
    """Raised when a network message has an invalid format."""


def encode_message(message: dict[str, Any]) -> bytes:
    """Convert a message dictionary into a UTF-8 JSON line.

    Args:
        message: Dictionary containing a message type and its data.

    Returns:
        UTF-8 encoded JSON bytes terminated by a newline.

    Raises:
        ProtocolError: If the message cannot be serialized or has no
            valid type field.
    """
    if not isinstance(message, dict):
        raise ProtocolError("Message must be a dictionary.")

    message_type = message.get("type")
    if not isinstance(message_type, str) or not message_type.strip():
        raise ProtocolError("Message must contain a non-empty type.")

    try:
        payload = json.dumps(
            message,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        return payload.encode("utf-8") + b"\n"
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ProtocolError("Message cannot be encoded as JSON.") from exc


def decode_message(data: bytes) -> dict[str, Any]:
    """Decode and validate one UTF-8 JSON message.

    Args:
        data: Bytes containing one complete JSON message.

    Returns:
        The decoded message dictionary.

    Raises:
        ProtocolError: If the data is invalid or the message type is missing.
    """
    if not isinstance(data, bytes):
        raise ProtocolError("Message data must be bytes.")

    try:
        text = data.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ProtocolError("Message must use UTF-8 encoding.") from exc

    if not text:
        raise ProtocolError("Message cannot be empty.")

    try:
        message = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProtocolError("Message contains invalid JSON.") from exc

    if not isinstance(message, dict):
        raise ProtocolError("Message must be a JSON object.")

    message_type = message.get("type")
    if not isinstance(message_type, str) or not message_type.strip():
        raise ProtocolError("Message must contain a non-empty type.")

    return message
