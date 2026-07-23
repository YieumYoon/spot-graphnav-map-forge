import io
import json
import tarfile

from bosdyn.api.graph_nav import map_pb2

from spot_graphnav_map_forge.archive import BackupArchive
from spot_graphnav_map_forge.backup import list_site_maps
from spot_graphnav_map_forge.cli import main
from spot_graphnav_map_forge.topology import (
    _edge_settings,
    _settings_fingerprint,
    build_effective_topology,
    compare_effective_topologies,
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


def _edge(source: str, target: str, edge_source: int = 1) -> map_pb2.Edge:
    edge = map_pb2.Edge()
    edge.id.from_waypoint = source
    edge.id.to_waypoint = target
    edge.annotations.edge_source = edge_source
    return edge


def _backup(
    path,
    *,
    active_site_edges: tuple[tuple[str, str, int], ...],
    tombstones: tuple[tuple[str, str, int], ...],
    false_tombstones: tuple[tuple[str, str, int], ...] = (),
) -> None:
    map_id = "site-map-1"
    waypoint_ids = ("wp-1", "wp-2", "wp-3", "wp-4")
    metadata = _bytes_field(1, map_id.encode()) + _bytes_field(2, b"Test Map")
    site_map = _bytes_field(1, metadata) + b"".join(
        _bytes_field(4, waypoint_id.encode()) for waypoint_id in waypoint_ids
    )
    raw_edges = (
        ("wp-1", "wp-2", 1),
        ("wp-2", "wp-3", 1),
        ("wp-3", "wp-4", 1),
    )
    records = [("graph_nav/site_maps/site-map-1", site_map)]
    records.extend(
        (
            f"graph_nav/waypoints/{waypoint_id}",
            map_pb2.Waypoint(id=waypoint_id).SerializeToString(),
        )
        for waypoint_id in waypoint_ids
    )
    records.extend(
        (
            f"graph_nav/edges/{index}",
            _edge(source, target, edge_source).SerializeToString(),
        )
        for index, (source, target, edge_source) in enumerate(raw_edges)
    )
    for prefix, rows, flag in (
        ("active", active_site_edges, None),
        ("false-tombstone", false_tombstones, False),
        ("tombstone", tombstones, True),
    ):
        for index, (source, target, edge_source) in enumerate(rows):
            payload = _bytes_field(1, map_id.encode()) + _bytes_field(
                2, _edge(source, target, edge_source).SerializeToString()
            )
            if flag is not None:
                payload += _integer_field(4, int(flag))
            records.append((f"graph_nav/site_edges/{prefix}-{index}", payload))
    with tarfile.open(path, "w") as archive:
        for name, payload in records:
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))


def _inventory(path):
    with BackupArchive(path) as archive:
        return build_effective_topology(archive, list_site_maps(archive)[0])


def test_effective_topology_overlays_raw_manual_and_tombstones(tmp_path) -> None:
    backup = tmp_path / "backup.tar"
    _backup(
        backup,
        active_site_edges=(
            ("wp-1", "wp-2", 1),
            ("wp-2", "wp-4", 7),
        ),
        tombstones=(("wp-2", "wp-3", 1),),
    )

    topology = _inventory(backup)

    assert topology["counts"] == {
        "waypoints": 4,
        "raw_edges": 3,
        "active_site_edges": 2,
        "site_edge_tombstones": 1,
        "tombstoned_raw_edges": 1,
        "effective_edges": 3,
        "site_override_edges": 1,
        "site_only_edges": 1,
        "raw_fallback_edges": 1,
        "site_edge_field_3_edges": 0,
        "area_callback_edges": 0,
        "crosswalk_edges": 0,
    }
    assert {
        (edge["key"][0], edge["key"][1]): edge["provenance"] for edge in topology["effective_edges"]
    } == {
        ("wp-1", "wp-2"): "site_override",
        ("wp-2", "wp-4"): "site_only",
        ("wp-3", "wp-4"): "raw_fallback",
    }


def test_topology_comparison_ignores_site_override_fallback(tmp_path) -> None:
    before_path = tmp_path / "before.tar"
    after_path = tmp_path / "after.tar"
    _backup(
        before_path,
        active_site_edges=(("wp-1", "wp-2", 1),),
        tombstones=(("wp-2", "wp-3", 1),),
    )
    _backup(
        after_path,
        active_site_edges=(),
        tombstones=(("wp-2", "wp-3", 1),),
    )

    comparison = compare_effective_topologies(_inventory(before_path), _inventory(after_path))

    assert comparison["graph_equivalent"]
    assert comparison["connection_set_equal"]
    assert comparison["missing_edges"] == []
    assert comparison["added_edges"] == []


def test_explicit_false_tombstone_flag_remains_active(tmp_path) -> None:
    backup = tmp_path / "backup.tar"
    _backup(
        backup,
        active_site_edges=(),
        tombstones=(),
        false_tombstones=(("wp-1", "wp-4", 7),),
    )

    topology = _inventory(backup)

    assert topology["counts"]["site_edge_tombstones"] == 0
    assert [
        edge["key"] for edge in topology["effective_edges"] if edge["provenance"] == "site_only"
    ] == [["wp-1", "wp-4"]]


def test_topology_comparison_reports_missing_manual_and_resurrected_raw_edge(tmp_path) -> None:
    before_path = tmp_path / "before.tar"
    after_path = tmp_path / "after.tar"
    _backup(
        before_path,
        active_site_edges=(("wp-2", "wp-4", 7),),
        tombstones=(("wp-2", "wp-3", 1),),
    )
    _backup(after_path, active_site_edges=(), tombstones=())

    comparison = compare_effective_topologies(_inventory(before_path), _inventory(after_path))

    assert not comparison["graph_equivalent"]
    assert [edge["key"] for edge in comparison["missing_edges"]] == [["wp-2", "wp-4"]]
    assert [edge["key"] for edge in comparison["added_edges"]] == [["wp-2", "wp-3"]]


def test_graph_baseline_cli_preserves_effective_edges_and_tombstones(tmp_path) -> None:
    backup = tmp_path / "backup.tar"
    output = tmp_path / "private" / "graph-baseline.json"
    _backup(
        backup,
        active_site_edges=(("wp-2", "wp-4", 7),),
        tombstones=(("wp-2", "wp-3", 1),),
    )

    assert (
        main(
            [
                "graph-baseline",
                str(backup),
                "--map",
                "Test Map",
                "--out",
                str(output),
            ]
        )
        == 0
    )

    baseline = json.loads(output.read_text(encoding="utf-8"))
    assert baseline["kind"] == "orbit_graph_baseline_inventory"
    assert baseline["sensitivity"] == "private_operational_data_do_not_commit"
    assert baseline["counts"]["effective_edges"] == 3
    assert baseline["counts"]["site_edge_tombstones"] == 1
    assert [row["key"] for row in baseline["tombstones"]] == [["wp-2", "wp-3"]]
    assert "operator deletion" in baseline["limitations"]["tombstone_origin"]


def test_edge_settings_preserve_crosswalk_and_public_annotation_values() -> None:
    edge = _edge("wp-1", "wp-2")
    edge.annotations.disable_alternate_route_finding = True
    edge.annotations.mobility_params.locomotion_hint = 5
    edge.annotations.override_mobility_params.paths.append("locomotion_hint")
    callback = edge.annotations.area_callbacks["crosswalk-region"]
    callback.service_name = "spot-crosswalk"
    callback.description = "crosswalk007"
    callback.recorded_data.custom_params.values["safety_distance"].double_value.value = 15.0

    settings = _edge_settings(edge)

    assert "edgeSource" not in settings
    assert settings["disableAlternateRouteFinding"] is True
    assert settings["mobilityParams"]["locomotionHint"] == 5
    assert settings["overrideMobilityParams"] == {"paths": ["locomotion_hint"]}
    assert settings["areaCallbacks"]["crosswalk-region"]["serviceName"] == "spot-crosswalk"
    assert (
        settings["areaCallbacks"]["crosswalk-region"]["recordedData"]["customParams"]["values"][
            "safety_distance"
        ]["doubleValue"]["value"]
        == 15.0
    )
    assert len(_settings_fingerprint(settings)) == 64
