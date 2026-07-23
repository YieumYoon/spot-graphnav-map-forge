from __future__ import annotations

import base64
import re
import uuid
from dataclasses import dataclass, field

DEFAULT_NAMESPACE = uuid.UUID("8b85c440-3858-55d4-93ef-15261b573287")

IDENTITY_MODE_CLONE = "clone"
IDENTITY_MODE_ORBIT_NATIVE = "orbit-native"
IDENTITY_MODE_PRESERVE = "preserve"
IDENTITY_MODES = frozenset(
    {IDENTITY_MODE_CLONE, IDENTITY_MODE_ORBIT_NATIVE, IDENTITY_MODE_PRESERVE}
)

_NATIVE_SUFFIX_PATTERN = re.compile(r"^[A-Za-z0-9+.]{22}==$")
_NATIVE_GRAPH_PREFIXES = {
    "waypoint": "mapped-waypoint",
    "waypoint_snapshot": "snapshot_mapped-waypoint",
    "edge_snapshot": "edge_snapshot_id_mapped-edge",
}
_ORBIT_UUID_KINDS = frozenset({"site_element", "site_dock", "walk", "server_recording"})

# These identities describe GraphNav objects or reusable Orbit objects. A preserve-mode Walk keeps
# them stable and creates a new Walk container around the selected subset.
PRESERVABLE_ID_KINDS = frozenset(
    {
        "waypoint",
        "waypoint_snapshot",
        "edge_snapshot",
        "site_element",
        "site_dock",
    }
)


@dataclass
class IdRemapper:
    clone_name: str
    namespace: uuid.UUID = DEFAULT_NAMESPACE
    preserve_kinds: frozenset[str] = frozenset()
    orbit_native: bool = False
    mappings: dict[str, dict[str, str]] = field(default_factory=dict)

    def map(self, kind: str, old_id: str) -> str:
        by_kind = self.mappings.setdefault(kind, {})
        if old_id not in by_kind:
            if kind in self.preserve_kinds:
                mapped = old_id
            elif self.orbit_native:
                mapped = orbit_native_id(self.namespace, self.clone_name, kind, old_id)
            else:
                mapped = str(uuid.uuid5(self.namespace, f"{self.clone_name}:{kind}:{old_id}"))
            by_kind[old_id] = mapped
        return by_kind[old_id]


def deterministic_uuid4(namespace: uuid.UUID, name: str) -> uuid.UUID:
    """Return a reproducible RFC 4122 UUID carrying version-4 and variant bits."""
    digest = uuid.uuid5(namespace, name).bytes
    return uuid.UUID(bytes=digest, version=4)


def orbit_native_id(namespace: uuid.UUID, clone_name: str, kind: str, old_id: str) -> str:
    """Create a disjoint ID with the shape emitted by tablet GraphNav/Orbit recorders."""
    seed = f"{clone_name}:{kind}:{old_id}"
    if kind in _NATIVE_GRAPH_PREFIXES:
        prefix, separator, suffix = old_id.rpartition("-")
        if not separator or not _NATIVE_SUFFIX_PATTERN.fullmatch(suffix):
            prefix = _NATIVE_GRAPH_PREFIXES[kind]
        token = base64.b64encode(uuid.uuid5(namespace, seed).bytes).decode("ascii")
        token = token.replace("/", ".")
        return f"{prefix}-{token}"
    if kind in _ORBIT_UUID_KINDS:
        return str(deterministic_uuid4(namespace, seed))
    return str(uuid.uuid5(namespace, seed))


def is_orbit_native_id(kind: str, value: str) -> bool:
    """Return whether an output identity has the observed tablet/Orbit wire shape."""
    if kind in _NATIVE_GRAPH_PREFIXES:
        prefix, separator, suffix = value.rpartition("-")
        if not separator or not _NATIVE_SUFFIX_PATTERN.fullmatch(suffix):
            return False
        if kind == "waypoint":
            return len(prefix.split("-")) >= 2
        expected_prefix = "snapshot_" if kind == "waypoint_snapshot" else "edge_snapshot_id_"
        return (
            prefix.startswith(expected_prefix)
            and len(prefix.removeprefix(expected_prefix).split("-")) >= 2
        )
    if kind in _ORBIT_UUID_KINDS:
        try:
            return uuid.UUID(value).version == 4
        except ValueError:
            return False
    return True
