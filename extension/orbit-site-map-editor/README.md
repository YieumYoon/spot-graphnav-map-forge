# Orbit Site Map Editor

An independent Chrome extension for editing the currently open Orbit **Site Map**. It uses live
Orbit IDs and native unsaved drafts; it does not load a B0 baseline.

## Install

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Choose **Load unpacked** and select `extension/orbit-site-map-editor`.
4. Reload the Orbit Site Map editor.

The migration extension may remain installed.

When updating an unpacked build, reload the extension first and then reload the Orbit tab. A
previous page may report `Extension context invalidated` because Chrome has retired that content
script; the extension fails closed and asks for one Orbit-tab reload instead of continuing to call
extension APIs. The active panel must show the manifest version or the temporary development build
label. Chrome's extension error list may retain older errors until they are cleared.

## Develop

Use the repo-local `$orbit-extension-dev` skill when working with Codex. The repeatable local gates
are:

```bash
uv run python scripts/check_editor_extension.py
uv run python scripts/check_editor_extension.py --full
```

Before loading a feature branch in Chrome, add a display-only build label:

```bash
uv run python scripts/set_editor_build.py dev
```

After live qualification, remove that transient label with
`uv run python scripts/set_editor_build.py release --keep-version`. Use
`release <version>` only for an integration or release version change.

## Workflows

| Tab | Use |
| --- | --- |
| **Explore** | Search and sort waypoints, edges, recordings, Areas, Docks, fiducials, and Actions; inspect Orbit selection; configure overlays |
| **Select** | Build exact-ID sets with queries, add/subtract/intersect/invert, N-hop/component/path/recording tools, viewport/rectangle/polygon selection, and named sets |
| **Edit** | Validate and Connect waypoint pairs, process a Connect queue, batch Archive edges, copy/paste edge settings, and share presets |
| **Validate** | Inspect components, isolated/leaves/bridges/articulations, duplicate names/pairs, cross-recording edges, callback issues, paths, reachability, and crosswalks |
| **Walk** | Create a mission-independent, read-only Site View coverage route with exact waypoint exclusions and numbered route targets |

Search accepts plain text plus predicates:

```text
type:edge source:manual recording:<exact-id> setting:stairs
type:waypoint degree>=3
type:dock charger
```

Every finding supports **Focus**, **Add selection**, **Copy IDs**, and **Explain**.

## Site View coverage route

The **Walk** tab reads only the current Site View waypoint settings and Docks. It does not read or
reuse an existing SiteWalk or SiteElement:

1. optionally select a start waypoint; otherwise the planner uses a Dock, then the largest active
   component as a fallback;
2. keep the default active-reachable scope, or explicitly choose the largest component or the
   all-components audit scope;
3. to omit an area, select its waypoints with **Select**, then choose
   **Add Orbit selection to exclusions** in **Walk**;
4. optionally return to the start, change the NavigateRoute chunk limit, or add an intentional
   Sleep as `waypoint-id, seconds, name`;
5. leave checkpoint compatibility at navigation-only. Enable short fallback Sleeps only when the
   installed Orbit version does not preserve navigation-only checkpoints;
6. select **Plan coverage**;
7. review red exclusion markers, the colored route, and numbered `#1, #2, …` route targets;
8. download the private JSON plan.

The default planner guarantees at least one visit to every waypoint reachable from the chosen
start/Dock over active edges after explicitly excluded waypoints and their incident edges are
removed. Archived/disabled edges, isolated waypoints, and other disconnected components are
excluded. A waypoint remains eligible when it has at least one active path even if another incident
edge is archived. Route targets are split at intentional Sleeps and the configured size limit, so
no Action is added merely because an intermediate waypoint is visited. The all-components scope is
an audit mode and requires separate localization boundaries.

The JSON is a dry-run plan, not an imported or saved SiteWalk. Existing SiteWalks and SiteElements
are neither read nor modified. See
[SiteWalk coverage planning](../../docs/orbit-sitewalk-coverage-planning.md) before materializing a
plan through a supported Orbit or public API workflow.

## Safe editing

For Connect, Archive, or edge settings:

1. select or enter exact live IDs;
2. review the count, overlay, Site Map ID, and observed draft index;
3. create one native unsaved edit;
4. verify the exact result and one new Orbit **Undo** step;
5. use that **Undo** or press **Save** yourself.

The extension never presses **Save**, never calls a private server write API, and rejects stale,
foreign, missing, duplicate, or changed targets. Connect validation is capped at 12 nearby
candidates per batch and restores the previous Orbit selection.

Orbit may advance its internal draft index by more than one for a single Undo step. The extension
therefore requires a positive draft-index change, exactly one new Undo step, and exact target
read-back. If the response is lost or read-back is inconclusive, it records an **unverified**
state and locks further edits. Do not Save; inspect the target and Orbit history. Use Undo
only when the change is visibly the newest Undo step, otherwise reload Orbit or restore the backup.
Clear the lock in **Edit** only after that inspection or recovery.

Named sets, presets, and Connect queues stay in Chrome local extension storage. Exported preset
libraries contain settings only; named sets and queues contain Site Map object IDs and must be
handled as private operational data.

Coverage plans are downloaded only on request. They contain exact waypoint and edge IDs and are
private operational data.

## Compatibility

The page adapter is qualified against the Orbit 5.1 editor actions:

- `setSelectedWaypoints` / `setSelectedEdges`;
- `addSiteEdge`;
- `archiveSiteEdges`;
- `updateSiteEdges`.

Re-run `docs/orbit-site-map-editor-qualification.md` after an Orbit upgrade. If a native action,
read-back, positive draft-index change, or exactly-one Undo-depth check disagrees, the adapter
reports that an unverified edit may exist and requires operator inspection before any later edit.
