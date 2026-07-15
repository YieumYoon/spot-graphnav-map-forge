import io
import json
import struct
import tarfile

from bosdyn.api.autowalk import walks_pb2
from bosdyn.api.graph_nav import map_pb2

from spot_graphnav_map_forge.actions import (
    clone_site_element,
    clone_triggered_site_element,
    triggered_action_reference,
)
from spot_graphnav_map_forge.builder import build_clone
from spot_graphnav_map_forge.validator import validate_bundle
from spot_graphnav_map_forge.wire import decode_fields, text_values

SOURCE_ELEMENT_ID = "11111111-1111-4111-8111-111111111111"
CLONED_ELEMENT_ID = "22222222-2222-4222-8222-222222222222"
SOURCE_WAYPOINT_ID = "synthetic-source-waypoint"
CLONED_WAYPOINT_ID = "synthetic-cloned-waypoint"
SOURCE_MISSION_ID = "33333333-3333-4333-8333-333333333333"


def _varint(value: int) -> bytes:
    output = bytearray()
    while value > 0x7F:
        output.append((value & 0x7F) | 0x80)
        value >>= 7
    output.append(value)
    return bytes(output)


def _length_delimited(number: int, value: bytes) -> bytes:
    return _varint((number << 3) | 2) + _varint(len(value)) + value


def _site_element_payload(element_id: str, waypoint_id: str, mission_id: str) -> bytes:
    metadata = b"".join(
        (
            _length_delimited(1, b"element_id"),
            _length_delimited(2, element_id.encode()),
            _length_delimited(3, b"waypoint=" + waypoint_id.encode()),
            _length_delimited(4, mission_id.encode()),
        )
    )
    return b"".join(
        (
            _length_delimited(1, element_id.encode()),
            _length_delimited(2, b"Thermal Inspection"),
            _length_delimited(3, waypoint_id.encode()),
            _varint((4 << 3) | 1),
            struct.pack("<Q", 0x0123456789ABCDEF),
            _length_delimited(10, metadata),
        )
    )


def _site_dock_payload(
    record_id: str, dock_id: int, docked_waypoint_id: str, prep_waypoint_id: str
) -> bytes:
    target = walks_pb2.Target()
    target.navigate_to.destination_waypoint_id = prep_waypoint_id
    return b"".join(
        (
            _length_delimited(1, record_id.encode()),
            _varint(2 << 3),
            _varint(dock_id),
            _length_delimited(3, docked_waypoint_id.encode()),
            _length_delimited(4, target.SerializeToString()),
        )
    )


def test_clone_site_element_rewrites_top_level_and_nested_identity_tokens() -> None:
    old_element = SOURCE_ELEMENT_ID
    old_waypoint = SOURCE_WAYPOINT_ID
    new_element = CLONED_ELEMENT_ID
    new_waypoint = CLONED_WAYPOINT_ID
    mission = SOURCE_MISSION_ID
    relocalize = walks_pb2.Target.Relocalize()
    relocalize.set_localization_request.initial_guess.waypoint_id = old_waypoint
    relocalize_field = _length_delimited(9, relocalize.SerializeToString())
    payload = _site_element_payload(old_element, old_waypoint, mission) + relocalize_field

    cloned = clone_site_element(payload, new_element, new_waypoint)

    fields = decode_fields(cloned.payload)
    assert text_values(fields, 1) == (new_element,)
    assert text_values(fields, 3) == (new_waypoint,)
    assert old_element.encode() not in cloned.payload
    assert old_waypoint.encode() not in cloned.payload
    assert mission.encode() in cloned.payload
    assert cloned.replacement_counts == {"element_id": 2, "waypoint_id": 3}
    assert cloned.source_mission_ids == ()
    assert cloned.external_uuid_references == (mission,)
    assert struct.pack("<Q", 0x0123456789ABCDEF) in cloned.payload
    cloned_relocalize = walks_pb2.Target.Relocalize.FromString(
        next(
            field.value for field in fields if field.number == 9 and isinstance(field.value, bytes)
        )
    )
    assert cloned_relocalize.set_localization_request.initial_guess.waypoint_id == new_waypoint


def test_clone_triggered_site_element_rewrites_inspection_and_parent_ids() -> None:
    old_inspection = "11111111-1111-4111-8111-111111111111"
    old_parent = "22222222-2222-4222-8222-222222222222"
    new_inspection = "33333333-3333-4333-8333-333333333333"
    new_parent = "44444444-4444-4444-8444-444444444444"
    mission = "55555555-5555-4555-8555-555555555555"
    action = walks_pb2.Action()
    metadata = action.data_acquisition.acquire_data_request.metadata.data.fields
    metadata["element_id"].string_value = old_inspection
    metadata["mission_id"].string_value = mission
    trigger_source = _length_delimited(1, old_parent.encode()) + _length_delimited(
        2, b"spot-cam-ptz"
    )
    trigger_envelope = _length_delimited(1, trigger_source)
    payload = b"".join(
        (
            _length_delimited(1, old_inspection.encode()),
            _length_delimited(2, b"Door Check (AI)"),
            _length_delimited(6, action.SerializeToString()),
            _length_delimited(14, trigger_envelope),
        )
    )

    cloned = clone_triggered_site_element(payload, new_inspection, new_parent)

    assert triggered_action_reference(cloned.payload) == (new_parent, "spot-cam-ptz")
    assert text_values(decode_fields(cloned.payload), 1) == (new_inspection,)
    assert old_inspection.encode() not in cloned.payload
    assert old_parent.encode() not in cloned.payload
    assert mission.encode() in cloned.payload
    assert cloned.source_mission_ids == (mission,)
    assert cloned.external_uuid_references == ()


def test_builder_emits_valid_rewritten_action_bundle(tmp_path) -> None:
    old_element = SOURCE_ELEMENT_ID
    old_waypoint = SOURCE_WAYPOINT_ID
    mission = SOURCE_MISSION_ID
    source_path = f"graph_nav/site_element/{old_element}"
    backup = tmp_path / "backup.tar"
    relocalize = walks_pb2.Target.Relocalize()
    relocalize.set_localization_request.initial_guess.waypoint_id = old_waypoint
    relocalize_field = _length_delimited(9, relocalize.SerializeToString())
    payload = _site_element_payload(old_element, old_waypoint, mission) + relocalize_field
    with tarfile.open(backup, "w") as archive:
        info = tarfile.TarInfo(source_path)
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    graph = map_pb2.Graph()
    graph.waypoints.add(id=old_waypoint)
    (workspace / "graph").write_bytes(graph.SerializeToString())
    metadata = {
        "source_backup": str(backup),
        "site_map": {"id": "map-1", "name": "Map 1"},
        "snapshot_sources": {"waypoint": {}, "edge": {}},
        "actions": [
            {
                "id": old_element,
                "name": "Thermal Inspection",
                "waypoint_id": old_waypoint,
                "source_path": source_path,
                "image_paths": [],
                "has_explicit_relocalization": True,
            }
        ],
    }
    (workspace / "workspace.json").write_text(json.dumps(metadata), encoding="utf-8")
    plan_path = workspace / "zone.plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "zone_name": "zone-a",
                "core_waypoint_ids": [old_waypoint],
                "halo_waypoint_ids": [],
                "clone_halo_actions": False,
            }
        ),
        encoding="utf-8",
    )

    bundle = tmp_path / "bundle"
    manifest = build_clone(workspace, plan_path, bundle)
    report = validate_bundle(bundle)

    action = manifest["actions"][0]
    cloned_payload = (bundle / action["cloned_payload"]).read_bytes()
    assert manifest["counts"]["actions_cloned"] == 1
    assert action["clone_status"] == "offline_rewritten"
    assert action["external_uuid_references"] == [mission]
    assert old_element.encode() not in cloned_payload
    assert old_waypoint.encode() not in cloned_payload
    cloned_relocalize = walks_pb2.Target.Relocalize.FromString(
        next(
            field.value
            for field in decode_fields(cloned_payload)
            if field.number == 9 and isinstance(field.value, bytes)
        )
    )
    assert (
        cloned_relocalize.set_localization_request.initial_guess.waypoint_id
        == action["new_waypoint_id"]
    )
    assert report.valid
    assert report.counts["actions_cloned"] == 1
    assert report.counts["actions_with_external_uuid_references"] == 1
    assert report.counts["explicit_relocalizations_cloned"] == 1

    payload_path = bundle / action["cloned_payload"]
    leaked_payload = cloned_payload.replace(
        action["new_element_id"].encode(), old_element.encode(), 1
    )
    payload_path.write_bytes(leaked_payload)
    invalid_report = validate_bundle(bundle, write_report=False)
    assert not invalid_report.valid
    assert any("source action ID leaked" in error for error in invalid_report.errors)


def test_builder_preserves_triggered_ai_inspection_in_bundle(tmp_path) -> None:
    parent_id = "11111111-1111-4111-8111-111111111111"
    inspection_id = "22222222-2222-4222-8222-222222222222"
    waypoint_id = "source-waypoint"
    mission_id = "33333333-3333-4333-8333-333333333333"
    parent_path = f"graph_nav/site_element/{parent_id}"
    inspection_path = f"graph_nav/site_element/{inspection_id}"
    parent_payload = _site_element_payload(parent_id, waypoint_id, mission_id)
    action = walks_pb2.Action()
    action_metadata = action.data_acquisition.acquire_data_request.metadata.data.fields
    action_metadata["element_id"].string_value = inspection_id
    action_metadata["mission_id"].string_value = mission_id
    trigger_source = _length_delimited(1, parent_id.encode()) + _length_delimited(
        2, b"spot-cam-ptz"
    )
    inspection_payload = b"".join(
        (
            _length_delimited(1, inspection_id.encode()),
            _length_delimited(2, b"Door Check (AI)"),
            _length_delimited(6, action.SerializeToString()),
            _length_delimited(14, _length_delimited(1, trigger_source)),
        )
    )
    backup = tmp_path / "backup.tar"
    with tarfile.open(backup, "w") as archive:
        for path, payload in (
            (parent_path, parent_payload),
            (inspection_path, inspection_payload),
        ):
            info = tarfile.TarInfo(path)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    graph = map_pb2.Graph()
    graph.waypoints.add(id=waypoint_id)
    (workspace / "graph").write_bytes(graph.SerializeToString())
    metadata = {
        "source_backup": str(backup),
        "site_map": {"id": "map-1", "name": "Map 1"},
        "snapshot_sources": {"waypoint": {}, "edge": {}},
        "actions": [
            {
                "id": parent_id,
                "name": "Door Check",
                "waypoint_id": waypoint_id,
                "source_path": parent_path,
                "image_paths": [],
            }
        ],
        "triggered_actions": [
            {
                "id": inspection_id,
                "name": "Door Check (AI)",
                "parent_element_id": parent_id,
                "trigger_image_service": "spot-cam-ptz",
                "source_path": inspection_path,
                "image_paths": [],
            }
        ],
    }
    (workspace / "workspace.json").write_text(json.dumps(metadata), encoding="utf-8")
    plan_path = workspace / "zone.plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "zone_name": "zone-ai",
                "core_waypoint_ids": [waypoint_id],
                "halo_waypoint_ids": [],
                "clone_halo_actions": False,
            }
        ),
        encoding="utf-8",
    )

    bundle = tmp_path / "bundle"
    manifest = build_clone(workspace, plan_path, bundle)
    report = validate_bundle(bundle, write_report=False)

    inspection = manifest["triggered_actions"][0]
    cloned_payload = (bundle / inspection["cloned_payload"]).read_bytes()
    assert manifest["counts"]["triggered_actions_cloned"] == 1
    assert triggered_action_reference(cloned_payload) == (
        inspection["new_parent_element_id"],
        "spot-cam-ptz",
    )
    assert inspection_id.encode() not in cloned_payload
    assert parent_id.encode() not in cloned_payload
    assert report.valid
    assert report.counts["triggered_actions_cloned"] == 1
    assert any("public Walk export" in warning for warning in report.warnings)

    excluded_plan_path = workspace / "zone-excluded.plan.json"
    excluded_plan_path.write_text(
        json.dumps(
            {
                "zone_name": "zone-ai-excluded",
                "core_waypoint_ids": [waypoint_id],
                "halo_waypoint_ids": [],
                "clone_halo_actions": False,
                "excluded_triggered_action_ids": [inspection_id],
                "triggered_action_exclusion_reason": "confirmed incomplete backup record",
            }
        ),
        encoding="utf-8",
    )
    excluded_bundle = tmp_path / "excluded-bundle"
    excluded_manifest = build_clone(workspace, excluded_plan_path, excluded_bundle)
    excluded_report = validate_bundle(excluded_bundle, write_report=False)

    assert excluded_manifest["triggered_actions"] == []
    assert excluded_manifest["counts"]["triggered_actions_explicitly_excluded"] == 1
    assert excluded_manifest["triggered_actions_excluded"] == [
        {
            "source_element_id": inspection_id,
            "name": "Door Check (AI)",
            "source_parent_element_id": parent_id,
            "reason": "confirmed incomplete backup record",
            "disposition": "not_cloned_explicit_plan_exclusion",
        }
    ]
    assert excluded_report.valid
    assert excluded_report.counts["triggered_actions_cloned"] == 0
    assert excluded_report.counts["triggered_actions_explicitly_excluded"] == 1
    assert not any("public Walk export" in warning for warning in excluded_report.warnings)
    assert any("explicitly excluded" in warning for warning in excluded_report.warnings)


def test_clone_site_element_classifies_daq_mission_id_as_provenance() -> None:
    old_element = SOURCE_ELEMENT_ID
    old_waypoint = SOURCE_WAYPOINT_ID
    new_element = CLONED_ELEMENT_ID
    new_waypoint = CLONED_WAYPOINT_ID
    mission = SOURCE_MISSION_ID
    action = walks_pb2.Action()
    metadata = action.data_acquisition.acquire_data_request.metadata.data.fields
    metadata["element_id"].string_value = old_element
    metadata["mission_id"].string_value = mission
    payload = b"".join(
        (
            _length_delimited(1, old_element.encode()),
            _length_delimited(2, b"DAQ Inspection"),
            _length_delimited(3, old_waypoint.encode()),
            _length_delimited(6, action.SerializeToString()),
        )
    )

    cloned = clone_site_element(payload, new_element, new_waypoint)

    assert cloned.source_mission_ids == (mission,)
    assert cloned.external_uuid_references == ()


def test_builder_clones_complete_dock_and_reports_boundary_skip(tmp_path) -> None:
    dock_record_id = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
    docked_waypoint_id = "source-docked-waypoint"
    prep_waypoint_id = "source-prep-waypoint"
    source_path = f"graph_nav/site_dock/{dock_record_id}"
    payload = _site_dock_payload(dock_record_id, 520, docked_waypoint_id, prep_waypoint_id)
    backup = tmp_path / "backup.tar"
    with tarfile.open(backup, "w") as archive:
        info = tarfile.TarInfo(source_path)
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    graph = map_pb2.Graph()
    graph.waypoints.add(id=docked_waypoint_id)
    graph.waypoints.add(id=prep_waypoint_id)
    (workspace / "graph").write_bytes(graph.SerializeToString())
    metadata = {
        "source_backup": str(backup),
        "site_map": {"id": "map-1", "name": "Map 1"},
        "snapshot_sources": {"waypoint": {}, "edge": {}},
        "actions": [],
        "docks": [
            {
                "id": dock_record_id,
                "dock_id": 520,
                "docked_waypoint_id": docked_waypoint_id,
                "target_kind": "navigate_to",
                "target_waypoint_ids": [prep_waypoint_id],
                "target_fingerprint": "unused-in-builder",
                "source_path": source_path,
            }
        ],
    }
    (workspace / "workspace.json").write_text(json.dumps(metadata), encoding="utf-8")

    full_plan = workspace / "full.plan.json"
    full_plan.write_text(
        json.dumps(
            {
                "zone_name": "dock-zone",
                "core_waypoint_ids": [docked_waypoint_id, prep_waypoint_id],
                "halo_waypoint_ids": [],
                "clone_halo_actions": False,
            }
        ),
        encoding="utf-8",
    )
    bundle = tmp_path / "dock-bundle"
    manifest = build_clone(workspace, full_plan, bundle)
    dock = manifest["docks"][0]
    target = walks_pb2.Target.FromString((bundle / dock["cloned_target"]).read_bytes())

    assert manifest["counts"]["docks_cloned"] == 1
    assert manifest["counts"]["docks_boundary_skipped"] == 0
    assert target.navigate_to.destination_waypoint_id == dock["new_target_waypoint_ids"][0]
    assert prep_waypoint_id.encode() not in target.SerializeToString()
    assert validate_bundle(bundle, write_report=False).valid

    boundary_plan = workspace / "boundary.plan.json"
    boundary_plan.write_text(
        json.dumps(
            {
                "zone_name": "dock-boundary-zone",
                "core_waypoint_ids": [docked_waypoint_id],
                "halo_waypoint_ids": [],
                "clone_halo_actions": False,
            }
        ),
        encoding="utf-8",
    )
    boundary_manifest = build_clone(workspace, boundary_plan, tmp_path / "dock-boundary-bundle")
    assert boundary_manifest["counts"]["docks_cloned"] == 0
    assert boundary_manifest["counts"]["docks_boundary_skipped"] == 1
    assert boundary_manifest["docks_skipped"][0]["reason"] == "selection_boundary"
