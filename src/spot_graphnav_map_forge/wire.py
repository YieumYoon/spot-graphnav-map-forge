"""Small protobuf wire reader for proprietary envelope messages.

The backup contains a few protobuf messages whose descriptors are not public. We only decode
their outer fields and leave embedded public GraphNav protobufs to the official SDK classes.
"""

from __future__ import annotations

import struct
from collections.abc import Iterable
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


def encode_fields(fields: Iterable[WireField]) -> bytes:
    """Encode decoded fields without interpreting their message schema.

    This is used when a proprietary envelope contains public protobuf extensions that are newer
    than (or intentionally absent from) the public SDK descriptor. Values and field order are
    retained; protobuf tags and lengths are emitted in their canonical varint form.
    """
    output = bytearray()
    for field in fields:
        output.extend(_encode_varint((field.number << 3) | field.wire_type))
        if field.wire_type == 0 and isinstance(field.value, int):
            output.extend(_encode_varint(field.value))
        elif field.wire_type == 1 and isinstance(field.value, int):
            output.extend(struct.pack("<Q", field.value))
        elif field.wire_type == 2 and isinstance(field.value, bytes):
            output.extend(_encode_varint(len(field.value)))
            output.extend(field.value)
        elif field.wire_type == 5 and isinstance(field.value, int):
            output.extend(struct.pack("<I", field.value))
        else:
            raise WireError(
                f"field {field.number} has a value incompatible with wire type {field.wire_type}"
            )
    return bytes(output)


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


def rewrite_length_delimited_tokens(
    payload: bytes,
    replacements: dict[str, tuple[bytes, bytes]],
) -> tuple[bytes, dict[str, int]]:
    """Rewrite identity tokens without reserializing unrelated protobuf fields.

    Proprietary envelopes can contain the same identity in nested messages. Only exact
    length-delimited values or UTF-8 leaf strings are changed. Tags, varints, fixed-width fields,
    and untouched length-delimited values retain their original bytes.
    """
    normalized: dict[str, tuple[bytes, bytes]] = {}
    seen: set[bytes] = set()
    for label, (old, new) in replacements.items():
        if not old or old == new:
            raise ValueError(f"invalid replacement for {label}")
        if old in seen:
            raise ValueError(f"duplicate source token for {label}")
        seen.add(old)
        normalized[label] = (old, new)
    rewritten, counts = _rewrite_payload(payload, normalized, depth=0)
    return rewritten, counts


def source_token_remains(payload: bytes, old: bytes, new: bytes) -> bool:
    """Return whether an old identity remains outside occurrences of its replacement.

    A generated identity can theoretically contain the source identity as a substring. A raw
    ``old in payload`` check would then report a false leak even though every source token was
    replaced. Removing complete replacement tokens first preserves the conservative leak check
    without that false positive.
    """
    return old in payload.replace(new, b"")


def _rewrite_payload(
    payload: bytes,
    replacements: dict[str, tuple[bytes, bytes]],
    depth: int,
) -> tuple[bytes, dict[str, int]]:
    if depth > 64:
        raise WireError("protobuf nesting exceeds rewrite limit")
    counts = {label: 0 for label in replacements}
    output = bytearray()
    offset = 0
    while offset < len(payload):
        tag_start = offset
        tag, offset = _read_varint(payload, offset)
        number = tag >> 3
        wire_type = tag & 0x07
        if number == 0:
            raise WireError("field number 0 is invalid")
        output.extend(payload[tag_start:offset])
        if wire_type == 0:
            value_start = offset
            _, offset = _read_varint(payload, offset)
            output.extend(payload[value_start:offset])
        elif wire_type == 1:
            end = offset + 8
            if end > len(payload):
                raise WireError("truncated fixed64 field")
            output.extend(payload[offset:end])
            offset = end
        elif wire_type == 2:
            length_start = offset
            size, value_start = _read_varint(payload, offset)
            end = value_start + size
            if end > len(payload):
                raise WireError("truncated length-delimited field")
            value = payload[value_start:end]
            rewritten_value, nested_counts = _rewrite_value(value, replacements, depth)
            for label, count in nested_counts.items():
                counts[label] += count
            if rewritten_value == value:
                output.extend(payload[length_start:end])
            else:
                output.extend(_encode_varint(len(rewritten_value)))
                output.extend(rewritten_value)
            offset = end
        elif wire_type == 5:
            end = offset + 4
            if end > len(payload):
                raise WireError("truncated fixed32 field")
            output.extend(payload[offset:end])
            offset = end
        else:
            raise WireError(f"unsupported protobuf wire type {wire_type}")
    return bytes(output), counts


def _rewrite_value(
    value: bytes,
    replacements: dict[str, tuple[bytes, bytes]],
    depth: int,
) -> tuple[bytes, dict[str, int]]:
    counts = {label: 0 for label in replacements}
    for label, (old, new) in replacements.items():
        if value == old:
            counts[label] = 1
            return new, counts

    if not any(old in value for old, _ in replacements.values()):
        return value, counts

    try:
        return _rewrite_payload(value, replacements, depth + 1)
    except WireError:
        pass

    try:
        text = value.decode("utf-8")
    except UnicodeDecodeError:
        return value, counts
    for label, (old, new) in replacements.items():
        old_text = old.decode("utf-8")
        new_text = new.decode("utf-8")
        count = text.count(old_text)
        if count:
            text = text.replace(old_text, new_text)
            counts[label] += count
    return text.encode("utf-8"), counts


def _encode_varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("varint cannot encode a negative value")
    output = bytearray()
    while value > 0x7F:
        output.append((value & 0x7F) | 0x80)
        value >>= 7
    output.append(value)
    return bytes(output)


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
