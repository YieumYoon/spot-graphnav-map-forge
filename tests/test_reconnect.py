from spot_graphnav_map_forge.reconnect import build_reconciliation_guide


def _edge(source, target, *, provenance="raw_fallback", edge_source="EDGE_SOURCE_ODOMETRY"):
    return {
        "key": sorted((source, target)),
        "from": source,
        "to": target,
        "provenance": provenance,
        "edge_source": edge_source,
    }


def _topology(waypoint_ids, edges, tombstones=()):
    return {
        "site_map": {"id": "map", "name": "Map", "recording_ids": []},
        "waypoint_ids": list(waypoint_ids),
        "effective_edges": list(edges),
        "tombstones": [
            {"key": sorted((source, target)), "from": source, "to": target}
            for source, target in tombstones
        ],
    }


def _waypoint(waypoint_id, x):
    return {
        "id": waypoint_id,
        "name": waypoint_id.upper(),
        "session_name": "session",
        "x": x,
        "y": 0.0,
        "source": "propagated_map_layout",
    }


def test_reconciliation_guide_marks_manual_connect_and_resurrected_delete() -> None:
    before = _topology(
        ("a", "b", "c", "d"),
        (
            _edge("a", "b", provenance="site_only", edge_source="EDGE_SOURCE_USER_REQUEST"),
            _edge("b", "c"),
            _edge("c", "d"),
        ),
        tombstones=(("a", "c"),),
    )
    after = _topology(
        ("a", "b", "c"),
        (
            _edge("b", "c"),
            _edge("a", "c"),
        ),
    )
    waypoints = [_waypoint(value, index) for index, value in enumerate(("a", "b", "c", "d"))]

    guide = build_reconciliation_guide(before, after, waypoints)

    assert not guide["graph_reconciled"]
    assert guide["counts"] == {
        "after_waypoints": 3,
        "expected_edges": 2,
        "observed_edges": 2,
        "connect": 1,
        "connect_manual": 1,
        "delete": 1,
        "delete_resurrected": 1,
        "intentional_cut_edges": 1,
    }
    action_rows = [
        (row["operation"], row["reason"], row["from"], row["to"]) for row in guide["actions"]
    ]
    assert action_rows == [
        ("connect", "missing_manual_edge", "a", "b"),
        ("delete", "resurrected_deleted_edge", "a", "c"),
    ]
    assert guide["intentional_cut_edges"] == [{"key": ["c", "d"], "from": "c", "to": "d"}]


def test_reconciliation_guide_accepts_raw_fallback_for_site_override() -> None:
    before = _topology(("a", "b"), (_edge("a", "b", provenance="site_override"),))
    after = _topology(("a", "b"), (_edge("a", "b", provenance="raw_fallback"),))
    waypoints = [_waypoint("a", 0), _waypoint("b", 1)]

    guide = build_reconciliation_guide(before, after, waypoints)

    assert guide["graph_reconciled"]
    assert guide["actions"] == []
