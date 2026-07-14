from __future__ import annotations

import uuid
from dataclasses import dataclass, field

DEFAULT_NAMESPACE = uuid.UUID("8b85c440-3858-55d4-93ef-15261b573287")


@dataclass
class IdRemapper:
    clone_name: str
    namespace: uuid.UUID = DEFAULT_NAMESPACE
    mappings: dict[str, dict[str, str]] = field(default_factory=dict)

    def map(self, kind: str, old_id: str) -> str:
        by_kind = self.mappings.setdefault(kind, {})
        if old_id not in by_kind:
            by_kind[old_id] = str(uuid.uuid5(self.namespace, f"{self.clone_name}:{kind}:{old_id}"))
        return by_kind[old_id]
