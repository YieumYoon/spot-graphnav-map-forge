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


def test_reconciliation_guide_marks_manual_connect_and_resurrected_archive() -> None:
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
    guide = build_reconciliation_guide(before, after)

    assert not guide["fully_reconciled"]
    assert guide["graph_reconciled"] is False
    assert guide["settings_reconciled"] is True
    assert guide["counts"] == {
        "baseline_waypoints": 4,
        "current_waypoints": 3,
        "current_b0_waypoints": 3,
        "ignored_extra_waypoints": 0,
        "baseline_effective_edges": 3,
        "desired_internal_edges": 2,
        "observed_edges": 2,
        "observed_edges_total": 2,
        "ignored_extra_edges": 0,
        "connect_edges": 1,
        "connect_manual_edges": 1,
        "delete_edges": 1,
        "resurrected_deleted_edges": 1,
        "update_edges": 0,
        "crosswalk_update_edges": 0,
        "direction_blocked_update_edges": 0,
        "settings_profile_edges": 0,
        "intentional_cut_edges": 1,
        "excluded_outside_edges": 0,
    }
    action_rows = [
        (row["operation"], row["reason"], row["from"], row["to"]) for row in guide["actions"]
    ]
    assert action_rows == [
        ("connect", "missing_manual_edge", "a", "b"),
        ("delete", "resurrected_deleted_edge", "a", "c"),
    ]
    assert guide["intentional_cuts"] == [{"from": "c", "to": "d", "manual": False}]


def test_reconciliation_guide_accepts_raw_fallback_for_site_override() -> None:
    before = _topology(("a", "b"), (_edge("a", "b", provenance="site_override"),))
    after = _topology(("a", "b"), (_edge("a", "b", provenance="raw_fallback"),))
    guide = build_reconciliation_guide(before, after)

    assert guide["fully_reconciled"]
    assert guide["settings_comparison_available"] is False
    assert guide["actions"] == []


def test_reconciliation_guide_reports_changed_public_edge_settings() -> None:
    expected = _edge("a", "b")
    expected["settings"] = {"disableAlternateRouteFinding": True}
    expected["settings_fingerprint"] = "expected"
    observed = _edge("a", "b")
    observed["settings"] = {"disableAlternateRouteFinding": False}
    observed["settings_fingerprint"] = "observed"
    observed["edge_source_value"] = 1

    guide = build_reconciliation_guide(
        _topology(("a", "b"), (expected,)),
        _topology(("a", "b"), (observed,)),
    )

    assert guide["counts"]["update_edges"] == 1
    assert guide["actions"] == [
        {
            "index": 1,
            "operation": "update",
            "reason": "edge_settings_mismatch",
            "from": "a",
            "to": "b",
            "edge_source": "EDGE_SOURCE_ODOMETRY",
            "baseline_provenance": "raw_fallback",
            "coordinate_scope": "orbit_live",
            "observed_source_value": 1,
            "desired_settings": {"disableAlternateRouteFinding": True},
            "observed_settings": {"disableAlternateRouteFinding": False},
            "settings_fingerprint": "expected",
            "settings_categories": ["edge behavior"],
            "crosswalk": False,
            "stored_direction_matches": True,
        }
    ]
