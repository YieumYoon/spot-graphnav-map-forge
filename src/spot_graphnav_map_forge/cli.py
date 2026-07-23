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
from .reconnect import build_graph_reconciliation, build_reconnect_inventory
from .remap import IDENTITY_MODES
from .topology import build_effective_topology
from .validator import validate_bundle
from .walk_archive import export_walk_archive, reissue_walk_recording, validate_walk_archive
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
        description=(
            "Read-only backup analysis for Orbit-assisted recording splits, plus an "
            "experimental offline GraphNav/Walk clone workflow."
        ),
        epilog=(
            "Recommended same-instance workflow: inspect, graph-baseline, and optionally "
            "reconcile-graph; move recordings and save only in Orbit. "
            "Experimental offline clone workflow: prepare, plan, audit, build, validate, "
            "export-walk, reissue-walk, validate-walk, and serve. "
            "See docs/workflows/ before choosing a workflow."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="List site maps in a backup.")
    inspect_parser.add_argument("backup", type=Path)
    inspect_parser.add_argument("--json", action="store_true")
    inspect_parser.set_defaults(handler=_inspect)

    wire_parser = subparsers.add_parser(
        "wire-dump", help="Research: inspect low-level protobuf envelope fields."
    )
    wire_parser.add_argument("backup", type=Path)
    wire_parser.add_argument("member")
    wire_parser.set_defaults(handler=_wire_dump)

    prepare_parser = subparsers.add_parser(
        "prepare",
        help="Experimental clone: reconstruct one final graph into an offline workspace.",
    )
    prepare_parser.add_argument("backup", type=Path)
    prepare_parser.add_argument("--map", dest="map_query", required=True)
    prepare_parser.add_argument("--out", type=Path, required=True)
    prepare_parser.set_defaults(handler=_prepare)

    edge_inventory_parser = subparsers.add_parser(
        "edge-inventory",
        help="Recommended split: create a private manual-edge planning inventory.",
    )
    edge_inventory_parser.add_argument("workspace", type=Path)
    edge_inventory_parser.add_argument("--out", type=Path, required=True)
    edge_inventory_parser.set_defaults(handler=_edge_inventory)

    graph_baseline_parser = subparsers.add_parser(
        "graph-baseline",
        help=(
            "Recommended split: freeze a private B0 effective graph, including manual edges and "
            "SiteEdge deletion tombstones plus public edge settings."
        ),
    )
    graph_baseline_parser.add_argument("backup", type=Path)
    graph_baseline_parser.add_argument("--map", dest="map_query", required=True)
    graph_baseline_parser.add_argument("--out", type=Path, required=True)
    graph_baseline_parser.set_defaults(handler=_graph_baseline)

    reconcile_graph_parser = subparsers.add_parser(
        "reconcile-graph",
        help=(
            "Recommended split audit: compare B0 with a post-move backup and create a read-only "
            "connect/delete/update guide."
        ),
    )
    reconcile_graph_parser.add_argument("workspace", type=Path)
    reconcile_graph_parser.add_argument("before_backup", type=Path)
    reconcile_graph_parser.add_argument("after_backup", type=Path)
    reconcile_graph_parser.add_argument("--before-map", required=True)
    reconcile_graph_parser.add_argument("--after-map", required=True)
    reconcile_graph_parser.add_argument("--out", type=Path, required=True)
    reconcile_graph_parser.set_defaults(handler=_reconcile_graph)

    plan_parser = subparsers.add_parser(
        "plan", help="Experimental clone: select a zone using a polygon JSON file."
    )
    plan_parser.add_argument("workspace", type=Path)
    plan_parser.add_argument("--polygon", type=Path, required=True)
    plan_parser.add_argument("--zone-name", required=True)
    plan_parser.add_argument("--halo-hops", type=int, default=1)
    plan_parser.add_argument("--clone-halo-actions", action="store_true")
    plan_parser.add_argument(
        "--identity-mode",
        choices=tuple(sorted(IDENTITY_MODES)),
        default="clone",
        help=(
            "Identity policy. 'clone' creates UUIDv5 object IDs; experimental 'orbit-native' "
            "creates tablet-shaped GraphNav IDs and UUIDv4-shaped Orbit object IDs; experimental "
            "'preserve' keeps GraphNav and SiteElement IDs while the exported Walk remains new."
        ),
    )
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
        "audit", help="Experimental clone: report dependencies and preservation risks."
    )
    audit_parser.add_argument("workspace", type=Path)
    audit_parser.add_argument("--plan", type=Path, required=True)
    audit_parser.add_argument("--out", type=Path)
    audit_parser.set_defaults(handler=_audit)

    build_parser = subparsers.add_parser(
        "build", help="Experimental clone: build an offline GraphNav bundle."
    )
    build_parser.add_argument("workspace", type=Path)
    build_parser.add_argument("--plan", type=Path, required=True)
    build_parser.add_argument("--out", type=Path, required=True)
    build_parser.add_argument(
        "--clone-name",
        help=(
            "Override the plan zone name used as the deterministic clone-ID namespace. "
            "Use a new value when two exported maps must coexist independently in Orbit."
        ),
    )
    build_parser.add_argument(
        "--identity-mode",
        choices=tuple(sorted(IDENTITY_MODES)),
        help=(
            "Override the plan identity mode for an audited offline experiment: clone, "
            "orbit-native, or preserve."
        ),
    )
    build_parser.set_defaults(handler=_build)

    validate_parser = subparsers.add_parser(
        "validate", help="Experimental clone: validate a cloned bundle offline."
    )
    validate_parser.add_argument("bundle", type=Path)
    validate_parser.set_defaults(handler=_validate)

    export_walk_parser = subparsers.add_parser(
        "export-walk",
        help="Experimental clone: package a bundle as a public Autowalk .walk.zip.",
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
        "--recording-template",
        type=Path,
        help=(
            "Same-map tablet recording used only for its public Walk/Dock/route profile and "
            "recording envelope; the output Graph and Actions still come from the clone bundle."
        ),
    )
    export_walk_parser.add_argument(
        "--walk-id",
        help=(
            "Explicit globally unique Walk UUID. Use a freshly issued UUID once for a new "
            "recording-compatible fork and reuse it for rebuilds."
        ),
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
    export_walk_parser.add_argument(
        "--sleep-waypoint-id",
        help=(
            "Explicitly synthesize one public Sleep action at this source or cloned waypoint ID. "
            "The generated action is reported separately from copied SiteElements."
        ),
    )
    export_walk_parser.add_argument(
        "--sleep-duration-seconds",
        type=float,
        default=0.25,
        help="Duration of the explicitly synthesized Sleep action (default: 0.25).",
    )
    export_walk_parser.add_argument(
        "--sleep-name",
        default="Sleep - 1",
        help="Display name for the explicitly synthesized Sleep action.",
    )
    export_walk_parser.add_argument(
        "--sleep-after-element",
        help="Insert the Sleep action after the unique existing element ID or exact name.",
    )
    export_walk_parser.set_defaults(handler=_export_walk)

    reissue_walk_parser = subparsers.add_parser(
        "reissue-walk",
        help=("Experimental probe: package a tablet Walk with its top-level Walk ID changed."),
    )
    reissue_walk_parser.add_argument("source", type=Path)
    reissue_walk_parser.add_argument("--out", type=Path, required=True)
    reissue_walk_parser.add_argument(
        "--new-walk-id",
        help="Explicit replacement UUID; defaults to a freshly generated UUIDv4.",
    )
    reissue_walk_parser.add_argument(
        "--graph-only",
        action="store_true",
        help=(
            "Diagnostic control: remove all Walk Elements and Docks while preserving the Graph, "
            "snapshots, anchors, names, and opaque sidecars."
        ),
    )
    reissue_walk_parser.add_argument(
        "--navigation-only-sentinel",
        action="store_true",
        help=(
            "With --graph-only, add one new skipped Element with no action and a copied source "
            "navigation target to test Orbit's all-data-duplicate gate."
        ),
    )
    reissue_walk_parser.add_argument(
        "--disconnected-waypoint-sentinel",
        action="store_true",
        help=(
            "With both sentinel flags, clone one waypoint, snapshot, and anchor under new IDs "
            "without adding an edge; all original GraphNav objects remain unchanged."
        ),
    )
    reissue_walk_parser.set_defaults(handler=_reissue_walk)

    validate_walk_parser = subparsers.add_parser(
        "validate-walk", help="Experimental clone: validate a .walk.zip archive offline."
    )
    validate_walk_parser.add_argument("archive", type=Path)
    validate_walk_parser.set_defaults(handler=_validate_walk)

    serve_parser = subparsers.add_parser(
        "serve", help="Experimental clone: run the local polygon editor."
    )
    serve_parser.add_argument("workspace", type=Path)
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8787)
    serve_parser.add_argument(
        "--reconciliation",
        type=Path,
        help="Optional graph reconciliation guide shown as connect/delete waypoint pairs.",
    )
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
        identity_mode=args.identity_mode,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(plan, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(plan["counts"], sort_keys=True))
    return 0


def _edge_inventory(args: argparse.Namespace) -> int:
    out = args.out.expanduser().resolve()
    if out.exists():
        raise ValueError(f"output already exists: {out}")
    inventory = build_reconnect_inventory(args.workspace)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(inventory, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(inventory["counts"], sort_keys=True))
    return 0


def _graph_baseline(args: argparse.Namespace) -> int:
    out = args.out.expanduser().resolve()
    if out.exists():
        raise ValueError(f"output already exists: {out}")
    with BackupArchive(args.backup) as archive:
        site_map = resolve_site_map(archive, args.map_query)
        baseline = build_effective_topology(archive, site_map)
    baseline["kind"] = "orbit_graph_baseline_inventory"
    baseline["sensitivity"] = "private_operational_data_do_not_commit"
    baseline["baseline_role"] = (
        "Immutable B0 reference for live exact-ID topology and public edge-settings "
        "reconciliation; a fresh B1 backup remains an optional final payload audit"
    )
    baseline["limitations"] = {
        "tombstone_origin": (
            "The backup does not identify whether a SiteEdge tombstone came from an operator "
            "deletion or Orbit normalization. Preserve and compare every tombstone by exact "
            "endpoint IDs."
        ),
        "edge_identity": "canonical unordered pair of exact waypoint IDs",
        "public_edge_settings": (
            "Public GraphNav Edge.annotations values are captured except edgeSource, which is "
            "treated as provenance and never overwritten by the extension."
        ),
        "private_wrapper_fields": (
            "Opaque/private SiteEdge wrapper fields are inventoried by field number only and "
            "cannot be reconstructed by the public-settings restore."
        ),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(baseline, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                **baseline["counts"],
                "manual_edges": baseline["edge_source_counts"].get("EDGE_SOURCE_USER_REQUEST", 0),
            },
            sort_keys=True,
        )
    )
    return 0


def _reconcile_graph(args: argparse.Namespace) -> int:
    out = args.out.expanduser().resolve()
    if out.exists():
        raise ValueError(f"output already exists: {out}")
    guide = build_graph_reconciliation(
        args.workspace,
        args.before_backup,
        args.after_backup,
        before_map_query=args.before_map,
        after_map_query=args.after_map,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(guide, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary = {"graph_reconciled": guide["graph_reconciled"], **guide["counts"]}
    print(json.dumps(summary, sort_keys=True))
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
    manifest = build_clone(
        args.workspace,
        args.plan,
        args.out,
        identity_mode=args.identity_mode,
        clone_name=args.clone_name,
    )
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
        recording_template=args.recording_template,
        walk_id=args.walk_id,
        triggered_ai_mode=args.triggered_ai_mode,
        sleep_waypoint_id=args.sleep_waypoint_id,
        sleep_duration_seconds=args.sleep_duration_seconds,
        sleep_name=args.sleep_name,
        sleep_after_element=args.sleep_after_element,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


def _reissue_walk(args: argparse.Namespace) -> int:
    result = reissue_walk_recording(
        args.source,
        args.out,
        new_walk_id=args.new_walk_id,
        graph_only=args.graph_only,
        navigation_only_sentinel=args.navigation_only_sentinel,
        disconnected_waypoint_sentinel=args.disconnected_waypoint_sentinel,
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
    serve_editor(
        args.workspace,
        args.host,
        args.port,
        reconciliation=args.reconciliation,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
