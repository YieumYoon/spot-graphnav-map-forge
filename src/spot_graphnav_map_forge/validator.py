from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from bosdyn.api import image_pb2
from bosdyn.api.autowalk import walks_pb2
from bosdyn.api.graph_nav import map_pb2
from google.protobuf.message import DecodeError

from .actions import source_mission_ids, triggered_action_reference
from .geometry import connected_components, load_graph
from .models import ValidationReport
from .remap import (
    IDENTITY_MODE_CLONE,
    IDENTITY_MODE_ORBIT_NATIVE,
    IDENTITY_MODE_PRESERVE,
    IDENTITY_MODES,
    PRESERVABLE_ID_KINDS,
    is_orbit_native_id,
)
from .wire import decode_fields, source_token_remains, text_values


def validate_bundle(bundle: Path, write_report: bool = True) -> ValidationReport:
    bundle = bundle.expanduser().resolve()
    report = ValidationReport()
    graph_path = bundle / "graph"
    manifest_path = bundle / "clone_manifest.json"
    if not graph_path.exists():
        report.error("graph is missing")
        return report
    graph = load_graph(graph_path)
    waypoint_ids = [waypoint.id for waypoint in graph.waypoints]
    waypoint_set = set(waypoint_ids)
    if len(waypoint_ids) != len(waypoint_set):
        report.error("duplicate waypoint IDs")

    edge_keys: list[tuple[str, str]] = []
    for edge in graph.edges:
        source = edge.id.from_waypoint
        target = edge.id.to_waypoint
        edge_keys.append((source, target))
        if source not in waypoint_set or target not in waypoint_set:
            report.error(f"edge endpoint missing: {source} -> {target}")
    edge_key_set = set(edge_keys)
    if len(edge_keys) != len(edge_key_set):
        report.error("duplicate directed edge IDs")

    for waypoint in graph.waypoints:
        if not waypoint.snapshot_id:
            continue
        path = bundle / "waypoint_snapshots" / waypoint.snapshot_id
        if not path.exists():
            report.error(f"waypoint snapshot missing: {waypoint.snapshot_id}")
            continue
        snapshot = map_pb2.WaypointSnapshot()
        snapshot.ParseFromString(path.read_bytes())
        if snapshot.id != waypoint.snapshot_id:
            report.error(f"waypoint snapshot ID mismatch: {waypoint.snapshot_id}")

    for edge in graph.edges:
        if not edge.snapshot_id:
            continue
        path = bundle / "edge_snapshots" / edge.snapshot_id
        if not path.exists():
            report.error(f"edge snapshot missing: {edge.snapshot_id}")
            continue
        snapshot = map_pb2.EdgeSnapshot()
        snapshot.ParseFromString(path.read_bytes())
        if snapshot.id != edge.snapshot_id:
            report.error(f"edge snapshot ID mismatch: {edge.snapshot_id}")

    components = connected_components(graph)
    report.counts = {
        "waypoints": len(graph.waypoints),
        "edges": len(graph.edges),
        "anchors": len(graph.anchoring.anchors),
        "components": len(components),
        "largest_component": len(components[0]) if components else 0,
    }
    if len(components) > 1:
        report.warnings.append(f"cloned graph has {len(components)} connected components")

    if not manifest_path.exists():
        report.error("clone_manifest.json is missing")
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        identity_policy = manifest.get("identity_policy", {})
        if not isinstance(identity_policy, dict):
            report.error("identity_policy must be an object")
            identity_policy = {}
        identity_mode = str(identity_policy.get("mode", IDENTITY_MODE_CLONE))
        if identity_mode not in IDENTITY_MODES:
            report.error(f"unsupported identity mode: {identity_mode}")
            identity_mode = IDENTITY_MODE_CLONE
        id_mappings = manifest.get("id_mappings", {})
        if not isinstance(id_mappings, dict):
            report.error("id_mappings must be an object")
            id_mappings = {}
        for kind, raw_mapping in id_mappings.items():
            if not isinstance(raw_mapping, dict):
                report.error(f"ID mapping must be an object: {kind}")
                continue
            preserve_kind = identity_mode == IDENTITY_MODE_PRESERVE and kind in PRESERVABLE_ID_KINDS
            for source_id, output_id in raw_mapping.items():
                if not isinstance(source_id, str) or not isinstance(output_id, str):
                    report.error(f"ID mapping must contain strings: {kind}")
                    continue
                if preserve_kind and source_id != output_id:
                    report.error(f"preserve mode changed {kind} identity: {source_id}")
                if identity_mode != IDENTITY_MODE_PRESERVE and source_id == output_id:
                    report.error(f"clone mode retained {kind} identity: {source_id}")
                if identity_mode == IDENTITY_MODE_ORBIT_NATIVE and not is_orbit_native_id(
                    kind, output_id
                ):
                    report.error(f"Orbit-native mode emitted incompatible {kind} ID: {output_id}")
        if identity_mode == IDENTITY_MODE_PRESERVE:
            report.warnings.append(
                "bundle preserves shared GraphNav/SiteElement identities; Orbit coexistence and "
                "deletion lifecycle remain an import-time experiment"
            )
        edge_transport = manifest.get("edge_transport", {})
        included_field_3_edges = edge_transport.get("selection_only_edges_included", [])
        excluded_field_3_edges = edge_transport.get("selection_only_edges_excluded", [])
        for row in included_field_3_edges:
            key = (str(row.get("new_from", "")), str(row.get("new_to", "")))
            if key not in edge_key_set:
                report.error(f"included field-3 edge missing from cloned graph: {key}")
        for row in excluded_field_3_edges:
            key = (str(row.get("new_from", "")), str(row.get("new_to", "")))
            if key in edge_key_set:
                report.error(f"excluded field-3 edge present in cloned graph: {key}")
        if manifest.get("counts", {}).get("selection_only_edges_included", 0) != len(
            included_field_3_edges
        ):
            report.error("field-3 included-edge count does not match manifest records")
        if manifest.get("counts", {}).get("selection_only_edges_excluded", 0) != len(
            excluded_field_3_edges
        ):
            report.error("field-3 excluded-edge count does not match manifest records")
        field_3_count = len(included_field_3_edges) + len(excluded_field_3_edges)
        if field_3_count:
            disposition = "included" if included_field_3_edges else "excluded"
            report.warnings.append(
                f"{field_3_count} Orbit field-3 edge(s) were {disposition}; verify and "
                "reapply their environment/travel settings in Orbit after import"
            )
        actions = manifest.get("actions", [])
        action_image_count = 0
        external_dependency_actions = 0
        source_mission_provenance_actions = 0
        explicit_relocalizations = 0
        new_action_ids: set[str] = set()
        for action in actions:
            source_element_id = action["source_element_id"]
            new_element_id = action["new_element_id"]
            source_waypoint_id = action["source_waypoint_id"]
            new_waypoint_id = action["new_waypoint_id"]
            if new_element_id in new_action_ids:
                report.error(f"duplicate cloned action ID: {new_element_id}")
            new_action_ids.add(new_element_id)
            if new_waypoint_id not in waypoint_set:
                report.error(f"cloned action waypoint missing from graph: {new_waypoint_id}")

            payload_path = bundle / action["cloned_payload"]
            if not payload_path.exists():
                report.error(f"cloned action payload missing: {source_element_id}")
            else:
                payload = payload_path.read_bytes()
                try:
                    fields = decode_fields(payload)
                    element_ids = text_values(fields, 1)
                    action_waypoint_ids = text_values(fields, 3)
                except ValueError as exc:
                    report.error(f"invalid cloned action payload {new_element_id}: {exc}")
                else:
                    if element_ids != (new_element_id,):
                        report.error(f"cloned action ID mismatch: {new_element_id}")
                    if action_waypoint_ids != (new_waypoint_id,):
                        report.error(f"cloned action waypoint mismatch: {new_element_id}")
                    observed_mission_ids = source_mission_ids(payload)
                    if observed_mission_ids != tuple(action.get("source_mission_ids", [])):
                        report.error(f"cloned action mission provenance mismatch: {new_element_id}")
                if source_token_remains(
                    payload, source_element_id.encode(), new_element_id.encode()
                ):
                    report.error(
                        f"source action ID leaked into cloned payload: {source_element_id}"
                    )
                if source_token_remains(
                    payload, source_waypoint_id.encode(), new_waypoint_id.encode()
                ):
                    report.error(
                        "source waypoint ID leaked into cloned action payload: "
                        f"{source_waypoint_id}"
                    )
            if action.get("external_uuid_references"):
                external_dependency_actions += 1
            if action.get("source_mission_ids"):
                source_mission_provenance_actions += 1
            if action.get("has_explicit_relocalization"):
                explicit_relocalizations += 1
            for image in action.get("images", []):
                action_image_count += 1
                image_path = bundle / image["cloned_path"]
                if not image_path.exists():
                    report.error(f"cloned action image missing: {image['cloned_path']}")
                    continue
                if source_element_id != new_element_id and source_element_id in image_path.name:
                    report.error(f"source action ID leaked into image name: {image_path.name}")
                image_payload = image_pb2.Image()
                try:
                    image_payload.ParseFromString(image_path.read_bytes())
                except Exception as exc:  # protobuf uses implementation-specific decode errors
                    report.error(f"invalid cloned action image {image['cloned_path']}: {exc}")
                else:
                    if not image_payload.data:
                        report.error(f"cloned action image has no data: {image['cloned_path']}")
        report.counts["actions_cloned"] = len(actions)
        report.counts["action_images_cloned"] = action_image_count
        report.counts["actions_with_external_uuid_references"] = external_dependency_actions
        report.counts["actions_with_source_mission_provenance"] = source_mission_provenance_actions
        report.counts["explicit_relocalizations_cloned"] = explicit_relocalizations
        triggered_actions = manifest.get("triggered_actions", [])
        triggered_image_count = 0
        for action in triggered_actions:
            source_element_id = action["source_element_id"]
            new_element_id = action["new_element_id"]
            source_parent_id = action["source_parent_element_id"]
            new_parent_id = action["new_parent_element_id"]
            if new_element_id in new_action_ids:
                report.error(f"duplicate cloned action ID: {new_element_id}")
            new_action_ids.add(new_element_id)
            if new_parent_id not in {row["new_element_id"] for row in actions}:
                report.error(
                    "triggered AI inspection parent is not a selected cloned action: "
                    f"{new_parent_id}"
                )
            payload_path = bundle / action["cloned_payload"]
            if not payload_path.exists():
                report.error(f"cloned triggered AI inspection payload missing: {source_element_id}")
                continue
            payload = payload_path.read_bytes()
            try:
                fields = decode_fields(payload)
                element_ids = text_values(fields, 1)
                reference = triggered_action_reference(payload)
            except ValueError as exc:
                report.error(f"invalid cloned triggered AI inspection {new_element_id}: {exc}")
                continue
            if element_ids != (new_element_id,):
                report.error(f"cloned triggered AI inspection ID mismatch: {new_element_id}")
            expected_reference = (new_parent_id, action["trigger_image_service"])
            if reference != expected_reference:
                report.error(
                    f"cloned triggered AI inspection parent reference mismatch: {new_element_id}"
                )
            observed_mission_ids = source_mission_ids(payload)
            if observed_mission_ids != tuple(action.get("source_mission_ids", [])):
                report.error(
                    f"cloned triggered AI inspection mission provenance mismatch: {new_element_id}"
                )
            for source_id, new_id, label in (
                (source_element_id, new_element_id, "action"),
                (source_parent_id, new_parent_id, "parent action"),
            ):
                if source_token_remains(payload, source_id.encode(), new_id.encode()):
                    report.error(
                        f"source {label} ID leaked into cloned triggered AI inspection: {source_id}"
                    )
            for image in action.get("images", []):
                triggered_image_count += 1
                image_path = bundle / image["cloned_path"]
                if not image_path.exists():
                    report.error(
                        f"cloned triggered AI inspection image missing: {image['cloned_path']}"
                    )
                    continue
                image_payload = image_pb2.Image()
                try:
                    image_payload.ParseFromString(image_path.read_bytes())
                except Exception as exc:  # protobuf uses implementation-specific decode errors
                    report.error(
                        "invalid cloned triggered AI inspection image "
                        f"{image['cloned_path']}: {exc}"
                    )
                else:
                    if not image_payload.data:
                        report.error(
                            "cloned triggered AI inspection image has no data: "
                            f"{image['cloned_path']}"
                        )
        report.counts["triggered_actions_cloned"] = len(triggered_actions)
        report.counts["triggered_action_images_cloned"] = triggered_image_count
        excluded_triggered_actions = manifest.get("triggered_actions_excluded", [])
        excluded_source_ids: set[str] = set()
        for action in excluded_triggered_actions:
            source_element_id = str(action.get("source_element_id", ""))
            if not source_element_id:
                report.error("excluded triggered AI inspection has no source element ID")
                continue
            if source_element_id in excluded_source_ids:
                report.error(f"duplicate excluded triggered AI inspection ID: {source_element_id}")
            excluded_source_ids.add(source_element_id)
            if not str(action.get("reason", "")).strip():
                report.error(
                    f"excluded triggered AI inspection has no audit reason: {source_element_id}"
                )
            if action.get("disposition") != "not_cloned_explicit_plan_exclusion":
                report.error(
                    f"excluded triggered AI inspection has invalid disposition: {source_element_id}"
                )
        cloned_source_ids = {str(action["source_element_id"]) for action in triggered_actions}
        overlap = sorted(excluded_source_ids & cloned_source_ids)
        if overlap:
            report.error(f"triggered AI inspection is both cloned and excluded: {overlap[0]}")
        planned_exclusions = set(
            manifest.get("selection", {}).get("excluded_triggered_action_ids", [])
        )
        if excluded_source_ids != planned_exclusions:
            report.error("excluded triggered AI inspection manifest does not match selection")
        report.counts["triggered_actions_explicitly_excluded"] = len(excluded_triggered_actions)
        if triggered_actions:
            report.warnings.append(
                f"{len(triggered_actions)} triggered AI inspection(s) are preserved in the "
                "bundle, but public Walk export cannot encode their parent trigger linkage"
            )
        if excluded_triggered_actions:
            report.warnings.append(
                f"{len(excluded_triggered_actions)} triggered AI inspection(s) were explicitly "
                "excluded by the audited plan"
            )
        if actions and not manifest.get("action_payload_identities_validated", False):
            if manifest.get("schema_version", 0) >= 3:
                report.error("manifest does not confirm action payload identity validation")
            elif not manifest.get("action_payloads_rewritten", False):
                report.error("manifest does not confirm action payload ID rewriting")
        if (
            actions
            and identity_mode != IDENTITY_MODE_PRESERVE
            and not manifest.get("action_payloads_rewritten", False)
        ):
            report.error("clone mode does not confirm action payload ID rewriting")
        if external_dependency_actions:
            report.warnings.append(
                f"{external_dependency_actions} cloned action(s) retain unclassified UUID "
                "references"
            )
        if not manifest.get("action_ingestion_ready", False):
            if identity_mode == IDENTITY_MODE_PRESERVE:
                report.warnings.append(
                    "action payload identities are preserved, but Orbit reuse and ingestion "
                    "remain unverified"
                )
            else:
                report.warnings.append(
                    "action payload identities are cloned, but fleet-manager ingestion remains "
                    "unverified"
                )

        docks = manifest.get("docks", [])
        new_dock_record_ids: set[str] = set()
        for dock in docks:
            new_record_id = dock["new_record_id"]
            if new_record_id in new_dock_record_ids:
                report.error(f"duplicate cloned dock record ID: {new_record_id}")
            new_dock_record_ids.add(new_record_id)
            new_docked_waypoint_id = dock["new_docked_waypoint_id"]
            if new_docked_waypoint_id not in waypoint_set:
                report.error(f"cloned dock waypoint missing from graph: {new_docked_waypoint_id}")
            target_path = bundle / dock["cloned_target"]
            if not target_path.exists():
                report.error(f"cloned dock target missing: {dock['source_record_id']}")
                continue
            target_payload = target_path.read_bytes()
            target = walks_pb2.Target()
            try:
                target.ParseFromString(target_payload)
            except DecodeError as exc:
                report.error(f"invalid cloned dock target {new_record_id}: {exc}")
                continue
            target_waypoint_ids = _target_waypoint_ids(target)
            if target_waypoint_ids != tuple(dock["new_target_waypoint_ids"]):
                report.error(f"cloned dock target waypoint mismatch: {new_record_id}")
            missing_target_ids = set(target_waypoint_ids) - waypoint_set
            if missing_target_ids:
                report.error(
                    "cloned dock target waypoint missing from graph: "
                    f"{next(iter(missing_target_ids))}"
                )
            source_ids = {
                dock["source_docked_waypoint_id"],
                *dock["source_target_waypoint_ids"],
            }
            waypoint_mappings = id_mappings.get("waypoint", {})
            if not isinstance(waypoint_mappings, dict):
                waypoint_mappings = {}
            leaked_source_ids = [
                source_id
                for source_id in source_ids
                if waypoint_mappings.get(source_id, source_id) != source_id
                and source_id.encode() in target_payload
            ]
            if leaked_source_ids:
                report.error(
                    f"source waypoint ID leaked into cloned dock target: {leaked_source_ids[0]}"
                )
        report.counts["docks_cloned"] = len(docks)
        report.counts["docks_boundary_skipped"] = len(manifest.get("docks_skipped", []))
        if docks and not manifest.get("dock_target_identities_validated", False):
            if manifest.get("schema_version", 0) >= 3:
                report.error("manifest does not confirm dock target identity validation")
            elif not manifest.get("dock_targets_rewritten", False):
                report.error("manifest does not confirm dock target ID rewriting")
        if (
            docks
            and identity_mode != IDENTITY_MODE_PRESERVE
            and not manifest.get("dock_targets_rewritten", False)
        ):
            report.error("clone mode does not confirm dock target ID rewriting")

        raw_waypoint_mappings = id_mappings.get("waypoint", {})
        old_waypoint_ids = (
            set(raw_waypoint_mappings) if isinstance(raw_waypoint_mappings, dict) else set()
        )
        if identity_mode == IDENTITY_MODE_PRESERVE:
            missing_preserved = old_waypoint_ids - waypoint_set
            if missing_preserved:
                report.error(
                    f"preserved source waypoint missing from graph: {next(iter(missing_preserved))}"
                )
        else:
            leaked = waypoint_set & old_waypoint_ids
            if leaked:
                report.error(f"source waypoint IDs leaked into clone: {next(iter(leaked))}")

    if write_report:
        (bundle / "validation_report.json").write_text(
            json.dumps(asdict(report), indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return report


def _target_waypoint_ids(target: walks_pb2.Target) -> tuple[str, ...]:
    kind = target.WhichOneof("target")
    if kind == "navigate_to":
        return (target.navigate_to.destination_waypoint_id,)
    if kind == "navigate_route":
        return tuple(target.navigate_route.route.waypoint_id)
    return ()
