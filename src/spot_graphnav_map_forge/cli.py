from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .archive import BackupArchive
from .audit import create_preservation_audit
from .backup import (
    graph_with_layout_projection,
    list_actions,
    list_docks,
    list_pano_states,
    list_site_maps,
    reconstruct_final_graph,
    resolve_site_map,
    walk_target_opaque_profile,
)
from .builder import build_clone
from .geometry import waypoint_coordinates
from .planner import create_plan
from .validator import validate_bundle
from .walk_archive import export_walk_archive, validate_walk_archive
from .web import serve_editor
from .wire import decode_fields


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))
    return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spot-map-forge",
        description="Offline-first Spot GraphNav map inspection and cloning.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="List site maps in a backup.")
    inspect_parser.add_argument("backup", type=Path)
    inspect_parser.add_argument("--json", action="store_true")
    inspect_parser.set_defaults(handler=_inspect)

    wire_parser = subparsers.add_parser(
        "wire-dump", help="Inspect low-level protobuf envelope fields."
    )
    wire_parser.add_argument("backup", type=Path)
    wire_parser.add_argument("member")
    wire_parser.set_defaults(handler=_wire_dump)

    prepare_parser = subparsers.add_parser(
        "prepare", help="Reconstruct one final site graph into an offline workspace."
    )
    prepare_parser.add_argument("backup", type=Path)
    prepare_parser.add_argument("--map", dest="map_query", required=True)
    prepare_parser.add_argument("--out", type=Path, required=True)
    prepare_parser.set_defaults(handler=_prepare)

    plan_parser = subparsers.add_parser("plan", help="Select a zone using a polygon JSON file.")
    plan_parser.add_argument("workspace", type=Path)
    plan_parser.add_argument("--polygon", type=Path, required=True)
    plan_parser.add_argument("--zone-name", required=True)
    plan_parser.add_argument("--halo-hops", type=int, default=1)
    plan_parser.add_argument("--clone-halo-actions", action="store_true")
    plan_parser.add_argument(
        "--exclude-unanchored-waypoints",
        action="store_true",
        help="Exclude polygon/halo waypoints that cannot reach a map-layout control point.",
    )
    plan_parser.add_argument(
        "--exclude-dependency-free-components",
        action="store_true",
        help="Exclude non-largest selected components with no actions, docks, or pano state.",
    )
    plan_parser.add_argument(
        "--include-selection-only-edges",
        action="store_true",
        help=(
            "Include Orbit SiteEdge field-3 edges in the bundle/Walk. Their public GraphNav "
            "annotations are retained, but Orbit may reset the UI settings; verify and reapply "
            "them after import. The default excludes these edges."
        ),
    )
    plan_parser.add_argument(
        "--exclude-triggered-action",
        action="append",
        default=[],
        dest="excluded_triggered_action_ids",
        metavar="ID",
        help="Explicitly omit one triggered SiteElement linked to a selected action; repeatable.",
    )
    plan_parser.add_argument(
        "--triggered-action-exclusion-reason",
        help="Required audit reason when --exclude-triggered-action is used.",
    )
    plan_parser.add_argument("--out", type=Path, required=True)
    plan_parser.set_defaults(handler=_plan)

    audit_parser = subparsers.add_parser(
        "audit", help="Report dependencies and preservation risks for a split plan."
    )
    audit_parser.add_argument("workspace", type=Path)
    audit_parser.add_argument("--plan", type=Path, required=True)
    audit_parser.add_argument("--out", type=Path)
    audit_parser.set_defaults(handler=_audit)

    build_parser = subparsers.add_parser("build", help="Build an offline cloned GraphNav bundle.")
    build_parser.add_argument("workspace", type=Path)
    build_parser.add_argument("--plan", type=Path, required=True)
    build_parser.add_argument("--out", type=Path, required=True)
    build_parser.set_defaults(handler=_build)

    validate_parser = subparsers.add_parser("validate", help="Validate a cloned bundle offline.")
    validate_parser.add_argument("bundle", type=Path)
    validate_parser.set_defaults(handler=_validate)

    export_walk_parser = subparsers.add_parser(
        "export-walk",
        help="Package a cloned bundle as an uploadable public Autowalk .walk.zip archive.",
    )
    export_walk_parser.add_argument("bundle", type=Path)
    export_walk_parser.add_argument("--out", type=Path, required=True)
    export_walk_parser.add_argument(
        "--name",
        help=(
            "Archive/map/mission/group name and deterministic Walk-ID seed; defaults to the "
            "clone name in the bundle manifest."
        ),
    )
    export_walk_parser.add_argument(
        "--recording-name",
        help=(
            "Replace every exported waypoint client-metadata session name. "
            "Source geometry, timestamps, and client identity are preserved."
        ),
    )
    export_walk_parser.add_argument(
        "--template-archive",
        type=Path,
        help="Optional tablet .walk.zip used only to copy opaque autowalk_metadata.",
    )
    export_walk_parser.add_argument(
        "--triggered-ai-mode",
        choices=("block", "fold-into-parent"),
        default="block",
        help=(
            "Triggered AI handling. The safe default blocks export; fold-into-parent is an "
            "experimental same-instance import probe and does not encode the private trigger."
        ),
    )
    export_walk_parser.set_defaults(handler=_export_walk)

    validate_walk_parser = subparsers.add_parser(
        "validate-walk", help="Validate an Autowalk .walk.zip archive offline."
    )
    validate_walk_parser.add_argument("archive", type=Path)
    validate_walk_parser.set_defaults(handler=_validate_walk)

    serve_parser = subparsers.add_parser(
        "serve", help="Run the local polygon editor for a prepared workspace."
    )
    serve_parser.add_argument("workspace", type=Path)
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8787)
    serve_parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Allow binding to a non-loopback host (not recommended).",
    )
    serve_parser.set_defaults(handler=_serve)
    return parser


def _inspect(args: argparse.Namespace) -> int:
    with BackupArchive(args.backup) as archive:
        maps = list_site_maps(archive)
        actions = list_actions(archive)
        docks = list_docks(archive)
        pano_states = list_pano_states(archive)
    map_action_ids = {
        record.id: {
            action.id for action in actions if action.waypoint_id in set(record.waypoint_ids)
        }
        for record in maps
    }
    action_counts = {record.id: len(map_action_ids[record.id]) for record in maps}
    triggered_action_counts = {
        record.id: sum(
            action.trigger_parent_element_id in map_action_ids[record.id]
            for action in actions
            if action.trigger_parent_element_id is not None
        )
        for record in maps
    }
    explicit_relocalization_counts = {
        record.id: sum(
            action.has_explicit_relocalization
            for action in actions
            if action.id in map_action_ids[record.id]
        )
        for record in maps
    }
    pano_counts = {
        record.id: sum(1 for state in pano_states if state.waypoint_id in set(record.waypoint_ids))
        for record in maps
    }
    dock_counts = {
        record.id: sum(1 for dock in docks if dock.docked_waypoint_id in set(record.waypoint_ids))
        for record in maps
    }
    data = {
        "backup": str(args.backup.expanduser().resolve()),
        "site_maps": [
            {
                "id": record.id,
                "name": record.name,
                "recordings": len(record.recording_ids),
                "waypoints": len(record.waypoint_ids),
                "actions": action_counts[record.id],
                "triggered_actions": triggered_action_counts[record.id],
                "explicit_relocalizations": explicit_relocalization_counts[record.id],
                "docks": dock_counts[record.id],
                "pano_states": pano_counts[record.id],
            }
            for record in maps
        ],
        "actions_total": len(actions),
        "triggered_actions_total": sum(
            action.trigger_parent_element_id is not None for action in actions
        ),
        "explicit_relocalizations_total": sum(
            action.has_explicit_relocalization for action in actions
        ),
        "docks_total": len(docks),
    }
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        print(f"Backup: {data['backup']}")
        for item in data["site_maps"]:
            print(
                f"- {item['name']} [{item['id']}]: "
                f"{item['waypoints']} waypoints, {item['recordings']} recordings, "
                f"{item['actions']} actions + "
                f"{item['triggered_actions']} triggered AI inspections, "
                f"{item['explicit_relocalizations']} explicit relocalizations, "
                f"{item['docks']} docks, "
                f"{item['pano_states']} pano states"
            )
        print(f"Actions total: {data['actions_total']}")
        print(f"Triggered AI inspections total: {data['triggered_actions_total']}")
        print(f"Explicit relocalizations total: {data['explicit_relocalizations_total']}")
        print(f"Docks total: {data['docks_total']}")
    return 0


def _wire_dump(args: argparse.Namespace) -> int:
    with BackupArchive(args.backup) as archive:
        fields = decode_fields(archive.read(args.member))
    for field in fields:
        text = field.text()
        if text is not None and text.isprintable():
            rendered = repr(text if len(text) <= 160 else text[:157] + "...")
        elif isinstance(field.value, bytes):
            rendered = f"<{len(field.value)} bytes>"
        else:
            rendered = str(field.value)
        print(f"{field.number}:{field.wire_type} {rendered}")
    return 0


def _prepare(args: argparse.Namespace) -> int:
    out = args.out.expanduser().resolve()
    if out.exists():
        raise ValueError(f"output already exists: {out}")
    with BackupArchive(args.backup) as archive:
        site_map = resolve_site_map(archive, args.map_query)
        (
            graph,
            waypoint_snapshots,
            edge_snapshots,
            selection_only_edges,
        ) = reconstruct_final_graph(archive, site_map)
        selection_only_edge_keys = set(selection_only_edges)
        site_waypoint_ids = set(site_map.waypoint_ids)
        all_actions = list_actions(archive)
        actions = [action for action in all_actions if action.waypoint_id in site_waypoint_ids]
        map_action_ids = {action.id for action in actions}
        triggered_actions = [
            action for action in all_actions if action.trigger_parent_element_id in map_action_ids
        ]
        docks = [
            dock for dock in list_docks(archive) if dock.docked_waypoint_id in site_waypoint_ids
        ]
        pano_states = [
            state for state in list_pano_states(archive) if state.waypoint_id in site_waypoint_ids
        ]
        target_profile = walk_target_opaque_profile(
            archive, site_map_waypoint_ids=site_waypoint_ids
        )
        out.mkdir(parents=True)
        (out / "graph").write_bytes(graph.SerializeToString())
        action_metadata: list[dict[str, object]] = [
            {
                "id": action.id,
                "name": action.name,
                "waypoint_id": action.waypoint_id,
                "source_path": action.source_path,
                "image_paths": list(action.image_paths),
                "has_explicit_relocalization": action.has_explicit_relocalization,
            }
            for action in actions
        ]
        map_layout = None
        if site_map.layout is not None:
            map_layout = {
                "id": site_map.layout.id,
                "name": site_map.layout.name,
                "floor_plan_name": site_map.layout.floor_plan_name,
                "control_points": [
                    {
                        "waypoint_id": control_point.waypoint_id,
                        "position": list(control_point.position),
                        "rotation": list(control_point.rotation),
                    }
                    for control_point in site_map.layout.control_points
                ],
            }
        metadata = {
            "schema_version": 3,
            "source_backup": str(args.backup.expanduser().resolve()),
            "site_map": {
                "id": site_map.id,
                "name": site_map.name,
                "recording_ids": list(site_map.recording_ids),
            },
            "counts": {
                "waypoints": len(graph.waypoints),
                "edges": len(graph.edges),
                "walk_transport_edges": len(graph.edges) - len(selection_only_edges),
                "selection_only_edges": len(selection_only_edges),
                "actions": len(actions),
                "triggered_actions": len(triggered_actions),
                "explicit_relocalizations": sum(
                    action.has_explicit_relocalization for action in actions
                ),
                "docks": len(docks),
                "pano_states": len(pano_states),
            },
            "snapshot_sources": {
                "waypoint": waypoint_snapshots,
                "edge": edge_snapshots,
            },
            "edge_transport": {
                "policy": "orbit_site_edge_field_3_selection_only",
                "selection_only_reason": (
                    "Orbit SiteEdge field 3 state is not reconstructed by public Walk import; "
                    "use for coordinate propagation and waypoint selection, make an explicit "
                    "include/exclude choice in the plan, and reapply settings in Orbit after import"
                ),
                "manual_reapply_required": bool(selection_only_edges),
                "selection_only_edges": [
                    {"from": source, "to": target} for source, target in selection_only_edges
                ],
            },
            "actions": action_metadata,
            "triggered_actions": [
                {
                    "id": action.id,
                    "name": action.name,
                    "parent_element_id": action.trigger_parent_element_id,
                    "trigger_image_service": action.trigger_image_service,
                    "source_path": action.source_path,
                    "image_paths": list(action.image_paths),
                    "has_explicit_relocalization": (action.has_explicit_relocalization),
                }
                for action in triggered_actions
            ],
            "docks": [
                {
                    "id": dock.id,
                    "dock_id": dock.dock_id,
                    "docked_waypoint_id": dock.docked_waypoint_id,
                    "target_kind": dock.target_kind,
                    "target_waypoint_ids": list(dock.target_waypoint_ids),
                    "target_fingerprint": dock.target_fingerprint,
                    "source_path": dock.source_path,
                }
                for dock in docks
            ],
            "pano_states": [
                {
                    "waypoint_id": state.waypoint_id,
                    "updated_seconds": state.updated_seconds,
                    "updated_nanos": state.updated_nanos,
                    "source_path": state.source_path,
                }
                for state in pano_states
            ],
            "map_layout": map_layout,
            "walk_target_opaque_profile": (
                {
                    "selection": target_profile.selection,
                    "source_path": target_profile.source_path,
                    "source_updated": target_profile.source_updated,
                    "observed_source_records": target_profile.observed_source_records,
                    "travel_params_fields_hex": target_profile.travel_params_fields.hex(),
                    "travel_params_field_numbers": list(target_profile.travel_params_field_numbers),
                    "target_fields_hex": target_profile.target_fields.hex(),
                    "target_field_numbers": list(target_profile.target_field_numbers),
                }
                if target_profile is not None
                else None
            ),
        }
        (out / "workspace.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        coordinate_graph = graph_with_layout_projection(graph, site_map.layout)
        coordinates = waypoint_coordinates(
            coordinate_graph,
            direct_anchor_source="map_layout_control_point",
            propagated_anchor_source="propagated_map_layout",
        )
        pano_waypoint_ids = {state.waypoint_id for state in pano_states}
        map_view = {
            "waypoints": [
                {
                    "id": coordinate.waypoint_id,
                    "x": coordinate.x,
                    "y": coordinate.y,
                    "source": coordinate.source,
                    "has_pano_state": coordinate.waypoint_id in pano_waypoint_ids,
                }
                for coordinate in coordinates.values()
            ],
            "edges": [
                {
                    "from": edge.id.from_waypoint,
                    "to": edge.id.to_waypoint,
                    "edge_source": edge.annotations.edge_source,
                    "transport": (
                        "selection_only"
                        if (edge.id.from_waypoint, edge.id.to_waypoint) in selection_only_edge_keys
                        else "walk"
                    ),
                }
                for edge in graph.edges
            ],
            "actions": metadata["actions"],
            "triggered_actions": metadata["triggered_actions"],
            "docks": metadata["docks"],
        }
        (out / "map_view.json").write_text(
            json.dumps(map_view, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(metadata["counts"], sort_keys=True))
    return 0


def _plan(args: argparse.Namespace) -> int:
    workspace = args.workspace.expanduser().resolve()
    out = args.out.expanduser().resolve()
    if out.exists():
        raise ValueError(f"output already exists: {out}")
    polygon_data = json.loads(args.polygon.read_text(encoding="utf-8"))
    raw_polygon = polygon_data.get("polygon") if isinstance(polygon_data, dict) else polygon_data
    if not isinstance(raw_polygon, list):
        raise ValueError("polygon JSON must be [[x, y], ...] or contain a polygon property")
    polygon = [(float(point[0]), float(point[1])) for point in raw_polygon]
    plan = create_plan(
        workspace=workspace,
        polygon=polygon,
        zone_name=args.zone_name,
        halo_hops=args.halo_hops,
        clone_halo_actions=args.clone_halo_actions,
        excluded_triggered_action_ids=args.excluded_triggered_action_ids,
        triggered_action_exclusion_reason=args.triggered_action_exclusion_reason,
        exclude_unanchored_waypoints=args.exclude_unanchored_waypoints,
        exclude_dependency_free_components=args.exclude_dependency_free_components,
        include_selection_only_edges=args.include_selection_only_edges,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(plan, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(plan["counts"], sort_keys=True))
    return 0


def _audit(args: argparse.Namespace) -> int:
    report = create_preservation_audit(args.workspace, args.plan)
    rendered = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.out is not None:
        out = args.out.expanduser().resolve()
        if out.exists():
            raise ValueError(f"output already exists: {out}")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered, encoding="utf-8")
        print(
            json.dumps(
                {
                    "output": str(out),
                    "selection": report["selection"],
                    "boundary_edges": report["topology"]["boundary_edges"],
                    "docks": report["dependencies"]["site_docks"]["classification_counts"],
                    "assessments": report["assessments"],
                },
                sort_keys=True,
            )
        )
    else:
        print(rendered, end="")
    return 0


def _build(args: argparse.Namespace) -> int:
    manifest = build_clone(args.workspace, args.plan, args.out)
    report = validate_bundle(args.out)
    print(json.dumps({"counts": manifest["counts"], "valid": report.valid}, sort_keys=True))
    return 0 if report.valid else 1


def _validate(args: argparse.Namespace) -> int:
    report = validate_bundle(args.bundle)
    print(
        json.dumps(
            {
                "valid": report.valid,
                "counts": report.counts,
                "errors": report.errors,
                "warnings": report.warnings,
            },
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report.valid else 1


def _export_walk(args: argparse.Namespace) -> int:
    result = export_walk_archive(
        args.bundle,
        args.out,
        name=args.name,
        recording_name=args.recording_name,
        template_archive=args.template_archive,
        triggered_ai_mode=args.triggered_ai_mode,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


def _validate_walk(args: argparse.Namespace) -> int:
    report = validate_walk_archive(args.archive)
    print(
        json.dumps(
            {
                "valid": report.valid,
                "counts": report.counts,
                "errors": report.errors,
                "warnings": report.warnings,
            },
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report.valid else 1


def _serve(args: argparse.Namespace) -> int:
    if args.host not in {"127.0.0.1", "localhost", "::1"} and not args.allow_remote:
        raise ValueError("non-loopback hosts require --allow-remote")
    serve_editor(args.workspace, args.host, args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
