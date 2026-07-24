# Python read-only support boundary

The Python package supports the Orbit extensions by inspecting immutable backups and producing
private JSON evidence. It has no map clone, import, upload, REST write, or automatic Orbit Save
path.

## Modules

| Module | Responsibility |
| --- | --- |
| `archive.py` | bounded, read-only tar access |
| `backup.py` | observed Site Map, Action, Dock, panorama-state, and layout records |
| `site_elements.py` | triggered SiteElement relationship parsing |
| `wire.py` | low-level private protobuf-envelope decoding |
| `models.py` | shared read-only records |
| `topology.py` | effective graph, SiteEdge tombstones, and public edge settings |
| `reconnect.py` | B0 baseline versus final-backup comparison |
| `cli.py` | the three allowlisted commands |

## CLI allowlist

- `inspect`
- `graph-baseline`
- `reconcile-graph`

Every command reads its input without modification and may write only a new local JSON report.
Output paths fail when the target already exists.

## Private-schema boundary

The backup adapter is based on observed records, not a vendor-published backup schema. Parsing
must fail closed when a required field is absent, duplicated, contradictory, or outside the
allowlisted structure. A successful parse is evidence for the qualified environment only.

## Archived implementation

The removed offline clone, remapping, GraphNav bundle, Walk packaging, and loopback editor code is
preserved at branch and tag `archive/offline-clone-2026-07`. Active modules must not import or
reintroduce it. See [the archive summary](../../docs/legacy/offline-clone.md).
