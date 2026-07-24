# Architecture and persistence boundaries

## Principle

Orbit is the only writer of Site Map state. The project may inspect live state, calculate a
proposed change, and ask Orbit to create an unsaved native draft. It does not upload generated
maps, write through private REST endpoints, synthesize server-owned recording objects, or press
**Save**.

This separates two kinds of compatibility:

- **data compatibility** — Orbit creates and persists its own objects;
- **adapter compatibility** — extension selectors and the narrow in-page adapter must be
  requalified when Orbit changes.

An adapter failure must disable the affected operation instead of guessing.

## Active components

### Orbit Site Map Editor

`extension/orbit-site-map-editor` is the primary product. Its content script owns the panel,
selection state, overlays, and workspaces. `page-bridge.js` is the narrow compatibility boundary
with the live Orbit page.

Read-only features can run after the relevant catalog is observed. Mutation assistance requires:

1. exact object identity;
2. current-state validation;
3. an available native Orbit operation;
4. deterministic read-back;
5. exactly one native Undo step;
6. explicit operator review.

The extension never owns persistence.

### Orbit Site Map Migration Assistant

`extension/orbit-graph-repair` is a separate, narrower extension for a same-instance recording
move. It compares the live result Site Map with an immutable B0 baseline and proposes native
Connect, Archive, and edge-settings drafts. Site Map boundary edges remain review-only.

### Read-only backup support

The Python package has no product write or import path:

| Module | Responsibility |
| --- | --- |
| `archive.py` | bounded, read-only tar access |
| `backup.py` | observed backup records and Site Map inventory |
| `site_elements.py` | read-only SiteElement relationship parsing |
| `wire.py` | low-level private-envelope decoding |
| `topology.py` | effective topology, archived-edge tombstones, and public edge settings |
| `reconnect.py` | B0 versus final-backup comparison |
| `cli.py` | `inspect`, `graph-baseline`, and `reconcile-graph` only |

The backup adapter reads an observed private format and is version-sensitive. It must fail closed
on missing, ambiguous, or contradictory records.

## Data flow

```text
private B0 backup ──read-only──> graph-baseline.json
                                      │
                                      ▼
live Orbit Site Map ──read-only──> Extension comparison
                                      │
                                      ▼
                         reviewed native Orbit draft
                                      │
                                      ▼
                      operator review / Undo / Save
```

An optional final backup can be compared with B0 for persistence evidence. That comparison does
not write to Orbit.

## Archived boundary

The former offline clone, identity remapping, bundle generation, Walk packaging, and import probes
are intentionally absent from the active package. They are preserved at the Git branch and tag
`archive/offline-clone-2026-07`; see [legacy/offline-clone.md](legacy/offline-clone.md).
