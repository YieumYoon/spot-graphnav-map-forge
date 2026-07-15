from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

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
    excluded_triggered_action_ids: list[str] | None = None,
    triggered_action_exclusion_reason: str | None = None,
    exclude_unanchored_waypoints: bool = False,
    exclude_dependency_free_components: bool = False,
    include_selection_only_edges: bool = False,
) -> dict[str, object]:
    workspace = workspace.expanduser().resolve()
    graph = load_graph(workspace / "graph")
    coordinates = _workspace_coordinates(workspace)
    raw_core = {
        waypoint_id
        for waypoint_id, coordinate in coordinates.items()
        if point_in_polygon((coordinate.x, coordinate.y), polygon)
    }
    if not raw_core:
        raise ValueError("polygon selected no waypoints")
    metadata = json.loads((workspace / "workspace.json").read_text(encoding="utf-8"))
    actions = metadata["actions"]
    selection_only_keys = selection_only_edge_keys(metadata)
    baseline_halo = connectivity_halo(graph, raw_core, halo_hops)
    baseline_selected = raw_core | baseline_halo
    unanchored_ids = {
        waypoint_id
        for waypoint_id, coordinate in coordinates.items()
        if coordinate.source == "waypoint_tform_ko_unanchored"
    }
    core = raw_core - unanchored_ids if exclude_unanchored_waypoints else set(raw_core)
    if not core:
        raise ValueError("selection cleanup removed every polygon waypoint")
    halo = connectivity_halo(graph, core, halo_hops)
    selected = core | halo
    excluded_unanchored_ids = (
        sorted((baseline_selected - selected) & unanchored_ids)
        if exclude_unanchored_waypoints
        else []
    )

    dependency_waypoint_ids = selection_dependency_waypoint_ids(metadata)
    components_before_cleanup = connected_components(graph, selected)
    excluded_components: list[set[str]] = []
    protected_components: list[dict[str, object]] = []
    if exclude_dependency_free_components and len(components_before_cleanup) > 1:
        largest_size = len(components_before_cleanup[0])
        for component in components_before_cleanup:
            if len(component) == largest_size:
                continue
            dependencies = component & dependency_waypoint_ids
            if dependencies:
                protected_components.append(
                    {
                        "size": len(component),
                        "dependency_waypoint_ids": sorted(dependencies),
                    }
                )
            else:
                excluded_components.append(component)
    excluded_component_ids = set().union(*excluded_components) if excluded_components else set()
    protected_components.sort(
        key=lambda row: (-int(row["size"]), tuple(row["dependency_waypoint_ids"]))
    )
    core -= excluded_component_ids
    halo -= excluded_component_ids
    selected = core | halo
    selection_components = connected_components(graph, selected)
    excluded_walk_edge_keys = set() if include_selection_only_edges else selection_only_keys
    walk_components = connected_components(
        graph,
        selected,
        excluded_edge_keys=excluded_walk_edge_keys,
    )
    source_counts = dict(
        sorted(Counter(coordinates[waypoint_id].source for waypoint_id in selected).items())
    )
    action_waypoint_ids = {
        str(action["id"]): str(action["waypoint_id"])
        for action in actions
        if action.get("id") and action.get("waypoint_id")
    }
    eligible_action_waypoints = selected if clone_halo_actions else core
    eligible_parent_ids = {
        action_id
        for action_id, waypoint_id in action_waypoint_ids.items()
        if waypoint_id in eligible_action_waypoints
    }
    excluded_triggered_actions, exclusion_reason = resolve_triggered_action_exclusions(
        metadata,
        excluded_triggered_action_ids or [],
        triggered_action_exclusion_reason,
        eligible_parent_ids=eligible_parent_ids,
    )
    selected_connectivity_edges = [
        edge
        for edge in graph.edges
        if edge.id.from_waypoint in selected and edge.id.to_waypoint in selected
    ]
    selected_selection_only_edges = [
        edge
        for edge in selected_connectivity_edges
        if (edge.id.from_waypoint, edge.id.to_waypoint) in selection_only_keys
    ]
    selected_edges = (
        selected_connectivity_edges
        if include_selection_only_edges
        else [
            edge
            for edge in selected_connectivity_edges
            if (edge.id.from_waypoint, edge.id.to_waypoint) not in selection_only_keys
        ]
    )
    edge_disposition = (
        "included_in_walk_public_annotations_only"
        if include_selection_only_edges
        else "excluded_from_bundle_and_walk"
    )

    return {
        "schema_version": 4,
        "zone_name": zone_name,
        "polygon": polygon,
        "halo_hops": halo_hops,
        "clone_halo_actions": clone_halo_actions,
        "excluded_triggered_action_ids": [
            str(action["id"]) for action in excluded_triggered_actions
        ],
        "triggered_action_exclusion_reason": exclusion_reason,
        "selection_cleanup": {
            "exclude_unanchored_waypoints": exclude_unanchored_waypoints,
            "exclude_dependency_free_components": exclude_dependency_free_components,
            "excluded_waypoint_ids": {
                "unanchored": excluded_unanchored_ids,
                "dependency_free_components": sorted(excluded_component_ids),
            },
            "excluded_component_sizes": sorted(
                (len(component) for component in excluded_components), reverse=True
            ),
            "protected_disconnected_components": protected_components,
        },
        "core_waypoint_ids": sorted(core),
        "halo_waypoint_ids": sorted(halo),
        "coordinate_sources": source_counts,
        "edge_source_counts": edge_source_counts(selected_edges),
        "edge_transport": {
            "policy": "orbit_site_edge_field_3_selection_only",
            "include_in_walk": include_selection_only_edges,
            "manual_reapply_required": bool(selected_selection_only_edges),
            "operator_guidance": (
                "After Orbit import, verify every listed edge and reapply its environment and "
                "travel settings. Included edges may import as ordinary edges with reset UI "
                "settings; excluded edges must be recreated in Orbit."
            ),
            "selection_only_edges": [
                {
                    "from": edge.id.from_waypoint,
                    "to": edge.id.to_waypoint,
                    "disposition": edge_disposition,
                }
                for edge in selected_selection_only_edges
            ],
        },
        "counts": {
            "core_waypoints": len(core),
            "halo_waypoints": len(halo),
            "raw_polygon_waypoints": len(raw_core),
            "baseline_selected_waypoints": len(baseline_selected),
            "unanchored_waypoints_excluded": len(excluded_unanchored_ids),
            "dependency_free_waypoints_excluded": len(excluded_component_ids),
            "dependency_free_components_excluded": len(excluded_components),
            "dependency_bearing_components_protected": len(protected_components),
            "selected_edges": len(selected_edges),
            "selected_connectivity_edges": len(selected_connectivity_edges),
            "selection_only_edges_selected": len(selected_selection_only_edges),
            "selection_only_edges_included": (
                len(selected_selection_only_edges) if include_selection_only_edges else 0
            ),
            "selection_only_edges_excluded": (
                0 if include_selection_only_edges else len(selected_selection_only_edges)
            ),
            "selection_components": len(selection_components),
            "components": len(walk_components),
            "largest_component": len(walk_components[0]) if walk_components else 0,
            "core_actions": sum(action["waypoint_id"] in core for action in actions),
            "halo_actions": sum(action["waypoint_id"] in halo for action in actions),
            "triggered_actions_explicitly_excluded": len(excluded_triggered_actions),
        },
    }


def selection_only_edge_keys(metadata: dict[str, Any]) -> set[tuple[str, str]]:
    """Read directed field-3 edge keys that need an explicit Walk transport decision."""
    transport = metadata.get("edge_transport", {})
    if not isinstance(transport, dict):
        return set()
    rows = transport.get("selection_only_edges", [])
    if not isinstance(rows, list):
        raise ValueError("edge_transport.selection_only_edges must be a list")
    keys: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, dict) or not row.get("from") or not row.get("to"):
            raise ValueError("selection-only edge must contain from and to waypoint IDs")
        key = (str(row["from"]), str(row["to"]))
        if key in keys:
            raise ValueError(f"duplicate selection-only edge: {key[0]} -> {key[1]}")
        keys.add(key)
    return keys


def selection_dependency_waypoint_ids(metadata: dict[str, Any]) -> set[str]:
    waypoint_ids = {
        str(action["waypoint_id"])
        for action in metadata.get("actions", [])
        if action.get("waypoint_id")
    }
    waypoint_ids.update(
        str(state["waypoint_id"])
        for state in metadata.get("pano_states", [])
        if state.get("waypoint_id")
    )
    for dock in metadata.get("docks", []):
        if dock.get("docked_waypoint_id"):
            waypoint_ids.add(str(dock["docked_waypoint_id"]))
        waypoint_ids.update(str(value) for value in dock.get("target_waypoint_ids", []))
    return waypoint_ids


def resolve_triggered_action_exclusions(
    metadata: dict[str, Any],
    raw_ids: object,
    raw_reason: object,
    *,
    eligible_parent_ids: set[str] | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Validate explicit, auditable exclusions of triggered SiteElements."""
    if not isinstance(raw_ids, list) or any(
        not isinstance(value, str) or not value.strip() for value in raw_ids
    ):
        raise ValueError("excluded_triggered_action_ids must be a list of non-empty strings")
    ids = [value.strip() for value in raw_ids]
    if len(set(ids)) != len(ids):
        raise ValueError("excluded_triggered_action_ids contains a duplicate ID")

    reason = str(raw_reason).strip() if raw_reason is not None else ""
    if ids and not reason:
        raise ValueError("triggered_action_exclusion_reason is required when excluding an action")
    if reason and not ids:
        raise ValueError("triggered_action_exclusion_reason requires an excluded action ID")

    by_id = {
        str(action["id"]): action
        for action in metadata.get("triggered_actions", [])
        if action.get("id")
    }
    unknown = sorted(set(ids) - set(by_id))
    if unknown:
        raise ValueError(f"excluded triggered action is not present in workspace: {unknown[0]}")
    if eligible_parent_ids is not None:
        ineligible = sorted(
            action_id
            for action_id in ids
            if str(by_id[action_id].get("parent_element_id", "")) not in eligible_parent_ids
        )
        if ineligible:
            raise ValueError(
                "excluded triggered action is not linked to a selected cloned action: "
                f"{ineligible[0]}"
            )
    return [by_id[action_id] for action_id in ids], reason or None


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
