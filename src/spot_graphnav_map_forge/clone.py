from __future__ import annotations

from dataclasses import dataclass

from bosdyn.api.graph_nav import map_pb2

from .remap import (
    IDENTITY_MODE_CLONE,
    IDENTITY_MODE_ORBIT_NATIVE,
    IDENTITY_MODE_PRESERVE,
    IDENTITY_MODES,
    PRESERVABLE_ID_KINDS,
    IdRemapper,
)


@dataclass(frozen=True)
class CloneResult:
    graph: map_pb2.Graph
    remapper: IdRemapper


def clone_subgraph(
    source: map_pb2.Graph,
    selected_waypoint_ids: set[str],
    clone_name: str,
    *,
    excluded_edge_keys: set[tuple[str, str]] | None = None,
    identity_mode: str = IDENTITY_MODE_CLONE,
) -> CloneResult:
    if identity_mode not in IDENTITY_MODES:
        raise ValueError("identity_mode must be one of: " + ", ".join(sorted(IDENTITY_MODES)))
    preserve_kinds = (
        PRESERVABLE_ID_KINDS if identity_mode == IDENTITY_MODE_PRESERVE else frozenset()
    )
    remapper = IdRemapper(
        clone_name=clone_name,
        preserve_kinds=preserve_kinds,
        orbit_native=identity_mode == IDENTITY_MODE_ORBIT_NATIVE,
    )
    clone = map_pb2.Graph()
    excluded_edges = excluded_edge_keys or set()

    for waypoint in source.waypoints:
        if waypoint.id not in selected_waypoint_ids:
            continue
        new_waypoint = clone.waypoints.add()
        new_waypoint.CopyFrom(waypoint)
        old_id = waypoint.id
        new_waypoint.id = remapper.map("waypoint", old_id)
        if waypoint.snapshot_id:
            new_waypoint.snapshot_id = remapper.map("waypoint_snapshot", waypoint.snapshot_id)

    for edge in source.edges:
        source_id = edge.id.from_waypoint
        target_id = edge.id.to_waypoint
        if source_id not in selected_waypoint_ids or target_id not in selected_waypoint_ids:
            continue
        if (source_id, target_id) in excluded_edges:
            continue
        new_edge = clone.edges.add()
        new_edge.CopyFrom(edge)
        new_edge.id.from_waypoint = remapper.map("waypoint", source_id)
        new_edge.id.to_waypoint = remapper.map("waypoint", target_id)
        if edge.snapshot_id:
            new_edge.snapshot_id = remapper.map("edge_snapshot", edge.snapshot_id)

    for anchor in source.anchoring.anchors:
        if anchor.id not in selected_waypoint_ids:
            continue
        new_anchor = clone.anchoring.anchors.add()
        new_anchor.CopyFrom(anchor)
        new_anchor.id = remapper.map("waypoint", anchor.id)

    # Anchored world-object IDs are sensor/fiducial identities, not clone object IDs.
    for anchored_object in source.anchoring.objects:
        clone.anchoring.objects.add().CopyFrom(anchored_object)

    return CloneResult(graph=clone, remapper=remapper)


def clone_waypoint_snapshot(payload: bytes, new_id: str) -> bytes:
    snapshot = map_pb2.WaypointSnapshot()
    snapshot.ParseFromString(payload)
    if snapshot.id == new_id:
        return payload
    snapshot.id = new_id
    return snapshot.SerializeToString()


def clone_edge_snapshot(payload: bytes, new_id: str) -> bytes:
    snapshot = map_pb2.EdgeSnapshot()
    snapshot.ParseFromString(payload)
    if snapshot.id == new_id:
        return payload
    snapshot.id = new_id
    return snapshot.SerializeToString()
