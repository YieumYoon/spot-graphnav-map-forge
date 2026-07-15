import io
import math
import tarfile

import pytest
from bosdyn.api import geometry_pb2
from bosdyn.api.autowalk import walks_pb2
from bosdyn.api.graph_nav import map_pb2

from spot_graphnav_map_forge.archive import BackupArchive
from spot_graphnav_map_forge.backup import (
    graph_with_layout_projection,
    list_actions,
    list_docks,
    list_pano_states,
    list_site_maps,
    parse_map_layout,
    reconstruct_final_graph,
    walk_target_opaque_profile,
)
from spot_graphnav_map_forge.wire import bytes_values, decode_fields


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


def test_parse_map_layout_is_not_named_site_view() -> None:
    metadata = _bytes_field(1, b"layout-1") + _bytes_field(2, b"Floor 1")
    floor_plan = _bytes_field(2, b"floor.png")
    pose = geometry_pb2.SE3Pose()
    pose.position.x = 12.5
    pose.rotation.w = 1.0
    control_point = _bytes_field(3, b"wp-1") + _bytes_field(4, pose.SerializeToString())
    layout = (
        _bytes_field(1, metadata) + _bytes_field(2, floor_plan) + _bytes_field(3, control_point)
    )
    site_map_payload = _bytes_field(2, layout)

    parsed = parse_map_layout(site_map_payload)

    assert parsed is not None
    assert parsed.id == "layout-1"
    assert parsed.floor_plan_name == "floor.png"
    assert parsed.control_points[0].waypoint_id == "wp-1"
    assert parsed.control_points[0].position[0] == 12.5


def test_layout_projection_does_not_mutate_graph() -> None:
    metadata = _bytes_field(1, b"layout-1") + _bytes_field(2, b"Floor 1")
    pose = geometry_pb2.SE3Pose()
    pose.rotation.w = 1.0
    control_point = _bytes_field(3, b"wp-1") + _bytes_field(4, pose.SerializeToString())
    layout = _bytes_field(1, metadata) + _bytes_field(3, control_point)
    parsed = parse_map_layout(_bytes_field(2, layout))
    graph = map_pb2.Graph()
    graph.waypoints.add(id="wp-1")

    projected = graph_with_layout_projection(graph, parsed)

    assert len(graph.anchoring.anchors) == 0
    assert projected.anchoring.anchors[0].id == "wp-1"


def test_list_pano_states_reads_waypoint_and_timestamp(tmp_path) -> None:
    timestamp = _integer_field(1, 1_781_812_110) + _integer_field(2, 709_186_949)
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
    assert states[0].updated_seconds == 1_781_812_110
    assert states[0].updated_nanos == 709_186_949


def test_list_actions_identifies_waypointless_triggered_ai_inspection(tmp_path) -> None:
    parent_id = "22222222-2222-4222-8222-222222222222"
    inspection_id = "11111111-1111-4111-8111-111111111111"
    trigger_source = _bytes_field(1, parent_id.encode()) + _bytes_field(2, b"spot-cam-ptz")
    trigger_envelope = _bytes_field(1, trigger_source)
    parent = (
        _bytes_field(1, parent_id.encode())
        + _bytes_field(2, b"Door Check")
        + _bytes_field(3, b"waypoint-1")
    )
    inspection = (
        _bytes_field(1, inspection_id.encode())
        + _bytes_field(2, b"Door Check (AI)")
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
    assert records[inspection_id].trigger_image_service == "spot-cam-ptz"


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


def test_reconstruct_final_graph_retains_edited_edges_and_excludes_tombstones(tmp_path) -> None:
    map_id = "site-map-1"
    waypoint_ids = ("wp-1", "wp-2", "wp-3", "wp-4")
    metadata = _bytes_field(1, map_id.encode()) + _bytes_field(2, b"Test Map")
    site_map_payload = _bytes_field(1, metadata) + b"".join(
        _bytes_field(4, waypoint_id.encode()) for waypoint_id in waypoint_ids
    )

    def edge_payload(source: str, target: str, *, flags: tuple[int, ...] = ()) -> bytes:
        edge = map_pb2.Edge()
        edge.id.from_waypoint = source
        edge.id.to_waypoint = target
        if flags == (3,):
            edge.annotations.disable_directed_exploration = True
            edge.annotations.disable_alternate_route_finding = True
        payload = _bytes_field(1, map_id.encode()) + _bytes_field(2, edge.SerializeToString())
        for flag in flags:
            payload += _integer_field(flag, 1)
        return payload

    backup = tmp_path / "backup.tar"
    with tarfile.open(backup, "w") as archive:
        records = [("graph_nav/site_maps/site-map-1", site_map_payload)]
        records.extend(
            (
                f"graph_nav/waypoints/{waypoint_id}",
                map_pb2.Waypoint(id=waypoint_id).SerializeToString(),
            )
            for waypoint_id in waypoint_ids
        )
        records.extend(
            (
                ("graph_nav/site_edges/active", edge_payload("wp-1", "wp-2")),
                ("graph_nav/site_edges/edited", edge_payload("wp-2", "wp-3", flags=(3,))),
                ("graph_nav/site_edges/tombstone", edge_payload("wp-1", "wp-3", flags=(4,))),
                (
                    "graph_nav/site_edges/edited-tombstone",
                    edge_payload("wp-3", "wp-4", flags=(3, 4)),
                ),
            )
        )
        for name, payload in records:
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))

    with BackupArchive(backup) as archive:
        site_map = list_site_maps(archive)[0]
        graph, _, _, selection_only_edges = reconstruct_final_graph(archive, site_map)

    assert [waypoint.id for waypoint in graph.waypoints] == list(waypoint_ids)
    assert [(edge.id.from_waypoint, edge.id.to_waypoint) for edge in graph.edges] == [
        ("wp-1", "wp-2"),
        ("wp-2", "wp-3"),
    ]
    edited = graph.edges[1]
    assert edited.annotations.disable_directed_exploration
    assert edited.annotations.disable_alternate_route_finding
    assert selection_only_edges == (("wp-2", "wp-3"),)


def test_reconstruct_final_graph_normalizes_site_edge_rotation(tmp_path) -> None:
    map_id = "site-map-1"
    metadata = _bytes_field(1, map_id.encode()) + _bytes_field(2, b"Test Map")
    site_map_payload = (
        _bytes_field(1, metadata) + _bytes_field(4, b"wp-1") + _bytes_field(4, b"wp-2")
    )
    edge = map_pb2.Edge()
    edge.id.from_waypoint = "wp-1"
    edge.id.to_waypoint = "wp-2"
    rotation = edge.from_tform_to.rotation
    rotation.x = -0.014272618107497692
    rotation.y = 0.004113393370062113
    rotation.z = 0.7441347241401672
    rotation.w = 0.6678644418716431
    site_edge = _bytes_field(1, map_id.encode()) + _bytes_field(2, edge.SerializeToString())
    backup = tmp_path / "backup.tar"
    with tarfile.open(backup, "w") as archive:
        records = (
            ("graph_nav/site_maps/site-map-1", site_map_payload),
            ("graph_nav/waypoints/wp-1", map_pb2.Waypoint(id="wp-1").SerializeToString()),
            ("graph_nav/waypoints/wp-2", map_pb2.Waypoint(id="wp-2").SerializeToString()),
            ("graph_nav/site_edges/manual", site_edge),
        )
        for name, payload in records:
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))

    with BackupArchive(backup) as archive:
        graph, _, _, _ = reconstruct_final_graph(archive, list_site_maps(archive)[0])

    normalized = graph.edges[0].from_tform_to.rotation
    norm = math.sqrt(normalized.x**2 + normalized.y**2 + normalized.z**2 + normalized.w**2)
    assert norm == pytest.approx(1.0, abs=1e-15)
    assert normalized.x == pytest.approx(-0.014272617907535865)


def test_walk_target_opaque_profile_uses_site_walk_consensus(tmp_path) -> None:
    travel = (
        _integer_field(5, 1)
        + _bytes_field(12, b"opaque-travel-12")
        + _bytes_field(13, b"opaque-travel-13")
    )
    target_field_4 = b"opaque-target-4"
    backup = tmp_path / "backup.tar"
    with tarfile.open(backup, "w") as archive:
        for name, updated in (("older", 10), ("newer", 20)):
            payload = (
                _bytes_field(1, name.encode())
                + _integer_field(8, updated)
                + _bytes_field(14, travel)
                + _bytes_field(15, target_field_4)
            )
            info = tarfile.TarInfo(f"graph_nav/site_walk/{name}")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))

    with BackupArchive(backup) as archive:
        profile = walk_target_opaque_profile(archive)

    assert profile is not None
    assert profile.selection == "site_walk_consensus"
    assert profile.source_path == "graph_nav/site_walk/newer"
    assert profile.observed_source_records == 2
    assert profile.travel_params_field_numbers == (12, 13)
    assert profile.target_field_numbers == (4,)
    assert [field.number for field in decode_fields(profile.travel_params_fields)] == [12, 13]
    assert [field.number for field in decode_fields(profile.target_fields)] == [4]


def test_walk_target_opaque_profile_rejects_conflicting_values(tmp_path) -> None:
    backup = tmp_path / "backup.tar"
    with tarfile.open(backup, "w") as archive:
        for name, opaque in (("one", b"first"), ("two", b"second")):
            payload = _bytes_field(14, _bytes_field(12, opaque)) + _bytes_field(15, b"target")
            info = tarfile.TarInfo(f"graph_nav/site_walk/{name}")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))

    with (
        BackupArchive(backup) as archive,
        pytest.raises(ValueError, match="opaque Target defaults conflict"),
    ):
        walk_target_opaque_profile(archive)


def test_walk_target_opaque_profile_prefers_scoped_site_dock_consensus(tmp_path) -> None:
    def dock_payload(waypoint_id: str, marker: bytes) -> bytes:
        target = walks_pb2.Target()
        target.navigate_to.destination_waypoint_id = waypoint_id
        target.navigate_to.travel_params.MergeFromString(_bytes_field(12, marker))
        target.MergeFromString(_bytes_field(4, b"target-" + marker))
        return _bytes_field(3, waypoint_id.encode()) + _bytes_field(4, target.SerializeToString())

    backup = tmp_path / "backup.tar"
    with tarfile.open(backup, "w") as archive:
        records = (
            ("graph_nav/site_dock/in-scope", dock_payload("wp-in", b"in")),
            ("graph_nav/site_dock/out-of-scope", dock_payload("wp-out", b"out")),
            (
                "graph_nav/site_walk/conflicting-one",
                _bytes_field(14, _bytes_field(12, b"walk-one"))
                + _bytes_field(15, b"walk-target-one"),
            ),
            (
                "graph_nav/site_walk/conflicting-two",
                _bytes_field(14, _bytes_field(12, b"walk-two"))
                + _bytes_field(15, b"walk-target-two"),
            ),
        )
        for path, payload in records:
            info = tarfile.TarInfo(path)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))

    with BackupArchive(backup) as archive:
        profile = walk_target_opaque_profile(archive, site_map_waypoint_ids={"wp-in"})

    assert profile is not None
    assert profile.selection == "site_map_dock_consensus"
    assert profile.observed_source_records == 1
    assert bytes_values(decode_fields(profile.travel_params_fields), 12) == (b"in",)
    assert bytes_values(decode_fields(profile.target_fields), 4) == (b"target-in",)
