import json
import struct
import uuid
import zipfile
from pathlib import Path

import pytest
from bosdyn.api import image_pb2
from bosdyn.api.autowalk import walks_pb2
from bosdyn.api.graph_nav import map_pb2
from google.protobuf import any_pb2

from spot_graphnav_map_forge.walk_archive import (
    export_walk_archive,
    reissue_walk_recording,
    validate_walk_archive,
)
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
    identity_mode: str | None = None,
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
    new_waypoint_id = (
        "mapped-waypoint-clMruAOUm7YxlJ5D7tH..g=="
        if identity_mode == "orbit-native"
        else "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    )
    snapshot_id = (
        "snapshot_mapped-waypoint-avzWVCdYcecalMtz1AglPA=="
        if identity_mode == "orbit-native"
        else "snapshot-cloned"
    )
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
    if identity_mode is not None:
        manifest["identity_policy"] = {"mode": identity_mode}
    (bundle / "clone_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return bundle, {
        "element_id": new_element_id,
        "source_element_id": old_element_id,
        "waypoint_id": new_waypoint_id,
        "source_waypoint_id": old_waypoint_id,
        "old_mission_id": old_mission_id,
        "snapshot_id": snapshot_id,
    }


def _recording_template_directory(
    tmp_path: Path,
    ids: dict[str, str],
    *,
    sleep_source_waypoint_id: str | None = None,
) -> tuple[Path, bytes]:
    root = tmp_path / "recording-template.walk"
    (root / "missions").mkdir(parents=True)
    graph = map_pb2.Graph()
    graph.waypoints.add(id=ids["source_waypoint_id"])
    graph.anchoring.anchors.add(id=ids["source_waypoint_id"])
    anchored_dock = graph.anchoring.objects.add(id="520")
    anchored_dock.seed_tform_object.rotation.w = 1
    if sleep_source_waypoint_id is not None:
        graph.waypoints.add(id=sleep_source_waypoint_id)
        graph.anchoring.anchors.add(id=sleep_source_waypoint_id)
        edge = graph.edges.add()
        edge.id.from_waypoint = ids["source_waypoint_id"]
        edge.id.to_waypoint = sleep_source_waypoint_id
    (root / "graph").write_bytes(graph.SerializeToString())

    walk = walks_pb2.Walk(
        id="11111111-1111-4111-8111-111111111111",
        map_name="recording-template",
        mission_name="recording-template",
    )
    walk.global_parameters.should_autofocus_ptz = True
    walk.global_parameters.hri_behaviors.play_undock_behaviors = True
    walk.playback_mode.SetInParent()
    walk.choreography_items.SetInParent()
    walk.interrupts.SetInParent()
    source_element = walk.elements.add(id=ids["source_element_id"], name="Gauge")
    source_element.target.navigate_route.route.waypoint_id.append(ids["source_waypoint_id"])
    source_element.target.navigate_route.travel_params.max_distance = 0.2
    source_element.target.navigate_route.destination_waypoint_tform_body_goal.SetInParent()
    if sleep_source_waypoint_id is not None:
        pose = walk.elements.add(
            id="22222222-2222-4222-8222-222222222222",
            name="Pose - 1",
        )
        pose.action.sleep.duration.seconds = 1
        pose.target.navigate_route.route.waypoint_id.extend(
            (ids["source_waypoint_id"], sleep_source_waypoint_id)
        )
        route_edge = pose.target.navigate_route.route.edge_id.add()
        route_edge.from_waypoint = ids["source_waypoint_id"]
        route_edge.to_waypoint = sleep_source_waypoint_id
        pose.target.navigate_route.travel_params.max_distance = 0.2
        pose.target.navigate_route.destination_waypoint_tform_body_goal.SetInParent()
    dock = walk.docks.add(
        dock_id=520,
        docked_waypoint_id=ids["source_waypoint_id"],
    )
    dock.target_prep_pose.navigate_to.destination_waypoint_id = ids["source_waypoint_id"]
    dock.prompt_duration.seconds = 60

    metadata = b"synthetic-recording-metadata"
    extension = any_pb2.Any(
        type_url="type.googleapis.com/example.internal.MissionMetaData",
        value=metadata,
    )
    mission_payload = walk.SerializeToString() + _length_delimited(
        1000, extension.SerializeToString()
    )
    (root / "missions" / "recording-template.walk").write_bytes(mission_payload)
    (root / "autowalk_metadata").write_bytes(metadata)
    return root, metadata


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
        assert archive.read("zone clone.walk/graph") == (bundle / "graph").read_bytes()
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


def test_export_walk_applies_recording_envelope_routes_and_dock_profile(tmp_path: Path) -> None:
    bundle, ids = _bundle(tmp_path, with_dock=True, with_opaque_profile=True)
    template, metadata = _recording_template_directory(tmp_path, ids)
    output = tmp_path / "recording-compatible.walk.zip"
    new_walk_id = "33333333-3333-4333-8333-333333333333"

    result = export_walk_archive(
        bundle,
        output,
        name="recording-compatible",
        recording_template=template,
        walk_id=new_walk_id,
    )

    assert result["validation"]["valid"]
    assert result["recording_compatibility"]["status"] == "recording_structure_applied"
    assert result["recording_compatibility"]["walk_extension_fields"] == [1000]
    assert result["recording_compatibility"]["routes"][0]["status"] == ("recorded_route_remapped")
    with zipfile.ZipFile(output) as archive:
        root = "recording-compatible.walk"
        output_graph = map_pb2.Graph.FromString(archive.read(f"{root}/graph"))
        assert archive.read(f"{root}/autowalk_metadata") == metadata
        mission_payload = archive.read(f"{root}/missions/recording-compatible.walk")
    source_graph = map_pb2.Graph.FromString((bundle / "graph").read_bytes())
    assert [waypoint.id for waypoint in output_graph.waypoints] == [
        waypoint.id for waypoint in source_graph.waypoints
    ]
    assert [edge.SerializeToString() for edge in output_graph.edges] == [
        edge.SerializeToString() for edge in source_graph.edges
    ]
    assert [anchor.id for anchor in output_graph.anchoring.anchors] == [ids["waypoint_id"]]
    assert [value.id for value in output_graph.anchoring.objects] == ["520"]
    anchoring = result["recording_compatibility"]["anchoring"]
    assert anchoring["anchors_added"] == 1
    assert anchoring["anchored_object_ids"] == ["520"]
    extension_payloads = bytes_values(decode_fields(mission_payload), 1000)
    assert len(extension_payloads) == 1
    extension = any_pb2.Any.FromString(extension_payloads[0])
    assert extension.value == metadata
    walk = walks_pb2.Walk.FromString(mission_payload)
    assert walk.id == new_walk_id
    assert walk.playback_mode.WhichOneof("mode") is None
    assert walk.global_parameters.should_autofocus_ptz
    assert walk.global_parameters.group_name == ""
    assert walk.global_parameters.self_right_attempts == 0
    assert walk.global_parameters.hri_behaviors.play_undock_behaviors
    assert walk.HasField("choreography_items")
    assert walk.HasField("interrupts")

    element = walk.elements[0]
    assert element.target.WhichOneof("target") == "navigate_route"
    assert list(element.target.navigate_route.route.waypoint_id) == [ids["waypoint_id"]]
    assert element.target_failure_behavior.retry_count == 2
    assert element.action_failure_behavior.retry_count == 2
    assert element.HasField("action_duration")
    fields = element.action.data_acquisition.acquire_data_request.metadata.data.fields
    assert fields["element_id"].string_value == element.id
    assert fields["mission_id"].string_value == new_walk_id

    dock = walk.docks[0]
    assert dock.dock_id == 520
    assert dock.docked_waypoint_id == ids["waypoint_id"]
    assert dock.target_prep_pose.navigate_to.destination_waypoint_id == ids["waypoint_id"]
    assert [field.number for field in decode_fields(dock.target_prep_pose.SerializeToString())] == [
        1
    ]
    assert dock.prompt_duration.seconds == 60


def test_export_walk_builds_sleep_route_from_recording_template(tmp_path: Path) -> None:
    bundle, ids = _bundle(tmp_path, with_opaque_profile=True)
    source_sleep_waypoint_id = "source-sleep-waypoint"
    output_sleep_waypoint_id = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
    output_sleep_snapshot_id = "sleep-snapshot-cloned"

    graph_path = bundle / "graph"
    graph = map_pb2.Graph.FromString(graph_path.read_bytes())
    graph.waypoints.add(
        id=output_sleep_waypoint_id,
        snapshot_id=output_sleep_snapshot_id,
    )
    edge = graph.edges.add()
    edge.id.from_waypoint = ids["waypoint_id"]
    edge.id.to_waypoint = output_sleep_waypoint_id
    graph_path.write_bytes(graph.SerializeToString())
    (bundle / "waypoint_snapshots" / output_sleep_snapshot_id).write_bytes(
        map_pb2.WaypointSnapshot(id=output_sleep_snapshot_id).SerializeToString()
    )
    manifest_path = bundle / "clone_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["selection"]["core_waypoint_ids"].append(source_sleep_waypoint_id)
    manifest["id_mappings"]["waypoint"][source_sleep_waypoint_id] = output_sleep_waypoint_id
    manifest["id_mappings"]["waypoint_snapshot"]["source-sleep-snapshot"] = output_sleep_snapshot_id
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    template, _ = _recording_template_directory(
        tmp_path,
        ids,
        sleep_source_waypoint_id=source_sleep_waypoint_id,
    )
    output = tmp_path / "recording-compatible-sleep.walk.zip"
    result = export_walk_archive(
        bundle,
        output,
        name="recording-compatible-sleep",
        recording_template=template,
        walk_id="33333333-3333-4333-8333-333333333333",
        sleep_waypoint_id=source_sleep_waypoint_id,
        sleep_after_element="Gauge",
    )

    assert result["validation"]["valid"]
    sleep_report = result["recording_compatibility"]["routes"][-1]
    assert sleep_report["status"] == "recorded_route_segment_remapped"
    with zipfile.ZipFile(output) as archive:
        mission_payload = archive.read(
            "recording-compatible-sleep.walk/missions/recording-compatible-sleep.walk"
        )
    walk = walks_pb2.Walk.FromString(mission_payload)
    sleep = next(element for element in walk.elements if element.name == "Sleep - 1")
    assert sleep.action.WhichOneof("action") == "sleep"
    assert sleep.target.WhichOneof("target") == "navigate_route"
    assert list(sleep.target.navigate_route.route.waypoint_id) == [
        ids["waypoint_id"],
        output_sleep_waypoint_id,
    ]
    assert [
        (edge_id.from_waypoint, edge_id.to_waypoint)
        for edge_id in sleep.target.navigate_route.route.edge_id
    ] == [(ids["waypoint_id"], output_sleep_waypoint_id)]
    assert sleep.HasField("action_duration")


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


def test_orbit_native_export_uses_uuid4_shaped_walk_and_sleep_element_ids(
    tmp_path: Path,
) -> None:
    bundle, ids = _bundle(
        tmp_path,
        identity_mode="orbit-native",
        with_opaque_profile=True,
    )
    output = tmp_path / "native.walk.zip"

    result = export_walk_archive(
        bundle,
        output,
        name="native",
        sleep_waypoint_id=ids["source_waypoint_id"],
    )

    assert uuid.UUID(result["walk_id"]).version == 4
    with zipfile.ZipFile(output) as archive:
        walk = walks_pb2.Walk.FromString(archive.read("native.walk/missions/native.walk"))
    assert [uuid.UUID(element.id).version for element in walk.elements] == [4, 4]
    assert [element.action.WhichOneof("action") for element in walk.elements] == [
        "data_acquisition",
        "sleep",
    ]

    with pytest.raises(ValueError, match="version-4 Walk UUID"):
        export_walk_archive(
            bundle,
            tmp_path / "native-bad-id.walk.zip",
            name="native-bad-id",
            walk_id="11111111-1111-5111-8111-111111111111",
        )


def test_export_walk_rejects_empty_recording_name(tmp_path: Path) -> None:
    bundle, _ = _bundle(tmp_path)

    with pytest.raises(ValueError, match="recording name cannot be empty"):
        export_walk_archive(
            bundle,
            tmp_path / "bad-recording.walk.zip",
            recording_name="   ",
        )


def test_export_walk_rejects_waypoint_metadata_override_in_preserve_mode(tmp_path: Path) -> None:
    bundle, _ = _bundle(tmp_path)
    manifest_path = bundle / "clone_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["identity_policy"] = {"mode": "preserve"}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="mutate metadata on shared waypoint identities"):
        export_walk_archive(
            bundle,
            tmp_path / "preserve-recording-name.walk.zip",
            recording_name="must-not-change",
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
    bundle, ids = _bundle(
        tmp_path,
        navigation_only=True,
        with_dock=True,
        with_opaque_profile=True,
    )
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
    target = walk.docks[0].target_prep_pose
    travel_params = target.navigate_to.travel_params
    assert travel_params.feature_quality_tolerance == travel_params.TOLERANCE_DEFAULT
    assert travel_params.blocked_path_wait_time.seconds == 5
    target_fields = decode_fields(target.SerializeToString())
    travel_fields = decode_fields(travel_params.SerializeToString())
    assert bytes_values(target_fields, 4) == (b"opaque-target-4",)
    assert bytes_values(travel_fields, 12) == (b"opaque-travel-12",)
    assert bytes_values(travel_fields, 13) == (b"opaque-travel-13",)
    assert validate_walk_archive(output).valid


def test_export_walk_refuses_dock_without_observed_target_profile(tmp_path: Path) -> None:
    bundle, _ = _bundle(tmp_path, navigation_only=True, with_dock=True)

    with pytest.raises(ValueError, match="refusing an incomplete Dock"):
        export_walk_archive(bundle, tmp_path / "incomplete-dock.walk.zip", name="dock")


def test_export_walk_adds_audited_sleep_action_at_source_waypoint(tmp_path: Path) -> None:
    bundle, ids = _bundle(tmp_path, with_opaque_profile=True)
    output = tmp_path / "sleep.walk.zip"

    result = export_walk_archive(
        bundle,
        output,
        name="sleep",
        sleep_waypoint_id="source-waypoint",
        sleep_duration_seconds=0.25,
        sleep_name="Sleep - 1",
        sleep_after_element="Gauge",
    )

    report = result["synthetic_sleep_action"]
    assert report["status"] == "explicitly_synthesized"
    assert report["requested_id_kind"] == "source"
    assert report["source_waypoint_id"] == "source-waypoint"
    assert report["cloned_waypoint_id"] == ids["waypoint_id"]
    assert report["duration_seconds"] == pytest.approx(0.25)
    assert report["element_index"] == 1
    assert report["inserted_after"] == "Gauge"
    assert result["action_kinds"] == {"data_acquisition": 1, "sleep": 1}

    with zipfile.ZipFile(output) as archive:
        walk = walks_pb2.Walk.FromString(archive.read("sleep.walk/missions/sleep.walk"))
    assert [element.name for element in walk.elements] == ["Gauge", "Sleep - 1"]
    sleep = walk.elements[1]
    assert sleep.id == report["element_id"]
    assert sleep.action.WhichOneof("action") == "sleep"
    assert sleep.action.sleep.duration.seconds == 0
    assert sleep.action.sleep.duration.nanos == 250_000_000
    assert sleep.target.navigate_to.destination_waypoint_id == ids["waypoint_id"]
    assert sleep.target.navigate_to.travel_params.max_distance == pytest.approx(0.2)
    assert (
        sleep.target.navigate_to.travel_params.feature_quality_tolerance
        == sleep.target.navigate_to.travel_params.TOLERANCE_DEFAULT
    )
    assert sleep.target.navigate_to.travel_params.blocked_path_wait_time.seconds == 5
    target_fields = decode_fields(sleep.target.SerializeToString())
    travel_fields = decode_fields(sleep.target.navigate_to.travel_params.SerializeToString())
    assert bytes_values(target_fields, 4) == (b"opaque-target-4",)
    assert bytes_values(travel_fields, 12) == (b"opaque-travel-12",)
    assert bytes_values(travel_fields, 13) == (b"opaque-travel-13",)
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


def _recorded_walk_directory(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    source = tmp_path / "recording.walk"
    (source / "missions").mkdir(parents=True)
    (source / "waypoint_snapshots").mkdir()
    (source / "edge_snapshots").mkdir()

    waypoint_id = "recorded-waypoint"
    snapshot_id = "recorded-snapshot"
    old_walk_id = "11111111-1111-4111-8111-111111111111"
    element_id = "22222222-2222-4222-8222-222222222222"
    graph = map_pb2.Graph()
    graph.waypoints.add(id=waypoint_id, snapshot_id=snapshot_id)
    graph.anchoring.anchors.add(id=waypoint_id)
    (source / "graph").write_bytes(graph.SerializeToString())
    (source / "waypoint_snapshots" / snapshot_id).write_bytes(
        map_pb2.WaypointSnapshot(id=snapshot_id).SerializeToString()
    )

    walk = walks_pb2.Walk(id=old_walk_id, map_name="recording", mission_name="recording")
    walk.global_parameters.group_name = "recording"
    walk.playback_mode.once.SetInParent()
    element = walk.elements.add(id=element_id, name="Inspection")
    element.target.navigate_to.destination_waypoint_id = waypoint_id
    request = element.action.data_acquisition.acquire_data_request
    request.metadata.data.fields["element_id"].string_value = element_id
    request.metadata.data.fields["mission_id"].string_value = old_walk_id
    dock = walk.docks.add(dock_id=520, docked_waypoint_id=waypoint_id)
    dock.target_prep_pose.navigate_to.destination_waypoint_id = waypoint_id
    walk_payload = walk.SerializeToString() + _length_delimited(1000, b"opaque-top-level")
    (source / "missions" / "recording.walk").write_bytes(walk_payload)
    (source / "missions" / "readme.txt").write_text("recorded", encoding="utf-8")
    (source / "autowalk_metadata").write_bytes(b"opaque-metadata")
    (source / "topography.png").write_bytes(b"opaque-topography")
    return source, {
        "old_walk_id": old_walk_id,
        "element_id": element_id,
        "waypoint_id": waypoint_id,
    }


def test_reissue_walk_changes_only_top_level_walk_id(tmp_path: Path) -> None:
    source, ids = _recorded_walk_directory(tmp_path)
    output = tmp_path / "recording-walk-id-only.walk.zip"
    new_walk_id = "33333333-3333-4333-8333-333333333333"

    result = reissue_walk_recording(source, output, new_walk_id=new_walk_id)

    assert result["new_walk_id"] == new_walk_id
    assert result["validation"]["valid"]
    assert result["identity_policy"]["changed"] == ["walk"]
    assert result["identity_policy"]["mode"] == "walk_id_only"
    assert result["integrity"] == {
        "source_files": 6,
        "byte_identical_non_mission_files": 5,
        "non_walk_id_mission_fields_byte_equal": True,
        "unchanged_mission_fields_byte_equal": True,
        "element_payloads_byte_equal": True,
        "dock_payloads_byte_equal": True,
        "elements_removed": 0,
        "docks_removed": 0,
        "unknown_top_level_fields_preserved": [1000],
        "daq_source_mission_records_preserved": 1,
        "daq_source_mission_records_removed": 0,
    }

    source_mission = (source / "missions" / "recording.walk").read_bytes()
    with zipfile.ZipFile(output) as archive:
        output_mission = archive.read("recording.walk/missions/recording.walk")
        for source_file in (path for path in source.rglob("*") if path.is_file()):
            if source_file.name == "recording.walk" and source_file.parent.name == "missions":
                continue
            relative = source_file.relative_to(source).as_posix()
            assert archive.read(f"recording.walk/{relative}") == source_file.read_bytes()

    source_fields = decode_fields(source_mission)
    output_fields = decode_fields(output_mission)
    assert bytes_values(source_fields, 8) == (ids["old_walk_id"].encode(),)
    assert bytes_values(output_fields, 8) == (new_walk_id.encode(),)
    assert tuple(field for field in source_fields if field.number != 8) == tuple(
        field for field in output_fields if field.number != 8
    )
    assert bytes_values(source_fields, 5) == bytes_values(output_fields, 5)
    assert bytes_values(source_fields, 6) == bytes_values(output_fields, 6)
    assert bytes_values(output_fields, 1000) == (b"opaque-top-level",)

    reissued_walk = walks_pb2.Walk.FromString(output_mission)
    assert reissued_walk.id == new_walk_id
    assert reissued_walk.elements[0].id == ids["element_id"]
    assert (
        reissued_walk.elements[0]
        .action.data_acquisition.acquire_data_request.metadata.data.fields["mission_id"]
        .string_value
        == ids["old_walk_id"]
    )
    assert validate_walk_archive(output).valid


def test_reissue_walk_graph_only_removes_elements_and_docks_at_wire_level(
    tmp_path: Path,
) -> None:
    source, _ = _recorded_walk_directory(tmp_path)
    output = tmp_path / "recording-graph-only.walk.zip"
    new_walk_id = "33333333-3333-4333-8333-333333333333"

    result = reissue_walk_recording(
        source,
        output,
        new_walk_id=new_walk_id,
        graph_only=True,
    )

    assert result["validation"]["valid"]
    assert result["identity_policy"] == {
        "mode": "graph_only_control",
        "changed": ["walk", "walk_elements_removed", "walk_docks_removed"],
        "preserved": [
            "graph",
            "waypoint",
            "waypoint_snapshot",
            "edge",
            "edge_snapshot",
            "anchor",
            "opaque_metadata",
        ],
        "changed_wire_fields": [5, 6, 8],
    }
    assert result["counts"]["elements"] == 0
    assert result["counts"]["actions"] == 0
    assert result["counts"]["docks"] == 0
    assert result["integrity"]["unchanged_mission_fields_byte_equal"]
    assert not result["integrity"]["non_walk_id_mission_fields_byte_equal"]
    assert result["integrity"]["elements_removed"] == 1
    assert result["integrity"]["docks_removed"] == 1
    assert result["integrity"]["daq_source_mission_records_preserved"] == 0
    assert result["integrity"]["daq_source_mission_records_removed"] == 1

    with zipfile.ZipFile(output) as archive:
        mission_payload = archive.read("recording.walk/missions/recording.walk")
        assert archive.read("recording.walk/graph") == (source / "graph").read_bytes()
        assert archive.read("recording.walk/autowalk_metadata") == b"opaque-metadata"
    mission_fields = decode_fields(mission_payload)
    assert not bytes_values(mission_fields, 5)
    assert not bytes_values(mission_fields, 6)
    assert bytes_values(mission_fields, 1000) == (b"opaque-top-level",)
    walk = walks_pb2.Walk.FromString(mission_payload)
    assert walk.id == new_walk_id
    assert not walk.elements
    assert not walk.docks
    assert validate_walk_archive(output).valid


def test_reissue_walk_can_add_one_skipped_navigation_only_sentinel(tmp_path: Path) -> None:
    source, ids = _recorded_walk_directory(tmp_path)
    output = tmp_path / "recording-navigation-only-sentinel.walk.zip"

    result = reissue_walk_recording(
        source,
        output,
        new_walk_id="33333333-3333-4333-8333-333333333333",
        graph_only=True,
        navigation_only_sentinel=True,
    )

    assert result["validation"]["valid"]
    assert result["identity_policy"] == {
        "mode": "graph_only_sentinel_probe",
        "changed": [
            "walk",
            "walk_elements_removed",
            "walk_docks_removed",
            "navigation_only_sentinel_added",
        ],
        "preserved": [
            "graph",
            "waypoint",
            "waypoint_snapshot",
            "edge",
            "edge_snapshot",
            "anchor",
            "opaque_metadata",
        ],
        "changed_wire_fields": [5, 6, 8],
    }
    assert result["counts"]["elements"] == 1
    assert result["counts"]["actions"] == 0
    assert result["counts"]["docks"] == 0
    sentinel_report = result["navigation_only_sentinel"]
    assert sentinel_report["status"] == "added"
    assert sentinel_report["is_skipped"]
    assert sentinel_report["action_kind"] is None
    assert sentinel_report["target_kind"] == "navigate_to"
    assert sentinel_report["element_id"] not in set(ids.values())

    with zipfile.ZipFile(output) as archive:
        mission_payload = archive.read("recording.walk/missions/recording.walk")
        assert archive.read("recording.walk/graph") == (source / "graph").read_bytes()
    mission_fields = decode_fields(mission_payload)
    assert len(bytes_values(mission_fields, 5)) == 1
    assert not bytes_values(mission_fields, 6)
    assert bytes_values(mission_fields, 1000) == (b"opaque-top-level",)
    walk = walks_pb2.Walk.FromString(mission_payload)
    assert len(walk.elements) == 1
    sentinel = walk.elements[0]
    assert sentinel.id == sentinel_report["element_id"]
    assert sentinel.is_skipped
    assert sentinel.action.WhichOneof("action") is None
    assert sentinel.target.navigate_to.destination_waypoint_id == ids["waypoint_id"]
    assert validate_walk_archive(output).valid


def test_reissue_walk_can_add_disconnected_waypoint_snapshot_and_anchor_sentinel(
    tmp_path: Path,
) -> None:
    source, ids = _recorded_walk_directory(tmp_path)
    output = tmp_path / "recording-disconnected-waypoint-sentinel.walk.zip"

    result = reissue_walk_recording(
        source,
        output,
        new_walk_id="33333333-3333-4333-8333-333333333333",
        graph_only=True,
        navigation_only_sentinel=True,
        disconnected_waypoint_sentinel=True,
    )

    assert result["validation"]["valid"]
    assert result["identity_policy"] == {
        "mode": "disconnected_waypoint_sentinel_probe",
        "changed": [
            "walk",
            "walk_elements_removed",
            "walk_docks_removed",
            "navigation_only_sentinel_added",
            "disconnected_waypoint_sentinel_added",
            "waypoint_snapshot_sentinel_added",
            "anchor_sentinel_added",
        ],
        "preserved": [
            "graph",
            "waypoint",
            "waypoint_snapshot",
            "edge",
            "edge_snapshot",
            "anchor",
            "opaque_metadata",
        ],
        "changed_wire_fields": [5, 6, 8],
    }
    assert result["counts"]["waypoints"] == 2
    assert result["counts"]["waypoint_snapshots"] == 2
    assert result["counts"]["elements"] == 1
    assert result["counts"]["actions"] == 0
    graph_report = result["disconnected_waypoint_sentinel"]
    assert graph_report["status"] == "added"
    assert graph_report["connected_edges"] == 0
    assert graph_report["recording_metadata"] == "preserved_from_source_snapshot"
    assert all(graph_report["integrity"].values())
    assert graph_report["waypoint_id"] not in set(ids.values())
    assert graph_report["snapshot_id"] not in set(ids.values())
    assert graph_report["anchor_id"] == graph_report["waypoint_id"]

    with zipfile.ZipFile(output) as archive:
        graph_payload = archive.read("recording.walk/graph")
        mission_payload = archive.read("recording.walk/missions/recording.walk")
        snapshot_payload = archive.read(
            f"recording.walk/waypoint_snapshots/{graph_report['snapshot_id']}"
        )
    source_graph = map_pb2.Graph.FromString((source / "graph").read_bytes())
    graph = map_pb2.Graph.FromString(graph_payload)
    assert len(graph.waypoints) == 2
    assert len(graph.anchoring.anchors) == 2
    assert graph.waypoints[0].SerializeToString() == source_graph.waypoints[0].SerializeToString()
    assert (
        graph.anchoring.anchors[0].SerializeToString()
        == source_graph.anchoring.anchors[0].SerializeToString()
    )
    new_waypoint = graph.waypoints[1]
    assert new_waypoint.id == graph_report["waypoint_id"]
    assert new_waypoint.snapshot_id == graph_report["snapshot_id"]
    assert graph.anchoring.anchors[1].id == new_waypoint.id
    assert not any(
        edge.id.from_waypoint == new_waypoint.id or edge.id.to_waypoint == new_waypoint.id
        for edge in graph.edges
    )
    assert map_pb2.WaypointSnapshot.FromString(snapshot_payload).id == new_waypoint.snapshot_id
    walk = walks_pb2.Walk.FromString(mission_payload)
    assert walk.elements[0].target.navigate_to.destination_waypoint_id == new_waypoint.id
    assert walk.elements[0].is_skipped
    assert walk.elements[0].action.WhichOneof("action") is None
    assert validate_walk_archive(output).valid


def test_reissue_walk_rejects_reused_source_identity(tmp_path: Path) -> None:
    source, ids = _recorded_walk_directory(tmp_path)

    with pytest.raises(ValueError, match="must not reuse"):
        reissue_walk_recording(
            source,
            tmp_path / "bad.walk.zip",
            new_walk_id=ids["old_walk_id"],
        )
