import json

import pytest
from bosdyn.api.graph_nav import map_pb2

from spot_graphnav_map_forge.planner import create_plan
from spot_graphnav_map_forge.web import build_workspace_payload, save_plan


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


def test_create_plan_and_workspace_payload(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    polygon = [(-0.25, -0.5), (1.25, -0.5), (1.25, 0.5), (-0.25, 0.5)]
    plan = create_plan(workspace, polygon, "zone-a", halo_hops=1)

    assert plan["core_waypoint_ids"] == ["wp-0", "wp-1"]
    assert plan["halo_waypoint_ids"] == ["wp-2"]
    assert plan["counts"]["core_actions"] == 1
    assert plan["counts"]["halo_actions"] == 1
    assert plan["edge_source_counts"]["EDGE_SOURCE_USER_REQUEST"] == 1

    payload = build_workspace_payload(workspace)
    assert payload["site_map"]["name"] == "Test Map"
    assert payload["counts"]["components"] == 1
    assert payload["counts"]["unanchored_waypoints"] == 0
    assert payload["waypoints"][2]["actions"] == 1


def test_save_plan_requires_explicit_overwrite(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    request = {
        "zone_name": "Zone A",
        "polygon": [[-0.25, -0.5], [1.25, -0.5], [1.25, 0.5], [-0.25, 0.5]],
        "halo_hops": 1,
    }
    path, plan = save_plan(workspace, request)
    assert path.name == "zone-a.plan.json"
    assert plan["counts"]["core_waypoints"] == 2

    with pytest.raises(FileExistsError):
        save_plan(workspace, request)

    request["overwrite"] = True
    overwritten_path, _ = save_plan(workspace, request)
    assert overwritten_path == path
