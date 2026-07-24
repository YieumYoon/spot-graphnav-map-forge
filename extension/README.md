# Chrome extensions

These are independent unpacked extensions. Install either or both.

## Orbit Site Map Editor

[`orbit-site-map-editor`](orbit-site-map-editor/README.md) assists normal editing of the currently
open live Site Map:

- search live waypoints, edges, recordings, Areas, Docks, fiducials, and Actions;
- build named exact-ID selections with query, graph, recording, and spatial tools;
- overlay selection, recording, findings, and settings;
- validate topology, paths, reachability, and crosswalks;
- process Connect queues and reviewed native Connect, batch Archive, and edge-settings drafts;
- copy, paste, and share allowlisted edge-setting presets;
- plan mission-independent Site View coverage of the active component reachable from a start/Dock,
  with exact waypoint exclusions, numbered targets, and optional short-Sleep compatibility
  fallbacks;
- never press **Save**.

It does not load a B0 baseline or perform migration reconciliation.

## Orbit Site Map Migration Assistant

[`orbit-graph-repair`](orbit-graph-repair/README.md) is the primary interactive component of the
recommended same-instance Site Map split workflow.

It runs inside the Orbit Site Map editor and:

- inspects exact waypoint, edge, and recording identity;
- compares a live result Site Map with an immutable B0 baseline;
- visualizes Connect, Archive, edge-settings, and Site Map boundary items;
- creates native unsaved Connect, Archive, and public edge-settings drafts;
- restores edge-scoped crosswalk profiles;
- verifies one native Undo step;
- never presses **Save**.

The `orbit-graph-repair` directory name is retained for unpacked-extension path stability even
though its display name is **Orbit Site Map Assistant**.

Start with the [Orbit-native Site Map split](../docs/workflows/orbit-native-map-split.md).
