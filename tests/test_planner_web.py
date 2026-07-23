import json

import pytest
from bosdyn.api.graph_nav import map_pb2

from spot_graphnav_map_forge.cli import main
from spot_graphnav_map_forge.planner import create_plan
from spot_graphnav_map_forge.reconnect import build_reconnect_inventory
from spot_graphnav_map_forge.web import EditorServer, build_workspace_payload, save_plan


def _workspace(tmp_path):
    graph = map_pb2.Graph()
    for waypoint_id in ("wp-0", "wp-1", "wp-2"):
        graph.waypoints.add(id=waypoint_id)
    anchor = graph.anchoring.anchors.add(id="wp-0")
    anchor.seed_tform_waypoint.rotation.w = 1.0
    for source, target in (("wp-0", "wp-1"), ("wp-1", "wp-2")):
        edge = graph.edges.add()
        edge.id.from_waypoint = source
        edge.id.to_waypoint = target
        edge.from_tform_to.position.x = 1.0
        edge.from_tform_to.rotation.w = 1.0
    graph.edges[0].annotations.edge_source = 5
    (tmp_path / "graph").write_bytes(graph.SerializeToString())
    metadata = {
        "site_map": {"id": "map-1", "name": "Test Map", "recording_ids": []},
        "counts": {"waypoints": 3, "edges": 2, "actions": 2},
        "snapshot_sources": {"waypoint": {}, "edge": {}},
        "edge_transport": {
            "policy": "orbit_site_edge_field_3_selection_only",
            "selection_only_edges": [{"from": "wp-1", "to": "wp-2"}],
        },
        "actions": [
            {
                "id": "action-0",
                "name": "Core action",
                "waypoint_id": "wp-0",
                "source_path": "source/action-0",
                "image_paths": [],
            },
            {
                "id": "action-2",
                "name": "Halo action",
                "waypoint_id": "wp-2",
                "source_path": "source/action-2",
                "image_paths": ["source/image-2"],
            },
        ],
        "triggered_actions": [
            {
                "id": "triggered-0",
                "name": "Incomplete AI placeholder",
                "parent_element_id": "action-0",
            }
        ],
    }
    (tmp_path / "workspace.json").write_text(json.dumps(metadata), encoding="utf-8")
    map_view = {
        "waypoints": [
            {"id": f"wp-{index}", "x": float(index), "y": 0.0, "source": "graph_anchor"}
            for index in range(3)
        ],
        "edges": [],
        "actions": metadata["actions"],
    }
    (tmp_path / "map_view.json").write_text(json.dumps(map_view), encoding="utf-8")
    return tmp_path


def _cleanup_workspace(tmp_path):
    graph = map_pb2.Graph()
    for waypoint_id in ("main-0", "main-1", "unanchored-0", "unanchored-1", "orphan"):
        graph.waypoints.add(id=waypoint_id)
    for source, target in (("main-0", "main-1"), ("unanchored-0", "unanchored-1")):
        edge = graph.edges.add()
        edge.id.from_waypoint = source
        edge.id.to_waypoint = target
        edge.from_tform_to.rotation.w = 1.0
    (tmp_path / "graph").write_bytes(graph.SerializeToString())
    metadata = {
        "site_map": {"id": "map-cleanup", "name": "Cleanup Map", "recording_ids": []},
        "counts": {"waypoints": 5, "edges": 2, "actions": 0},
        "snapshot_sources": {"waypoint": {}, "edge": {}},
        "actions": [],
        "triggered_actions": [],
        "docks": [],
        "pano_states": [],
    }
    (tmp_path / "workspace.json").write_text(json.dumps(metadata), encoding="utf-8")
    map_view = {
        "waypoints": [
            {"id": "main-0", "x": 0.0, "y": 0.0, "source": "map_layout_control_point"},
            {"id": "main-1", "x": 1.0, "y": 0.0, "source": "propagated_map_layout"},
            {
                "id": "unanchored-0",
                "x": 2.0,
                "y": 0.0,
                "source": "waypoint_tform_ko_unanchored",
            },
            {
                "id": "unanchored-1",
                "x": 3.0,
                "y": 0.0,
                "source": "waypoint_tform_ko_unanchored",
            },
            {"id": "orphan", "x": 4.0, "y": 0.0, "source": "map_layout_control_point"},
        ],
        "edges": [],
        "actions": [],
    }
    (tmp_path / "map_view.json").write_text(json.dumps(map_view), encoding="utf-8")
    return tmp_path


def test_create_plan_and_workspace_payload(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    polygon = [(-0.25, -0.5), (1.25, -0.5), (1.25, 0.5), (-0.25, 0.5)]
    plan = create_plan(workspace, polygon, "zone-a", halo_hops=1)

    assert plan["core_waypoint_ids"] == ["wp-0", "wp-1"]
    assert plan["halo_waypoint_ids"] == ["wp-2"]
    assert plan["counts"]["core_actions"] == 1
    assert plan["counts"]["halo_actions"] == 1
    assert plan["edge_source_counts"]["EDGE_SOURCE_USER_REQUEST"] == 1
    assert plan["counts"]["selected_connectivity_edges"] == 2
    assert plan["counts"]["selected_edges"] == 1
    assert plan["counts"]["selection_only_edges_excluded"] == 1
    assert plan["counts"]["components"] == 2
    assert not plan["edge_transport"]["include_in_walk"]

    included_plan = create_plan(
        workspace,
        polygon,
        "zone-including-field-3",
        halo_hops=1,
        include_selection_only_edges=True,
    )
    assert included_plan["counts"]["selected_edges"] == 2
    assert included_plan["counts"]["selection_only_edges_included"] == 1
    assert included_plan["counts"]["selection_only_edges_excluded"] == 0
    assert included_plan["counts"]["components"] == 1
    assert included_plan["edge_transport"]["selection_only_edges"][0]["disposition"] == (
        "included_in_walk_public_annotations_only"
    )

    exclusion_plan = create_plan(
        workspace,
        polygon,
        "zone-exclusion",
        halo_hops=1,
        excluded_triggered_action_ids=["triggered-0"],
        triggered_action_exclusion_reason="confirmed incomplete backup record",
    )
    assert exclusion_plan["excluded_triggered_action_ids"] == ["triggered-0"]
    assert exclusion_plan["counts"]["triggered_actions_explicitly_excluded"] == 1

    with pytest.raises(ValueError, match="exclusion_reason is required"):
        create_plan(
            workspace,
            polygon,
            "zone-invalid",
            excluded_triggered_action_ids=["triggered-0"],
        )
    with pytest.raises(ValueError, match="not present in workspace"):
        create_plan(
            workspace,
            polygon,
            "zone-unknown",
            excluded_triggered_action_ids=["unknown"],
            triggered_action_exclusion_reason="not present",
        )

    payload = build_workspace_payload(workspace)
    assert payload["site_map"]["name"] == "Test Map"
    assert payload["counts"]["components"] == 1
    assert payload["counts"]["unanchored_waypoints"] == 0
    assert payload["waypoints"][2]["actions"] == 1
    assert payload["edges"][1]["transport"] == "selection_only"
    assert payload["counts"]["manual_edges"] == 1
    assert payload["counts"]["manual_field_3_edges"] == 0
    assert payload["counts"]["manual_local_frame_edges"] == 0
    assert payload["manual_edges"] == [
        {
            "index": 1,
            "graph_index": 0,
            "from": "wp-0",
            "to": "wp-1",
            "from_name": "",
            "to_name": "",
            "from_session": "",
            "to_session": "",
            "cross_session_label": False,
            "from_x": 0.0,
            "from_y": 0.0,
            "to_x": 1.0,
            "to_y": 0.0,
            "from_coordinate_source": "graph_anchor",
            "to_coordinate_source": "graph_anchor",
            "coordinate_scope": "map",
            "distance": 1.0,
            "snapshot_id": "",
            "transport": "walk",
            "field_3": False,
        }
    ]


def test_reconnect_inventory_is_read_only_and_cli_writable(tmp_path) -> None:
    workspace = _workspace(tmp_path)

    inventory = build_reconnect_inventory(workspace)

    assert inventory["kind"] == "orbit_manual_edge_reconnect_inventory"
    assert inventory["sensitivity"] == "private_operational_data_do_not_commit"
    assert inventory["counts"] == {
        "waypoints": 3,
        "edges": 2,
        "manual_edges": 1,
        "manual_endpoint_waypoints": 2,
        "manual_cross_session_edges": 0,
        "manual_field_3_edges": 0,
        "manual_local_frame_edges": 0,
    }
    assert inventory["manual_endpoint_waypoint_ids"] == ["wp-0", "wp-1"]
    waypoints = {row["id"]: row for row in inventory["waypoints"]}
    assert waypoints["wp-0"]["snapshot_id"] == ""
    assert waypoints["wp-0"]["incident_edges"] == [
        {
            "direction": "out",
            "neighbor_waypoint_id": "wp-1",
            "source": "EDGE_SOURCE_USER_REQUEST",
            "transport": "walk",
        }
    ]

    output = tmp_path / "private" / "manual-edge-inventory.json"
    assert main(["edge-inventory", str(workspace), "--out", str(output)]) == 0
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["counts"] == inventory["counts"]


def test_editor_server_loads_only_graph_reconciliation_guides(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    guide_path = tmp_path / "guide.json"
    guide = {
        "kind": "orbit_graph_reconciliation_guide",
        "before_site_map": {"id": "map-1", "name": "Test Map"},
        "graph_reconciled": True,
        "counts": {"intentional_cut_edges": 0},
        "actions": [],
    }
    guide_path.write_text(json.dumps(guide), encoding="utf-8")

    server = EditorServer(("127.0.0.1", 0), workspace, guide_path)
    try:
        payload = json.loads(server.workspace_payload)
    finally:
        server.server_close()
    assert payload["reconciliation"] == guide

    guide_path.write_text(json.dumps({"kind": "other"}), encoding="utf-8")
    with pytest.raises(ValueError, match="not a graph reconciliation guide"):
        EditorServer(("127.0.0.1", 0), workspace, guide_path)

    guide["before_site_map"] = {"id": "another-map"}
    guide_path.write_text(json.dumps(guide), encoding="utf-8")
    with pytest.raises(ValueError, match="baseline does not match"):
        EditorServer(("127.0.0.1", 0), workspace, guide_path)


def test_save_plan_requires_explicit_overwrite(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    request = {
        "zone_name": "Zone A",
        "polygon": [[-0.25, -0.5], [1.25, -0.5], [1.25, 0.5], [-0.25, 0.5]],
        "halo_hops": 1,
        "excluded_triggered_action_ids": ["triggered-0"],
        "triggered_action_exclusion_reason": "confirmed incomplete backup record",
    }
    path, plan = save_plan(workspace, request)
    assert path.name == "zone-a.plan.json"
    assert plan["counts"]["core_waypoints"] == 2
    assert plan["excluded_triggered_action_ids"] == ["triggered-0"]

    with pytest.raises(FileExistsError):
        save_plan(workspace, request)

    request["overwrite"] = True
    overwritten_path, _ = save_plan(workspace, request)
    assert overwritten_path == path


def test_selection_cleanup_excludes_unanchored_and_dependency_free_components(tmp_path) -> None:
    workspace = _cleanup_workspace(tmp_path)
    polygon = [(-1.0, -1.0), (5.0, -1.0), (5.0, 1.0), (-1.0, 1.0)]

    plan = create_plan(
        workspace,
        polygon,
        "clean-zone",
        exclude_unanchored_waypoints=True,
        exclude_dependency_free_components=True,
    )

    assert plan["core_waypoint_ids"] == ["main-0", "main-1"]
    assert plan["halo_waypoint_ids"] == []
    assert plan["counts"]["unanchored_waypoints_excluded"] == 2
    assert plan["counts"]["dependency_free_waypoints_excluded"] == 1
    assert plan["counts"]["dependency_free_components_excluded"] == 1
    assert plan["counts"]["components"] == 1
    assert plan["selection_cleanup"]["excluded_waypoint_ids"] == {
        "unanchored": ["unanchored-0", "unanchored-1"],
        "dependency_free_components": ["orphan"],
    }

    metadata_path = workspace / "workspace.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["actions"] = [{"id": "orphan-action", "waypoint_id": "orphan"}]
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    protected_plan = create_plan(
        workspace,
        polygon,
        "protected-zone",
        exclude_unanchored_waypoints=True,
        exclude_dependency_free_components=True,
    )

    assert protected_plan["core_waypoint_ids"] == ["main-0", "main-1", "orphan"]
    assert protected_plan["counts"]["dependency_free_waypoints_excluded"] == 0
    assert protected_plan["counts"]["dependency_bearing_components_protected"] == 1
    assert protected_plan["counts"]["components"] == 2
    assert protected_plan["selection_cleanup"]["protected_disconnected_components"] == [
        {"size": 1, "dependency_waypoint_ids": ["orphan"]}
    ]
