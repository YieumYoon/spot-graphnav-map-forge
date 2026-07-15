import json
import struct
import zipfile
from pathlib import Path

import pytest
from bosdyn.api import image_pb2
from bosdyn.api.autowalk import walks_pb2
from bosdyn.api.graph_nav import map_pb2

from spot_graphnav_map_forge.walk_archive import export_walk_archive, validate_walk_archive
from spot_graphnav_map_forge.wire import bytes_values, decode_fields


def _varint(value: int) -> bytes:
    output = bytearray()
    while value > 0x7F:
        output.append((value & 0x7F) | 0x80)
        value >>= 7
    output.append(value)
    return bytes(output)


def _length_delimited(number: int, value: bytes) -> bytes:
    return _varint((number << 3) | 2) + _varint(len(value)) + value


def _fixed64(number: int, value: float) -> bytes:
    return _varint((number << 3) | 1) + struct.pack("<d", value)


def _site_element(
    element_id: str,
    waypoint_id: str,
    name: str,
    action: walks_pb2.Action | None = None,
    wrapper: walks_pb2.ActionWrapper | None = None,
    relocalize_marker: bytes | None = b"",
    explicit_relocalize: bytes | None = None,
) -> bytes:
    fields = [
        _length_delimited(1, element_id.encode()),
        _length_delimited(2, name.encode()),
        _length_delimited(3, waypoint_id.encode()),
    ]
    if action is not None:
        fields.append(_length_delimited(6, action.SerializeToString()))
    if relocalize_marker is not None:
        fields.append(_length_delimited(8, relocalize_marker))
    if explicit_relocalize is not None:
        fields.append(_length_delimited(9, explicit_relocalize))
    if wrapper is not None:
        fields.append(_length_delimited(10, wrapper.SerializeToString()))
    return b"".join(fields)


def _triggered_site_element(
    element_id: str,
    parent_element_id: str,
    name: str,
    action: walks_pb2.Action,
) -> bytes:
    trigger_source = _length_delimited(1, parent_element_id.encode()) + _length_delimited(
        2, b"spot-cam-ptz"
    )
    return b"".join(
        (
            _length_delimited(1, element_id.encode()),
            _length_delimited(2, name.encode()),
            _length_delimited(6, action.SerializeToString()),
            _length_delimited(10, b""),
            _length_delimited(14, _length_delimited(1, trigger_source)),
        )
    )


def _image(data: bytes, *, cols: int = 8, rows: int = 6) -> image_pb2.Image:
    return image_pb2.Image(
        cols=cols,
        rows=rows,
        data=data,
        format=image_pb2.Image.FORMAT_JPEG,
        pixel_format=image_pb2.Image.PIXEL_FORMAT_RGB_U8,
    )


def _bundle(
    tmp_path: Path,
    *,
    navigation_only: bool = False,
    with_dock: bool = False,
    with_opaque_profile: bool = False,
    relocalize_marker: bytes | None = b"",
    explicit_relocalize: bytes | None = None,
) -> tuple[Path, dict[str, str]]:
    bundle = tmp_path / "bundle"
    (bundle / "waypoint_snapshots").mkdir(parents=True)
    (bundle / "edge_snapshots").mkdir()
    (bundle / "action_payloads" / "images").mkdir(parents=True)
    (bundle / "dock_payloads").mkdir()

    old_element_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    new_element_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    old_waypoint_id = "source-waypoint"
    new_waypoint_id = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    snapshot_id = "snapshot-cloned"
    old_mission_id = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
    graph = map_pb2.Graph()
    waypoint = graph.waypoints.add(id=new_waypoint_id, snapshot_id=snapshot_id)
    waypoint.annotations.client_metadata.session_name = "source-session"
    waypoint.annotations.client_metadata.client_id = "source-client"
    (bundle / "graph").write_bytes(graph.SerializeToString())
    snapshot = map_pb2.WaypointSnapshot(id=snapshot_id)
    (bundle / "waypoint_snapshots" / snapshot_id).write_bytes(snapshot.SerializeToString())

    action = None
    wrapper = None
    image_records = []
    if not navigation_only:
        action = walks_pb2.Action()
        daq = action.data_acquisition
        request = daq.acquire_data_request
        request.action_id.action_name = "Gauge"
        request.metadata.data.fields["element_id"].string_value = new_element_id
        request.metadata.data.fields["mission_id"].string_value = old_mission_id
        capture = daq.record_time_images.add(image_service="spot-cam-image")
        capture.source.name = "ptz"
        capture.shot.frame_name_image_sensor = "ptz"
        capture.shot.image.CopyFrom(_image(b""))

        wrapper = walks_pb2.ActionWrapper()
        body_pose = wrapper.robot_body_pose.target_tform_body
        body_pose.position.x = 0.35
        body_pose.position.y = -0.12
        body_pose.position.z = 0.04
        body_pose.rotation.z = 0.5
        body_pose.rotation.w = 0.8660254037844386
        alignment = wrapper.spot_cam_alignment.alignments.add()
        alignment.reference_image.image_service = "spot-cam-image"
        alignment.reference_image.source.name = "ptz"
        alignment.reference_image.shot.frame_name_image_sensor = "ptz"
        alignment.reference_image.shot.image.CopyFrom(_image(b""))

        daq_name = f"{new_element_id}-daq-spot-cam-image-ptz-ptz-1"
        alignment_name = f"{new_element_id}-alignment-0-spot-cam-image-ptz-ptz-1"
        for filename, payload in (
            (daq_name, _image(b"daq-image")),
            (alignment_name, _image(b"alignment-image")),
        ):
            relative = f"action_payloads/images/{filename}"
            (bundle / relative).write_bytes(payload.SerializeToString())
            image_records.append(
                {
                    "source_path": f"graph_nav/site_element_images/{filename}",
                    "cloned_path": relative,
                }
            )

    payload_name = f"{new_element_id}.site_element"
    (bundle / "action_payloads" / payload_name).write_bytes(
        _site_element(
            new_element_id,
            new_waypoint_id,
            "Gauge",
            action,
            wrapper,
            relocalize_marker,
            explicit_relocalize,
        )
    )
    docks = []
    if with_dock:
        target = walks_pb2.Target()
        target.navigate_to.destination_waypoint_id = new_waypoint_id
        target_name = "ffffffff-ffff-4fff-8fff-ffffffffffff.target"
        (bundle / "dock_payloads" / target_name).write_bytes(target.SerializeToString())
        docks.append(
            {
                "source_record_id": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
                "new_record_id": "ffffffff-ffff-4fff-8fff-ffffffffffff",
                "dock_id": 520,
                "source_docked_waypoint_id": old_waypoint_id,
                "new_docked_waypoint_id": new_waypoint_id,
                "source_target_waypoint_ids": [old_waypoint_id],
                "new_target_waypoint_ids": [new_waypoint_id],
                "cloned_target": f"dock_payloads/{target_name}",
            }
        )
    manifest = {
        "schema_version": 2,
        "clone_name": "zone clone",
        "source": {
            "backup": "/read-only/source.tar",
            "site_map": {"id": "site-map-1", "name": "Source"},
        },
        "selection": {
            "core_waypoint_ids": [old_waypoint_id],
            "halo_waypoint_ids": [],
            "clone_halo_actions": False,
        },
        "id_mappings": {
            "waypoint": {old_waypoint_id: new_waypoint_id},
            "waypoint_snapshot": {"source-snapshot": snapshot_id},
            "site_element": {old_element_id: new_element_id},
        },
        "actions": [
            {
                "source_element_id": old_element_id,
                "new_element_id": new_element_id,
                "name": "Gauge",
                "source_waypoint_id": old_waypoint_id,
                "new_waypoint_id": new_waypoint_id,
                "cloned_payload": f"action_payloads/{payload_name}",
                "replacement_counts": {"element_id": 2, "waypoint_id": 1},
                "source_mission_ids": [old_mission_id] if action else [],
                "external_uuid_references": [],
                "images": image_records,
            }
        ],
        "docks": docks,
        "docks_skipped": [],
        "action_payloads_rewritten": True,
        "dock_targets_rewritten": True,
        "action_ingestion_ready": False,
        "walk_target_opaque_profile": (
            {
                "selection": "consensus_across_backup",
                "source_path": "graph_nav/site_walk/source-defaults",
                "source_updated": 20,
                "observed_site_walks": 2,
                "travel_params_fields_hex": (
                    _length_delimited(12, b"opaque-travel-12")
                    + _length_delimited(13, b"opaque-travel-13")
                ).hex(),
                "travel_params_field_numbers": [12, 13],
                "target_fields_hex": _length_delimited(4, b"opaque-target-4").hex(),
                "target_field_numbers": [4],
            }
            if with_opaque_profile
            else None
        ),
    }
    (bundle / "clone_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return bundle, {
        "element_id": new_element_id,
        "waypoint_id": new_waypoint_id,
        "old_mission_id": old_mission_id,
        "snapshot_id": snapshot_id,
    }


def _add_triggered_aivi(bundle: Path, ids: dict[str, str]) -> tuple[bytes, bytes, str]:
    manifest_path = bundle / "clone_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    parent_record = manifest["actions"][0]
    parent_path = bundle / parent_record["cloned_payload"]
    parent_fields = decode_fields(parent_path.read_bytes())
    parent_action = walks_pb2.Action.FromString(bytes_values(parent_fields, 6)[0])
    parent_wrapper = walks_pb2.ActionWrapper.FromString(bytes_values(parent_fields, 10)[0])
    parent_requests = parent_action.data_acquisition.acquire_data_request.acquisition_requests
    parent_capture = parent_requests.image_captures.add()
    parent_capture.image_service = "spot-cam-image"
    parent_capture.image_request.image_source_name = "ptz"
    parent_capture.image_request.quality_percent = 50
    parent_path.write_bytes(
        _site_element(
            ids["element_id"],
            ids["waypoint_id"],
            "Gauge",
            parent_action,
            parent_wrapper,
        )
    )

    inspection_action = walks_pb2.Action()
    inspection_daq = inspection_action.data_acquisition
    inspection_request = inspection_daq.acquire_data_request
    inspection_capture = inspection_request.acquisition_requests.network_compute_captures.add()
    inspection_capture.server_config.SetInParent()
    inspection_capture.input_data_bridge.parameters.model_name = "AIVI - Learning"
    inspection_capture.input_data_bridge.parameters.custom_params.values[
        "question"
    ].string_value.value = "Is the door open?"
    inspection_request.min_timeout.seconds = 90
    inspection_capability = inspection_daq.last_known_capabilities.network_compute_sources.add()
    inspection_capability.server_config.service_name = "AIVI - Learning"
    inspection_capability.models.data.add(model_name="AIVI - Learning")

    source_inspection_id = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
    new_inspection_id = "ffffffff-ffff-4fff-8fff-ffffffffffff"
    inspection_name = "Door Check (AI)"
    inspection_filename = f"{new_inspection_id}.site_element"
    (bundle / "action_payloads" / inspection_filename).write_bytes(
        _triggered_site_element(
            new_inspection_id,
            ids["element_id"],
            inspection_name,
            inspection_action,
        )
    )
    source_parent_id = parent_record["source_element_id"]
    manifest["id_mappings"]["site_element"][source_inspection_id] = new_inspection_id
    manifest["triggered_actions"] = [
        {
            "source_element_id": source_inspection_id,
            "new_element_id": new_inspection_id,
            "name": inspection_name,
            "source_parent_element_id": source_parent_id,
            "new_parent_element_id": ids["element_id"],
            "trigger_image_service": "spot-cam-ptz",
            "cloned_payload": f"action_payloads/{inspection_filename}",
            "replacement_counts": {
                "element_id": 1,
                "trigger_parent_element_id": 1,
            },
            "source_mission_ids": [],
            "external_uuid_references": [],
            "images": [],
        }
    ]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return (
        inspection_capture.SerializeToString(deterministic=True),
        inspection_capability.SerializeToString(deterministic=True),
        new_inspection_id,
    )


def test_export_walk_rehydrates_images_and_rewrites_daq_identity(tmp_path: Path) -> None:
    bundle, ids = _bundle(tmp_path)
    template = tmp_path / "template.walk.zip"
    with zipfile.ZipFile(template, "w") as archive:
        archive.writestr("template.walk/autowalk_metadata", b"opaque-metadata")
    output = tmp_path / "zone clone.walk.zip"

    result = export_walk_archive(bundle, output, template_archive=template)

    assert result["validation"]["valid"]
    assert result["counts"]["embedded_images"] == 2
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        assert "zone clone.walk/missions/" in names
        assert "zone clone.walk/waypoint_snapshots/" in names
        assert "zone clone.walk/edge_snapshots/" in names
        assert "zone clone.walk/autowalk_metadata" in names
        assert archive.read("zone clone.walk/autowalk_metadata") == b"opaque-metadata"
        assert f"zone clone.walk/waypoint_snapshots/{ids['snapshot_id']}" in names
        walk = walks_pb2.Walk.FromString(archive.read("zone clone.walk/missions/zone clone.walk"))
    assert len(walk.elements) == 1
    element = walk.elements[0]
    assert element.id == ids["element_id"]
    assert element.target.navigate_to.destination_waypoint_id == ids["waypoint_id"]
    navigate_to = element.target.navigate_to
    assert navigate_to.travel_params.max_distance == pytest.approx(0.2)
    assert (
        navigate_to.travel_params.feature_quality_tolerance
        == navigate_to.travel_params.TOLERANCE_DEFAULT
    )
    assert navigate_to.travel_params.blocked_path_wait_time.seconds == 5
    assert navigate_to.destination_waypoint_tform_body_goal.position.x == pytest.approx(0.35)
    assert navigate_to.destination_waypoint_tform_body_goal.position.y == pytest.approx(-0.12)
    assert navigate_to.destination_waypoint_tform_body_goal.angle == pytest.approx(
        1.0471975511965976
    )
    assert element.target.HasField("relocalize")
    fields = element.action.data_acquisition.acquire_data_request.metadata.data.fields
    assert fields["element_id"].string_value == ids["element_id"]
    assert fields["mission_id"].string_value == ids["old_mission_id"]
    assert fields["mission_id"].string_value != walk.id
    assert walk.global_parameters.group_name == "zone clone"
    assert walk.global_parameters.self_right_attempts == 1
    assert walk.playback_mode.WhichOneof("mode") == "once"
    assert walk.HasField("interrupts")
    assert not walk.HasField("choreography_items")
    assert element.target_failure_behavior.retry_count == 0
    assert element.action.data_acquisition.record_time_images[0].shot.image.data == b"daq-image"
    assert (
        element.action_wrapper.spot_cam_alignment.alignments[0].reference_image.shot.image.data
        == b"alignment-image"
    )
    assert validate_walk_archive(output).valid


def test_export_walk_keeps_navigation_only_site_element(tmp_path: Path) -> None:
    bundle, ids = _bundle(tmp_path, navigation_only=True)
    output = tmp_path / "navigation.walk.zip"

    result = export_walk_archive(bundle, output, name="navigation")

    assert result["counts"]["navigation_only_elements"] == 1
    with zipfile.ZipFile(output) as archive:
        walk = walks_pb2.Walk.FromString(archive.read("navigation.walk/missions/navigation.walk"))
    assert walk.elements[0].id == ids["element_id"]
    assert walk.elements[0].action.WhichOneof("action") is None


def test_export_walk_can_replace_recording_session_and_refresh_walk_id(tmp_path: Path) -> None:
    bundle, _ = _bundle(tmp_path)
    original_output = tmp_path / "original.walk.zip"
    refreshed_output = tmp_path / "refreshed.walk.zip"

    original = export_walk_archive(bundle, original_output)
    refreshed = export_walk_archive(
        bundle,
        refreshed_output,
        name="fresh walk",
        recording_name="fresh recording",
    )

    assert refreshed["walk_id"] != original["walk_id"]
    assert refreshed["recording_session"] == {
        "mode": "overridden",
        "name": "fresh recording",
        "source_names": {"source-session": 1},
        "waypoints_updated": 1,
    }
    with zipfile.ZipFile(refreshed_output) as archive:
        walk = walks_pb2.Walk.FromString(archive.read("fresh walk.walk/missions/fresh walk.walk"))
        graph = map_pb2.Graph.FromString(archive.read("fresh walk.walk/graph"))
    assert walk.id == refreshed["walk_id"]
    assert walk.map_name == "fresh walk"
    assert walk.mission_name == "fresh walk"
    assert walk.global_parameters.group_name == "fresh walk"
    assert graph.waypoints[0].annotations.client_metadata.session_name == "fresh recording"
    assert graph.waypoints[0].annotations.client_metadata.client_id == "source-client"


def test_export_walk_rejects_empty_recording_name(tmp_path: Path) -> None:
    bundle, _ = _bundle(tmp_path)

    with pytest.raises(ValueError, match="recording name cannot be empty"):
        export_walk_archive(
            bundle,
            tmp_path / "bad-recording.walk.zip",
            recording_name="   ",
        )


def test_export_walk_preserves_relocalize_presence_and_unknown_fields(tmp_path: Path) -> None:
    relocalize = walks_pb2.Target.Relocalize()
    relocalize.set_localization_request.initial_guess.waypoint_id = (
        "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    )
    relocalize.MergeFromString(_length_delimited(11, b"opaque-relocalize"))
    relocalize_payload = relocalize.SerializeToString()
    bundle, _ = _bundle(tmp_path, explicit_relocalize=relocalize_payload)
    output = tmp_path / "relocalize.walk.zip"

    export_walk_archive(bundle, output, name="relocalize")

    with zipfile.ZipFile(output) as archive:
        walk = walks_pb2.Walk.FromString(archive.read("relocalize.walk/missions/relocalize.walk"))
    assert walk.elements[0].target.HasField("relocalize")
    assert walk.elements[0].target.relocalize.SerializeToString() == relocalize_payload


def test_export_walk_does_not_invent_relocalize_when_site_field_is_absent(
    tmp_path: Path,
) -> None:
    bundle, _ = _bundle(
        tmp_path,
        relocalize_marker=None,
        explicit_relocalize=None,
    )
    output = tmp_path / "no-relocalize.walk.zip"

    export_walk_archive(bundle, output, name="no-relocalize")

    with zipfile.ZipFile(output) as archive:
        walk = walks_pb2.Walk.FromString(
            archive.read("no-relocalize.walk/missions/no-relocalize.walk")
        )
    assert not walk.elements[0].target.HasField("relocalize")


def test_export_walk_preserves_site_element_navigation_target_fields(tmp_path: Path) -> None:
    bundle, ids = _bundle(tmp_path)
    manifest = json.loads((bundle / "clone_manifest.json").read_text(encoding="utf-8"))
    action_record = manifest["actions"][0]
    payload_path = bundle / action_record["cloned_payload"]
    body_goal = walks_pb2.Target().navigate_to.destination_waypoint_tform_body_goal
    body_goal.position.x = 0.35000000000000003
    body_goal.position.y = -0.12000000000000001
    body_goal.angle = 1.0471975511965974
    payload_path.write_bytes(
        payload_path.read_bytes()
        + _fixed64(4, 0.35)
        + _length_delimited(15, body_goal.SerializeToString(deterministic=True))
    )
    output = tmp_path / "site-target.walk.zip"

    export_walk_archive(bundle, output, name="site-target")

    with zipfile.ZipFile(output) as archive:
        walk = walks_pb2.Walk.FromString(archive.read("site-target.walk/missions/site-target.walk"))
    navigate_to = walk.elements[0].target.navigate_to
    assert navigate_to.destination_waypoint_id == ids["waypoint_id"]
    assert navigate_to.travel_params.max_distance == 0.35
    assert navigate_to.destination_waypoint_tform_body_goal.SerializeToString(
        deterministic=True
    ) == body_goal.SerializeToString(deterministic=True)


def test_export_walk_rejects_unmatched_sidecar(tmp_path: Path) -> None:
    bundle, ids = _bundle(tmp_path)
    manifest_path = bundle / "clone_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    image = manifest["actions"][0]["images"][0]
    source = bundle / image["cloned_path"]
    bad_relative = f"action_payloads/images/{ids['element_id']}-unknown-1"
    source.rename(bundle / bad_relative)
    image["cloned_path"] = bad_relative
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="no DAQ image sidecar matches"):
        export_walk_archive(bundle, tmp_path / "bad.walk.zip")


def test_export_walk_reports_stale_extra_sidecar(tmp_path: Path) -> None:
    bundle, ids = _bundle(tmp_path)
    stale_name = f"{ids['element_id']}-stale-old-image-1"
    stale_relative = f"action_payloads/images/{stale_name}"
    (bundle / stale_relative).write_bytes(_image(b"stale-image").SerializeToString())
    manifest_path = bundle / "clone_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["actions"][0]["images"].append(
        {
            "source_path": f"graph_nav/site_element_images/{stale_name}",
            "cloned_path": stale_relative,
        }
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = export_walk_archive(bundle, tmp_path / "stale.walk.zip", name="stale")

    assert result["validation"]["valid"]
    assert result["counts"]["embedded_images"] == 2
    assert result["counts"]["unused_action_image_sidecars"] == 1
    assert result["unused_action_image_sidecar_files"] == [stale_name]


def test_export_walk_rejects_unsafe_name(tmp_path: Path) -> None:
    bundle, _ = _bundle(tmp_path, navigation_only=True)
    with pytest.raises(ValueError, match="unsafe Walk archive name"):
        export_walk_archive(bundle, tmp_path / "bad.walk.zip", name="../bad")


def test_export_walk_refuses_to_silently_drop_triggered_actions(tmp_path: Path) -> None:
    bundle, _ = _bundle(tmp_path)
    manifest_path = bundle / "clone_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["triggered_actions"] = [{"name": "Door Check (AI)"}]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="refuses to silently omit"):
        export_walk_archive(bundle, tmp_path / "triggered.walk.zip")


def test_export_walk_can_experimentally_fold_triggered_aivi_into_parent(
    tmp_path: Path,
) -> None:
    bundle, ids = _bundle(tmp_path)
    inspection_capture, inspection_capability, inspection_id = _add_triggered_aivi(bundle, ids)
    output = tmp_path / "triggered-fold.walk.zip"

    result = export_walk_archive(
        bundle,
        output,
        name="triggered-fold",
        triggered_ai_mode="fold-into-parent",
    )

    assert result["validation"]["valid"]
    assert result["counts"]["triggered_ai_inspections_folded"] == 1
    assert result["counts"]["triggered_ai_network_compute_captures_added"] == 1
    assert result["orbit_ai_trigger"] == {
        "aivi_name_suffix_elements": 0,
        "triggered_ai_inspections_selected": 1,
        "capture_actions": "preserved",
        "mode": "fold-into-parent",
        "trigger_configuration": "experimental_triggered_ai_request_folded_into_parent_action",
        "private_parent_trigger_field": "not_represented_in_public_walk",
        "runtime_equivalence": "unverified_requires_orbit_import_and_reexport",
    }
    assert result["triggered_ai_folds"][0]["triggered_ai_inspection_element_id"] == inspection_id
    assert (
        result["triggered_ai_folds"][0]["network_compute_captures"][0]["input_binding"]
        == "implicit_private_parent_trigger_removed"
    )

    with zipfile.ZipFile(output) as archive:
        walk = walks_pb2.Walk.FromString(
            archive.read("triggered-fold.walk/missions/triggered-fold.walk")
        )
    assert len(walk.elements) == 1
    element = walk.elements[0]
    assert element.id == ids["element_id"]
    request = element.action.data_acquisition.acquire_data_request.acquisition_requests
    assert len(request.image_captures) == 1
    assert request.image_captures[0].image_service == "spot-cam-image"
    assert request.image_captures[0].image_request.image_source_name == "ptz"
    assert len(request.network_compute_captures) == 1
    assert (
        request.network_compute_captures[0].SerializeToString(deterministic=True)
        == inspection_capture
    )
    capabilities = element.action.data_acquisition.last_known_capabilities
    assert inspection_capability in {
        capability.SerializeToString(deterministic=True)
        for capability in capabilities.network_compute_sources
    }
    assert validate_walk_archive(output).valid


def test_export_walk_includes_cloned_dock(tmp_path: Path) -> None:
    bundle, ids = _bundle(tmp_path, navigation_only=True, with_dock=True)
    output = tmp_path / "dock.walk.zip"

    result = export_walk_archive(bundle, output, name="dock")

    assert result["counts"]["docks"] == 1
    with zipfile.ZipFile(output) as archive:
        walk = walks_pb2.Walk.FromString(archive.read("dock.walk/missions/dock.walk"))
    assert len(walk.docks) == 1
    assert walk.docks[0].dock_id == 520
    assert walk.docks[0].docked_waypoint_id == ids["waypoint_id"]
    assert walk.docks[0].target_prep_pose.navigate_to.destination_waypoint_id == ids["waypoint_id"]
    assert walk.docks[0].prompt_duration.seconds == 10
    assert validate_walk_archive(output).valid


def test_export_walk_preserves_backup_opaque_target_profile(tmp_path: Path) -> None:
    bundle, _ = _bundle(tmp_path, with_opaque_profile=True)
    output = tmp_path / "opaque.walk.zip"

    result = export_walk_archive(bundle, output, name="opaque")

    assert result["opaque_target_profile"] == {
        "status": "preserved",
        "source_path": "graph_nav/site_walk/source-defaults",
        "travel_params_field_numbers": [12, 13],
        "target_field_numbers": [4],
    }
    with zipfile.ZipFile(output) as archive:
        walk = walks_pb2.Walk.FromString(archive.read("opaque.walk/missions/opaque.walk"))
    target = walk.elements[0].target
    target_fields = decode_fields(target.SerializeToString())
    travel_fields = decode_fields(target.navigate_to.travel_params.SerializeToString())
    assert bytes_values(target_fields, 4) == (b"opaque-target-4",)
    assert bytes_values(travel_fields, 12) == (b"opaque-travel-12",)
    assert bytes_values(travel_fields, 13) == (b"opaque-travel-13",)
