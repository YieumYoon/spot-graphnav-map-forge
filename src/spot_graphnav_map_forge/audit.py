"""Read-only preservation audit for a polygon split plan."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from bosdyn.api.graph_nav import map_pb2

from .archive import BackupArchive
from .backup import SITE_WALK_PREFIX
from .geometry import connected_components, load_graph
from .planner import (
    edge_source_counts,
    resolve_triggered_action_exclusions,
    selection_only_edge_keys,
)


def create_preservation_audit(workspace: Path, plan_path: Path) -> dict[str, object]:
    workspace = workspace.expanduser().resolve()
    plan_path = plan_path.expanduser().resolve()
    metadata = json.loads((workspace / "workspace.json").read_text(encoding="utf-8"))
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    graph = load_graph(workspace / "graph")

    all_waypoints = {waypoint.id for waypoint in graph.waypoints}
    core = set(plan["core_waypoint_ids"])
    halo = set(plan["halo_waypoint_ids"])
    selected = core | halo
    selection_only_keys = selection_only_edge_keys(metadata)
    include_selection_only_edges = bool(
        plan.get("edge_transport", {}).get("include_in_walk", False)
    )
    unknown = selected - all_waypoints
    if unknown:
        raise ValueError(f"plan contains waypoint not present in workspace: {sorted(unknown)[0]}")
    remainder = all_waypoints - core

    boundary_edges: list[map_pb2.Edge] = []
    core_edges: list[map_pb2.Edge] = []
    remainder_edges: list[map_pb2.Edge] = []
    for edge in graph.edges:
        source_in_core = edge.id.from_waypoint in core
        target_in_core = edge.id.to_waypoint in core
        if source_in_core != target_in_core:
            boundary_edges.append(edge)
        elif source_in_core:
            core_edges.append(edge)
        else:
            remainder_edges.append(edge)

    selected_selection_only_edges = [
        edge
        for edge in graph.edges
        if (edge.id.from_waypoint, edge.id.to_waypoint) in selection_only_keys
        and edge.id.from_waypoint in selected
        and edge.id.to_waypoint in selected
    ]
    walk_excluded_keys = set() if include_selection_only_edges else selection_only_keys
    walk_components = connected_components(
        graph,
        selected,
        excluded_edge_keys=walk_excluded_keys,
    )

    actions = metadata.get("actions", [])
    triggered_actions = metadata.get("triggered_actions", [])
    selected_action_waypoints = selected if plan.get("clone_halo_actions") else core
    selected_action_ids = {
        str(action["id"])
        for action in actions
        if action.get("id") and action.get("waypoint_id") in selected_action_waypoints
    }
    excluded_triggered_actions, exclusion_reason = resolve_triggered_action_exclusions(
        metadata,
        plan.get("excluded_triggered_action_ids", []),
        plan.get("triggered_action_exclusion_reason"),
        eligible_parent_ids=selected_action_ids,
    )
    excluded_triggered_action_ids = {str(action["id"]) for action in excluded_triggered_actions}
    retained_triggered_actions = [
        action
        for action in triggered_actions
        if str(action.get("id", "")) not in excluded_triggered_action_ids
    ]
    docks = metadata.get("docks", [])
    pano_states = metadata.get("pano_states", [])
    layout = metadata.get("map_layout") or {}
    layout_ids = {
        row["waypoint_id"] for row in layout.get("control_points", []) if row.get("waypoint_id")
    }

    source_backup = Path(metadata["source_backup"])
    with BackupArchive(source_backup) as archive:
        site_walks = _site_walk_references(
            archive=archive,
            waypoint_ids=all_waypoints,
            core=core,
            actions=actions,
        )
        all_paths = tuple(archive.names())
        capture_candidates = _capture_candidates(all_paths)
        explicit_recording_membership_files = tuple(archive.names("graph_nav/recordings/"))

    core_pano = sum(row["waypoint_id"] in core for row in pano_states)
    halo_pano = sum(row["waypoint_id"] in halo for row in pano_states)
    remainder_pano = sum(row["waypoint_id"] in remainder for row in pano_states)
    cross_walks = sum(row["classification"] == "cross_partition" for row in site_walks)
    dock_records = _dock_classifications(docks, selected)
    boundary_docks = sum(row["classification"] == "selection_boundary" for row in dock_records)
    triggered_action_zones = _triggered_action_zone_counts(
        triggered_actions, actions, core, halo, remainder
    )
    retained_triggered_action_zones = _triggered_action_zone_counts(
        retained_triggered_actions, actions, core, halo, remainder
    )
    excluded_triggered_action_zones = _triggered_action_zone_counts(
        excluded_triggered_actions, actions, core, halo, remainder
    )
    explicit_relocalization_zones = _zone_counts(
        [row for row in actions if row.get("has_explicit_relocalization")],
        core,
        halo,
        remainder,
    )

    recording_status = "available" if explicit_recording_membership_files else "unavailable"
    partition_blockers = [
        "fleet-manager acceptance of an identity-preserving backup rewrite is unverified",
    ]
    if recording_status == "unavailable":
        partition_blockers.append(
            "backup exposes SiteMap recording IDs but no explicit recording-to-waypoint table"
        )
    if cross_walks:
        partition_blockers.append(f"{cross_walks} SiteWalk(s) reference both partition sides")
    if core_pano and not capture_candidates:
        partition_blockers.append(
            "waypoint pano state exists, but panorama capture payloads are absent from this backup"
        )
    if boundary_docks:
        partition_blockers.append(
            f"{boundary_docks} dock placement(s) cross the selected waypoint boundary"
        )
    if retained_triggered_action_zones["core"]:
        retained_core_count = retained_triggered_action_zones["core"]
        partition_blockers.append(
            f"{retained_core_count} selected triggered AI inspection(s) have an "
            "Orbit-only parent linkage that public Walk cannot encode"
        )

    return {
        "schema_version": 1,
        "workspace": str(workspace),
        "plan": str(plan_path),
        "site_map": metadata["site_map"],
        "selection": {
            "core_waypoints": len(core),
            "halo_waypoints": len(halo),
            "remainder_waypoints": len(remainder),
            "core_components": len(connected_components(graph, core)),
            "remainder_components": len(connected_components(graph, remainder)),
            "walk_components": len(walk_components),
            "walk_largest_component": len(walk_components[0]) if walk_components else 0,
            "cleanup": plan.get("selection_cleanup", {}),
        },
        "topology": {
            "core_internal_edges": len(core_edges),
            "remainder_internal_edges": len(remainder_edges),
            "boundary_edges": len(boundary_edges),
            "boundary_edge_source_counts": edge_source_counts(boundary_edges),
            "field_3_edges_selected": len(selected_selection_only_edges),
            "field_3_edges_included_in_walk": (
                len(selected_selection_only_edges) if include_selection_only_edges else 0
            ),
            "field_3_edges_excluded_from_walk": (
                0 if include_selection_only_edges else len(selected_selection_only_edges)
            ),
        },
        "dependencies": {
            "actions": _zone_counts(actions, core, halo, remainder),
            "triggered_actions": triggered_action_zones,
            "triggered_actions_retained": retained_triggered_action_zones,
            "triggered_action_exclusions": {
                "reason": exclusion_reason,
                "zone_counts": excluded_triggered_action_zones,
                "records": [
                    {
                        "id": action["id"],
                        "name": action.get("name"),
                        "parent_element_id": action.get("parent_element_id"),
                        "disposition": "not_cloned_explicit_plan_exclusion",
                    }
                    for action in excluded_triggered_actions
                ],
            },
            "explicit_relocalizations": explicit_relocalization_zones,
            "waypoint_pano_states": {
                "core": core_pano,
                "halo": halo_pano,
                "remainder": remainder_pano,
                "capture_payload_candidates": len(capture_candidates),
                "capture_history_status": (
                    "candidate_payloads_present" if capture_candidates else "absent_from_backup"
                ),
            },
            "map_layout_control_points": {
                "core": len(layout_ids & core),
                "halo": len(layout_ids & halo),
                "remainder": len(layout_ids & remainder),
            },
            "site_docks": {
                "total": len(dock_records),
                "classification_counts": dict(
                    sorted(Counter(row["classification"] for row in dock_records).items())
                ),
                "records": dock_records,
            },
            "site_walks": {
                "total_referencing_map": len(site_walks),
                "classification_counts": dict(
                    sorted(Counter(row["classification"] for row in site_walks).items())
                ),
                "reference_method": "exact UTF-8 waypoint/action ID scan (inferred)",
                "records": site_walks,
            },
            "recordings": {
                "declared_by_site_map": len(metadata["site_map"].get("recording_ids", [])),
                "waypoint_membership_status": recording_status,
                "explicit_membership_files": len(explicit_recording_membership_files),
            },
        },
        "assessments": {
            "copy": {
                "offline_bundle_generation": "implemented",
                "edge_transport": {
                    "policy": "explicit_operator_choice",
                    "field_3_edges_selected": len(selected_selection_only_edges),
                    "include_in_walk": include_selection_only_edges,
                    "post_import_action": (
                        "verify each listed edge in Orbit and reapply environment/travel "
                        "settings; recreate the edge first when excluded"
                    ),
                },
                "triggered_ai_exclusions": {
                    "explicitly_excluded": len(excluded_triggered_actions),
                    "reason": exclusion_reason,
                    "status": (
                        "audited_explicit_omission" if excluded_triggered_actions else "none"
                    ),
                },
                "fleet_manager_new_site_map_ingestion": "unverified",
                "dock_export": {
                    "selected_complete": sum(
                        row["classification"] == "selected_complete" for row in dock_records
                    ),
                    "selection_boundary_skipped": boundary_docks,
                },
                "historical_site_view_capture_migration": (
                    "not_possible_from_this_backup"
                    if core_pano and not capture_candidates
                    else "unverified"
                ),
            },
            "partition_preserve_ids": {
                "status": "research_required",
                "implemented": False,
                "blockers": partition_blockers,
            },
        },
    }


def _zone_counts(
    rows: list[dict[str, object]], core: set[str], halo: set[str], remainder: set[str]
) -> dict[str, int]:
    return {
        "core": sum(row.get("waypoint_id") in core for row in rows),
        "halo": sum(row.get("waypoint_id") in halo for row in rows),
        "remainder": sum(row.get("waypoint_id") in remainder for row in rows),
    }


def _triggered_action_zone_counts(
    triggered_actions: list[dict[str, object]],
    actions: list[dict[str, object]],
    core: set[str],
    halo: set[str],
    remainder: set[str],
) -> dict[str, int]:
    parent_waypoints = {
        str(row["id"]): str(row["waypoint_id"])
        for row in actions
        if row.get("id") and row.get("waypoint_id")
    }
    parent_ids = [str(row.get("parent_element_id", "")) for row in triggered_actions]
    return {
        "core": sum(parent_waypoints.get(parent_id) in core for parent_id in parent_ids),
        "halo": sum(parent_waypoints.get(parent_id) in halo for parent_id in parent_ids),
        "remainder": sum(parent_waypoints.get(parent_id) in remainder for parent_id in parent_ids),
    }


def _site_walk_references(
    archive: BackupArchive,
    waypoint_ids: set[str],
    core: set[str],
    actions: list[dict[str, object]],
) -> list[dict[str, object]]:
    waypoint_tokens = tuple((value, value.encode()) for value in waypoint_ids)
    action_waypoint = {
        str(row["id"]): str(row["waypoint_id"])
        for row in actions
        if row.get("id") and row.get("waypoint_id")
    }
    action_tokens = tuple((value, value.encode()) for value in action_waypoint)
    records: list[dict[str, object]] = []
    for path in archive.names(SITE_WALK_PREFIX):
        payload = archive.read(path)
        direct_waypoints = {value for value, token in waypoint_tokens if token in payload}
        action_ids = {value for value, token in action_tokens if token in payload}
        referenced_waypoints = direct_waypoints | {action_waypoint[value] for value in action_ids}
        if not referenced_waypoints:
            continue
        core_refs = referenced_waypoints & core
        remainder_refs = referenced_waypoints - core
        if core_refs and remainder_refs:
            classification = "cross_partition"
        elif core_refs:
            classification = "core_only"
        else:
            classification = "remainder_only"
        records.append(
            {
                "id": Path(path).name,
                "classification": classification,
                "waypoint_refs": len(referenced_waypoints),
                "action_refs": len(action_ids),
            }
        )
    return sorted(records, key=lambda row: str(row["id"]))


def _capture_candidates(paths: tuple[str, ...]) -> tuple[str, ...]:
    markers = ("run_capture", "run_archive", "/captures/", "graph_nav/image/")
    return tuple(
        path
        for path in paths
        if any(marker in path.casefold() for marker in markers) and not path.endswith("/")
    )


def _dock_classifications(
    docks: list[dict[str, object]], selected: set[str]
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for dock in docks:
        waypoint_ids = {
            str(dock["docked_waypoint_id"]),
            *(str(value) for value in dock.get("target_waypoint_ids", [])),
        }
        selected_refs = waypoint_ids & selected
        if waypoint_ids <= selected:
            classification = "selected_complete"
        elif selected_refs:
            classification = "selection_boundary"
        else:
            classification = "outside_selection"
        records.append(
            {
                "id": dock["id"],
                "dock_id": dock["dock_id"],
                "classification": classification,
                "waypoint_refs": sorted(waypoint_ids),
                "missing_selected_waypoint_refs": sorted(waypoint_ids - selected),
            }
        )
    return sorted(records, key=lambda row: (int(row["dock_id"]), str(row["id"])))
