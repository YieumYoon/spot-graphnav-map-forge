from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MapLayoutControlPoint:
    """A waypoint placement used to draw a Site Map over a floor plan.

    This is not Orbit's Site View panorama feature. The proprietary backup stores this
    floor-plan/layout message alongside a Site Map record.
    """

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
    """One deduplicated SiteDock backed by a public Autowalk Target."""

    id: str
    dock_id: int
    docked_waypoint_id: str
    target_kind: str
    target_waypoint_ids: tuple[str, ...]
    target_fingerprint: str
    source_path: str


@dataclass(frozen=True)
class PanoStateRecord:
    """Waypoint-keyed state for Orbit's 360-degree Site View capture feature."""

    waypoint_id: str
    updated_seconds: int | None
    updated_nanos: int | None
    source_path: str


@dataclass(frozen=True)
class WalkTargetOpaqueProfile:
    """Unambiguous opaque Target fields recovered from records in one backup."""

    selection: str
    source_path: str
    source_updated: int | None
    observed_source_records: int
    travel_params_fields: bytes
    travel_params_field_numbers: tuple[int, ...]
    target_fields: bytes
    target_field_numbers: tuple[int, ...]


@dataclass
class ValidationReport:
    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def error(self, message: str) -> None:
        self.valid = False
        self.errors.append(message)
