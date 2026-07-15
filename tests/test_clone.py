import json
import tarfile

from bosdyn.api.graph_nav import map_pb2

from spot_graphnav_map_forge.builder import build_clone
from spot_graphnav_map_forge.clone import clone_subgraph
from spot_graphnav_map_forge.validator import validate_bundle


def test_clone_remaps_waypoints_snapshots_edges_and_anchors() -> None:
    graph = map_pb2.Graph()
    first = graph.waypoints.add(id="old-a", snapshot_id="snap-a")
    first.waypoint_tform_ko.position.x = 1.0
    graph.waypoints.add(id="old-b", snapshot_id="snap-b")
    graph.waypoints.add(id="outside", snapshot_id="snap-out")
    edge = graph.edges.add(snapshot_id="edge-snap")
    edge.id.from_waypoint = "old-a"
    edge.id.to_waypoint = "old-b"
    outside_edge = graph.edges.add()
    outside_edge.id.from_waypoint = "old-b"
    outside_edge.id.to_waypoint = "outside"
    anchor = graph.anchoring.anchors.add(id="old-a")
    anchor.seed_tform_waypoint.position.x = 12.0

    result = clone_subgraph(graph, {"old-a", "old-b"}, "zone-a")

    assert len(result.graph.waypoints) == 2
    assert len(result.graph.edges) == 1
    assert len(result.graph.anchoring.anchors) == 1
    waypoint_map = result.remapper.mappings["waypoint"]
    assert result.graph.edges[0].id.from_waypoint == waypoint_map["old-a"]
    assert result.graph.edges[0].id.to_waypoint == waypoint_map["old-b"]
    assert result.graph.anchoring.anchors[0].id == waypoint_map["old-a"]
    assert result.graph.waypoints[0].snapshot_id != "snap-a"


def test_remapping_is_deterministic_per_zone() -> None:
    graph = map_pb2.Graph()
    graph.waypoints.add(id="old-a")
    first = clone_subgraph(graph, {"old-a"}, "zone-a")
    second = clone_subgraph(graph, {"old-a"}, "zone-a")
    other = clone_subgraph(graph, {"old-a"}, "zone-b")
    assert first.graph.waypoints[0].id == second.graph.waypoints[0].id
    assert first.graph.waypoints[0].id != other.graph.waypoints[0].id


def test_clone_can_exclude_selection_only_edges_without_dropping_waypoints() -> None:
    graph = map_pb2.Graph()
    graph.waypoints.add(id="old-a")
    graph.waypoints.add(id="old-b")
    edge = graph.edges.add(snapshot_id="edge-snap")
    edge.id.from_waypoint = "old-a"
    edge.id.to_waypoint = "old-b"

    result = clone_subgraph(
        graph,
        {"old-a", "old-b"},
        "zone-a",
        excluded_edge_keys={("old-a", "old-b")},
    )

    assert len(result.graph.waypoints) == 2
    assert len(result.graph.edges) == 0
    assert "edge_snapshot" not in result.remapper.mappings


def test_build_uses_explicit_selection_only_edge_transport_choice(tmp_path) -> None:
    backup = tmp_path / "backup.tar"
    with tarfile.open(backup, "w"):
        pass
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    graph = map_pb2.Graph()
    graph.waypoints.add(id="old-a")
    graph.waypoints.add(id="old-b")
    edge = graph.edges.add()
    edge.id.from_waypoint = "old-a"
    edge.id.to_waypoint = "old-b"
    (workspace / "graph").write_bytes(graph.SerializeToString())
    metadata = {
        "source_backup": str(backup),
        "site_map": {"id": "map-1", "name": "Map 1", "recording_ids": []},
        "snapshot_sources": {"waypoint": {}, "edge": {}},
        "actions": [],
        "triggered_actions": [],
        "docks": [],
        "edge_transport": {
            "policy": "orbit_site_edge_field_3_selection_only",
            "selection_only_edges": [{"from": "old-a", "to": "old-b"}],
        },
    }
    (workspace / "workspace.json").write_text(json.dumps(metadata), encoding="utf-8")

    def write_plan(name: str, include: bool):
        disposition = (
            "included_in_walk_public_annotations_only"
            if include
            else "excluded_from_bundle_and_walk"
        )
        plan = {
            "zone_name": name,
            "core_waypoint_ids": ["old-a", "old-b"],
            "halo_waypoint_ids": [],
            "edge_transport": {
                "include_in_walk": include,
                "selection_only_edges": [
                    {"from": "old-a", "to": "old-b", "disposition": disposition}
                ],
            },
        }
        path = workspace / f"{name}.json"
        path.write_text(json.dumps(plan), encoding="utf-8")
        return path

    excluded_bundle = tmp_path / "excluded"
    excluded = build_clone(workspace, write_plan("excluded", False), excluded_bundle)
    assert excluded["counts"]["edges"] == 0
    assert excluded["counts"]["selection_only_edges_excluded"] == 1
    assert validate_bundle(excluded_bundle).valid

    included_bundle = tmp_path / "included"
    included = build_clone(workspace, write_plan("included", True), included_bundle)
    assert included["counts"]["edges"] == 1
    assert included["counts"]["selection_only_edges_included"] == 1
    assert validate_bundle(included_bundle).valid
