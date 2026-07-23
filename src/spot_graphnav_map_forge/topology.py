"""Read-only reconstruction and comparison of Orbit-visible graph connectivity."""

from __future__ import annotations

import base64
import hashlib
import json
import math
from collections import Counter
from typing import Any

from bosdyn.api.graph_nav import map_pb2
from google.protobuf.descriptor import FieldDescriptor
from google.protobuf.message import Message

from .archive import BackupArchive
from .backup import _scalar_id
from .models import SiteMapRecord
from .wire import bytes_values, decode_fields, integer_values

RAW_EDGE_PREFIX = "graph_nav/edges/"
SITE_EDGE_PREFIX = "graph_nav/site_edges/"
_INT64_FIELD_TYPES = {
    FieldDescriptor.TYPE_INT64,
    FieldDescriptor.TYPE_UINT64,
    FieldDescriptor.TYPE_SINT64,
    FieldDescriptor.TYPE_FIXED64,
    FieldDescriptor.TYPE_SFIXED64,
}


def canonical_edge_key(source: str, target: str) -> tuple[str, str]:
    """Return the undirected endpoint key used for graph-only comparison."""
    return (source, target) if source <= target else (target, source)


def build_effective_topology(archive: BackupArchive, site_map: SiteMapRecord) -> dict[str, object]:
    """Reconstruct the endpoint graph Orbit presents for one Site Map.

    Observed Orbit 5.1.8 semantics are a topology overlay:

    ``(raw recording edges union active SiteEdges) minus SiteEdge tombstones``.

    Active SiteEdges override raw payload/settings when both exist, but graph-only mode compares
    only canonical endpoint pairs. SiteEdges without raw counterparts are retained as site-only
    connections, which includes the observed manually created edges.
    """
    waypoint_ids = set(site_map.waypoint_ids)
    raw_edges: dict[tuple[str, str], dict[str, object]] = {}
    active_site_edges: dict[tuple[str, str], dict[str, object]] = {}
    tombstones: dict[tuple[str, str], dict[str, object]] = {}

    for path in archive.names(RAW_EDGE_PREFIX):
        edge = _parse_edge(archive.read(path), path)
        if edge.id.from_waypoint not in waypoint_ids or edge.id.to_waypoint not in waypoint_ids:
            continue
        _insert_unique(raw_edges, edge, path, "raw edge")

    for path in archive.names(SITE_EDGE_PREFIX):
        fields = decode_fields(archive.read(path))
        if _scalar_id(fields, 1, "") != site_map.id:
            continue
        embedded = bytes_values(fields, 2)
        if not embedded:
            raise ValueError(f"SiteEdge has no embedded public Edge: {path}")
        edge = _parse_edge(embedded[0], path)
        if edge.id.from_waypoint not in waypoint_ids or edge.id.to_waypoint not in waypoint_ids:
            continue
        destination = tombstones if any(integer_values(fields, 4)) else active_site_edges
        kind = "SiteEdge tombstone" if destination is tombstones else "active SiteEdge"
        _insert_unique(
            destination,
            edge,
            path,
            kind,
            site_edge_field_numbers=sorted({field.number for field in fields}),
        )

    conflicting = set(active_site_edges) & set(tombstones)
    if conflicting:
        source, target = sorted(conflicting)[0]
        raise ValueError(
            "active SiteEdge and tombstone share endpoints; revision order is unknown: "
            f"{source} <-> {target}"
        )

    effective_keys = (set(raw_edges) | set(active_site_edges)) - set(tombstones)
    effective_edges: list[dict[str, object]] = []
    provenance_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    for key in sorted(effective_keys):
        raw = raw_edges.get(key)
        site = active_site_edges.get(key)
        if site is not None and raw is not None:
            provenance = "site_override"
            selected = site
        elif site is not None:
            provenance = "site_only"
            selected = site
        else:
            provenance = "raw_fallback"
            selected = raw
        if selected is None:  # pragma: no cover - guarded by effective_keys construction
            raise AssertionError(f"effective edge has no source record: {key}")
        provenance_counts[provenance] += 1
        source_counts[str(selected["edge_source"])] += 1
        settings = _edge_settings(selected["edge"])
        effective_edges.append(
            {
                "key": list(key),
                "from": selected["from"],
                "to": selected["to"],
                "edge_source": selected["edge_source"],
                "snapshot_id": selected["snapshot_id"],
                "provenance": provenance,
                "raw_path": raw["path"] if raw is not None else None,
                "site_edge_path": site["path"] if site is not None else None,
                "site_edge_field_numbers": (
                    site["site_edge_field_numbers"] if site is not None else []
                ),
                "settings": settings,
                "settings_fingerprint": _settings_fingerprint(settings),
                "area_callback_ids": sorted(selected["edge"].annotations.area_callbacks.keys()),
                "has_crosswalk": _has_crosswalk(selected["edge"]),
            }
        )

    tombstone_rows: list[dict[str, object]] = []
    for key, row in sorted(tombstones.items()):
        tombstone_rows.append(
            {
                "key": list(key),
                "from": row["from"],
                "to": row["to"],
                "edge_source": row["edge_source"],
                "path": row["path"],
                "has_raw_counterpart": key in raw_edges,
            }
        )

    return {
        "schema_version": 1,
        "kind": "orbit_effective_graph_topology",
        "site_map": {
            "id": site_map.id,
            "name": site_map.name,
            "recording_ids": list(site_map.recording_ids),
        },
        "waypoint_ids": sorted(waypoint_ids),
        "counts": {
            "waypoints": len(waypoint_ids),
            "raw_edges": len(raw_edges),
            "active_site_edges": len(active_site_edges),
            "site_edge_tombstones": len(tombstones),
            "tombstoned_raw_edges": sum(key in raw_edges for key in tombstones),
            "effective_edges": len(effective_edges),
            "site_override_edges": provenance_counts["site_override"],
            "site_only_edges": provenance_counts["site_only"],
            "raw_fallback_edges": provenance_counts["raw_fallback"],
            "site_edge_field_3_edges": sum(
                3 in edge["site_edge_field_numbers"] for edge in effective_edges
            ),
            "area_callback_edges": sum(bool(edge["area_callback_ids"]) for edge in effective_edges),
            "crosswalk_edges": sum(bool(edge["has_crosswalk"]) for edge in effective_edges),
        },
        "edge_source_counts": dict(sorted(source_counts.items())),
        "effective_edges": effective_edges,
        "tombstones": tombstone_rows,
    }


def compare_effective_topologies(
    before: dict[str, object], after: dict[str, object]
) -> dict[str, object]:
    """Compare exact waypoint membership and undirected endpoint connectivity."""
    before_waypoints = {str(value) for value in before["waypoint_ids"]}  # type: ignore[index]
    after_waypoints = {str(value) for value in after["waypoint_ids"]}  # type: ignore[index]
    before_edges = _edge_index(before)
    after_edges = _edge_index(after)
    missing_waypoints = sorted(before_waypoints - after_waypoints)
    added_waypoints = sorted(after_waypoints - before_waypoints)
    missing_edge_keys = sorted(set(before_edges) - set(after_edges))
    added_edge_keys = sorted(set(after_edges) - set(before_edges))
    waypoint_set_equal = not missing_waypoints and not added_waypoints
    connection_set_equal = not missing_edge_keys and not added_edge_keys
    return {
        "schema_version": 1,
        "kind": "orbit_effective_graph_topology_comparison",
        "graph_equivalent": waypoint_set_equal and connection_set_equal,
        "waypoint_set_equal": waypoint_set_equal,
        "connection_set_equal": connection_set_equal,
        "before": {
            "site_map": before["site_map"],
            "counts": before["counts"],
        },
        "after": {
            "site_map": after["site_map"],
            "counts": after["counts"],
        },
        "missing_waypoint_ids": missing_waypoints,
        "added_waypoint_ids": added_waypoints,
        "missing_edges": [before_edges[key] for key in missing_edge_keys],
        "added_edges": [after_edges[key] for key in added_edge_keys],
        "comparison_policy": {
            "edge_identity": "canonical unordered endpoint pair",
            "ignored": [
                "SiteEdge/raw provenance",
                "stored direction",
                "edge source",
                "snapshots",
                "mobility and annotation settings",
            ],
        },
    }


def _edge_index(topology: dict[str, object]) -> dict[tuple[str, str], dict[str, object]]:
    result: dict[tuple[str, str], dict[str, object]] = {}
    for value in topology["effective_edges"]:  # type: ignore[index]
        row = dict(value)  # type: ignore[arg-type]
        key_values = row["key"]
        key = (str(key_values[0]), str(key_values[1]))  # type: ignore[index]
        if key in result:
            raise ValueError(f"duplicate effective edge in topology inventory: {key}")
        result[key] = row
    return result


def _parse_edge(payload: bytes, path: str) -> Any:
    edge = map_pb2.Edge()
    edge.ParseFromString(payload)
    if not edge.id.from_waypoint or not edge.id.to_waypoint:
        raise ValueError(f"edge has an incomplete endpoint ID: {path}")
    return edge


def _insert_unique(
    destination: dict[tuple[str, str], dict[str, object]],
    edge: Any,
    path: str,
    kind: str,
    *,
    site_edge_field_numbers: list[int] | None = None,
) -> None:
    key = canonical_edge_key(edge.id.from_waypoint, edge.id.to_waypoint)
    if key in destination:
        raise ValueError(f"duplicate {kind} endpoint pair: {key[0]} <-> {key[1]}")
    destination[key] = {
        "from": edge.id.from_waypoint,
        "to": edge.id.to_waypoint,
        "edge_source": _edge_source_name(edge.annotations.edge_source),
        "snapshot_id": edge.snapshot_id,
        "path": path,
        "edge": edge,
        "site_edge_field_numbers": site_edge_field_numbers or [],
    }


def _edge_source_name(value: int) -> str:
    enum = map_pb2.Edge.Annotations.DESCRIPTOR.fields_by_name["edge_source"].enum_type
    item = enum.values_by_number.get(value)
    return item.name if item is not None else str(value)


def _edge_settings(edge: Any) -> dict[str, object]:
    """Return the public, JSON-safe Edge annotation settings excluding provenance.

    The output deliberately uses protobuf JSON field names but keeps enum values numeric and
    int64 values decimal strings. That matches Orbit's protobufjs object model closely enough for
    a version-checked native ``updateSiteEdges`` draft without guessing private SiteEdge fields.
    """
    settings = _message_to_javascript_object(edge.annotations)
    settings.pop("edgeSource", None)
    return settings


def _settings_fingerprint(settings: dict[str, object]) -> str:
    canonical = json.dumps(
        settings,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _has_crosswalk(edge: Any) -> bool:
    return any(
        callback.service_name == "spot-crosswalk"
        for callback in edge.annotations.area_callbacks.values()
    )


def _message_to_javascript_object(message: Message) -> dict[str, object]:
    result: dict[str, object] = {}
    for field, value in message.ListFields():
        name = field.json_name
        if field.is_repeated:
            if field.message_type is not None and field.message_type.GetOptions().map_entry:
                value_field = field.message_type.fields_by_name["value"]
                result[name] = {
                    str(key): _field_to_javascript_value(value_field, item)
                    for key, item in value.items()
                }
            else:
                result[name] = [_field_to_javascript_value(field, item) for item in value]
        else:
            result[name] = _field_to_javascript_value(field, value)
    return result


def _field_to_javascript_value(field: FieldDescriptor, value: Any) -> object:
    if field.type == FieldDescriptor.TYPE_MESSAGE:
        return _message_to_javascript_object(value)
    if field.type == FieldDescriptor.TYPE_ENUM:
        return int(value)
    if field.type in _INT64_FIELD_TYPES:
        return str(int(value))
    if field.type == FieldDescriptor.TYPE_BYTES:
        return base64.b64encode(bytes(value)).decode("ascii")
    if field.type in {
        FieldDescriptor.TYPE_DOUBLE,
        FieldDescriptor.TYPE_FLOAT,
    }:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"non-finite protobuf value in {field.full_name}")
        return number
    if field.type in {
        FieldDescriptor.TYPE_INT32,
        FieldDescriptor.TYPE_UINT32,
        FieldDescriptor.TYPE_SINT32,
        FieldDescriptor.TYPE_FIXED32,
        FieldDescriptor.TYPE_SFIXED32,
    }:
        return int(value)
    if field.type == FieldDescriptor.TYPE_BOOL:
        return bool(value)
    if field.type == FieldDescriptor.TYPE_STRING:
        return str(value)
    raise ValueError(f"unsupported protobuf field type {field.type} in {field.full_name}")
