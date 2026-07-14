from bosdyn.api.graph_nav import map_pb2

from spot_graphnav_map_forge.clone import clone_subgraph


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
