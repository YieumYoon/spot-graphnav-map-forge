from bosdyn.api.graph_nav import map_pb2

from spot_graphnav_map_forge.geometry import (
    connectivity_halo,
    point_in_polygon,
    select_core,
    waypoint_coordinates,
)


def _graph() -> map_pb2.Graph:
    graph = map_pb2.Graph()
    for index, (x, y) in enumerate(((0.0, 0.0), (1.0, 0.0), (2.0, 0.0))):
        waypoint = graph.waypoints.add()
        waypoint.id = f"wp-{index}"
        waypoint.waypoint_tform_ko.position.x = x
        waypoint.waypoint_tform_ko.position.y = y
    for source, target in (("wp-0", "wp-1"), ("wp-1", "wp-2")):
        edge = graph.edges.add()
        edge.id.from_waypoint = source
        edge.id.to_waypoint = target
    return graph


def test_polygon_includes_boundary() -> None:
    polygon = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
    assert point_in_polygon((0.0, 0.5), polygon)
    assert point_in_polygon((0.5, 0.5), polygon)
    assert not point_in_polygon((2.0, 0.5), polygon)


def test_core_and_halo() -> None:
    graph = _graph()
    core = select_core(graph, ((-0.1, -0.1), (1.1, -0.1), (1.1, 0.1), (-0.1, 0.1)))
    assert core == {"wp-0", "wp-1"}
    assert connectivity_halo(graph, core, hops=1) == {"wp-2"}


def test_coordinates_propagate_from_anchor_over_edges() -> None:
    graph = _graph()
    graph.edges[0].from_tform_to.position.x = 1.0
    graph.edges[1].from_tform_to.position.x = 1.0
    anchor = graph.anchoring.anchors.add(id="wp-0")
    anchor.seed_tform_waypoint.position.x = 10.0
    coordinates = waypoint_coordinates(graph)
    assert coordinates["wp-0"].x == 10.0
    assert coordinates["wp-1"].x == 11.0
    assert coordinates["wp-2"].x == 12.0
    assert coordinates["wp-2"].source == "propagated_graph_anchor"
