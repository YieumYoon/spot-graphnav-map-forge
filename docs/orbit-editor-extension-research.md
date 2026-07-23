# Orbit editor extension research

## Scope

This document records observations from the Orbit 5.1.8 Site Map editor and defines a safe product
boundary for an in-page map-editing assistant. Initial investigation was read-only. Later controlled
probes created and undid native unsaved Connect, Archive, and edge-settings drafts through Orbit's
own editor actions. No server write API was called and the assistant never pressed Save.

The goal is not to replace Orbit's editor. The extension should expose hidden context, guide native
Orbit operations, and verify their result. Native Orbit remains the only component that creates,
archives, modifies, and saves Site Map entities.

The implementation-level identity model, operator runbook, AI-agent contract, failure modes, and
Orbit-upgrade qualification procedure are maintained in the
[Orbit Site Map Assistant knowledge base](orbit-map-assistant-knowledge-base.md).

## What the native editor already provides

### General editing

- Site Map name editing, undo, redo, clear changes, and save.
- Missions/actions and Site Map editor modes.
- Recording selection and removal from the current Site Map.
- Floor-plan image management, waypoint pins, Areas, and height/display filters.
- Waypoint and edge selection modes with keyboard shortcuts.
- Graph-processing controls for merge and suggested loop closures when available.
- A hidden map search that accepts waypoint ID, waypoint name, edge ID, or fiducial ID.
- Edge and waypoint filters. Edge filters include manually created edges, loop closures, stairs,
  gait, velocity, hazard detection, friction, edge cost, and other mobility settings. Waypoint
  filters primarily cover panorama-update behavior.

### Selected waypoint panel

Orbit displays the following only after a waypoint has been selected:

- waypoint name;
- exact waypoint ID under **Advanced**, with a copy-ID control;
- visible docks and fiducials;
- visual and thermal panorama-update settings;
- localization, lost-detector, and infrared-light settings;
- pin, unpin, and point-cloud actions.

The exact ID therefore already exists in the native UI. The discoverability problem is that it is
selection-only, nested under **Advanced**, and not connected to recording or topology context.

### Selected edge panel

Orbit displays:

- exact from/to waypoint IDs under **Advanced**;
- velocity, gait, body height, strict path following, and audio/visual behavior;
- obstacle cushion, hazard detection, friction, direction, environment, alternate-route finding,
  directed exploration, ground-clutter avoidance, stairs, enable/disable, and high-cost settings;
- Area assignment and an archive action.

Orbit does not identify the selected edge's provenance in this panel. The operator cannot directly
see whether it is odometry, a loop closure, localization, or user-created/manual.

### Recording information

Recording tooltips contain the exact recording ID, name, robot-time start/end, duration, waypoint
count, and robot. This information is not joined to the selected waypoint in the native editor.

## Information available for augmentation

The loaded Orbit editor state contains enough information for a read-only extension inspector.
The extension can join entities by exact IDs without using coordinates or display names as
identity.

### Waypoint inspector

- exact waypoint ID and display name;
- snapshot ID;
- map-frame anchored position and raw waypoint transform;
- creation timestamp;
- recording-session name and exact recording ID;
- recording robot and client version;
- incident edge IDs and neighbor waypoint IDs;
- edge degree and counts by provenance;
- dock, fiducial, pin, panorama, action, and localization indicators.

### Edge inspector

- canonical and stored-direction endpoint IDs;
- edge source: odometry, small-loop closure, fiducial-loop closure, alternate route, manual/user
  request, or localization;
- edge snapshot ID;
- archived, disabled, and pending state;
- transform, length, direction, and mobility annotations;
- endpoint recording sessions and whether the edge crosses a recording-session boundary;
- baseline/post-move reconciliation state.

### Recording inspector

- exact recording ID, name, time range, duration, robot, client, and waypoint count;
- exact waypoint-ID membership;
- internal and boundary edge counts by provenance;
- manually created edges wholly inside the recording;
- manually created edges crossing to another recording;
- dependencies such as Actions, Docks, pins, panorama state, and Areas.

### Map health summary

The extension can calculate live counts, but backup-based state remains the authority for a
rollback or preservation claim. Useful live indicators include:

- waypoint, edge, and recording counts;
- duplicate waypoint-name count;
- edge counts by source and disabled/archived state;
- graph components, isolated waypoints, and bridge edges;
- estimated waypoint totals for proposed recording partitions;
- cross-partition manually created edges and intentional Site Map boundary edges;
- comparison status against an imported immutable backup guide.

## Field validation

One controlled Orbit 5.1.8 map contained 4,733 waypoints, 3,845 effective visible edges, and 54
recording sessions. The loaded editor classified the edge set as:

| Edge source | Count |
| --- | ---: |
| Odometry | 3,017 |
| Manual/user request | 312 |
| Localization | 313 |
| Small-loop closure | 178 |
| Fiducial-loop closure | 25 |

The 54 recordings covered all 4,733 waypoints. The largest recording contained 410 waypoints and
the median contained 61. Of the 312 manually created edges, 145 joined waypoints in the same recording and
167 crossed recording-session boundaries. This makes cross-recording edge context a first-class
partition requirement rather than an exceptional case.

Selecting and focusing entities changed only the camera and selection state. A before/after
fingerprint of the loaded SiteEdge set, SiteWaypoint set, and editor form remained identical, and
the native Save button remained disabled.

## Recommended user experience

The extension should have three modes in one Orbit-side panel.

### Inspect

- Show a compact card for the selected or hovered waypoint/edge.
- Keep exact IDs one-click copyable.
- Join a selected waypoint to its recording session and incident edges.
- Show edge provenance and cross-recording status next to the native edge controls.
- Provide exact-ID search and focus without requiring the hidden Orbit search shortcut.
- Label only selected, filtered, or high-zoom entities on the canvas.

Displaying 4,733 long waypoint IDs simultaneously would be unreadable and expensive. Canvas labels
must be viewport-limited and zoom-gated, with a configurable cap. Exact IDs belong in the inspector
and search results; the canvas should normally use waypoint names plus A/B markers.

### Partition plan

- Color recordings and show their waypoint counts.
- Let the operator stage a source/target recording selection without changing Orbit.
- Show projected waypoint totals and a configurable warning threshold, initially 3,000.
- Classify internal, boundary, and cross-target edges.
- Emphasize manual cross-recording edges and dependencies that require an explicit decision.
- Export an immutable reviewed plan containing exact recording and map IDs.

### Repair

- Load the immutable B0 graph inventory and compare it with the currently open Orbit map, or import
  an optional post-move reconciliation guide.
- Focus exact CONNECT/DELETE waypoint pairs using Orbit's own view action.
- Show endpoint metadata and whether each pair is manual, raw fallback, resurrected deletion, or an
  intentional partition cut.
- Mark work locally and verify that the expected edge state changed after the operator uses Orbit.
- Compare shared edges' public GraphNav annotation profiles, including edge-scoped crosswalk
  callbacks, and offer a confirmed native UPDATE draft when they differ.
- Treat a fresh post-save backup as the optional final payload/wrapper audit; live endpoint equality
  proves topology and public settings only, not private wrappers or waypoint payloads.

## Editing-assistance boundary

The safe default is a human-confirmed native edit:

1. The extension validates the exact map and endpoint IDs.
2. It focuses and highlights the pair.
3. It switches or points to Orbit's native selection tool.
4. The operator invokes native create/archive/parameter controls.
5. The extension re-reads the resulting draft and reports the expected or unexpected delta.
6. The operator saves in Orbit.
7. A fresh backup provides the final verification gate.

The versioned page adapter may dispatch only the exact native editor actions verified in this
document: Connect, Archive, and public edge-settings Update. It must not call undocumented write
endpoints or press Save. Every mutating operation requires a preview/confirmation, exact identity
and stale-state guards, a one-step edit-history check, and a read-back of the resulting draft.

## Architecture

Keep the implementation split into three replaceable layers:

| Layer | Responsibility | Compatibility boundary |
| --- | --- | --- |
| Offline analyzer | Parse immutable backups, compute topology and dependencies, create plans | Backup/schema adapter |
| Chrome extension UI | Inspector, partition planner, repair checklist, canvas overlays | Stable extension-owned UI |
| Orbit page adapter | Read selected entities and anchors; invoke narrow native view/selection behavior | Orbit-version-specific adapter |

The page adapter should expose a versioned, read-mostly contract instead of arbitrary store access.
Each command must validate the current Site Map ID and requested entity IDs. Unsupported fields or
actions fail closed. The extension should report the active adapter version and capability probes
so an Orbit upgrade cannot silently downgrade a safety check.

## Current implementation status

Version 0.8 of the unpacked Orbit Site Map Assistant implements selected-entity inspection, live B0
graph and public edge-settings reconciliation, native CONNECT and Archive assistance, bulk Archive,
and native public edge-settings restore. It
follows Orbit's native waypoint/edge selection and displays exact waypoint, edge, snapshot, and
recording IDs; recording metadata; edge provenance and cross-recording state; coordinates, degree,
neighbors, incident-edge sources, crosswalk callbacks, and public settings; plus live map-health
counts and the 3,000-waypoint advisory.

The extension accepts the complete `orbit_graph_baseline_inventory`, reads a one-shot full graph
snapshot from the current editor and produces CONNECT, DELETE, UPDATE, and informational
boundary-CUT lists. Exact waypoint IDs absent from B0, plus every incident edge, are reported as
newer extra-recording scope and excluded from action generation. UPDATE compares the complete public
`Edge.annotations` profile except provenance (`edgeSource`). Edge-scoped `spot-crosswalk`
area callbacks are included. This path does not require B1, but it does not prove private SiteEdge
wrapper or waypoint-snapshot payload equality.

The adapter was exercised against Orbit 5.1.8 with waypoint, localization-edge, and manually
created-edge selections. Exact recording IDs correctly distinguished a cross-recording manually created edge
whose endpoint recordings had the same display label. The native Save control remained disabled
through inspection, copying, and live baseline comparison. A native connection trace established
that Orbit dispatches `mapEditorInfoSlice/setSelectedWaypoints`, asynchronously validates the pair,
builds `pendingEdgeCreation.createdEdgeCandidate`, and commits it to the local editor history with
`mapEditorFormSlice/addSiteEdge`. Version 0.5 uses that exact path, rejects warnings and unexpected
state transitions, and never presses Save. Recording overlays, partition staging, and DELETE
assistance are not yet implemented.

The CONNECT button was then exercised on the live 5.1.8 editor with an exact missing pair. Orbit selected
both requested IDs, returned no validation errors or warnings, inserted the canonical endpoint key,
and advanced its local form history from index 0 to 1. The assistant marked the pair complete only
after those checks. Native Undo removed the draft and returned the history to index 0; Save was not
invoked by the assistant.

The native Archive flow was also traced with a selected odometry edge in `edge_selection` mode.
Orbit first displayed its anchoring/layout warning, then dispatched
`mapEditorFormSlice/archiveSiteEdges` with an array containing the complete active SiteEdge. The raw
edge remained active in `siteEdges`, while the form stored an `archived: true` override under
`form.data.edges.nonEntities`; history advanced from 13 to 14 and the edge selection cleared. Native
Undo removed that tombstone and returned history to 13. Version 0.5 reproduces this edge-selection
and tombstone path, repeats the warning, verifies the exact endpoint key, and never presses Save.

Bundle inspection established that Orbit's edge form commits settings with
`mapEditorFormSlice/updateSiteEdges` and a payload containing complete updated SiteEdges plus
`originalEdgesById`. Version 0.8 uses that native draft path. It preserves each live wrapper,
identity, transform, snapshot and source; replaces only the B0 public annotation profile; rejects
reversed stored directions, stale settings, changed sources and invalid batches; then requires exact
read-back and one history increment. Crosswalk-only and all-settings batches remain unsaved and are
individually reversible with one native Undo.

## Implementation order

1. **Selected entity inspector** — waypoint/edge IDs, recording join, provenance, coordinates,
   neighbors, and copy/search controls.
2. **Map health header** — live counts, source distribution, duplicate names, and 3,000-waypoint
   threshold warning.
3. **Recording overlay** — color/filter by exact recording ID and summarize manual boundary edges.
4. **Partition staging** — read-only recording selection with projected source/target totals and
   cut classification.
5. **Repair verification** — CONNECT and Archive verify exact drafts in Orbit's local edit history.
6. **Native edit assistance** — CONNECT and Archive are implemented one reviewed pair at a time;
   never bulk-save.

The implemented write boundary is deliberately narrow: native unsaved CONNECT drafts only. It
provides immediate operational value while retaining the versioned, fail-closed inspection contract
required by later editing features.
