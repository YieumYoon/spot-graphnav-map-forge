import io
import json
import tarfile

from bosdyn.api.graph_nav import map_pb2

from spot_graphnav_map_forge.audit import create_preservation_audit


def test_audit_reports_cross_partition_walk_and_missing_capture_history(tmp_path) -> None:
    backup = tmp_path / "backup.tar"
    walk_payload = b"walk references wp-0 and wp-2 plus action-0"
    with tarfile.open(backup, "w") as archive:
        info = tarfile.TarInfo("graph_nav/site_walk/walk-1")
        info.size = len(walk_payload)
        archive.addfile(info, io.BytesIO(walk_payload))

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    graph = map_pb2.Graph()
    for waypoint_id in ("wp-0", "wp-1", "wp-2"):
        graph.waypoints.add(id=waypoint_id)
    for source, target in (("wp-0", "wp-1"), ("wp-1", "wp-2")):
        edge = graph.edges.add()
        edge.id.from_waypoint = source
        edge.id.to_waypoint = target
    (workspace / "graph").write_bytes(graph.SerializeToString())
    metadata = {
        "source_backup": str(backup),
        "site_map": {
            "id": "map-1",
            "name": "Map 1",
            "recording_ids": ["recording-1"],
        },
        "actions": [
            {"id": "action-0", "waypoint_id": "wp-0"},
            {"id": "action-2", "waypoint_id": "wp-2"},
        ],
        "triggered_actions": [
            {
                "id": "triggered-0",
                "name": "Incomplete AI placeholder",
                "parent_element_id": "action-0",
            }
        ],
        "docks": [
            {
                "id": "dock-complete",
                "dock_id": 520,
                "docked_waypoint_id": "wp-0",
                "target_waypoint_ids": ["wp-1"],
            },
            {
                "id": "dock-boundary",
                "dock_id": 521,
                "docked_waypoint_id": "wp-0",
                "target_waypoint_ids": ["wp-2"],
            },
        ],
        "pano_states": [{"waypoint_id": "wp-0"}],
        "map_layout": {"control_points": [{"waypoint_id": "wp-0"}]},
        "edge_transport": {
            "policy": "orbit_site_edge_field_3_selection_only",
            "selection_only_edges": [{"from": "wp-0", "to": "wp-1"}],
        },
    }
    (workspace / "workspace.json").write_text(json.dumps(metadata), encoding="utf-8")
    plan = {
        "core_waypoint_ids": ["wp-0", "wp-1"],
        "halo_waypoint_ids": [],
        "excluded_triggered_action_ids": ["triggered-0"],
        "triggered_action_exclusion_reason": "confirmed incomplete backup record",
        "edge_transport": {
            "include_in_walk": False,
            "selection_only_edges": [
                {
                    "from": "wp-0",
                    "to": "wp-1",
                    "disposition": "excluded_from_bundle_and_walk",
                }
            ],
        },
    }
    plan_path = workspace / "zone.plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    report = create_preservation_audit(workspace, plan_path)

    assert report["topology"]["boundary_edges"] == 1
    assert report["dependencies"]["actions"] == {"core": 1, "halo": 0, "remainder": 1}
    assert report["dependencies"]["triggered_actions"] == {
        "core": 1,
        "halo": 0,
        "remainder": 0,
    }
    assert report["dependencies"]["triggered_actions_retained"] == {
        "core": 0,
        "halo": 0,
        "remainder": 0,
    }
    assert report["dependencies"]["triggered_action_exclusions"]["records"][0]["id"] == (
        "triggered-0"
    )
    assert not any(
        "selected triggered AI inspection" in blocker
        for blocker in report["assessments"]["partition_preserve_ids"]["blockers"]
    )
    assert report["dependencies"]["waypoint_pano_states"]["core"] == 1
    assert (
        report["dependencies"]["waypoint_pano_states"]["capture_history_status"]
        == "absent_from_backup"
    )
    assert report["dependencies"]["site_walks"]["classification_counts"] == {"cross_partition": 1}
    assert report["dependencies"]["recordings"]["waypoint_membership_status"] == "unavailable"
    assert report["dependencies"]["site_docks"]["classification_counts"] == {
        "selected_complete": 1,
        "selection_boundary": 1,
    }
    assert report["assessments"]["copy"]["dock_export"] == {
        "selected_complete": 1,
        "selection_boundary_skipped": 1,
    }
    assert report["assessments"]["copy"]["fleet_manager_new_site_map_ingestion"] == "unverified"
    assert report["topology"]["field_3_edges_selected"] == 1
    assert report["topology"]["field_3_edges_excluded_from_walk"] == 1
    assert not report["assessments"]["copy"]["edge_transport"]["include_in_walk"]
    assert (
        report["assessments"]["copy"]["historical_site_view_capture_migration"]
        == "not_possible_from_this_backup"
    )
