import pytest

from bunker.network.protocol import (
    ProtocolError,
    decode_message,
    encode_message,
)


def test_encode_and_decode_message():
    message = {"type": "ping", "message": "Привет"}

    encoded = encode_message(message)

    assert encoded.endswith(b"\n")
    assert decode_message(encoded) == message


@pytest.mark.parametrize(
    "message",
    [
        {},
        {"type": ""},
        {"type": 123},
    ],
)
def test_encode_rejects_invalid_message(message):
    with pytest.raises(ProtocolError):
        encode_message(message)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not-json",
        b"\xff",
        b"[]",
        b'{"message": "missing type"}',
    ],
)
def test_decode_rejects_invalid_message(data):
    with pytest.raises(ProtocolError):
        decode_message(data)


def test_encode_rejects_non_serializable_values():
    with pytest.raises(ProtocolError):
        encode_message({"type": "test", "value": object()})
