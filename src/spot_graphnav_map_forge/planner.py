from __future__ import annotations

import json
from pathlib import Path

from bosdyn.api.graph_nav import map_pb2

from .geometry import (
    Point,
    WaypointCoordinate,
    connected_components,
    connectivity_halo,
    load_graph,
    point_in_polygon,
)


def create_plan(
    workspace: Path,
    polygon: list[Point],
    zone_name: str,
    halo_hops: int = 1,
    clone_halo_actions: bool = False,
) -> dict[str, object]:
    workspace = workspace.expanduser().resolve()
    graph = load_graph(workspace / "graph")
    coordinates = _workspace_coordinates(workspace)
    core = {
        waypoint_id
        for waypoint_id, coordinate in coordinates.items()
        if point_in_polygon((coordinate.x, coordinate.y), polygon)
    }
    if not core:
        raise ValueError("polygon selected no waypoints")
    halo = connectivity_halo(graph, core, halo_hops)
    selected = core | halo
    components = connected_components(graph, selected)
    source_counts: dict[str, int] = {}
    for waypoint_id in selected:
        source = coordinates[waypoint_id].source
        source_counts[source] = source_counts.get(source, 0) + 1

    metadata = json.loads((workspace / "workspace.json").read_text(encoding="utf-8"))
    actions = metadata["actions"]
    selected_edges = [
        edge
        for edge in graph.edges
        if edge.id.from_waypoint in selected and edge.id.to_waypoint in selected
    ]

    return {
        "schema_version": 1,
        "zone_name": zone_name,
        "polygon": polygon,
        "halo_hops": halo_hops,
        "clone_halo_actions": clone_halo_actions,
        "core_waypoint_ids": sorted(core),
        "halo_waypoint_ids": sorted(halo),
        "coordinate_sources": source_counts,
        "edge_source_counts": edge_source_counts(selected_edges),
        "counts": {
            "core_waypoints": len(core),
            "halo_waypoints": len(halo),
            "selected_edges": len(selected_edges),
            "components": len(components),
            "largest_component": len(components[0]) if components else 0,
            "core_actions": sum(action["waypoint_id"] in core for action in actions),
            "halo_actions": sum(action["waypoint_id"] in halo for action in actions),
        },
    }


def edge_source_counts(edges: list[map_pb2.Edge]) -> dict[str, int]:
    enum = map_pb2.Edge.Annotations.DESCRIPTOR.fields_by_name["edge_source"].enum_type
    names = {value.number: value.name for value in enum.values}
    counts: dict[str, int] = {}
    for edge in edges:
        name = names.get(edge.annotations.edge_source, str(edge.annotations.edge_source))
        counts[name] = counts.get(name, 0) + 1
    return counts


def _workspace_coordinates(workspace: Path) -> dict[str, WaypointCoordinate]:
    payload = json.loads((workspace / "map_view.json").read_text(encoding="utf-8"))
    return {
        row["id"]: WaypointCoordinate(
            waypoint_id=row["id"],
            x=float(row["x"]),
            y=float(row["y"]),
            source=row["source"],
        )
        for row in payload["waypoints"]
    }
