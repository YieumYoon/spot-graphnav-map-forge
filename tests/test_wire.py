from spot_graphnav_map_forge.wire import WireError, WireField, decode_fields, encode_fields


def test_decode_common_wire_types() -> None:
    fields = decode_fields(b"\x08\x96\x01\x12\x03map\x1d\x78\x56\x34\x12")
    assert [(field.number, field.wire_type, field.value) for field in fields] == [
        (1, 0, 150),
        (2, 2, b"map"),
        (3, 5, 0x12345678),
    ]


def test_rejects_truncated_field() -> None:
    try:
        decode_fields(b"\x12\x05abc")
    except WireError as exc:
        assert "truncated" in str(exc)
    else:
        raise AssertionError("expected WireError")


def test_encode_fields_round_trips_supported_wire_types() -> None:
    fields = (
        WireField(1, 0, 150),
        WireField(2, 2, b"map"),
        WireField(3, 5, 0x12345678),
        WireField(4, 1, 0x0123456789ABCDEF),
    )

    encoded = encode_fields(fields)

    assert decode_fields(encoded) == fields
