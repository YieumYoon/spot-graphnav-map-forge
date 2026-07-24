"""Small read-only protobuf wire decoder for observed private envelopes."""

from __future__ import annotations

import struct
from dataclasses import dataclass


class WireError(ValueError):
    """Raised when a protobuf wire payload is malformed."""


@dataclass(frozen=True)
class WireField:
    number: int
    wire_type: int
    value: int | bytes

    def text(self) -> str | None:
        if not isinstance(self.value, bytes):
            return None
        try:
            return self.value.decode("utf-8")
        except UnicodeDecodeError:
            return None


def decode_fields(payload: bytes) -> tuple[WireField, ...]:
    fields: list[WireField] = []
    offset = 0
    while offset < len(payload):
        tag, offset = _read_varint(payload, offset)
        number = tag >> 3
        wire_type = tag & 0x07
        if number == 0:
            raise WireError("field number 0 is invalid")
        if wire_type == 0:
            value, offset = _read_varint(payload, offset)
        elif wire_type == 1:
            end = offset + 8
            if end > len(payload):
                raise WireError("truncated fixed64 field")
            value = struct.unpack("<Q", payload[offset:end])[0]
            offset = end
        elif wire_type == 2:
            size, offset = _read_varint(payload, offset)
            end = offset + size
            if end > len(payload):
                raise WireError("truncated length-delimited field")
            value = payload[offset:end]
            offset = end
        elif wire_type == 5:
            end = offset + 4
            if end > len(payload):
                raise WireError("truncated fixed32 field")
            value = struct.unpack("<I", payload[offset:end])[0]
            offset = end
        else:
            raise WireError(f"unsupported protobuf wire type {wire_type}")
        fields.append(WireField(number, wire_type, value))
    return tuple(fields)


def bytes_values(fields: tuple[WireField, ...], number: int) -> tuple[bytes, ...]:
    return tuple(
        field.value for field in fields if field.number == number and isinstance(field.value, bytes)
    )


def text_values(fields: tuple[WireField, ...], number: int) -> tuple[str, ...]:
    values: list[str] = []
    for value in bytes_values(fields, number):
        try:
            values.append(value.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise WireError(f"field {number} is not UTF-8") from exc
    return tuple(values)


def integer_values(fields: tuple[WireField, ...], number: int) -> tuple[int, ...]:
    return tuple(
        int(field.value)
        for field in fields
        if field.number == number and isinstance(field.value, int)
    )


def _read_varint(payload: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while offset < len(payload) and shift < 70:
        byte = payload[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
        shift += 7
    raise WireError("truncated or oversized varint")
