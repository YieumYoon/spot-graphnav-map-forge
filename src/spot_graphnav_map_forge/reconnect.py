"""Read-only B0 versus final-backup reconciliation for Orbit-native editing."""

from __future__ import annotations

import json
from pathlib import Path

from .archive import BackupArchive
from .backup import resolve_site_map
from .topology import build_effective_topology, canonical_edge_key


def build_graph_reconciliation(
    baseline_path: Path,
    after_backup: Path,
    *,
    after_map_query: str,
) -> dict[str, object]:
    """Compare an immutable graph-baseline JSON file with one final Site Map backup."""
    baseline_path = baseline_path.expanduser().resolve()
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    _validate_baseline(baseline)
    with BackupArchive(after_backup) as archive:
        after_map = resolve_site_map(archive, after_map_query)
        after = build_effective_topology(archive, after_map)
    return build_reconciliation_guide(baseline, after)


def build_reconciliation_guide(
    before: dict[str, object],
    after: dict[str, object],
) -> dict[str, object]:
    """Compare the B0 induced subgraph with one final Source or Destination Site Map."""
    before_waypoints = {str(value) for value in before["waypoint_ids"]}  # type: ignore[index]
    after_waypoints = {str(value) for value in after["waypoint_ids"]}  # type: ignore[index]
    unexpected_waypoints = sorted(after_waypoints - before_waypoints)
    if unexpected_waypoints:
        raise ValueError(
            f"final Site Map contains waypoint IDs absent from B0; first: {unexpected_waypoints[0]}"
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
    retained_keys = sorted(expected_keys & observed_keys)
    settings_profile_keys = {
        key
        for key in expected_keys
        if isinstance(before_edges[key].get("settings"), dict)
        and isinstance(before_edges[key].get("settings_fingerprint"), str)
    }
    settings_keys = [
        key
        for key in retained_keys
        if key in settings_profile_keys
        and isinstance(after_edges[key].get("settings"), dict)
        and isinstance(after_edges[key].get("settings_fingerprint"), str)
        if before_edges[key].get("settings_fingerprint")
        != after_edges[key].get("settings_fingerprint")
    ]
    boundary_keys = sorted(
        key for key in before_edges if (key[0] in after_waypoints) != (key[1] in after_waypoints)
    )

    actions: list[dict[str, object]] = []
    for key in missing_keys:
        edge = before_edges[key]
        manual = (
            edge.get("edge_source") == "EDGE_SOURCE_USER_REQUEST"
            or edge.get("provenance") == "site_only"
        )
        actions.append(
            _action(
                len(actions) + 1,
                "connect",
                "missing_manual_edge" if manual else "missing_expected_edge",
                edge,
            )
        )
    for key in added_keys:
        edge = after_edges[key]
        actions.append(
            _action(
                len(actions) + 1,
                "delete",
                "resurrected_deleted_edge" if key in before_tombstones else "unexpected_edge",
                edge,
            )
        )
    for key in settings_keys:
        edge = before_edges[key]
        actions.append(
            {
                **_action(
                    len(actions) + 1,
                    "update",
                    "edge_settings_mismatch",
                    edge,
                ),
                "observed_source_value": after_edges[key].get("edge_source_value"),
                "desired_settings": edge.get("settings", {}),
                "observed_settings": after_edges[key].get("settings", {}),
                "settings_fingerprint": edge.get("settings_fingerprint"),
                "settings_categories": _settings_categories(edge),
                "crosswalk": bool(edge.get("has_crosswalk")),
                "stored_direction_matches": (
                    edge.get("from") == after_edges[key].get("from")
                    and edge.get("to") == after_edges[key].get("to")
                ),
            }
        )

    connect_count = len(missing_keys)
    delete_count = len(added_keys)
    update_count = len(settings_keys)
    counts = {
        "baseline_waypoints": len(before_waypoints),
        "current_waypoints": len(after_waypoints),
        "current_b0_waypoints": len(after_waypoints),
        "ignored_extra_waypoints": 0,
        "baseline_effective_edges": len(before_edges),
        "desired_internal_edges": len(expected_keys),
        "observed_edges": len(observed_keys),
        "observed_edges_total": len(observed_keys),
        "ignored_extra_edges": 0,
        "connect_edges": connect_count,
        "connect_manual_edges": sum(
            action["reason"] == "missing_manual_edge" for action in actions
        ),
        "delete_edges": delete_count,
        "resurrected_deleted_edges": sum(
            action["reason"] == "resurrected_deleted_edge" for action in actions
        ),
        "update_edges": update_count,
        "crosswalk_update_edges": sum(
            action["operation"] == "update" and bool(action.get("crosswalk")) for action in actions
        ),
        "direction_blocked_update_edges": sum(
            action["operation"] == "update" and action.get("stored_direction_matches") is False
            for action in actions
        ),
        "settings_profile_edges": len(settings_profile_keys),
        "intentional_cut_edges": len(boundary_keys),
        "excluded_outside_edges": 0,
    }
    return {
        "schema_version": 1,
        "kind": "orbit_graph_reconciliation_guide",
        "sensitivity": "private_operational_data_do_not_commit",
        "comparison_source": "final_backup_vs_b0_baseline",
        "baseline_site_map": before["site_map"],
        "after_site_map": after["site_map"],
        "graph_reconciled": connect_count == 0 and delete_count == 0,
        "settings_reconciled": update_count == 0,
        "fully_reconciled": not actions,
        "settings_comparison_available": expected_keys <= settings_profile_keys,
        "counts": counts,
        "actions": actions,
        "intentional_cuts": [
            {
                "from": before_edges[key]["from"],
                "to": before_edges[key]["to"],
                "manual": (
                    before_edges[key].get("edge_source") == "EDGE_SOURCE_USER_REQUEST"
                    or before_edges[key].get("provenance") == "site_only"
                ),
            }
            for key in boundary_keys
        ],
        "comparison_policy": {
            "identity": "exact waypoint ID and canonical unordered endpoint pair",
            "desired_graph": "B0 effective induced subgraph for final Site Map waypoint set",
            "current_graph": "effective topology reconstructed from the final backup",
            "boundary_edges": "reported only; never emitted as edit actions",
            "public_edge_settings": "compared from B0 and restored only in native Orbit",
            "persistence": "read-only backup evidence; Orbit remains the only writer",
        },
    }


def _validate_baseline(value: object) -> None:
    if not isinstance(value, dict):
        raise ValueError("baseline must be a JSON object")
    if value.get("kind") != "orbit_graph_baseline_inventory":
        raise ValueError("baseline is not an orbit_graph_baseline_inventory")
    for field in ("site_map", "waypoint_ids", "effective_edges", "tombstones"):
        if field not in value:
            raise ValueError(f"baseline is missing required field: {field}")


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


def _action(
    index: int,
    operation: str,
    reason: str,
    edge: dict[str, object],
) -> dict[str, object]:
    return {
        "index": index,
        "operation": operation,
        "reason": reason,
        "from": str(edge["from"]),
        "to": str(edge["to"]),
        "edge_source": edge.get("edge_source") or "",
        "baseline_provenance": edge.get("provenance"),
        "coordinate_scope": "orbit_live",
    }


def _settings_categories(edge: dict[str, object]) -> list[str]:
    settings = edge.get("settings")
    if not isinstance(settings, dict):
        return []
    categories: list[str] = []
    if edge.get("has_crosswalk"):
        categories.append("crosswalk")
    if "mobilityParams" in settings or "overrideMobilityParams" in settings:
        categories.append("mobility")
    remaining = set(settings) - {
        "areaCallbacks",
        "mobilityParams",
        "overrideMobilityParams",
    }
    if remaining:
        categories.append("edge behavior")
    return categories
