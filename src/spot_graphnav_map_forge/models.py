from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MapLayoutControlPoint:
    """A waypoint placement used to draw a Site Map over a floor plan."""

    waypoint_id: str
    position: tuple[float, float, float]
    rotation: tuple[float, float, float, float]


@dataclass(frozen=True)
class MapLayoutRecord:
    id: str
    name: str
    floor_plan_name: str
    control_points: tuple[MapLayoutControlPoint, ...]


@dataclass(frozen=True)
class SiteMapRecord:
    id: str
    name: str
    recording_ids: tuple[str, ...]
    waypoint_ids: tuple[str, ...]
    source_path: str
    layout: MapLayoutRecord | None = None


@dataclass(frozen=True)
class ActionRecord:
    id: str
    name: str
    waypoint_id: str
    source_path: str
    image_paths: tuple[str, ...] = ()
    trigger_parent_element_id: str | None = None
    trigger_image_service: str | None = None
    has_explicit_relocalization: bool = False


@dataclass(frozen=True)
class DockRecord:
    id: str
    dock_id: int
    docked_waypoint_id: str
    target_kind: str
    target_waypoint_ids: tuple[str, ...]
    target_fingerprint: str
    source_path: str


@dataclass(frozen=True)
class PanoStateRecord:
    waypoint_id: str
    updated_seconds: int | None
    updated_nanos: int | None
    source_path: str
