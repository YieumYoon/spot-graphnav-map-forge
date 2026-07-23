# Package workflow boundaries

The Python package serves two workflows. Keep their dependencies and support claims separate even
though they share backup parsing code.

## Shared read-only foundation

| Module | Responsibility |
| --- | --- |
| `archive.py` | bounded, read-only backup access |
| `backup.py` | observed backup records, map resolution, and graph reconstruction |
| `wire.py` | low-level protobuf envelope inspection |
| `models.py` | shared internal data models |
| `topology.py` | effective B0 topology, tombstones, and public edge settings |

Shared modules must not perform network writes or mutate a source backup.

## Recommended Orbit-native workflow

| Module or command | Responsibility |
| --- | --- |
| `graph-baseline` in `cli.py` | create the immutable B0 inventory used by the extension |
| `topology.py` | resolve raw edges, active SiteEdges, tombstones, and settings |
| `reconnect.py` | optional B0/B1 backup comparison and prebuilt repair guide |
| `edge-inventory` in `cli.py` | narrower manual-edge planning inventory |
| `extension/orbit-graph-repair` | live comparison and native unsaved Orbit drafts |

The Python side of this workflow is read-only. Recording moves and every Save occur in Orbit.

## Experimental offline clone workflow

| Module | Responsibility |
| --- | --- |
| `geometry.py` | polygon and coordinate operations |
| `planner.py` | polygon/halo selection and dependency policy |
| `audit.py` | preservation and unsupported-dependency report |
| `remap.py` | clone, Orbit-shaped, and preserve identity policies |
| `clone.py` | graph and payload cloning |
| `builder.py` | offline bundle assembly |
| `validator.py` | offline bundle validation |
| `walk_archive.py` | Autowalk packaging, validation, and import probes |
| `web.py`, `web_assets/` | loopback polygon editor and diagnostic reconciliation view |

These modules do not become part of the recommended same-instance workflow merely because they
share the same CLI. Their generated archives remain experimental and require separate import,
runtime, and re-export gates.

## CLI boundary

Recommended/shared commands:

- `inspect`
- `edge-inventory`
- `graph-baseline`
- `reconcile-graph`

Research and experimental clone commands:

- `wire-dump`
- `prepare`
- `plan`
- `audit`
- `build`
- `validate`
- `export-walk`
- `reissue-walk`
- `validate-walk`
- `serve`

Do not make an experimental command an implicit step of the recommended workflow. If a future
command serves both paths, document which output contract and evidence level apply to each use.
