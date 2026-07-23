from __future__ import annotations

import json
from pathlib import Path

from bosdyn.api.autowalk import walks_pb2
from bosdyn.api.graph_nav import map_pb2

from .actions import clone_site_element, clone_triggered_site_element
from .archive import BackupArchive
from .clone import clone_edge_snapshot, clone_subgraph, clone_waypoint_snapshot
from .geometry import load_graph
from .planner import resolve_triggered_action_exclusions, selection_only_edge_keys
from .remap import (
    IDENTITY_MODE_CLONE,
    IDENTITY_MODE_ORBIT_NATIVE,
    IDENTITY_MODE_PRESERVE,
    IDENTITY_MODES,
    PRESERVABLE_ID_KINDS,
)
from .wire import bytes_values, decode_fields


def build_clone(
    workspace: Path,
    plan_path: Path,
    out: Path,
    *,
    identity_mode: str | None = None,
    clone_name: str | None = None,
) -> dict[str, object]:
    workspace = workspace.expanduser().resolve()
    plan_path = plan_path.expanduser().resolve()
    out = out.expanduser().resolve()
    if out.exists():
        raise ValueError(f"output already exists: {out}")

    metadata = json.loads((workspace / "workspace.json").read_text(encoding="utf-8"))
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    graph = load_graph(workspace / "graph")
    core = set(plan["core_waypoint_ids"])
    halo = set(plan["halo_waypoint_ids"])
    selected = core | halo
    plan_clone_name = str(plan["zone_name"])
    resolved_clone_name = clone_name.strip() if clone_name is not None else plan_clone_name
    if not resolved_clone_name:
        raise ValueError("clone_name must not be empty")
    clone_name_source = "build_override" if clone_name is not None else "plan"
    plan_identity_mode = str(plan.get("identity_mode", IDENTITY_MODE_CLONE))
    resolved_identity_mode = identity_mode or plan_identity_mode
    if resolved_identity_mode not in IDENTITY_MODES:
        raise ValueError("identity_mode must be one of: " + ", ".join(sorted(IDENTITY_MODES)))
    identity_mode_source = "build_override" if identity_mode is not None else "plan"
    selection_only_keys = selection_only_edge_keys(metadata)
    selected_selection_only_keys = {
        key for key in selection_only_keys if key[0] in selected and key[1] in selected
    }
    declared_selection_only_keys = {
        (str(row.get("from", "")), str(row.get("to", "")))
        for row in plan.get("edge_transport", {}).get("selection_only_edges", [])
        if isinstance(row, dict)
    }
    if selected_selection_only_keys != declared_selection_only_keys:
        raise ValueError(
            "plan selection-only edge policy does not match workspace; regenerate the plan"
        )
    include_selection_only_edges = bool(
        plan.get("edge_transport", {}).get("include_in_walk", False)
    )
    excluded_edge_keys = set() if include_selection_only_edges else selection_only_keys
    result = clone_subgraph(
        graph,
        selected,
        resolved_clone_name,
        excluded_edge_keys=excluded_edge_keys,
        identity_mode=resolved_identity_mode,
    )
    snapshot_sources = metadata["snapshot_sources"]
    copied_waypoint_snapshots = 0
    copied_edge_snapshots = 0
    source_backup = Path(metadata["source_backup"])
    selected_actions = [
        action
        for action in metadata["actions"]
        if action["waypoint_id"] in (selected if plan.get("clone_halo_actions") else core)
    ]
    selected_action_ids = {str(action["id"]) for action in selected_actions}
    excluded_triggered_actions, exclusion_reason = resolve_triggered_action_exclusions(
        metadata,
        plan.get("excluded_triggered_action_ids", []),
        plan.get("triggered_action_exclusion_reason"),
        eligible_parent_ids=selected_action_ids,
    )
    excluded_triggered_action_ids = {str(action["id"]) for action in excluded_triggered_actions}
    selected_triggered_actions = [
        action
        for action in metadata.get("triggered_actions", [])
        if action.get("parent_element_id") in selected_action_ids
        and str(action.get("id", "")) not in excluded_triggered_action_ids
    ]

    out.mkdir(parents=True)
    waypoint_dir = out / "waypoint_snapshots"
    edge_dir = out / "edge_snapshots"
    action_dir = out / "action_payloads"
    image_dir = action_dir / "images"
    dock_dir = out / "dock_payloads"
    waypoint_dir.mkdir()
    edge_dir.mkdir()
    action_dir.mkdir()
    image_dir.mkdir()
    dock_dir.mkdir()
    (out / "graph").write_bytes(result.graph.SerializeToString())

    cloned_actions: list[dict[str, object]] = []
    cloned_triggered_actions: list[dict[str, object]] = []
    cloned_docks: list[dict[str, object]] = []
    skipped_docks: list[dict[str, object]] = []

    with BackupArchive(source_backup) as archive:
        for old_id, new_id in result.remapper.mappings.get("waypoint_snapshot", {}).items():
            source_path = snapshot_sources["waypoint"].get(old_id)
            if not source_path:
                continue
            payload = clone_waypoint_snapshot(archive.read(source_path), new_id)
            (waypoint_dir / new_id).write_bytes(payload)
            copied_waypoint_snapshots += 1

        for old_id, new_id in result.remapper.mappings.get("edge_snapshot", {}).items():
            source_path = snapshot_sources["edge"].get(old_id)
            if not source_path:
                continue
            payload = clone_edge_snapshot(archive.read(source_path), new_id)
            (edge_dir / new_id).write_bytes(payload)
            copied_edge_snapshots += 1

        for action in selected_actions:
            old_element_id = action["id"]
            new_element_id = result.remapper.map("site_element", old_element_id)
            new_waypoint_id = result.remapper.map("waypoint", action["waypoint_id"])
            cloned = clone_site_element(
                archive.read(action["source_path"]),
                new_element_id=new_element_id,
                new_waypoint_id=new_waypoint_id,
            )
            payload_name = f"{new_element_id}.site_element"
            (action_dir / payload_name).write_bytes(cloned.payload)
            images: list[dict[str, str]] = []
            for source_path in action["image_paths"]:
                source_name = Path(source_path).name
                destination_name = _clone_image_name(
                    source_name=source_name,
                    old_element_id=old_element_id,
                    new_element_id=new_element_id,
                )
                image_payload = archive.read(source_path)
                changed_source_tokens = [
                    token
                    for old_id, new_id, token in (
                        (old_element_id, new_element_id, old_element_id.encode()),
                        (action["waypoint_id"], new_waypoint_id, action["waypoint_id"].encode()),
                    )
                    if old_id != new_id and token in image_payload
                ]
                if changed_source_tokens:
                    raise ValueError(
                        "action image contains an identity reference requiring a schema: "
                        f"{source_path}"
                    )
                (image_dir / destination_name).write_bytes(image_payload)
                images.append(
                    {
                        "source_path": source_path,
                        "cloned_path": f"action_payloads/images/{destination_name}",
                    }
                )
            cloned_actions.append(
                {
                    "source_element_id": old_element_id,
                    "new_element_id": new_element_id,
                    "name": action["name"],
                    "source_waypoint_id": action["waypoint_id"],
                    "new_waypoint_id": new_waypoint_id,
                    "cloned_payload": f"action_payloads/{payload_name}",
                    "replacement_counts": cloned.replacement_counts,
                    "source_mission_ids": list(cloned.source_mission_ids),
                    "external_uuid_references": list(cloned.external_uuid_references),
                    "has_explicit_relocalization": bool(action.get("has_explicit_relocalization")),
                    "dependency_status": (
                        "external_references_preserved"
                        if cloned.external_uuid_references
                        else (
                            "source_mission_provenance_preserved"
                            if cloned.source_mission_ids
                            else "self_contained"
                        )
                    ),
                    "images": images,
                    "clone_status": (
                        "identity_preserved"
                        if resolved_identity_mode == IDENTITY_MODE_PRESERVE
                        else "offline_rewritten"
                    ),
                    "ingestion_status": "unverified",
                    "walk_export_status": "eligible",
                }
            )

        for action in selected_triggered_actions:
            old_element_id = str(action["id"])
            old_parent_element_id = str(action["parent_element_id"])
            new_element_id = result.remapper.map("site_element", old_element_id)
            new_parent_element_id = result.remapper.map("site_element", old_parent_element_id)
            cloned = clone_triggered_site_element(
                archive.read(action["source_path"]),
                new_element_id=new_element_id,
                new_parent_element_id=new_parent_element_id,
            )
            payload_name = f"{new_element_id}.site_element"
            (action_dir / payload_name).write_bytes(cloned.payload)
            images: list[dict[str, str]] = []
            for source_path in action.get("image_paths", []):
                source_name = Path(source_path).name
                destination_name = _clone_image_name(
                    source_name=source_name,
                    old_element_id=old_element_id,
                    new_element_id=new_element_id,
                )
                image_payload = archive.read(source_path)
                if any(
                    old_id != new_id and old_id.encode() in image_payload
                    for old_id, new_id in (
                        (old_element_id, new_element_id),
                        (old_parent_element_id, new_parent_element_id),
                    )
                ):
                    raise ValueError(
                        "triggered AI inspection image contains an identity reference requiring a "
                        f"schema: {source_path}"
                    )
                (image_dir / destination_name).write_bytes(image_payload)
                images.append(
                    {
                        "source_path": source_path,
                        "cloned_path": f"action_payloads/images/{destination_name}",
                    }
                )
            cloned_triggered_actions.append(
                {
                    "source_element_id": old_element_id,
                    "new_element_id": new_element_id,
                    "name": action["name"],
                    "source_parent_element_id": old_parent_element_id,
                    "new_parent_element_id": new_parent_element_id,
                    "trigger_image_service": cloned.trigger_image_service,
                    "cloned_payload": f"action_payloads/{payload_name}",
                    "replacement_counts": cloned.replacement_counts,
                    "source_mission_ids": list(cloned.source_mission_ids),
                    "external_uuid_references": list(cloned.external_uuid_references),
                    "images": images,
                    "clone_status": (
                        "identity_preserved"
                        if resolved_identity_mode == IDENTITY_MODE_PRESERVE
                        else "offline_rewritten"
                    ),
                    "walk_export_status": "blocked_missing_public_trigger_link_schema",
                }
            )

        for dock in metadata.get("docks", []):
            source_waypoint_ids = {
                dock["docked_waypoint_id"],
                *dock["target_waypoint_ids"],
            }
            if not source_waypoint_ids & selected:
                continue
            missing_waypoint_ids = sorted(source_waypoint_ids - selected)
            if missing_waypoint_ids:
                skipped_docks.append(
                    {
                        "source_record_id": dock["id"],
                        "dock_id": dock["dock_id"],
                        "source_waypoint_ids": sorted(source_waypoint_ids),
                        "missing_selected_waypoint_ids": missing_waypoint_ids,
                        "reason": "selection_boundary",
                    }
                )
                continue

            source_payload = archive.read(dock["source_path"])
            target = _clone_dock_target(source_payload, result.remapper.mappings["waypoint"])
            cloned_target_ids = _target_waypoint_ids(target)
            expected_new_target_ids = tuple(
                result.remapper.map("waypoint", waypoint_id)
                for waypoint_id in dock["target_waypoint_ids"]
            )
            if cloned_target_ids != expected_new_target_ids:
                raise ValueError(f"cloned dock target mismatch: {dock['id']}")
            new_record_id = result.remapper.map("site_dock", dock["id"])
            payload_name = f"{new_record_id}.target"
            (dock_dir / payload_name).write_bytes(target.SerializeToString(deterministic=True))
            cloned_docks.append(
                {
                    "source_record_id": dock["id"],
                    "new_record_id": new_record_id,
                    "dock_id": dock["dock_id"],
                    "source_docked_waypoint_id": dock["docked_waypoint_id"],
                    "new_docked_waypoint_id": result.remapper.map(
                        "waypoint", dock["docked_waypoint_id"]
                    ),
                    "source_target_waypoint_ids": list(dock["target_waypoint_ids"]),
                    "new_target_waypoint_ids": list(expected_new_target_ids),
                    "cloned_target": f"dock_payloads/{payload_name}",
                    "clone_status": (
                        "identity_preserved"
                        if resolved_identity_mode == IDENTITY_MODE_PRESERVE
                        else "offline_rewritten"
                    ),
                }
            )

    manifest: dict[str, object] = {
        "schema_version": 3,
        "clone_name": resolved_clone_name,
        "identity_policy": {
            "mode": resolved_identity_mode,
            "source": identity_mode_source,
            "plan_mode": plan_identity_mode,
            "clone_name_source": clone_name_source,
            "plan_clone_name": plan_clone_name,
            "id_format": (
                "spot_native_graphnav_and_uuid4_orbit_objects"
                if resolved_identity_mode == IDENTITY_MODE_ORBIT_NATIVE
                else "source_preserved"
                if resolved_identity_mode == IDENTITY_MODE_PRESERVE
                else "uuid5"
            ),
            "preserved_id_kinds": (
                sorted(PRESERVABLE_ID_KINDS)
                if resolved_identity_mode == IDENTITY_MODE_PRESERVE
                else []
            ),
            "new_id_kinds": (
                ["walk", "server_recording"]
                if resolved_identity_mode == IDENTITY_MODE_PRESERVE
                else [
                    "waypoint",
                    "waypoint_snapshot",
                    "edge_snapshot",
                    "site_element",
                    "site_dock",
                    "walk",
                    "server_recording",
                ]
            ),
            "walk_identity": "new_transport_container",
            "recording_identity": "assigned_by_orbit_at_import",
            "site_dock_record_transport": ("manifest_only_public_walk_dock_has_no_record_uuid"),
        },
        "source": {
            "backup": str(source_backup),
            "site_map": metadata["site_map"],
            "workspace": str(workspace),
            "plan": str(plan_path),
        },
        "selection": {
            "core_waypoint_ids": sorted(core),
            "halo_waypoint_ids": sorted(halo),
            "clone_halo_actions": bool(plan.get("clone_halo_actions")),
            "excluded_triggered_action_ids": sorted(excluded_triggered_action_ids),
            "cleanup": plan.get("selection_cleanup", {}),
        },
        "edge_transport": {
            "policy": "orbit_site_edge_field_3_selection_only",
            "include_in_walk": include_selection_only_edges,
            "manual_reapply_required": bool(selected_selection_only_keys),
            "operator_guidance": (
                "After Orbit import, verify every listed edge and reapply its environment and "
                "travel settings. Included edges may import as ordinary edges with reset UI "
                "settings; excluded edges must be recreated in Orbit."
            ),
            "selection_only_edges_excluded": [
                {
                    "source_from": source,
                    "source_to": target,
                    "new_from": result.remapper.map("waypoint", source),
                    "new_to": result.remapper.map("waypoint", target),
                    "disposition": "excluded_from_bundle_and_walk",
                }
                for source, target in sorted(
                    set() if include_selection_only_edges else selected_selection_only_keys
                )
            ],
            "selection_only_edges_included": [
                {
                    "source_from": source,
                    "source_to": target,
                    "new_from": result.remapper.map("waypoint", source),
                    "new_to": result.remapper.map("waypoint", target),
                    "disposition": "included_in_walk_public_annotations_only",
                }
                for source, target in sorted(
                    selected_selection_only_keys if include_selection_only_edges else set()
                )
            ],
        },
        "id_mappings": result.remapper.mappings,
        "counts": {
            "waypoints": len(result.graph.waypoints),
            "edges": len(result.graph.edges),
            "selection_only_edges_included": (
                len(selected_selection_only_keys) if include_selection_only_edges else 0
            ),
            "selection_only_edges_excluded": (
                0 if include_selection_only_edges else len(selected_selection_only_keys)
            ),
            "waypoint_snapshots": copied_waypoint_snapshots,
            "edge_snapshots": copied_edge_snapshots,
            "actions_cloned": len(cloned_actions),
            "action_images_cloned": sum(len(action["images"]) for action in cloned_actions),
            "explicit_relocalizations_cloned": sum(
                bool(action["has_explicit_relocalization"]) for action in cloned_actions
            ),
            "triggered_actions_cloned": len(cloned_triggered_actions),
            "triggered_actions_explicitly_excluded": len(excluded_triggered_actions),
            "triggered_action_images_cloned": sum(
                len(action["images"]) for action in cloned_triggered_actions
            ),
            "docks_cloned": len(cloned_docks),
            "docks_boundary_skipped": len(skipped_docks),
        },
        "edge_source_counts": _edge_source_counts(result.graph),
        "actions": cloned_actions,
        "triggered_actions": cloned_triggered_actions,
        "triggered_actions_excluded": [
            {
                "source_element_id": str(action["id"]),
                "name": action.get("name"),
                "source_parent_element_id": action.get("parent_element_id"),
                "reason": exclusion_reason,
                "disposition": "not_cloned_explicit_plan_exclusion",
            }
            for action in excluded_triggered_actions
        ],
        "docks": cloned_docks,
        "docks_skipped": skipped_docks,
        "action_payloads_rewritten": resolved_identity_mode != IDENTITY_MODE_PRESERVE,
        "action_payload_identities_validated": True,
        "dock_targets_rewritten": resolved_identity_mode != IDENTITY_MODE_PRESERVE,
        "dock_target_identities_validated": True,
        "action_ingestion_ready": False,
        "walk_target_opaque_profile": metadata.get("walk_target_opaque_profile"),
    }
    (out / "clone_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _clone_image_name(source_name: str, old_element_id: str, new_element_id: str) -> str:
    if old_element_id in source_name:
        return source_name.replace(old_element_id, new_element_id, 1)
    return f"{new_element_id}-{source_name}"


def _edge_source_counts(graph: map_pb2.Graph) -> dict[str, int]:
    enum = map_pb2.Edge.Annotations.DESCRIPTOR.fields_by_name["edge_source"].enum_type
    names = {value.number: value.name for value in enum.values}
    counts: dict[str, int] = {}
    for edge in graph.edges:
        name = names.get(edge.annotations.edge_source, str(edge.annotations.edge_source))
        counts[name] = counts.get(name, 0) + 1
    return counts


def _clone_dock_target(
    site_dock_payload: bytes, waypoint_mappings: dict[str, str]
) -> walks_pb2.Target:
    fields = decode_fields(site_dock_payload)
    target_values = bytes_values(fields, 4)
    if len(target_values) != 1:
        raise ValueError("SiteDock must contain exactly one public Target field")
    target = walks_pb2.Target()
    target.ParseFromString(target_values[0])
    kind = target.WhichOneof("target")
    if kind == "navigate_to":
        old_id = target.navigate_to.destination_waypoint_id
        target.navigate_to.destination_waypoint_id = waypoint_mappings[old_id]
    elif kind == "navigate_route":
        route = target.navigate_route.route
        for index, old_id in enumerate(route.waypoint_id):
            route.waypoint_id[index] = waypoint_mappings[old_id]
        for edge_id in route.edge_id:
            edge_id.from_waypoint = waypoint_mappings[edge_id.from_waypoint]
            edge_id.to_waypoint = waypoint_mappings[edge_id.to_waypoint]
    else:
        raise ValueError(f"unsupported SiteDock target kind: {kind}")
    return target


def _target_waypoint_ids(target: walks_pb2.Target) -> tuple[str, ...]:
    kind = target.WhichOneof("target")
    if kind == "navigate_to":
        return (target.navigate_to.destination_waypoint_id,)
    if kind == "navigate_route":
        return tuple(target.navigate_route.route.waypoint_id)
    return ()
