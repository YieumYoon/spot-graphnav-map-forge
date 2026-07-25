from __future__ import annotations

import argparse
import json
from pathlib import Path

from .archive import BackupArchive
from .backup import (
    list_actions,
    list_docks,
    list_pano_states,
    list_site_maps,
    resolve_site_map,
)
from .reconnect import build_graph_reconciliation
from .topology import build_effective_topology


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
            "Read-only Orbit backup inventory and B0 graph baselines for the Orbit Site Map "
            "extensions."
        ),
        epilog=(
            "This CLI never uploads, imports, remaps, or mutates Orbit data. Recording moves, "
            "editor drafts, Undo, and Save remain native Orbit operations."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="List Site Maps in a backup.")
    inspect_parser.add_argument("backup", type=Path)
    inspect_parser.add_argument("--json", action="store_true")
    inspect_parser.set_defaults(handler=_inspect)

    graph_baseline_parser = subparsers.add_parser(
        "graph-baseline",
        help=(
            "Create a private B0 effective graph for native Orbit reconciliation, including "
            "manual edges, archived-edge tombstones, and public edge settings."
        ),
    )
    graph_baseline_parser.add_argument("backup", type=Path)
    graph_baseline_parser.add_argument("--map", dest="map_query", required=True)
    graph_baseline_parser.add_argument("--out", type=Path, required=True)
    graph_baseline_parser.set_defaults(handler=_graph_baseline)

    reconcile_graph_parser = subparsers.add_parser(
        "reconcile-graph",
        help=(
            "Compare a private B0 baseline with one final backup without modifying either input."
        ),
    )
    reconcile_graph_parser.add_argument("baseline", type=Path)
    reconcile_graph_parser.add_argument("after_backup", type=Path)
    reconcile_graph_parser.add_argument("--after-map", required=True)
    reconcile_graph_parser.add_argument("--out", type=Path, required=True)
    reconcile_graph_parser.set_defaults(handler=_reconcile_graph)
    return parser


def _inspect(args: argparse.Namespace) -> int:
    with BackupArchive(args.backup) as archive:
        maps = list_site_maps(archive)
        actions = list_actions(archive)
        docks = list_docks(archive)
        pano_states = list_pano_states(archive)
    map_waypoint_ids = {record.id: set(record.waypoint_ids) for record in maps}
    map_action_ids = {
        record.id: {
            action.id for action in actions if action.waypoint_id in map_waypoint_ids[record.id]
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
        record.id: sum(
            1 for state in pano_states if state.waypoint_id in map_waypoint_ids[record.id]
        )
        for record in maps
    }
    dock_counts = {
        record.id: sum(
            1 for dock in docks if dock.docked_waypoint_id in map_waypoint_ids[record.id]
        )
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
                f"{item['actions']} Actions + "
                f"{item['triggered_actions']} triggered AI inspections, "
                f"{item['explicit_relocalizations']} explicit relocalizations, "
                f"{item['docks']} Docks, "
                f"{item['pano_states']} panorama states"
            )
        print(f"Actions total: {data['actions_total']}")
        print(f"Triggered AI inspections total: {data['triggered_actions_total']}")
        print(f"Explicit relocalizations total: {data['explicit_relocalizations_total']}")
        print(f"Docks total: {data['docks_total']}")
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
        "reconciliation; a final backup is optional read-only persistence evidence"
    )
    baseline["limitations"] = {
        "tombstone_origin": (
            "The backup does not identify whether a SiteEdge tombstone came from an operator "
            "deletion (Orbit Archive action) or Orbit normalization. Preserve and compare every "
            "tombstone by exact endpoint IDs."
        ),
        "edge_identity": "canonical unordered pair of exact waypoint IDs",
        "public_edge_settings": (
            "Public GraphNav Edge.annotations values are captured except edgeSource, which is "
            "treated as provenance and never overwritten by an extension."
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
        args.baseline,
        args.after_backup,
        after_map_query=args.after_map,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(guide, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary = {"fully_reconciled": guide["fully_reconciled"], **guide["counts"]}
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
