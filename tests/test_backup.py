import io
import tarfile

from bosdyn.api import geometry_pb2
from bosdyn.api.autowalk import walks_pb2

from spot_graphnav_map_forge.archive import BackupArchive
from spot_graphnav_map_forge.backup import (
    list_actions,
    list_docks,
    list_pano_states,
    parse_map_layout,
)


def _varint(value: int) -> bytes:
    result = bytearray()
    while value >= 0x80:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.append(value)
    return bytes(result)


def _bytes_field(number: int, value: bytes) -> bytes:
    return _varint((number << 3) | 2) + _varint(len(value)) + value


def _integer_field(number: int, value: int) -> bytes:
    return _varint(number << 3) + _varint(value)


def test_parse_map_layout_reads_observed_floor_plan_control_points() -> None:
    metadata = _bytes_field(1, b"layout-1") + _bytes_field(2, b"Floor 1")
    floor_plan = _bytes_field(2, b"floor.png")
    pose = geometry_pb2.SE3Pose()
    pose.position.x = 12.5
    pose.rotation.w = 1.0
    control_point = _bytes_field(3, b"wp-1") + _bytes_field(4, pose.SerializeToString())
    layout = (
        _bytes_field(1, metadata) + _bytes_field(2, floor_plan) + _bytes_field(3, control_point)
    )

    parsed = parse_map_layout(_bytes_field(2, layout))

    assert parsed is not None
    assert parsed.id == "layout-1"
    assert parsed.floor_plan_name == "floor.png"
    assert parsed.control_points[0].waypoint_id == "wp-1"
    assert parsed.control_points[0].position[0] == 12.5


def test_list_pano_states_reads_waypoint_and_timestamp(tmp_path) -> None:
    timestamp = _integer_field(1, 1_700_000_000) + _integer_field(2, 123_000_000)
    payload = _bytes_field(1, b"wp-pano") + _bytes_field(2, timestamp)
    backup = tmp_path / "backup.tar"
    with tarfile.open(backup, "w") as archive:
        info = tarfile.TarInfo("graph_nav/waypoint_pano_states/wp-pano")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))

    with BackupArchive(backup) as archive:
        states = list_pano_states(archive)

    assert len(states) == 1
    assert states[0].waypoint_id == "wp-pano"
    assert states[0].updated_seconds == 1_700_000_000
    assert states[0].updated_nanos == 123_000_000


def test_list_actions_identifies_waypointless_triggered_ai_inspection(tmp_path) -> None:
    parent_id = "22222222-2222-4222-8222-222222222222"
    inspection_id = "11111111-1111-4111-8111-111111111111"
    trigger_source = _bytes_field(1, parent_id.encode()) + _bytes_field(2, b"camera-service")
    trigger_envelope = _bytes_field(1, trigger_source)
    parent = (
        _bytes_field(1, parent_id.encode())
        + _bytes_field(2, b"Synthetic Check")
        + _bytes_field(3, b"waypoint-1")
    )
    inspection = (
        _bytes_field(1, inspection_id.encode())
        + _bytes_field(2, b"Synthetic Check AI")
        + _bytes_field(14, trigger_envelope)
    )
    backup = tmp_path / "backup.tar"
    with tarfile.open(backup, "w") as archive:
        for name, payload in ((parent_id, parent), (inspection_id, inspection)):
            info = tarfile.TarInfo(f"graph_nav/site_element/{name}")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))

    with BackupArchive(backup) as archive:
        records = {record.id: record for record in list_actions(archive)}

    assert records[parent_id].waypoint_id == "waypoint-1"
    assert records[parent_id].trigger_parent_element_id is None
    assert records[inspection_id].waypoint_id == ""
    assert records[inspection_id].trigger_parent_element_id == parent_id
    assert records[inspection_id].trigger_image_service == "camera-service"


def test_list_actions_identifies_explicit_relocalization(tmp_path) -> None:
    relocalize_id = "11111111-1111-4111-8111-111111111111"
    ordinary_id = "22222222-2222-4222-8222-222222222222"
    relocalize = walks_pb2.Target.Relocalize()
    relocalize.set_localization_request.initial_guess.waypoint_id = "waypoint-1"
    explicit = (
        _bytes_field(1, relocalize_id.encode())
        + _bytes_field(2, b"Localize")
        + _bytes_field(3, b"waypoint-1")
        + _bytes_field(9, relocalize.SerializeToString())
    )
    ordinary = (
        _bytes_field(1, ordinary_id.encode())
        + _bytes_field(2, b"Capture")
        + _bytes_field(3, b"waypoint-2")
        + _bytes_field(9, b"")
    )
    backup = tmp_path / "backup.tar"
    with tarfile.open(backup, "w") as archive:
        for name, payload in ((relocalize_id, explicit), (ordinary_id, ordinary)):
            info = tarfile.TarInfo(f"graph_nav/site_element/{name}")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))

    with BackupArchive(backup) as archive:
        records = {record.id: record for record in list_actions(archive)}

    assert records[relocalize_id].has_explicit_relocalization
    assert not records[ordinary_id].has_explicit_relocalization


def test_list_docks_parses_public_target_and_deduplicates_revisions(tmp_path) -> None:
    target = walks_pb2.Target()
    target.navigate_to.destination_waypoint_id = "prep-wp"

    def dock_payload(record_id: str) -> bytes:
        return b"".join(
            (
                _bytes_field(1, record_id.encode()),
                _integer_field(2, 520),
                _bytes_field(3, b"docked-wp"),
                _bytes_field(4, target.SerializeToString()),
            )
        )

    backup = tmp_path / "backup.tar"
    with tarfile.open(backup, "w") as archive:
        for name, payload in (
            ("dock-a", dock_payload("dock-a")),
            ("dock-b", dock_payload("dock-b")),
            ("tombstone", _bytes_field(1, b"tombstone") + _bytes_field(4, b"")),
        ):
            info = tarfile.TarInfo(f"graph_nav/site_dock/{name}")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))

    with BackupArchive(backup) as archive:
        docks = list_docks(archive)

    assert len(docks) == 1
    assert docks[0].dock_id == 520
    assert docks[0].docked_waypoint_id == "docked-wp"
    assert docks[0].target_kind == "navigate_to"
    assert docks[0].target_waypoint_ids == ("prep-wp",)
    assert len(docks[0].target_fingerprint) == 64
