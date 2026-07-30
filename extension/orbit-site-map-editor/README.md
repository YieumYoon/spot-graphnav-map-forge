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

Record each functional change with its semantic change type. This updates the numeric
Chrome version and adds a display-only development label:

```bash
uv run python scripts/set_editor_build.py bump feature --label action-names
```

`fix` increments the patch component, `feature` increments the minor component, and `breaking`
increments the major component. `bump` works even when a development label is already active.
After live qualification, remove only the transient label with
`uv run python scripts/set_editor_build.py release --keep-version`; the new numeric version remains.

## Workflows

| Tab | Use |
| --- | --- |
| **Explore** | Search and sort waypoints, edges, recordings, Areas, Docks, fiducials, and Actions; inspect Orbit selection; configure overlays |
| **Select** | Build exact-ID sets with queries, add/subtract/intersect/invert, N-hop/component/path/recording tools, viewport/rectangle/polygon selection, and named sets |
| **Action Names** | Select Actions on the Orbit map, assign each inspection type, preview structured names, and apply one reviewed unsaved change; waypoint names are never changed |
| **Edit** | Validate and Connect waypoint pairs, process a Connect queue, batch Archive edges, copy/paste edge settings, and share presets |
| **Validate** | Inspect components, isolated/leaves/bridges/articulations, duplicate names/pairs, cross-recording edges, callback issues, paths, reachability, and crosswalks |
| **Areas** | Show Area callback settings as map labels and merge or replace settings across checked Areas or all editable Areas in one reviewed unsaved change |
| **Walk** | Create a mission-independent, read-only Site View coverage route with exact waypoint exclusions and numbered route targets |

The header layout control defaults to a separate **Right** rail. **Left** moves that rail to the
other side, and **Float** restores the original overlay. Rail modes reduce Orbit's own viewport
width instead of covering its left or right panels, and the preference is retained across reloads.
Collapsing or deactivating the extension releases the reserved space immediately.

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

The **Action Names** tab changes Action names only. It starts in **Normal** mode, where opening map
Actions does not change the rename list. Switch to **Add Actions** only while building the list;
each newly opened Action is then added in selection order. Leaving the tab or applying renames
returns to Normal. Orbit waypoint selection is not used, and multiple Actions attached to one
waypoint remain independent selections. Reopening an already selected Action does not duplicate
it. Press `A` to toggle the mode; the shortcut is limited to this tab and ignored while typing.
The fixed structure is
`enterprise-site-area-[workCenter]-[equipment]-sequence-type`. Enterprise, site, and area are
required. Work center and machine/equipment are optional and are omitted cleanly when blank. Enter
the first sequence exactly as it should appear—for example `0001`; its leading zeros determine the
display width. Each selected Action advances the sequence once and has its own `THRM`, `MECQ`,
`LEAK`, or `AIVI` selector. The extension suggests a type from an existing suffix, Action name,
and available Action metadata. When none provides a useful clue, the type remains blank. Review
the suggestions and change any incorrect value. The complete preview updates immediately. Missing
types, missing or stale Actions, and name collisions prevent applying the change.

While **Action Names** is open, **Show Action names on map** independently controls translucent
current-name labels and defaults to on; it does not depend on the Explore tab's Detailed overlay.
Orbit stores each Action as a body-pose offset from its waypoint, so the extension composes that
offset with the waypoint map transform and places the label beside the Action icon. Actions tied to
the same waypoint keep their separate positions. The status below the toggle reports how many
Actions expose enough position data to project.

At a wide map scale the overlay samples one Action per evenly spaced screen cell, without giving
the current or selected Action priority. Zooming in reduces the cell size until every Action in
the visible area can show its own name from approximately `1.2×` zoom.

The Explore tab's **Detailed overlay** keeps separate **Overall**, **Waypoints**, **Edges**, and
**Areas** groups. Each group has its own visibility control; the three object groups also provide
**Show all values** and **Hide all values** shortcuts. The map can show one value such as Edge
speed, gait, stored connection direction, or Orbit's direction-of-travel setting without the other
details. Waypoint values include identity, recording, degree, robot, timestamp, and the read-back
visual/thermal panorama settings. Edge values expose the public mobility, path, environment, cost,
and Area-callback annotations as independent controls. Edge labels use the effective values shown
by Orbit's editor. When an omitted protobuf field receives an Orbit form default, the label shows
that value with `(default)`—for example `directed exploration on (default)`—instead of the
ambiguous `not set`. Explicit settings omit the suffix. Orbit's `Walk`/`Crawl`, `Avoid`/`Prefer
Avoid`, strict-path, and ground-clutter wording is used instead of lower-level protobuf enum names.

Area controls visually separate **Area identity**, **Same Edge settings, grouped by Area**, and
**Callback parameters**. The middle section does not read a second Area-owned copy: it aggregates
the same per-Edge settings shown by the **Edges** group across the Edges attached to that Area.
Callback parameters default to hidden and include only current values; Orbit's form specs,
defaults, option lists, and UI metadata are filtered out, and duplicate top-level/recorded-data
representations are collapsed. Every callback value that can appear in an Area label has a
matching searchable control. Mixed callback or associated-Edge variants are labeled `mixed (N)`
instead of choosing one value.

Waypoint, Edge, and Area labels remain available at wide map scales through deterministic
screen-cell sampling; selected, work-selection, and finding objects are prioritized. Area labels
use a coarser density step than Waypoint labels at the widest scales, progressively reveal more
while zooming in, and show every visible Area from `1.5×` zoom. Map labels still use a bounded
summary, so select the few values needed for the current inspection. These preferences are
retained across reloads, and legacy flat overlay preferences are migrated automatically.
Action-name labels remain owned by **Action Names** and independent of this master control.

The overlay reads only the extension's read-only graph snapshot. For Edge fields, it applies the
documented or live-qualified Orbit defaults and identifies them with `(default)`; Area Edge
aggregation compares these effective values, so an omitted default and its explicit equivalent do
not produce a false `mixed` result. Orbit's native Waypoint localize/lost-detector/infrared controls
and the allow-travel state of Edges already filtered out of the active graph are not inferred or
shown as fabricated values.

The **Areas** tab derives each Area's effective callback and traversal settings from its associated
active Edges. Explore's Area overlay controls choose the label fields shown at the Area or
associated-waypoint centroid; each list row can expand the exact current callback and Edge-settings
JSON. Checked-Area scope changes only checked Areas;
all-Area scope targets every editable Area. Choose whether the JSON targets Area callbacks or
associated Edge settings. Merge mode applies only listed fields and preserves omitted fields
(`null` removes one field), while replace mode substitutes the selected settings object and always
preserves Area callbacks when replacing Edge settings. The review reports exact Area and Edge
counts before creating one native unsaved Edge-settings draft.

The extension never presses **Save**, never calls a private server write API, and rejects stale,
foreign, missing, duplicate, or changed targets. Connect validation is capped at 12 nearby
candidates per batch, restores the previous Orbit selection, and shows Orbit's available error or
warning detail when a candidate is rejected. The default Connect candidate radius is 2m, matching
Orbit's observed native edge-length limit; a previously saved operator radius remains unchanged.

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
- `updateSiteEdges`;
- `missionsAndActionsForm/updateActions`.

Re-run `docs/orbit-site-map-editor-qualification.md` after an Orbit upgrade. If a native action,
read-back, positive draft-index change, or exactly-one Undo-depth check disagrees, the adapter
reports that an unverified edit may exist and requires operator inspection before any later edit.
