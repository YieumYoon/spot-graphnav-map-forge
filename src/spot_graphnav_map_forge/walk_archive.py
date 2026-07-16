"""Build and validate uploadable public Autowalk ``.walk.zip`` archives."""

from __future__ import annotations

import hashlib
import json
import math
import struct
import uuid
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from bosdyn.api import image_pb2
from bosdyn.api.autowalk import walks_pb2
from bosdyn.api.graph_nav import map_pb2
from google.protobuf.message import DecodeError

from .geometry import load_graph
from .models import ValidationReport
from .remap import DEFAULT_NAMESPACE
from .validator import validate_bundle
from .wire import WireField, bytes_values, decode_fields

MISSIONS_README = """Missions have multiple formats.

Files without an extension should be serialized bosdyn.api.mission.Node protobufs. This is the
older format. These files can be deserialized and sent directly to the mission service.

Files with the '.walk' extension should be serialized bosdyn.api.autowalk.Walk protobufs. This is
the newer format. These files need to be converted to bosdyn.api.mission.Node protobufs before
sending to the mission service. This can be done using the autowalk service.

Files with the '.node' extension should be serialized bosdyn.api.mission.Node protobufs.

As of 3.3, we NO LONGER save '.node' files for autowalk missions.

If there are files with the same name, but a different extension, the tablet will first try to
load '.walk' files, then '.node' files, then extensionless files. If the tablet can convert the
older, extensionless format to the new '.walk' format it will.
"""


@dataclass(frozen=True)
class _Sidecar:
    path: Path
    name: str
    image: image_pb2.Image


@dataclass(frozen=True)
class _OpaqueTargetProfile:
    source_path: str
    travel_params_fields: bytes
    travel_params_field_numbers: tuple[int, ...]
    target_fields: bytes
    target_field_numbers: tuple[int, ...]


_TRIGGERED_AI_MODES = {"block", "fold-into-parent"}


def export_walk_archive(
    bundle: Path,
    out: Path,
    *,
    name: str | None = None,
    recording_name: str | None = None,
    template_archive: Path | None = None,
    triggered_ai_mode: str = "block",
    sleep_waypoint_id: str | None = None,
    sleep_duration_seconds: float = 0.25,
    sleep_name: str = "Sleep - 1",
    sleep_after_element: str | None = None,
) -> dict[str, object]:
    """Convert a validated clone bundle into a clone-ID Autowalk archive.

    The proprietary SiteElement envelope is used only as a carrier for its public ``Action`` and
    ``ActionWrapper`` fields. Image sidecars from the backup are re-embedded into those public
    messages before the Walk is serialized.
    """
    bundle = bundle.expanduser().resolve()
    out = out.expanduser().resolve()
    if out.exists():
        raise ValueError(f"output already exists: {out}")
    manifest = json.loads((bundle / "clone_manifest.json").read_text(encoding="utf-8"))
    if triggered_ai_mode not in _TRIGGERED_AI_MODES:
        raise ValueError(
            "triggered_ai_mode must be one of: " + ", ".join(sorted(_TRIGGERED_AI_MODES))
        )
    triggered_actions = manifest.get("triggered_actions", [])
    if not isinstance(triggered_actions, list):
        raise ValueError("triggered_actions must be a list")
    if triggered_actions and triggered_ai_mode == "block":
        raise ValueError(
            f"clone contains {len(triggered_actions)} triggered AI inspection(s); public "
            "Autowalk has no field for the SiteElement parent trigger link, so export refuses "
            "to silently omit or change their behavior"
        )
    bundle_report = validate_bundle(bundle, write_report=False)
    if not bundle_report.valid:
        raise ValueError("clone bundle is invalid: " + "; ".join(bundle_report.errors[:3]))

    archive_name = _validate_archive_name(name or str(manifest["clone_name"]))
    normalized_recording_name = (
        _validate_recording_name(recording_name) if recording_name is not None else None
    )
    graph = load_graph(bundle / "graph")
    recording_session = _override_recording_session_name(graph, normalized_recording_name)
    walk_id = _walk_id(manifest, archive_name)
    walk = _new_walk(archive_name, walk_id)
    opaque_target_profile = _load_opaque_target_profile(manifest)

    embedded_images = 0
    unused_image_sidecars: list[str] = []
    navigation_only = 0
    aivi_named_elements = 0
    action_kind_counts: Counter[str] = Counter()
    emitted_elements: list[walks_pb2.Element] = []
    triggered_by_parent: dict[str, list[dict[str, object]]] = {}
    if triggered_ai_mode == "fold-into-parent":
        for record in triggered_actions:
            if not isinstance(record, dict):
                raise ValueError("triggered AI inspection manifest records must be objects")
            parent_id = str(record.get("new_parent_element_id", ""))
            if not parent_id:
                raise ValueError("triggered AI inspection has no new_parent_element_id")
            triggered_by_parent.setdefault(parent_id, []).append(record)
    triggered_ai_folds: list[dict[str, object]] = []
    for action_record in manifest.get("actions", []):
        element, image_count, unused = _walk_element(bundle, action_record, opaque_target_profile)
        for triggered_record in triggered_by_parent.pop(element.id, []):
            triggered_ai_folds.append(
                _fold_triggered_ai_into_parent(bundle, element, triggered_record)
            )
        emitted_elements.append(element)
        embedded_images += image_count
        unused_image_sidecars.extend(unused)
        action_kind = element.action.WhichOneof("action")
        if action_kind is None:
            navigation_only += 1
        else:
            action_kind_counts[action_kind] += 1
        if element.name.casefold().endswith("aivi"):
            aivi_named_elements += 1
    if triggered_by_parent:
        raise ValueError(
            "triggered AI inspection parent was not emitted as a Walk Element: "
            + ", ".join(sorted(triggered_by_parent))
        )

    synthetic_sleep: dict[str, object] | None = None
    if sleep_waypoint_id is not None:
        sleep_element, synthetic_sleep = _walk_sleep_element(
            graph,
            manifest,
            walk_id,
            sleep_waypoint_id,
            sleep_duration_seconds,
            sleep_name,
            opaque_target_profile,
        )
        insert_at = len(emitted_elements)
        if sleep_after_element is not None:
            matching_indexes = [
                index
                for index, element in enumerate(emitted_elements)
                if element.id == sleep_after_element or element.name == sleep_after_element
            ]
            if len(matching_indexes) != 1:
                raise ValueError(
                    "--sleep-after-element must match exactly one existing element ID or name, "
                    f"got {len(matching_indexes)} matches: {sleep_after_element!r}"
                )
            insert_at = matching_indexes[0] + 1
        emitted_elements.insert(insert_at, sleep_element)
        synthetic_sleep["element_index"] = insert_at
        synthetic_sleep["inserted_after"] = sleep_after_element
        action_kind_counts["sleep"] += 1
    elif sleep_after_element is not None:
        raise ValueError("--sleep-after-element requires --sleep-waypoint-id")

    for element in emitted_elements:
        walk.elements.add().CopyFrom(element)
    for dock_record in manifest.get("docks", []):
        walk.docks.add().CopyFrom(_walk_dock(bundle, dock_record, opaque_target_profile))

    metadata = _read_template_metadata(template_archive) if template_archive else None
    root = f"{archive_name}.walk"
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, mode="x", compression=zipfile.ZIP_DEFLATED) as archive:
        # Some fleet-manager importers validate the extracted archive layout before parsing the
        # graph. Keep every required directory explicit even when a minimal graph has no edge
        # snapshots; ZIP archives otherwise omit an empty directory entirely.
        for directory in ("missions", "waypoint_snapshots", "edge_snapshots"):
            archive.writestr(f"{root}/{directory}/", b"")
        archive.writestr(f"{root}/graph", graph.SerializeToString())
        if metadata is not None:
            archive.writestr(f"{root}/autowalk_metadata", metadata)
        archive.writestr(f"{root}/missions/readme.txt", MISSIONS_README.encode())
        archive.writestr(
            f"{root}/missions/{archive_name}.walk",
            walk.SerializeToString(),
        )
        waypoint_snapshot_ids = sorted(
            {waypoint.snapshot_id for waypoint in graph.waypoints if waypoint.snapshot_id}
        )
        for snapshot_id in waypoint_snapshot_ids:
            snapshot_path = bundle / "waypoint_snapshots" / snapshot_id
            if not snapshot_path.is_file():
                raise ValueError(f"waypoint snapshot missing: {snapshot_id}")
            archive.write(
                snapshot_path,
                arcname=f"{root}/waypoint_snapshots/{snapshot_id}",
            )
        edge_snapshot_ids = sorted({edge.snapshot_id for edge in graph.edges if edge.snapshot_id})
        for snapshot_id in edge_snapshot_ids:
            snapshot_path = bundle / "edge_snapshots" / snapshot_id
            if not snapshot_path.is_file():
                raise ValueError(f"edge snapshot missing: {snapshot_id}")
            archive.write(
                snapshot_path,
                arcname=f"{root}/edge_snapshots/{snapshot_id}",
            )

    archive_report = validate_walk_archive(out)
    if not archive_report.valid:
        raise ValueError("generated Walk archive is invalid: " + "; ".join(archive_report.errors))
    return {
        "archive": str(out),
        "root": root,
        "walk_id": walk_id,
        "name": archive_name,
        "recording_session": recording_session,
        "counts": {
            **archive_report.counts,
            "navigation_only_elements": navigation_only,
            "embedded_images": embedded_images,
            "unused_action_image_sidecars": len(unused_image_sidecars),
            "triggered_ai_inspections_folded": len(triggered_ai_folds),
            "triggered_ai_network_compute_captures_added": sum(
                int(record["network_compute_captures_added"]) for record in triggered_ai_folds
            ),
        },
        "action_kinds": dict(sorted(action_kind_counts.items())),
        "autowalk_metadata": "copied_from_template" if metadata is not None else "omitted",
        "opaque_target_profile": (
            {
                "status": "preserved",
                "source_path": opaque_target_profile.source_path,
                "travel_params_field_numbers": list(
                    opaque_target_profile.travel_params_field_numbers
                ),
                "target_field_numbers": list(opaque_target_profile.target_field_numbers),
            }
            if opaque_target_profile is not None
            else {"status": "absent_from_bundle"}
        ),
        "orbit_ai_trigger": {
            "aivi_name_suffix_elements": aivi_named_elements,
            "triggered_ai_inspections_selected": len(triggered_actions),
            "capture_actions": "preserved",
            "mode": triggered_ai_mode,
            "trigger_configuration": (
                "experimental_triggered_ai_request_folded_into_parent_action"
                if triggered_ai_folds
                else "none_linked_to_selected_actions_in_backup"
            ),
            "private_parent_trigger_field": (
                "not_represented_in_public_walk" if triggered_ai_folds else "not_applicable"
            ),
            "runtime_equivalence": (
                "unverified_requires_orbit_import_and_reexport"
                if triggered_ai_folds
                else "not_applicable"
            ),
        },
        "triggered_ai_folds": triggered_ai_folds,
        "synthetic_sleep_action": synthetic_sleep or {"status": "not_requested"},
        "unused_action_image_sidecar_files": unused_image_sidecars,
        "bundle_warnings": bundle_report.warnings,
        "validation": asdict(archive_report),
    }


def _fold_triggered_ai_into_parent(
    bundle: Path,
    parent: walks_pb2.Element,
    record: dict[str, object],
) -> dict[str, object]:
    """Experimentally place one Orbit-triggered AIVI request in its capture parent.

    The triggered AI inspection remains intact in the clone bundle. Only its public
    network-compute capture and matching capability records are copied into the parent Walk
    Action. The private SiteElement field-14 trigger is deliberately not claimed to be represented
    by this transport.
    """
    inspection_id = str(record.get("new_element_id", ""))
    inspection_name = str(record.get("name", inspection_id))
    payload_path = bundle / str(record.get("cloned_payload", ""))
    if not payload_path.is_file():
        raise ValueError(f"triggered AI inspection payload missing: {inspection_id}")
    if record.get("images"):
        raise ValueError(
            "triggered AI inspection has image sidecars that fold mode cannot transport: "
            f"{inspection_id}"
        )

    site_fields = decode_fields(payload_path.read_bytes())
    action_values = bytes_values(site_fields, 6)
    wrapper_values = bytes_values(site_fields, 10)
    if len(action_values) != 1:
        raise ValueError(
            f"triggered AI inspection must contain exactly one public Action: {inspection_id}"
        )
    if len(wrapper_values) > 1 or (wrapper_values and wrapper_values[0]):
        raise ValueError(
            "triggered AI inspection has a non-empty ActionWrapper that fold mode cannot "
            f"transport: {inspection_id}"
        )

    action_wire = decode_fields(action_values[0])
    _require_only_wire_fields(action_wire, {2}, "triggered AI inspection Action", inspection_id)
    daq_values = bytes_values(action_wire, 2)
    if len(daq_values) != 1:
        raise ValueError(
            f"triggered AI inspection has no unique DataAcquisition payload: {inspection_id}"
        )
    daq_wire = decode_fields(daq_values[0])
    _require_only_wire_fields(
        daq_wire, {1, 3}, "triggered AI inspection DataAcquisition", inspection_id
    )
    request_values = bytes_values(daq_wire, 1)
    if len(request_values) != 1:
        raise ValueError(
            f"triggered AI inspection has no unique AcquireDataRequest: {inspection_id}"
        )
    request_wire = decode_fields(request_values[0])
    _require_only_wire_fields(
        request_wire, {4, 5}, "triggered AI inspection AcquireDataRequest", inspection_id
    )
    acquisition_values = bytes_values(request_wire, 4)
    if len(acquisition_values) != 1:
        raise ValueError(
            f"triggered AI inspection has no unique AcquisitionRequestList: {inspection_id}"
        )
    _require_only_wire_fields(
        decode_fields(acquisition_values[0]),
        {4},
        "triggered AI inspection AcquisitionRequestList",
        inspection_id,
    )
    capability_values = bytes_values(daq_wire, 3)
    if len(capability_values) > 1:
        raise ValueError(f"triggered AI inspection has multiple capability lists: {inspection_id}")
    if capability_values:
        _require_only_wire_fields(
            decode_fields(capability_values[0]),
            {5},
            "triggered AI inspection AcquisitionCapabilityList",
            inspection_id,
        )

    try:
        inspection_action = walks_pb2.Action.FromString(action_values[0])
    except DecodeError as exc:
        raise ValueError(
            f"triggered AI inspection public Action is invalid: {inspection_id}: {exc}"
        ) from exc
    if inspection_action.WhichOneof("action") != "data_acquisition":
        raise ValueError(f"triggered AI inspection is not DataAcquisition: {inspection_id}")
    if parent.action.WhichOneof("action") != "data_acquisition":
        raise ValueError(f"triggered AI inspection parent is not DataAcquisition: {parent.id}")

    trigger_service = str(record.get("trigger_image_service", ""))
    if trigger_service != "spot-cam-ptz":
        raise ValueError(
            f"fold mode has no proven image binding for trigger service {trigger_service!r}: "
            f"{inspection_id}"
        )
    parent_daq = parent.action.data_acquisition
    parent_request = parent_daq.acquire_data_request
    parent_ptz = [
        capture
        for capture in parent_request.acquisition_requests.image_captures
        if capture.image_service == "spot-cam-image"
        and capture.image_request.image_source_name == "ptz"
    ]
    if len(parent_ptz) != 1:
        raise ValueError(
            f"fold mode requires exactly one spot-cam-image/ptz parent capture, got "
            f"{len(parent_ptz)}: {parent.id}"
        )

    inspection_daq = inspection_action.data_acquisition
    inspection_request = inspection_daq.acquire_data_request
    inspection_captures = inspection_request.acquisition_requests.network_compute_captures
    if not inspection_captures:
        raise ValueError(f"triggered AI inspection has no network-compute capture: {inspection_id}")

    existing_captures = {
        capture.SerializeToString(deterministic=True)
        for capture in parent_request.acquisition_requests.network_compute_captures
    }
    added = 0
    capture_reports: list[dict[str, object]] = []
    for capture in inspection_captures:
        if capture.WhichOneof("input") != "input_data_bridge":
            raise ValueError(
                "triggered AI inspection does not use NetworkComputeInputDataBridge: "
                f"{inspection_id}"
            )
        inputs = capture.input_data_bridge.image_sources_and_services
        if inputs:
            if len(inputs) != 1:
                raise ValueError(
                    f"triggered AI inspection has multiple explicit image inputs: {inspection_id}"
                )
            source = inputs[0]
            if (
                source.image_service != parent_ptz[0].image_service
                or source.WhichOneof("request_data") != "image_request"
                or source.image_request.SerializeToString(deterministic=True)
                != parent_ptz[0].image_request.SerializeToString(deterministic=True)
            ):
                raise ValueError(
                    "triggered AI inspection image input does not match its parent PTZ capture: "
                    f"{inspection_id}"
                )
            input_binding = "explicit_public_parent_ptz_request"
        else:
            input_binding = "implicit_private_parent_trigger_removed"

        serialized = capture.SerializeToString(deterministic=True)
        if serialized not in existing_captures:
            parent_request.acquisition_requests.network_compute_captures.add().CopyFrom(capture)
            existing_captures.add(serialized)
            added += 1
        capture_reports.append(
            {
                "model_name": capture.input_data_bridge.parameters.model_name,
                "server_service_name": capture.server_config.service_name,
                "input_binding": input_binding,
                "payload_sha256": hashlib.sha256(serialized).hexdigest(),
            }
        )

    existing_capabilities = {
        capability.SerializeToString(deterministic=True)
        for capability in parent_daq.last_known_capabilities.network_compute_sources
    }
    capabilities_added = 0
    for capability in inspection_daq.last_known_capabilities.network_compute_sources:
        serialized = capability.SerializeToString(deterministic=True)
        if serialized in existing_capabilities:
            continue
        parent_daq.last_known_capabilities.network_compute_sources.add().CopyFrom(capability)
        existing_capabilities.add(serialized)
        capabilities_added += 1

    if inspection_request.HasField("min_timeout") and (
        not parent_request.HasField("min_timeout")
        or _duration_key(inspection_request.min_timeout) > _duration_key(parent_request.min_timeout)
    ):
        parent_request.min_timeout.CopyFrom(inspection_request.min_timeout)

    return {
        "triggered_ai_inspection_element_id": inspection_id,
        "triggered_ai_inspection_name": inspection_name,
        "parent_element_id": parent.id,
        "trigger_image_service": trigger_service,
        "network_compute_captures": capture_reports,
        "network_compute_captures_added": added,
        "network_compute_capabilities_added": capabilities_added,
        "private_field_14_transport": "not_represented",
        "status": "experimental_requires_orbit_import_and_reexport",
    }


def _require_only_wire_fields(
    fields: tuple[WireField, ...],
    supported: set[int],
    label: str,
    element_id: str,
) -> None:
    unsupported = sorted({field.number for field in fields} - supported)
    if unsupported:
        raise ValueError(
            f"{label} contains fields fold mode cannot transport {unsupported}: {element_id}"
        )


def _duration_key(duration: object) -> tuple[int, int]:
    return int(duration.seconds), int(duration.nanos)


def validate_walk_archive(path: Path) -> ValidationReport:
    """Validate graph, snapshot, target, identity, and image closure inside a Walk ZIP."""
    path = path.expanduser().resolve()
    report = ValidationReport()
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        report.error(f"invalid Walk archive: {exc}")
        return report

    with archive:
        files: dict[str, zipfile.ZipInfo] = {}
        directories: set[str] = set()
        roots: set[str] = set()
        for info in archive.infolist():
            if info.is_dir():
                directories.add(info.filename)
                continue
            pure = PurePosixPath(info.filename)
            if pure.is_absolute() or ".." in pure.parts or len(pure.parts) < 2:
                report.error(f"unsafe or rootless archive path: {info.filename}")
                continue
            roots.add(pure.parts[0])
            if info.filename in files:
                report.error(f"duplicate archive member: {info.filename}")
            files[info.filename] = info
        if len(roots) != 1:
            report.error(f"archive must contain exactly one root, got {sorted(roots)}")
            return report
        root = next(iter(roots))
        if not root.endswith(".walk"):
            report.error(f"archive root must end in .walk: {root}")
        if f"{root}/autowalk_metadata" not in files:
            report.warnings.append(
                "autowalk_metadata is absent; core public archive structure is valid, but "
                "product acceptance must be tested"
            )
        for required_directory in ("missions", "waypoint_snapshots", "edge_snapshots"):
            prefix = f"{root}/{required_directory}/"
            if prefix not in directories and not any(
                filename.startswith(prefix) for filename in files
            ):
                report.error(f"{required_directory} directory is missing")
        graph_name = f"{root}/graph"
        if graph_name not in files:
            report.error("graph is missing")
            return report
        mission_names = sorted(
            filename
            for filename in files
            if filename.startswith(f"{root}/missions/") and filename.endswith(".walk")
        )
        if len(mission_names) != 1:
            report.error(f"archive must contain one public Walk mission, got {len(mission_names)}")
            return report

        try:
            graph = map_pb2.Graph.FromString(archive.read(graph_name))
            walk = walks_pb2.Walk.FromString(archive.read(mission_names[0]))
        except DecodeError as exc:
            report.error(f"invalid protobuf in Walk archive: {exc}")
            return report

        _validate_walk_names(root, mission_names[0], walk, report)
        waypoint_list = [waypoint.id for waypoint in graph.waypoints]
        waypoint_ids = set(waypoint_list)
        if len(waypoint_list) != len(waypoint_ids):
            report.error("duplicate waypoint IDs")
        edge_list = [(edge.id.from_waypoint, edge.id.to_waypoint) for edge in graph.edges]
        edge_ids = set(edge_list)
        if len(edge_list) != len(edge_ids):
            report.error("duplicate directed edge IDs")
        for source, target in edge_list:
            if source not in waypoint_ids or target not in waypoint_ids:
                report.error(f"edge endpoint missing: {source} -> {target}")
        _validate_graph_snapshots(archive, files, root, graph, report)
        image_count = 0
        action_count = 0
        element_ids: set[str] = set()
        for element in walk.elements:
            if not element.id:
                report.error(f"Walk element has no ID: {element.name}")
            elif element.id in element_ids:
                report.error(f"duplicate Walk element ID: {element.id}")
            element_ids.add(element.id)
            _validate_target(element, waypoint_ids, edge_ids, report)
            action_kind = element.action.WhichOneof("action")
            if action_kind is not None:
                action_count += 1
            if action_kind == "data_acquisition":
                _validate_daq_identity(element, walk.id, report)
                for capture in element.action.data_acquisition.record_time_images:
                    if capture.shot.HasField("image"):
                        image_count += 1
                        if not capture.shot.image.data:
                            report.error(f"DAQ image data missing: {element.id}")
            for alignment in element.action_wrapper.spot_cam_alignment.alignments:
                if alignment.reference_image.shot.HasField("image"):
                    image_count += 1
                    if not alignment.reference_image.shot.image.data:
                        report.error(f"alignment image data missing: {element.id}")

        dock_keys: set[tuple[int, str, bytes]] = set()
        for dock in walk.docks:
            if not dock.dock_id:
                report.error("Walk dock has no dock_id")
            if dock.docked_waypoint_id not in waypoint_ids:
                report.error(f"dock waypoint missing: {dock.dock_id} -> {dock.docked_waypoint_id}")
            _validate_target_message(
                dock.target_prep_pose,
                f"dock {dock.dock_id}",
                waypoint_ids,
                edge_ids,
                report,
            )
            key = (
                dock.dock_id,
                dock.docked_waypoint_id,
                dock.target_prep_pose.SerializeToString(deterministic=True),
            )
            if key in dock_keys:
                report.error(f"duplicate Walk dock: {dock.dock_id}")
            dock_keys.add(key)

        report.counts = {
            "waypoints": len(graph.waypoints),
            "edges": len(graph.edges),
            "elements": len(walk.elements),
            "actions": action_count,
            "embedded_images": image_count,
            "docks": len(walk.docks),
            "waypoint_snapshots": sum(bool(item.snapshot_id) for item in graph.waypoints),
            "edge_snapshots": sum(bool(item.snapshot_id) for item in graph.edges),
        }
    return report


def _new_walk(name: str, walk_id: str) -> walks_pb2.Walk:
    walk = walks_pb2.Walk(id=walk_id, map_name=name, mission_name=name)
    walk.global_parameters.group_name = name
    walk.global_parameters.self_right_attempts = 1
    walk.global_parameters.hri_behaviors.play_undock_behaviors = True
    walk.playback_mode.once.SetInParent()
    walk.interrupts.SetInParent()
    return walk


def _walk_element(
    bundle: Path,
    action_record: dict[str, object],
    opaque_target_profile: _OpaqueTargetProfile | None,
) -> tuple[walks_pb2.Element, int, list[str]]:
    element_id = str(action_record["new_element_id"])
    waypoint_id = str(action_record["new_waypoint_id"])
    payload_path = bundle / str(action_record["cloned_payload"])
    fields = decode_fields(payload_path.read_bytes())
    action_values = bytes_values(fields, 6)
    wrapper_values = bytes_values(fields, 10)
    if len(action_values) > 1:
        raise ValueError(f"SiteElement has multiple Action fields: {element_id}")
    if len(wrapper_values) > 1:
        raise ValueError(f"SiteElement has multiple ActionWrapper fields: {element_id}")

    element = walks_pb2.Element(name=str(action_record["name"]), id=element_id)
    _set_default_element_behaviors(element)
    try:
        if action_values:
            element.action.ParseFromString(action_values[0])
        if wrapper_values:
            element.action_wrapper.ParseFromString(wrapper_values[0])
    except DecodeError as exc:
        raise ValueError(f"public action payload is invalid for {element_id}: {exc}") from exc

    _set_navigation_target(element, waypoint_id, fields, opaque_target_profile)

    sidecars = _load_sidecars(bundle, action_record, element_id)
    image_count, unused_sidecars = _rehydrate_images(element, sidecars)
    if element.action.WhichOneof("action") == "data_acquisition":
        request = element.action.data_acquisition.acquire_data_request
        request.metadata.data.fields["element_id"].string_value = element_id
        if not request.action_id.action_name:
            request.action_id.action_name = element.name
    return element, image_count, unused_sidecars


def _set_navigation_target(
    element: walks_pb2.Element,
    waypoint_id: str,
    site_fields: tuple[WireField, ...],
    opaque_target_profile: _OpaqueTargetProfile | None,
) -> None:
    """Rebuild Orbit's waypoint-relative action target from backup-only fields."""
    navigate_to = element.target.navigate_to
    navigate_to.destination_waypoint_id = waypoint_id
    max_distance_values = [
        field.value
        for field in site_fields
        if field.number == 4 and field.wire_type == 1 and isinstance(field.value, int)
    ]
    if len(max_distance_values) > 1:
        raise ValueError(f"SiteElement has multiple waypoint max-distance fields: {element.id}")
    navigate_to.travel_params.max_distance = (
        struct.unpack("<d", struct.pack("<Q", max_distance_values[0]))[0]
        if max_distance_values
        else 0.2
    )
    navigate_to.travel_params.feature_quality_tolerance = (
        navigate_to.travel_params.TOLERANCE_DEFAULT
    )
    navigate_to.travel_params.blocked_path_wait_time.seconds = 5

    body_goal_values = bytes_values(site_fields, 15)
    if len(body_goal_values) > 1:
        raise ValueError(f"SiteElement has multiple waypoint body-goal fields: {element.id}")
    if body_goal_values:
        try:
            navigate_to.destination_waypoint_tform_body_goal.ParseFromString(body_goal_values[0])
        except DecodeError as exc:
            raise ValueError(
                f"SiteElement waypoint body-goal payload is invalid: {element.id}: {exc}"
            ) from exc
    elif element.action_wrapper.HasField("robot_body_pose"):
        body_pose = element.action_wrapper.robot_body_pose.target_tform_body
        body_goal = navigate_to.destination_waypoint_tform_body_goal
        body_goal.position.x = body_pose.position.x
        body_goal.position.y = body_pose.position.y
        rotation = body_pose.rotation
        body_goal.angle = math.atan2(
            2.0 * (rotation.w * rotation.z + rotation.x * rotation.y),
            1.0 - 2.0 * (rotation.y * rotation.y + rotation.z * rotation.z),
        )

    relocalize_markers = bytes_values(site_fields, 8)
    if len(relocalize_markers) > 1:
        raise ValueError(f"SiteElement has multiple relocalize markers: {element.id}")
    if relocalize_markers and relocalize_markers[0]:
        raise ValueError(f"SiteElement field 8 marker is unexpectedly non-empty: {element.id}")
    relocalize_values = bytes_values(site_fields, 9)
    if len(relocalize_values) > 1:
        raise ValueError(f"SiteElement has multiple relocalize fields: {element.id}")
    if relocalize_values or relocalize_markers:
        element.target.relocalize.SetInParent()
    if relocalize_values:
        try:
            element.target.relocalize.MergeFromString(relocalize_values[0])
        except DecodeError as exc:
            raise ValueError(
                f"SiteElement relocalize payload is invalid: {element.id}: {exc}"
            ) from exc
    if opaque_target_profile is not None:
        _merge_opaque_target_profile(
            element.target,
            opaque_target_profile,
            f"element {element.id}",
        )


def _load_opaque_target_profile(
    manifest: dict[str, object],
) -> _OpaqueTargetProfile | None:
    record = manifest.get("walk_target_opaque_profile")
    if record is None:
        return None
    if not isinstance(record, dict):
        raise ValueError("walk_target_opaque_profile must be an object or null")
    try:
        source_path = str(record["source_path"])
        travel_params_fields = bytes.fromhex(str(record["travel_params_fields_hex"]))
        target_fields = bytes.fromhex(str(record["target_fields_hex"]))
        travel_numbers = tuple(int(value) for value in record["travel_params_field_numbers"])
        target_numbers = tuple(int(value) for value in record["target_field_numbers"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid walk_target_opaque_profile: {exc}") from exc

    decoded_travel_numbers = tuple(field.number for field in decode_fields(travel_params_fields))
    decoded_target_numbers = tuple(field.number for field in decode_fields(target_fields))
    if decoded_travel_numbers != travel_numbers:
        raise ValueError("opaque TravelParams field-number manifest mismatch")
    if decoded_target_numbers != target_numbers:
        raise ValueError("opaque Target field-number manifest mismatch")

    target_descriptor = walks_pb2.Target.DESCRIPTOR
    navigate_descriptor = target_descriptor.fields_by_name["navigate_to"].message_type
    travel_descriptor = navigate_descriptor.fields_by_name["travel_params"].message_type
    public_travel_numbers = set(travel_descriptor.fields_by_number)
    public_target_numbers = set(target_descriptor.fields_by_number)
    overlap = public_travel_numbers & set(travel_numbers)
    if overlap:
        raise ValueError(
            "opaque TravelParams profile overlaps public fields: "
            + ", ".join(str(value) for value in sorted(overlap))
        )
    overlap = public_target_numbers & set(target_numbers)
    if overlap:
        raise ValueError(
            "opaque Target profile overlaps public fields: "
            + ", ".join(str(value) for value in sorted(overlap))
        )
    return _OpaqueTargetProfile(
        source_path=source_path,
        travel_params_fields=travel_params_fields,
        travel_params_field_numbers=travel_numbers,
        target_fields=target_fields,
        target_field_numbers=target_numbers,
    )


def _walk_sleep_element(
    graph: map_pb2.Graph,
    manifest: dict[str, object],
    walk_id: str,
    requested_waypoint_id: str,
    duration_seconds: float,
    name: str,
    opaque_target_profile: _OpaqueTargetProfile | None,
) -> tuple[walks_pb2.Element, dict[str, object]]:
    """Create one explicitly requested public Sleep element with an auditable identity."""
    if opaque_target_profile is None:
        raise ValueError(
            "synthetic Sleep export requires an observed opaque target profile in the bundle"
        )
    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("Sleep action name cannot be empty")
    if "\0" in normalized_name or any(ord(char) < 32 for char in normalized_name):
        raise ValueError("Sleep action name contains a control character")
    if not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise ValueError("Sleep duration must be a positive finite number of seconds")
    total_nanos = round(duration_seconds * 1_000_000_000)
    if total_nanos <= 0:
        raise ValueError("Sleep duration rounds to zero nanoseconds")
    seconds, nanos = divmod(total_nanos, 1_000_000_000)
    if seconds > 315_576_000_000:
        raise ValueError("Sleep duration exceeds the protobuf Duration limit")

    graph_waypoint_ids = {waypoint.id for waypoint in graph.waypoints}
    mappings = manifest.get("id_mappings", {})
    waypoint_mappings = mappings.get("waypoint", {}) if isinstance(mappings, dict) else {}
    if not isinstance(waypoint_mappings, dict):
        raise ValueError("manifest waypoint ID mappings must be an object")
    if requested_waypoint_id in graph_waypoint_ids:
        waypoint_id = requested_waypoint_id
        source_ids = [
            str(source_id)
            for source_id, cloned_id in waypoint_mappings.items()
            if cloned_id == waypoint_id
        ]
        source_waypoint_id = source_ids[0] if len(source_ids) == 1 else None
        requested_id_kind = "cloned"
    else:
        mapped_id = waypoint_mappings.get(requested_waypoint_id)
        if not isinstance(mapped_id, str) or mapped_id not in graph_waypoint_ids:
            raise ValueError(
                f"Sleep waypoint is not present in the cloned graph: {requested_waypoint_id}"
            )
        waypoint_id = mapped_id
        source_waypoint_id = requested_waypoint_id
        requested_id_kind = "source"

    element_id = str(
        uuid.uuid5(
            DEFAULT_NAMESPACE,
            f"{walk_id}:synthetic-sleep:{waypoint_id}:{normalized_name}:{seconds}:{nanos}",
        )
    )
    element = walks_pb2.Element(name=normalized_name, id=element_id)
    _set_default_element_behaviors(element)
    element.action.sleep.duration.seconds = seconds
    element.action.sleep.duration.nanos = nanos
    navigate_to = element.target.navigate_to
    navigate_to.destination_waypoint_id = waypoint_id
    navigate_to.travel_params.max_distance = 0.2
    navigate_to.travel_params.feature_quality_tolerance = (
        navigate_to.travel_params.TOLERANCE_DEFAULT
    )
    navigate_to.travel_params.blocked_path_wait_time.seconds = 5
    _merge_opaque_target_profile(element.target, opaque_target_profile, f"Sleep {element_id}")
    return element, {
        "status": "explicitly_synthesized",
        "element_id": element_id,
        "name": normalized_name,
        "duration_seconds": seconds + nanos / 1_000_000_000,
        "requested_waypoint_id": requested_waypoint_id,
        "requested_id_kind": requested_id_kind,
        "source_waypoint_id": source_waypoint_id,
        "cloned_waypoint_id": waypoint_id,
        "target_profile": "public_defaults_plus_observed_opaque_fields",
    }


def _merge_opaque_target_profile(
    target: walks_pb2.Target,
    profile: _OpaqueTargetProfile,
    owner: str,
) -> None:
    _merge_opaque_message_fields(
        target.navigate_to.travel_params,
        profile.travel_params_fields,
        profile.travel_params_field_numbers,
        f"{owner} TravelParams",
    )
    _merge_opaque_message_fields(
        target,
        profile.target_fields,
        profile.target_field_numbers,
        f"{owner} Target",
    )


def _merge_opaque_message_fields(
    message: object,
    profile_payload: bytes,
    field_numbers: tuple[int, ...],
    owner: str,
) -> None:
    expected = decode_fields(profile_payload)
    current = decode_fields(message.SerializeToString(deterministic=True))
    existing = tuple(field for field in current if field.number in field_numbers)
    if existing and existing != expected:
        raise ValueError(f"{owner} already contains a different opaque field profile")
    if not existing:
        message.MergeFromString(profile_payload)
    merged = decode_fields(message.SerializeToString(deterministic=True))
    retained = tuple(field for field in merged if field.number in field_numbers)
    if retained != expected:
        raise ValueError(f"{owner} did not retain the opaque field profile exactly")


def _walk_dock(
    bundle: Path,
    dock_record: dict[str, object],
    opaque_target_profile: _OpaqueTargetProfile | None,
) -> walks_pb2.Dock:
    if opaque_target_profile is None:
        raise ValueError(
            "dock export requires an observed opaque target profile; refusing an incomplete Dock"
        )
    target_path = bundle / str(dock_record["cloned_target"])
    if not target_path.is_file():
        raise ValueError(f"cloned dock target missing: {target_path}")
    target = walks_pb2.Target()
    try:
        target.ParseFromString(target_path.read_bytes())
    except DecodeError as exc:
        raise ValueError(f"invalid cloned dock target: {target_path}") from exc
    if target.WhichOneof("target") != "navigate_to":
        raise ValueError(f"cloned dock target is not NavigateTo: {target_path}")
    travel_fields = decode_fields(target.navigate_to.travel_params.SerializeToString())
    travel_field_numbers = {field.number for field in travel_fields}
    if 5 not in travel_field_numbers:
        target.navigate_to.travel_params.feature_quality_tolerance = (
            target.navigate_to.travel_params.TOLERANCE_DEFAULT
        )
    if 10 not in travel_field_numbers:
        target.navigate_to.travel_params.blocked_path_wait_time.seconds = 5
    _merge_opaque_target_profile(
        target,
        opaque_target_profile,
        f"dock {dock_record['dock_id']}",
    )
    dock = walks_pb2.Dock(
        dock_id=int(dock_record["dock_id"]),
        docked_waypoint_id=str(dock_record["new_docked_waypoint_id"]),
    )
    dock.target_prep_pose.CopyFrom(target)
    dock.prompt_duration.seconds = 10
    return dock


def _set_default_element_behaviors(element: walks_pb2.Element) -> None:
    for behavior in (element.target_failure_behavior, element.action_failure_behavior):
        behavior.prompt_duration.seconds = 60
        behavior.proceed_if_able.SetInParent()
    element.battery_monitor.battery_start_threshold = 60
    element.battery_monitor.battery_stop_threshold = 15


def _load_sidecars(
    bundle: Path, action_record: dict[str, object], element_id: str
) -> list[_Sidecar]:
    sidecars: list[_Sidecar] = []
    for record in action_record.get("images", []):
        path = bundle / str(record["cloned_path"])
        if not path.is_file():
            raise ValueError(f"action image sidecar missing: {path}")
        image = image_pb2.Image()
        try:
            image.ParseFromString(path.read_bytes())
        except DecodeError as exc:
            raise ValueError(f"invalid Image sidecar: {path}") from exc
        if not image.data:
            raise ValueError(f"Image sidecar contains no image data: {path}")
        if not path.name.startswith(element_id):
            raise ValueError(f"action image name does not start with cloned ID: {path.name}")
        sidecars.append(_Sidecar(path=path, name=path.name, image=image))
    return sidecars


def _rehydrate_images(
    element: walks_pb2.Element, sidecars: list[_Sidecar]
) -> tuple[int, list[str]]:
    used: set[Path] = set()
    for index, alignment in enumerate(element.action_wrapper.spot_cam_alignment.alignments):
        reference = alignment.reference_image
        if not reference.shot.HasField("image"):
            continue
        expected = reference.shot.image
        prefix = (
            f"{element.id}-alignment-{index}-{reference.image_service}-"
            f"{reference.source.name}-{reference.shot.frame_name_image_sensor}-"
        )
        candidates = [
            item
            for item in sidecars
            if item.path not in used
            and item.name.startswith(prefix)
            and _compatible_image(expected, item.image)
        ]
        if not candidates:
            if expected.data:
                continue
            raise ValueError(
                "no alignment image sidecar matches "
                f"{element.id}: {reference.image_service}/{reference.source.name}/"
                f"{reference.shot.frame_name_image_sensor}"
            )
        candidates.sort(key=lambda item: item.name)
        selected = candidates[0]
        reference.shot.image.CopyFrom(selected.image)
        used.add(selected.path)

    if element.action.WhichOneof("action") == "data_acquisition":
        captures = element.action.data_acquisition.record_time_images
        for capture in captures:
            expected = capture.shot.image
            prefix = (
                f"{element.id}-daq-{capture.image_service}-{capture.source.name}-"
                f"{capture.shot.frame_name_image_sensor}-"
            )
            candidates = [
                item
                for item in sidecars
                if item.path not in used
                and item.name.startswith(prefix)
                and _compatible_image(expected, item.image)
            ]
            if not candidates:
                if expected.data:
                    continue
                raise ValueError(
                    "no DAQ image sidecar matches "
                    f"{element.id}: {capture.image_service}/{capture.source.name}/"
                    f"{capture.shot.frame_name_image_sensor}"
                )
            candidates.sort(key=lambda item: item.name)
            selected = candidates[0]
            capture.shot.image.CopyFrom(selected.image)
            used.add(selected.path)

    unused = [item.name for item in sidecars if item.path not in used]
    _require_embedded_images(element)
    return len(used), unused


def _compatible_image(expected: image_pb2.Image, actual: image_pb2.Image) -> bool:
    for field in ("cols", "rows", "format", "pixel_format"):
        value = getattr(expected, field)
        if value and value != getattr(actual, field):
            return False
    return True


def _require_embedded_images(element: walks_pb2.Element) -> None:
    if element.action.WhichOneof("action") == "data_acquisition":
        for capture in element.action.data_acquisition.record_time_images:
            if capture.shot.HasField("image") and not capture.shot.image.data:
                raise ValueError(f"DAQ image remained empty after rehydration: {element.id}")
    for alignment in element.action_wrapper.spot_cam_alignment.alignments:
        if (
            alignment.reference_image.shot.HasField("image")
            and not alignment.reference_image.shot.image.data
        ):
            raise ValueError(f"alignment image remained empty after rehydration: {element.id}")


def _validate_walk_names(
    root: str, mission_name: str, walk: walks_pb2.Walk, report: ValidationReport
) -> None:
    archive_name = root.removesuffix(".walk")
    expected_mission = f"{root}/missions/{archive_name}.walk"
    if mission_name != expected_mission:
        report.error(f"mission filename does not match archive root: {mission_name}")
    if walk.map_name != archive_name:
        report.error(f"Walk map_name mismatch: {walk.map_name!r}")
    if walk.mission_name != archive_name:
        report.error(f"Walk mission_name mismatch: {walk.mission_name!r}")
    if not walk.id:
        report.error("Walk ID is missing")


def _validate_graph_snapshots(
    archive: zipfile.ZipFile,
    files: dict[str, zipfile.ZipInfo],
    root: str,
    graph: map_pb2.Graph,
    report: ValidationReport,
) -> None:
    for waypoint in graph.waypoints:
        if not waypoint.snapshot_id:
            continue
        name = f"{root}/waypoint_snapshots/{waypoint.snapshot_id}"
        if name not in files:
            report.error(f"waypoint snapshot missing: {waypoint.snapshot_id}")
            continue
        try:
            snapshot = map_pb2.WaypointSnapshot.FromString(archive.read(name))
        except DecodeError as exc:
            report.error(f"invalid waypoint snapshot {waypoint.snapshot_id}: {exc}")
            continue
        if snapshot.id != waypoint.snapshot_id:
            report.error(f"waypoint snapshot ID mismatch: {waypoint.snapshot_id}")
    for edge in graph.edges:
        if not edge.snapshot_id:
            continue
        name = f"{root}/edge_snapshots/{edge.snapshot_id}"
        if name not in files:
            report.error(f"edge snapshot missing: {edge.snapshot_id}")
            continue
        try:
            snapshot = map_pb2.EdgeSnapshot.FromString(archive.read(name))
        except DecodeError as exc:
            report.error(f"invalid edge snapshot {edge.snapshot_id}: {exc}")
            continue
        if snapshot.id != edge.snapshot_id:
            report.error(f"edge snapshot ID mismatch: {edge.snapshot_id}")


def _validate_target(
    element: walks_pb2.Element,
    waypoint_ids: set[str],
    edge_ids: set[tuple[str, str]],
    report: ValidationReport,
) -> None:
    _validate_target_message(
        element.target,
        f"element {element.id}",
        waypoint_ids,
        edge_ids,
        report,
    )


def _validate_target_message(
    target: walks_pb2.Target,
    owner: str,
    waypoint_ids: set[str],
    edge_ids: set[tuple[str, str]],
    report: ValidationReport,
) -> None:
    kind = target.WhichOneof("target")
    if kind == "navigate_to":
        waypoint_id = target.navigate_to.destination_waypoint_id
        if waypoint_id not in waypoint_ids:
            report.error(f"{owner} target waypoint missing: {waypoint_id}")
    elif kind == "navigate_route":
        route = target.navigate_route.route
        for waypoint_id in route.waypoint_id:
            if waypoint_id not in waypoint_ids:
                report.error(f"{owner} route waypoint missing: {waypoint_id}")
        for edge in route.edge_id:
            key = (edge.from_waypoint, edge.to_waypoint)
            if key not in edge_ids:
                report.error(f"{owner} route edge missing: {key}")
    else:
        report.error(f"{owner} has no navigation target")


def _validate_daq_identity(
    element: walks_pb2.Element, walk_id: str, report: ValidationReport
) -> None:
    del walk_id  # Source mission provenance need not equal the transport Walk ID.
    fields = element.action.data_acquisition.acquire_data_request.metadata.data.fields
    element_value = fields.get("element_id")
    mission_value = fields.get("mission_id")
    if element_value is None and mission_value is None:
        return
    if element_value is None or element_value.string_value != element.id:
        report.error(f"DAQ element_id mismatch: {element.id}")
    if mission_value is None or not mission_value.string_value:
        report.error(f"DAQ mission_id is missing beside element_id: {element.id}")


def _walk_id(manifest: dict[str, object], archive_name: str) -> str:
    source = manifest.get("source", {})
    site_map = source.get("site_map", {}) if isinstance(source, dict) else {}
    source_map_id = site_map.get("id", "unknown") if isinstance(site_map, dict) else "unknown"
    return str(uuid.uuid5(DEFAULT_NAMESPACE, f"{archive_name}:autowalk:{source_map_id}"))


def _override_recording_session_name(
    graph: map_pb2.Graph, recording_name: str | None
) -> dict[str, object]:
    source_names = Counter(
        waypoint.annotations.client_metadata.session_name for waypoint in graph.waypoints
    )
    if recording_name is None:
        return {
            "mode": "preserved",
            "source_names": dict(sorted(source_names.items())),
            "waypoints_updated": 0,
        }
    for waypoint in graph.waypoints:
        waypoint.annotations.client_metadata.session_name = recording_name
    return {
        "mode": "overridden",
        "name": recording_name,
        "source_names": dict(sorted(source_names.items())),
        "waypoints_updated": len(graph.waypoints),
    }


def _validate_archive_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        raise ValueError("Walk archive name cannot be empty")
    if normalized in {".", ".."} or any(char in normalized for char in ("/", "\\", "\0")):
        raise ValueError(f"unsafe Walk archive name: {name!r}")
    if any(ord(char) < 32 for char in normalized):
        raise ValueError("Walk archive name contains control characters")
    normalized = normalized.removesuffix(".walk")
    if not normalized:
        raise ValueError("Walk archive name cannot be empty")
    return normalized


def _validate_recording_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        raise ValueError("recording name cannot be empty")
    if "\0" in normalized:
        raise ValueError("recording name cannot contain a NUL character")
    return normalized


def _read_template_metadata(path: Path) -> bytes:
    path = path.expanduser().resolve()
    if path.is_dir():
        direct = path / "autowalk_metadata"
        candidates = [direct] if direct.is_file() else list(path.glob("*.walk/autowalk_metadata"))
        if len(candidates) != 1:
            raise ValueError("template folder must contain exactly one autowalk_metadata file")
        return candidates[0].read_bytes()
    try:
        with zipfile.ZipFile(path) as archive:
            names = [
                info.filename
                for info in archive.infolist()
                if not info.is_dir() and PurePosixPath(info.filename).name == "autowalk_metadata"
            ]
            if len(names) != 1:
                raise ValueError("template archive must contain exactly one autowalk_metadata file")
            return archive.read(names[0])
    except zipfile.BadZipFile as exc:
        raise ValueError(f"invalid template Walk archive: {path}") from exc
