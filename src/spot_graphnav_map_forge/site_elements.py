"""Read-only parsing helpers for observed SiteElement backup envelopes."""

from __future__ import annotations

from .wire import WireField, bytes_values, decode_fields, text_values


def triggered_action_reference(payload: bytes) -> tuple[str, str] | None:
    """Return the parent SiteElement ID and image service for a triggered AI inspection."""
    return _triggered_action_reference(decode_fields(payload))


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
