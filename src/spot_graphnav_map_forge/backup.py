"""Read-only adapter for observed Orbit backup records."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Any

from bosdyn.api import geometry_pb2
from bosdyn.api.autowalk import walks_pb2

from .archive import BackupArchive
from .models import (
    ActionRecord,
    DockRecord,
    MapLayoutControlPoint,
    MapLayoutRecord,
    PanoStateRecord,
    SiteMapRecord,
)
from .site_elements import triggered_action_reference
from .wire import bytes_values, decode_fields, integer_values, text_values

SITE_MAP_PREFIX = "graph_nav/site_maps/"
SITE_ELEMENT_PREFIX = "graph_nav/site_element/"
SITE_ELEMENT_IMAGE_PREFIX = "graph_nav/site_element_images/"
SITE_DOCK_PREFIX = "graph_nav/site_dock/"
PANO_STATE_PREFIX = "graph_nav/waypoint_pano_states/"


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
        raise ValueError(f"Site Map not found: {query}")
    matches = exact or partial
    raise ValueError("Site Map query is ambiguous: " + ", ".join(r.name for r in matches))


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
    """List complete SiteDock records, collapsing duplicate stored revisions."""
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
    """List waypoint-keyed state for Site View panorama captures."""
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
    """Parse the observed floor-plan/layout projection attached to a Site Map."""
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


def _scalar_id(fields: tuple[Any, ...], number: int, fallback: str) -> str:
    texts = text_values(fields, number)
    if texts:
        return texts[0]
    integers = integer_values(fields, number)
    if integers:
        return str(integers[0])
    return fallback


def _target_waypoint_ids(target: walks_pb2.Target) -> tuple[str, ...]:
    kind = target.WhichOneof("target")
    if kind == "navigate_to":
        waypoint_id = target.navigate_to.destination_waypoint_id
        return (waypoint_id,) if waypoint_id else ()
    if kind == "navigate_route":
        return tuple(target.navigate_route.route.waypoint_id)
    return ()
