"""Adapter for the backup's graph_nav records."""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from bosdyn.api import geometry_pb2
from bosdyn.api.autowalk import walks_pb2
from bosdyn.api.graph_nav import map_pb2

from .actions import triggered_action_reference
from .archive import BackupArchive
from .models import (
    ActionRecord,
    DockRecord,
    MapLayoutControlPoint,
    MapLayoutRecord,
    PanoStateRecord,
    SiteMapRecord,
    WalkTargetOpaqueProfile,
)
from .wire import WireField, bytes_values, decode_fields, encode_fields, integer_values, text_values

SITE_MAP_PREFIX = "graph_nav/site_maps/"
SITE_WAYPOINT_PREFIX = "graph_nav/site_waypoints/"
SITE_EDGE_PREFIX = "graph_nav/site_edges/"
RAW_WAYPOINT_PREFIX = "graph_nav/waypoints/"
WAYPOINT_SNAPSHOT_PREFIX = "graph_nav/waypoint_snapshots/"
EDGE_SNAPSHOT_PREFIX = "graph_nav/edge_snapshots/"
SITE_ELEMENT_PREFIX = "graph_nav/site_element/"
SITE_ELEMENT_IMAGE_PREFIX = "graph_nav/site_element_images/"
SITE_DOCK_PREFIX = "graph_nav/site_dock/"
PANO_STATE_PREFIX = "graph_nav/waypoint_pano_states/"
SITE_WALK_PREFIX = "graph_nav/site_walk/"


def list_site_maps(archive: BackupArchive) -> list[SiteMapRecord]:
    records: list[SiteMapRecord] = []
    for path in archive.names(SITE_MAP_PREFIX):
        payload = archive.read(path)
        fields = decode_fields(payload)
        fallback_id = Path(path).name
        metadata_values = bytes_values(fields, 1)
        metadata = decode_fields(metadata_values[0]) if metadata_values else ()
        map_id = _scalar_id(metadata, 1, fallback_id)
        names = text_values(metadata, 2)
        records.append(
            SiteMapRecord(
                id=map_id,
                name=names[0] if names else fallback_id,
                recording_ids=text_values(fields, 3),
                waypoint_ids=text_values(fields, 4),
                source_path=path,
                layout=parse_map_layout(payload),
            )
        )
    return sorted(records, key=lambda record: (record.name.casefold(), record.id))


def resolve_site_map(archive: BackupArchive, query: str) -> SiteMapRecord:
    maps = list_site_maps(archive)
    exact = [record for record in maps if query in {record.id, record.name}]
    if len(exact) == 1:
        return exact[0]
    partial = [record for record in maps if query.casefold() in record.name.casefold()]
    if len(partial) == 1:
        return partial[0]
    if not exact and not partial:
        raise ValueError(f"site map not found: {query}")
    matches = exact or partial
    raise ValueError("site map query is ambiguous: " + ", ".join(r.name for r in matches))


def reconstruct_final_graph(
    archive: BackupArchive, site_map: SiteMapRecord
) -> tuple[
    map_pb2.Graph,
    dict[str, str],
    dict[str, str],
    tuple[tuple[str, str], ...],
]:
    """Reconstruct the final graph, preferring site-level edited objects.

    Returns the graph plus snapshot-id-to-tar-path indexes for selected waypoint and edge
    snapshots, followed by the directed edge keys that are retained only for workspace selection
    and coordinate propagation. Snapshot payloads are not read here, keeping preparation memory
    bounded.
    """
    wanted = set(site_map.waypoint_ids)
    raw_waypoints: dict[str, Any] = {}
    for path in archive.names(RAW_WAYPOINT_PREFIX):
        waypoint = map_pb2.Waypoint()
        waypoint.ParseFromString(archive.read(path))
        if waypoint.id in wanted:
            raw_waypoints[waypoint.id] = waypoint

    site_waypoints: dict[str, Any] = {}
    for path in archive.names(SITE_WAYPOINT_PREFIX):
        fields = decode_fields(archive.read(path))
        if _scalar_id(fields, 1, "") != site_map.id:
            continue
        embedded = bytes_values(fields, 2)
        if not embedded:
            continue
        waypoint = map_pb2.Waypoint()
        waypoint.ParseFromString(embedded[0])
        if waypoint.id in wanted:
            site_waypoints[waypoint.id] = waypoint

    graph = map_pb2.Graph()
    missing: list[str] = []
    for waypoint_id in site_map.waypoint_ids:
        waypoint = site_waypoints.get(waypoint_id) or raw_waypoints.get(waypoint_id)
        if waypoint is None:
            missing.append(waypoint_id)
        else:
            graph.waypoints.add().CopyFrom(waypoint)
    if missing:
        raise ValueError(
            f"{len(missing)} site-map waypoints have no site/raw record; first: {missing[0]}"
        )

    selection_only_edges: list[tuple[str, str]] = []
    for path in archive.names(SITE_EDGE_PREFIX):
        fields = decode_fields(archive.read(path))
        if _scalar_id(fields, 1, "") != site_map.id:
            continue
        if not _site_edge_is_active(fields):
            continue
        embedded = bytes_values(fields, 2)
        if not embedded:
            continue
        edge = map_pb2.Edge()
        edge.ParseFromString(embedded[0])
        _normalize_edge_rotation(edge)
        graph.edges.add().CopyFrom(edge)
        if _site_edge_is_selection_only(fields):
            selection_only_edges.append((edge.id.from_waypoint, edge.id.to_waypoint))

    waypoint_snapshots = _snapshot_path_index(archive, WAYPOINT_SNAPSHOT_PREFIX)
    edge_snapshots = _snapshot_path_index(archive, EDGE_SNAPSHOT_PREFIX)
    selected_waypoint_snapshots = {
        waypoint.snapshot_id: waypoint_snapshots[waypoint.snapshot_id]
        for waypoint in graph.waypoints
        if waypoint.snapshot_id in waypoint_snapshots
    }
    selected_edge_snapshots = {
        edge.snapshot_id: edge_snapshots[edge.snapshot_id]
        for edge in graph.edges
        if edge.snapshot_id in edge_snapshots
    }
    return (
        graph,
        selected_waypoint_snapshots,
        selected_edge_snapshots,
        tuple(sorted(selection_only_edges)),
    )


def _site_edge_is_active(fields: Any) -> bool:
    """Return whether a SiteEdge wrapper may participate in workspace connectivity.

    The wrapper schema is proprietary, so the flag names are intentionally not guessed. In the
    observed Orbit 5.1.8 archive format, field 3 appears on edited edges whose public GraphNav
    annotations still carry the selected environment and traversal settings. Public Walk import
    does not reliably reconstruct their private SiteEdge state, so they remain available for
    offline selection and coordinate propagation and require an explicit include/exclude transport
    choice. Field 4 marks wrappers that Orbit no longer presents as graph edges, including wrappers
    that also have field 3, and those wrappers are omitted entirely.
    """
    return not any(integer_values(fields, 4))


def _site_edge_is_selection_only(fields: Any) -> bool:
    """Return whether an active wrapper needs an explicit public-Walk transport choice."""
    return _site_edge_is_active(fields) and any(integer_values(fields, 3))


def _normalize_edge_rotation(edge: map_pb2.Edge) -> None:
    """Normalize promoted float32 edge quaternions to the final GraphNav representation.

    Some site-edited/manual edge rotations are stored at float32 precision promoted into the
    public double-valued Quaternion. Same-version final graph exports normalize those values. A
    tight tolerance avoids changing already normalized recorded edges.
    """
    rotation = edge.from_tform_to.rotation
    norm = math.sqrt(
        rotation.x * rotation.x
        + rotation.y * rotation.y
        + rotation.z * rotation.z
        + rotation.w * rotation.w
    )
    if norm == 0.0 or math.isclose(norm, 1.0, rel_tol=0.0, abs_tol=1e-12):
        return
    rotation.x /= norm
    rotation.y /= norm
    rotation.z /= norm
    rotation.w /= norm


def walk_target_opaque_profile(
    archive: BackupArchive,
    *,
    site_map_waypoint_ids: set[str] | None = None,
) -> WalkTargetOpaqueProfile | None:
    """Recover an unambiguous Target extension profile from the backup.

    Complete SiteDock targets are preferred because each contains the exact public Target
    envelope, including the opaque fields emitted by an Orbit-edited Walk. When a Site Map scope
    is supplied, docks on that map participate first. If none of those carry a complete profile,
    complete docks elsewhere in the same backup provide a version-matched fallback. Every
    participating dock must agree.

    If no complete dock target is available, SiteWalk defaults are accepted only when they also
    agree exactly. Conflicts are rejected instead of selecting a value by recency or majority.
    """
    target_descriptor = walks_pb2.Target.DESCRIPTOR
    navigate_descriptor = target_descriptor.fields_by_name["navigate_to"].message_type
    travel_descriptor = navigate_descriptor.fields_by_name["travel_params"].message_type
    known_target_fields = set(target_descriptor.fields_by_number)
    known_travel_fields = set(travel_descriptor.fields_by_number)

    def collect_dock_candidates(
        waypoint_scope: set[str] | None,
    ) -> list[tuple[str, bytes, bytes]]:
        candidates: list[tuple[str, bytes, bytes]] = []
        for path in archive.names(SITE_DOCK_PREFIX):
            fields = decode_fields(archive.read(path))
            docked_waypoint_ids = text_values(fields, 3)
            if waypoint_scope is not None and (
                not docked_waypoint_ids or docked_waypoint_ids[0] not in waypoint_scope
            ):
                continue
            target_values = bytes_values(fields, 4)
            if len(target_values) != 1:
                continue
            target_payload = target_values[0]
            try:
                target = walks_pb2.Target.FromString(target_payload)
            except Exception:  # protobuf uses implementation-specific decode errors
                continue
            if target.WhichOneof("target") != "navigate_to":
                continue
            target_fields = encode_fields(
                field
                for field in decode_fields(target_payload)
                if field.number not in known_target_fields
            )
            travel_fields = encode_fields(
                field
                for field in decode_fields(
                    target.navigate_to.travel_params.SerializeToString(deterministic=True)
                )
                if field.number not in known_travel_fields
            )
            if target_fields and travel_fields:
                candidates.append((path, travel_fields, target_fields))
        return candidates

    dock_candidates = collect_dock_candidates(site_map_waypoint_ids)
    selection = "site_map_dock_consensus"
    if not dock_candidates and site_map_waypoint_ids is not None:
        dock_candidates = collect_dock_candidates(None)
        selection = "backup_dock_consensus"

    if dock_candidates:
        profiles = {(travel, target) for _, travel, target in dock_candidates}
        if len(profiles) != 1:
            raise ValueError(
                f"SiteDock opaque Target defaults conflict: {len(profiles)} complete profiles"
            )
        travel_fields, target_fields = next(iter(profiles))
        return WalkTargetOpaqueProfile(
            selection=selection,
            source_path=min(path for path, _, _ in dock_candidates),
            source_updated=None,
            observed_source_records=len(dock_candidates),
            travel_params_fields=travel_fields,
            travel_params_field_numbers=tuple(
                field.number for field in decode_fields(travel_fields)
            ),
            target_fields=target_fields,
            target_field_numbers=tuple(field.number for field in decode_fields(target_fields)),
        )

    site_walk_candidates: list[tuple[int, str, bytes, bytes]] = []
    for path in archive.names(SITE_WALK_PREFIX):
        fields = decode_fields(archive.read(path))
        travel_values = bytes_values(fields, 14)
        target_defaults = bytes_values(fields, 15)
        if len(travel_values) != 1 or len(target_defaults) != 1:
            continue
        travel_fields = encode_fields(
            field
            for field in decode_fields(travel_values[0])
            if field.number not in known_travel_fields
        )
        if not travel_fields:
            continue
        # The SiteWalk wrapper stores only Target field 4's value, not its tag.
        target_fields = encode_fields((WireField(4, 2, target_defaults[0]),))
        updated = max(integer_values(fields, 8) or (0,))
        site_walk_candidates.append((updated, path, travel_fields, target_fields))

    if not site_walk_candidates:
        return None
    profiles = {(travel, target) for _, _, travel, target in site_walk_candidates}
    if len(profiles) != 1:
        raise ValueError(
            "SiteWalk opaque Target defaults conflict and no complete SiteDock profile exists: "
            f"{len(profiles)} profiles"
        )
    travel_fields, target_fields = next(iter(profiles))
    source_updated, source_path, _, _ = max(site_walk_candidates)
    return WalkTargetOpaqueProfile(
        selection="site_walk_consensus",
        source_path=source_path,
        source_updated=source_updated,
        observed_source_records=len(site_walk_candidates),
        travel_params_fields=travel_fields,
        travel_params_field_numbers=tuple(field.number for field in decode_fields(travel_fields)),
        target_fields=target_fields,
        target_field_numbers=tuple(field.number for field in decode_fields(target_fields)),
    )


def list_actions(archive: BackupArchive) -> list[ActionRecord]:
    image_paths: dict[str, list[str]] = defaultdict(list)
    for path in archive.names(SITE_ELEMENT_IMAGE_PREFIX):
        element_id = Path(path).name.split("-", 5)
        if len(element_id) >= 5:
            image_paths["-".join(element_id[:5])].append(path)

    records: list[ActionRecord] = []
    for path in archive.names(SITE_ELEMENT_PREFIX):
        payload = archive.read(path)
        fields = decode_fields(payload)
        fallback_id = Path(path).name
        element_id = _scalar_id(fields, 1, fallback_id)
        names = text_values(fields, 2)
        waypoint_ids = text_values(fields, 3)
        trigger = triggered_action_reference(payload)
        relocalize_values = bytes_values(fields, 9)
        if len(relocalize_values) > 1:
            raise ValueError(f"SiteElement has multiple relocalize fields: {element_id}")
        if relocalize_values:
            walks_pb2.Target.Relocalize.FromString(relocalize_values[0])
        records.append(
            ActionRecord(
                id=element_id,
                name=names[0] if names else fallback_id,
                waypoint_id=waypoint_ids[0] if waypoint_ids else "",
                source_path=path,
                image_paths=tuple(sorted(image_paths.get(element_id, []))),
                trigger_parent_element_id=trigger[0] if trigger else None,
                trigger_image_service=trigger[1] if trigger else None,
                has_explicit_relocalization=bool(relocalize_values and relocalize_values[0]),
            )
        )
    return sorted(records, key=lambda record: (record.name.casefold(), record.id))


def list_docks(archive: BackupArchive) -> list[DockRecord]:
    """List complete SiteDock records, collapsing duplicate stored revisions.

    Orbit's SiteDock envelope is proprietary, but field 4 is the public
    ``bosdyn.api.autowalk.Target`` message. Incomplete records with no dock number or docked
    waypoint are tombstone-like rows and cannot describe an exportable dock.
    """
    records_by_signature: dict[tuple[int, str, bytes], DockRecord] = {}
    for path in archive.names(SITE_DOCK_PREFIX):
        fields = decode_fields(archive.read(path))
        record_id = _scalar_id(fields, 1, Path(path).name)
        dock_ids = integer_values(fields, 2)
        docked_waypoint_ids = text_values(fields, 3)
        target_values = bytes_values(fields, 4)
        if not dock_ids or not docked_waypoint_ids or not target_values:
            continue
        target = walks_pb2.Target()
        target.ParseFromString(target_values[0])
        target_kind = target.WhichOneof("target")
        target_waypoint_ids = _target_waypoint_ids(target)
        if target_kind is None or not target_waypoint_ids:
            continue
        canonical_target = target.SerializeToString(deterministic=True)
        signature = (dock_ids[0], docked_waypoint_ids[0], canonical_target)
        records_by_signature.setdefault(
            signature,
            DockRecord(
                id=record_id,
                dock_id=dock_ids[0],
                docked_waypoint_id=docked_waypoint_ids[0],
                target_kind=target_kind,
                target_waypoint_ids=target_waypoint_ids,
                target_fingerprint=hashlib.sha256(canonical_target).hexdigest(),
                source_path=path,
            ),
        )
    return sorted(
        records_by_signature.values(),
        key=lambda record: (record.dock_id, record.docked_waypoint_id, record.id),
    )


def list_pano_states(archive: BackupArchive) -> list[PanoStateRecord]:
    """List waypoint-keyed state for Site View panorama captures.

    The observed Orbit 5.1.8 archive format stores one small record per participating waypoint.
    Field 2 is a protobuf Timestamp, not the panorama image payload itself.
    """
    records: list[PanoStateRecord] = []
    for path in archive.names(PANO_STATE_PREFIX):
        fields = decode_fields(archive.read(path))
        waypoint_ids = text_values(fields, 1)
        waypoint_id = waypoint_ids[0] if waypoint_ids else Path(path).name
        timestamp_values = bytes_values(fields, 2)
        timestamp = decode_fields(timestamp_values[0]) if timestamp_values else ()
        seconds = integer_values(timestamp, 1)
        nanos = integer_values(timestamp, 2)
        records.append(
            PanoStateRecord(
                waypoint_id=waypoint_id,
                updated_seconds=seconds[0] if seconds else None,
                updated_nanos=nanos[0] if nanos else None,
                source_path=path,
            )
        )
    return sorted(records, key=lambda record: record.waypoint_id)


def parse_map_layout(site_map_payload: bytes) -> MapLayoutRecord | None:
    """Parse the floor-plan/layout projection bundled with a Site Map backup record.

    The message descriptor is proprietary. The field names here deliberately describe only
    observed semantics and must not be confused with Orbit's Site View panorama feature.
    """
    fields = decode_fields(site_map_payload)
    layout_values = bytes_values(fields, 2)
    if not layout_values:
        return None
    layout_fields = decode_fields(layout_values[0])
    metadata_values = bytes_values(layout_fields, 1)
    metadata = decode_fields(metadata_values[0]) if metadata_values else ()
    layout_id = _scalar_id(metadata, 1, "")
    names = text_values(metadata, 2)

    floor_plan_name = ""
    floor_plan_values = bytes_values(layout_fields, 2)
    if floor_plan_values:
        floor_plan_fields = decode_fields(floor_plan_values[0])
        floor_plan_names = text_values(floor_plan_fields, 2)
        if floor_plan_names:
            floor_plan_name = floor_plan_names[0]

    control_points: list[MapLayoutControlPoint] = []
    for row_payload in bytes_values(layout_fields, 3):
        row = decode_fields(row_payload)
        waypoint_ids = text_values(row, 3)
        pose_values = bytes_values(row, 4)
        if not waypoint_ids or not pose_values:
            continue
        pose = geometry_pb2.SE3Pose()
        pose.ParseFromString(pose_values[0])
        control_points.append(
            MapLayoutControlPoint(
                waypoint_id=waypoint_ids[0],
                position=(pose.position.x, pose.position.y, pose.position.z),
                rotation=(
                    pose.rotation.x,
                    pose.rotation.y,
                    pose.rotation.z,
                    pose.rotation.w,
                ),
            )
        )
    return MapLayoutRecord(
        id=layout_id,
        name=names[0] if names else layout_id,
        floor_plan_name=floor_plan_name,
        control_points=tuple(control_points),
    )


def graph_with_layout_projection(
    graph: map_pb2.Graph, layout: MapLayoutRecord | None
) -> map_pb2.Graph:
    """Return a workspace-only graph with layout control points projected as anchors.

    The returned graph exists only for 2D coordinate propagation. It must not be serialized as
    the cloned GraphNav graph because the floor-plan layout is a separate data model.
    """
    projected = map_pb2.Graph()
    projected.CopyFrom(graph)
    if layout is None:
        return projected
    wanted = {waypoint.id for waypoint in graph.waypoints}
    existing = {anchor.id for anchor in projected.anchoring.anchors}
    for control_point in layout.control_points:
        if control_point.waypoint_id not in wanted or control_point.waypoint_id in existing:
            continue
        anchor = projected.anchoring.anchors.add(id=control_point.waypoint_id)
        anchor.seed_tform_waypoint.position.x = control_point.position[0]
        anchor.seed_tform_waypoint.position.y = control_point.position[1]
        anchor.seed_tform_waypoint.position.z = control_point.position[2]
        anchor.seed_tform_waypoint.rotation.x = control_point.rotation[0]
        anchor.seed_tform_waypoint.rotation.y = control_point.rotation[1]
        anchor.seed_tform_waypoint.rotation.z = control_point.rotation[2]
        anchor.seed_tform_waypoint.rotation.w = control_point.rotation[3]
        existing.add(control_point.waypoint_id)
    return projected


def _scalar_id(fields: tuple[Any, ...], number: int, fallback: str) -> str:
    texts = text_values(fields, number)
    if texts:
        return texts[0]
    integers = integer_values(fields, number)
    if integers:
        return str(integers[0])
    return fallback


def _snapshot_path_index(archive: BackupArchive, prefix: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in archive.names(prefix):
        filename = Path(path).name
        snapshot_id = filename.rsplit(".", 1)[0]
        result[snapshot_id] = path
    return result


def _target_waypoint_ids(target: walks_pb2.Target) -> tuple[str, ...]:
    kind = target.WhichOneof("target")
    if kind == "navigate_to":
        waypoint_id = target.navigate_to.destination_waypoint_id
        return (waypoint_id,) if waypoint_id else ()
    if kind == "navigate_route":
        return tuple(target.navigate_route.route.waypoint_id)
    return ()
