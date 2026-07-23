from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .archive import BackupArchive
from .backup import resolve_site_map
from .topology import build_effective_topology, canonical_edge_key
from .web import build_workspace_payload


def build_reconnect_inventory(workspace: Path) -> dict[str, object]:
    """Build a deterministic, read-only inventory for Orbit-native edge reconciliation."""
    payload = build_workspace_payload(workspace)
    incident_edges: dict[str, list[dict[str, object]]] = defaultdict(list)
    for edge in payload["edges"]:
        source = str(edge["from"])
        target = str(edge["to"])
        shared = {
            "source": edge["source"],
            "transport": edge["transport"],
        }
        incident_edges[source].append(
            {"direction": "out", "neighbor_waypoint_id": target, **shared}
        )
        incident_edges[target].append({"direction": "in", "neighbor_waypoint_id": source, **shared})

    waypoint_rows: list[dict[str, object]] = []
    for waypoint in payload["waypoints"]:
        waypoint_id = str(waypoint["id"])
        edges = sorted(
            incident_edges[waypoint_id],
            key=lambda edge: (
                str(edge["direction"]),
                str(edge["neighbor_waypoint_id"]),
                str(edge["transport"]),
            ),
        )
        waypoint_rows.append(
            {
                **waypoint,
                "incident_edge_count": len(edges),
                "incident_edges": edges,
            }
        )

    manual_edges = list(payload["manual_edges"])
    endpoint_ids = sorted(
        {str(waypoint_id) for edge in manual_edges for waypoint_id in (edge["from"], edge["to"])}
    )
    counts = {
        "waypoints": len(waypoint_rows),
        "edges": len(payload["edges"]),
        "manual_edges": len(manual_edges),
        "manual_endpoint_waypoints": len(endpoint_ids),
        "manual_cross_session_edges": sum(
            bool(edge["cross_session_label"]) for edge in manual_edges
        ),
        "manual_field_3_edges": sum(bool(edge["field_3"]) for edge in manual_edges),
        "manual_local_frame_edges": sum(
            edge["coordinate_scope"] == "local_frame" for edge in manual_edges
        ),
    }
    return {
        "schema_version": 1,
        "kind": "orbit_manual_edge_reconnect_inventory",
        "sensitivity": "private_operational_data_do_not_commit",
        "site_map": payload["site_map"],
        "counts": counts,
        "coordinate_note": (
            "Coordinates are matching evidence, not waypoint identity. Local-frame coordinates "
            "must not be compared across disconnected components."
        ),
        "manual_endpoint_waypoint_ids": endpoint_ids,
        "waypoints": sorted(waypoint_rows, key=lambda waypoint: str(waypoint["id"])),
        "manual_edges": manual_edges,
        "edge_transport": payload["edge_transport"],
    }


def build_graph_reconciliation(
    workspace: Path,
    before_backup: Path,
    after_backup: Path,
    *,
    before_map_query: str,
    after_map_query: str,
) -> dict[str, object]:
    """Build a read-only connect/delete guide after native recording reassignment."""
    payload = build_workspace_payload(workspace)
    with BackupArchive(before_backup) as archive:
        before_map = resolve_site_map(archive, before_map_query)
        before = build_effective_topology(archive, before_map)
    with BackupArchive(after_backup) as archive:
        after_map = resolve_site_map(archive, after_map_query)
        after = build_effective_topology(archive, after_map)
    workspace_map = payload["site_map"]
    if workspace_map["id"] != before_map.id:  # type: ignore[index]
        raise ValueError(
            "workspace Site Map does not match the baseline backup: "
            f"{workspace_map['id']} != {before_map.id}"  # type: ignore[index]
        )
    return build_reconciliation_guide(before, after, list(payload["waypoints"]))


def build_reconciliation_guide(
    before: dict[str, object],
    after: dict[str, object],
    waypoint_rows: list[dict[str, object]],
) -> dict[str, object]:
    """Compare the baseline induced subgraph with one post-move Site Map."""
    before_waypoints = {str(value) for value in before["waypoint_ids"]}  # type: ignore[index]
    after_waypoints = {str(value) for value in after["waypoint_ids"]}  # type: ignore[index]
    unexpected_waypoints = sorted(after_waypoints - before_waypoints)
    if unexpected_waypoints:
        raise ValueError(
            "post-move Site Map contains waypoint IDs absent from the baseline; first: "
            f"{unexpected_waypoints[0]}"
        )

    before_edges = _topology_edge_index(before)
    after_edges = _topology_edge_index(after)
    before_tombstones = {
        _row_key(row): row
        for row in before["tombstones"]  # type: ignore[index]
    }
    expected_keys = {
        key for key in before_edges if key[0] in after_waypoints and key[1] in after_waypoints
    }
    observed_keys = set(after_edges)
    missing_keys = sorted(expected_keys - observed_keys)
    added_keys = sorted(observed_keys - expected_keys)
    cut_keys = sorted(
        key for key in before_edges if (key[0] in after_waypoints) != (key[1] in after_waypoints)
    )

    waypoint_by_id = {str(row["id"]): row for row in waypoint_rows}
    missing_coordinate_ids = sorted(after_waypoints - set(waypoint_by_id))
    if missing_coordinate_ids:
        raise ValueError(
            "baseline workspace has no coordinate for post-move waypoint; first: "
            f"{missing_coordinate_ids[0]}"
        )

    actions: list[dict[str, object]] = []
    for key in missing_keys:
        edge = before_edges[key]
        manual = (
            edge.get("edge_source") == "EDGE_SOURCE_USER_REQUEST"
            or edge.get("provenance") == "site_only"
        )
        actions.append(
            _guide_action(
                len(actions) + 1,
                "connect",
                "missing_manual_edge" if manual else "missing_expected_edge",
                edge,
                waypoint_by_id,
            )
        )
    for key in added_keys:
        edge = after_edges[key]
        resurrected = key in before_tombstones
        actions.append(
            _guide_action(
                len(actions) + 1,
                "delete",
                "resurrected_deleted_edge" if resurrected else "unexpected_edge",
                edge,
                waypoint_by_id,
            )
        )

    counts = {
        "after_waypoints": len(after_waypoints),
        "expected_edges": len(expected_keys),
        "observed_edges": len(observed_keys),
        "connect": sum(action["operation"] == "connect" for action in actions),
        "connect_manual": sum(action["reason"] == "missing_manual_edge" for action in actions),
        "delete": sum(action["operation"] == "delete" for action in actions),
        "delete_resurrected": sum(
            action["reason"] == "resurrected_deleted_edge" for action in actions
        ),
        "intentional_cut_edges": len(cut_keys),
    }
    return {
        "schema_version": 1,
        "kind": "orbit_graph_reconciliation_guide",
        "sensitivity": "private_operational_data_do_not_commit",
        "graph_reconciled": not actions,
        "before_site_map": before["site_map"],
        "after_site_map": after["site_map"],
        "counts": counts,
        "actions": actions,
        "intentional_cut_edges": [
            {
                "key": list(key),
                "from": before_edges[key]["from"],
                "to": before_edges[key]["to"],
            }
            for key in cut_keys
        ],
        "policy": {
            "expected_graph": "baseline effective graph induced by post-move waypoint IDs",
            "connect": "baseline connection missing from the post-move Site Map",
            "delete": "post-move connection absent from the baseline induced graph",
            "cut_edges": "reported only; never recreated across Site Maps",
            "ignored": "all edge settings and annotations except endpoint IDs",
        },
    }


def _topology_edge_index(
    topology: dict[str, object],
) -> dict[tuple[str, str], dict[str, object]]:
    return {
        _row_key(row): row
        for row in topology["effective_edges"]  # type: ignore[index]
    }


def _row_key(row: dict[str, object]) -> tuple[str, str]:
    key = row.get("key")
    if isinstance(key, list) and len(key) == 2:
        return canonical_edge_key(str(key[0]), str(key[1]))
    return canonical_edge_key(str(row["from"]), str(row["to"]))


def _guide_action(
    index: int,
    operation: str,
    reason: str,
    edge: dict[str, object],
    waypoint_by_id: dict[str, dict[str, object]],
) -> dict[str, object]:
    source_id = str(edge["from"])
    target_id = str(edge["to"])
    source = waypoint_by_id[source_id]
    target = waypoint_by_id[target_id]
    source_x = float(source["x"])
    source_y = float(source["y"])
    target_x = float(target["x"])
    target_y = float(target["y"])
    return {
        "index": index,
        "operation": operation,
        "reason": reason,
        "from": source_id,
        "to": target_id,
        "from_name": source.get("name") or source_id,
        "to_name": target.get("name") or target_id,
        "from_session": source.get("session_name") or "",
        "to_session": target.get("session_name") or "",
        "from_x": source_x,
        "from_y": source_y,
        "to_x": target_x,
        "to_y": target_y,
        "from_coordinate_source": source.get("source") or "",
        "to_coordinate_source": target.get("source") or "",
        "coordinate_scope": (
            "local_frame"
            if "waypoint_tform_ko_unanchored" in {source.get("source"), target.get("source")}
            else "map"
        ),
        "edge_source": edge.get("edge_source") or "",
        "baseline_provenance": edge.get("provenance"),
    }
