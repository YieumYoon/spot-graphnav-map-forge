"""Offline cloning for proprietary SiteElement action envelopes."""

from __future__ import annotations

import re
from dataclasses import dataclass

from bosdyn.api.autowalk import walks_pb2
from google.protobuf.message import DecodeError

from .wire import (
    WireField,
    bytes_values,
    decode_fields,
    rewrite_length_delimited_tokens,
    source_token_remains,
    text_values,
)

_UUID_PATTERN = re.compile(
    rb"(?<![0-9A-Fa-f])"
    rb"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
    rb"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"
    rb"(?![0-9A-Fa-f])"
)


@dataclass(frozen=True)
class SiteElementClone:
    payload: bytes
    source_element_id: str
    source_waypoint_id: str
    new_element_id: str
    new_waypoint_id: str
    replacement_counts: dict[str, int]
    source_mission_ids: tuple[str, ...]
    external_uuid_references: tuple[str, ...]


@dataclass(frozen=True)
class TriggeredSiteElementClone:
    payload: bytes
    source_element_id: str
    source_parent_element_id: str
    new_element_id: str
    new_parent_element_id: str
    trigger_image_service: str
    replacement_counts: dict[str, int]
    source_mission_ids: tuple[str, ...]
    external_uuid_references: tuple[str, ...]


def source_mission_ids(payload: bytes) -> tuple[str, ...]:
    """Return observed DAQ mission provenance from a SiteElement envelope."""
    return _source_mission_ids(decode_fields(payload))


def triggered_action_reference(payload: bytes) -> tuple[str, str] | None:
    """Return the parent SiteElement ID and image service for a triggered AI inspection."""
    return _triggered_action_reference(decode_fields(payload))


def clone_site_element(
    payload: bytes,
    new_element_id: str,
    new_waypoint_id: str,
) -> SiteElementClone:
    """Clone a SiteElement envelope while preserving its opaque action configuration.

    Observed SiteElement field 1 is the element identity and field 3 is its waypoint identity.
    Exact copies of those tokens in nested protobuf metadata are rewritten too. Unknown fields are
    retained byte-for-byte unless an enclosing length changes because it contains a rewritten ID.
    """
    fields = decode_fields(payload)
    element_ids = text_values(fields, 1)
    waypoint_ids = text_values(fields, 3)
    if len(element_ids) != 1:
        raise ValueError(f"SiteElement must contain exactly one field-1 ID, got {len(element_ids)}")
    if len(waypoint_ids) != 1:
        raise ValueError(
            f"SiteElement must contain exactly one field-3 waypoint ID, got {len(waypoint_ids)}"
        )
    source_element_id = element_ids[0]
    source_waypoint_id = waypoint_ids[0]
    replacements = {
        "element_id": (source_element_id.encode(), new_element_id.encode()),
        "waypoint_id": (source_waypoint_id.encode(), new_waypoint_id.encode()),
    }
    rewritten, counts = rewrite_length_delimited_tokens(payload, replacements)
    for label, (old, new) in replacements.items():
        if source_token_remains(rewritten, old, new):
            raise ValueError(f"source {label} remains in cloned SiteElement payload")
        if counts[label] < 1:
            raise ValueError(f"source {label} was not rewritten")

    cloned_fields = decode_fields(rewritten)
    if text_values(cloned_fields, 1) != (new_element_id,):
        raise ValueError("cloned SiteElement field-1 ID mismatch")
    if text_values(cloned_fields, 3) != (new_waypoint_id,):
        raise ValueError("cloned SiteElement field-3 waypoint ID mismatch")

    mission_ids = _source_mission_ids(fields)
    provenance_ids = {value.lower() for value in mission_ids}
    external_references = tuple(
        sorted(
            {
                match.group().decode("ascii").lower()
                for match in _UUID_PATTERN.finditer(payload)
                if match.group().decode("ascii").lower()
                not in {source_element_id.lower(), *provenance_ids}
            }
        )
    )
    return SiteElementClone(
        payload=rewritten,
        source_element_id=source_element_id,
        source_waypoint_id=source_waypoint_id,
        new_element_id=new_element_id,
        new_waypoint_id=new_waypoint_id,
        replacement_counts=counts,
        source_mission_ids=mission_ids,
        external_uuid_references=external_references,
    )


def clone_triggered_site_element(
    payload: bytes,
    new_element_id: str,
    new_parent_element_id: str,
) -> TriggeredSiteElementClone:
    """Clone a waypoint-less triggered SiteElement and rewrite its parent action link.

    Orbit 5.1.8 stores each triggered AI inspection as a separate SiteElement. Its proprietary
    field 14 links the inspection to the image-producing parent SiteElement. The original
    inspection record is kept in the clone bundle even though public Autowalk cannot encode that
    linkage.
    """
    fields = decode_fields(payload)
    element_ids = text_values(fields, 1)
    if len(element_ids) != 1:
        raise ValueError(
            f"triggered SiteElement must contain exactly one field-1 ID, got {len(element_ids)}"
        )
    reference = _triggered_action_reference(fields)
    if reference is None:
        raise ValueError("triggered SiteElement has no field-14 parent reference")
    source_element_id = element_ids[0]
    source_parent_element_id, image_service = reference
    replacements = {
        "element_id": (source_element_id.encode(), new_element_id.encode()),
        "trigger_parent_element_id": (
            source_parent_element_id.encode(),
            new_parent_element_id.encode(),
        ),
    }
    rewritten, counts = rewrite_length_delimited_tokens(payload, replacements)
    for label, (old, new) in replacements.items():
        if source_token_remains(rewritten, old, new):
            raise ValueError(f"source {label} remains in cloned triggered SiteElement payload")
        if counts[label] < 1:
            raise ValueError(f"source {label} was not rewritten")

    cloned_fields = decode_fields(rewritten)
    if text_values(cloned_fields, 1) != (new_element_id,):
        raise ValueError("cloned triggered SiteElement field-1 ID mismatch")
    cloned_reference = _triggered_action_reference(cloned_fields)
    if cloned_reference != (new_parent_element_id, image_service):
        raise ValueError("cloned triggered SiteElement parent reference mismatch")

    mission_ids = _source_mission_ids(fields)
    provenance_ids = {value.lower() for value in mission_ids}
    identity_ids = {
        source_element_id.lower(),
        source_parent_element_id.lower(),
        *provenance_ids,
    }
    external_references = tuple(
        sorted(
            {
                match.group().decode("ascii").lower()
                for match in _UUID_PATTERN.finditer(payload)
                if match.group().decode("ascii").lower() not in identity_ids
            }
        )
    )
    return TriggeredSiteElementClone(
        payload=rewritten,
        source_element_id=source_element_id,
        source_parent_element_id=source_parent_element_id,
        new_element_id=new_element_id,
        new_parent_element_id=new_parent_element_id,
        trigger_image_service=image_service,
        replacement_counts=counts,
        source_mission_ids=mission_ids,
        external_uuid_references=external_references,
    )


def _source_mission_ids(fields: tuple[WireField, ...]) -> tuple[str, ...]:
    action_values = bytes_values(fields, 6)
    if len(action_values) != 1:
        return ()
    try:
        action = walks_pb2.Action.FromString(action_values[0])
    except DecodeError:
        return ()
    if action.WhichOneof("action") != "data_acquisition":
        return ()
    metadata = action.data_acquisition.acquire_data_request.metadata.data.fields
    value = metadata.get("mission_id")
    if value is None or value.WhichOneof("kind") != "string_value" or not value.string_value:
        return ()
    return (value.string_value,)


def _triggered_action_reference(
    fields: tuple[WireField, ...],
) -> tuple[str, str] | None:
    values = bytes_values(fields, 14)
    if not values:
        return None
    if len(values) != 1:
        raise ValueError(f"SiteElement has multiple field-14 trigger envelopes: {len(values)}")
    sources = bytes_values(decode_fields(values[0]), 1)
    if len(sources) != 1:
        raise ValueError("SiteElement field-14 trigger envelope must contain exactly one source")
    source_fields = decode_fields(sources[0])
    parent_ids = text_values(source_fields, 1)
    image_services = text_values(source_fields, 2)
    if len(parent_ids) != 1 or len(image_services) != 1:
        raise ValueError(
            "SiteElement field-14 trigger source must contain one parent ID and image service"
        )
    return parent_ids[0], image_services[0]
