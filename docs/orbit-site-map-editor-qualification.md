# Orbit Site Map Editor qualification

This record covers both Orbit Site Map extensions and separates observed runtime evidence from
unverified assumptions. It contains no Site Map, recording, waypoint, edge, robot, or server
identifiers.

## Qualified target

- Orbit Site Map editor: 5.1 series
- Extension: `extension/orbit-site-map-editor`
- Extension release: `0.12.4`
- Native edit adapter baseline: 0.2.2
- Migration Assistant extension: `extension/orbit-graph-repair`
- Migration Assistant release: 0.8.1
- Current-build static qualification date: 2026-07-27
- Latest live mutation qualification date: 2026-07-24

Re-run the complete checklist after an Orbit upgrade or an adapter action-name change.

## Runtime evidence

Verified in a live, authenticated Orbit Site Map editor:

- the Editor extension loads independently from the migration extension;
- the live snapshot reports Site Map, waypoint, edge, recording, anchor, selection, and draft-index
  state;
- universal search returns bounded waypoint and edge matches;
- the object-type filter limits results to waypoints;
- **Select** focuses and selects the exact live waypoint;
- Inspector renders the selected waypoint's exact ID, recording, degree, edge sources, position,
  robot, and timestamp fields;
- nearby candidates exclude the selected waypoint and existing graph neighbors;
- gray candidate lines and points render over the current viewport;
- native validation changes one candidate to green;
- validation restores the original single-waypoint selection;
- validation does not enable Orbit **Save** or create a draft-history step.

## Completed first-release probe

One validated candidate passed all of these checks in the live Orbit editor:

1. **Connect** opened the extension-owned exact-pair review without blocking the Orbit tab.
2. **Create unsaved draft** produced one additional live edge.
3. Orbit **Undo** became enabled and its depth increased by exactly one.
4. Orbit **Save** became enabled, but the extension did not press it.
5. One Orbit **Undo** removed the edge, restored the prior edge count and draft index, and disabled
   **Save** again.

Result: **passed**. Orbit **Save** was never pressed.

Use the same five checks for every future qualification. If any step disagrees with the expected
state, stop and requalify the adapter on a disposable Site Map.

## 0.2.1 adapter discovery

The backed-up live Site Map exposed an Orbit 5.1 history detail that the first 0.2 adapter modeled
incorrectly:

| Operation | Draft-index delta | Undo-depth delta | Observed native effect | One Undo restored baseline |
|---|---:|---:|---|---|
| Batch Archive | +1 | +1 | active edge count -1 | yes |
| Edge-settings update | +2 | +1 | unsaved settings draft | yes |
| Queue Connect | +3 | +1 | active edge count +1 | yes |

The internal draft-index delta is therefore not the number of operator Undo steps. Release 0.2.2
qualifies a mutation only when both history metrics are present, the draft index increases, the
Undo depth increases by exactly one, and the exact target read-back succeeds. If post-dispatch
verification fails, the extension warns that an unverified native draft may exist; it does not
claim that the dispatch was rolled back. It records the observed draft/Undo context and locks later
edits. The operator must not Save, must inspect the exact target and history, and should use
**Undo** only if Orbit shows that change as the newest Undo step; otherwise reload Orbit or restore
the backup.

These observations motivated 0.2.2. The final 0.2.2 probe is recorded below.

## Automated gates

Run:

```bash
uv run python scripts/check_editor_extension.py --full --release
uv run python scripts/check_assistant_extension.py --release
```

The canonical gate validates the active-package read-only boundary, manifest references and
dynamic build labels, checks every extension JavaScript file, runs the full pytest suite, and
checks Ruff lint and formatting. Omit `--release` while a transient development `version_name` is
active.

The Assistant gate independently validates its manifest version and file references, checks every
Assistant JavaScript file, rejects a transient development label in release mode, and compares the
manifest version with the Assistant release record.

The bridge simulations cover selection restoration, warning and duplicate rejection, exact live
catalog projection, multi-object native selection, and exactly one Connect, batch Archive, or edge
settings Undo step even when Orbit advances its internal draft index by more than one. The
extension-context simulation also proves that reloading an
unpacked extension fails closed for invalid runtime/storage getters, callback errors, and rejected
Promises. Reinjection replaces the page-adapter listener, carries a unique session ID, and rejects
a repeated native mutation request ID without creating a second draft step. A pending Connect from
the replaced adapter is cancelled before `addSiteEdge`, and post-dispatch exceptions, response
timeouts, and context invalidation are reported as ambiguous instead of as “no mutation.”

Negative simulations also reject missing Undo telemetry, an unchanged Undo depth, concurrent native
mutations, noncanonical edge IDs that cannot be normalized, and loss of future Orbit annotation
fields. An ambiguous mutation or validation-history change stops the current validation batch and
locks later validation and native edits until explicit operator acknowledgement.

The 0.4 simulations additionally prove:

- `site_view_snapshot` reads only SiteWaypoint panorama and Dock settings, omits mission and
  SiteElement data even when they exist in Redux, and performs zero Redux dispatches;
- Site View eligibility and planned-route coverage are mission-independent;
- exact waypoint exclusions remove those waypoints and incident active edges before planning,
  distinguish explicit exclusions from disconnected scope, and reject unknown/excluded-start/all
  exclusion cases;
- open and return-to-start coverage walks visit every required waypoint using only active edges;
- the default scope chooses an explicit start, then a Dock-connected active component, then the
  largest active component; archived/disabled edges and isolated starts are rejected correctly;
- disconnected and isolated components remain separate and carry relocalization warnings;
- intentional Sleep targets split the execution route without creating an Action at every waypoint;
- ordered route targets have contiguous `#1, #2, …` sequence numbers;
- short-Sleep compatibility mode changes only otherwise actionless route checkpoints;
- optional Sleep Actions are scheduled at their first planned waypoint visit;
- removing a planned edge invalidates the plan;
- a synthetic 5,000-waypoint branching graph validates without recursion failure and keeps every
  NavigateRoute target at or below 150 waypoint IDs.

The 0.5 static gates additionally prove that the History tab, edit-plan import/export, local
journal, before/after plan preview, and proposed-edit overlay are absent. Native mutation
verification still requires a positive draft-index change, exactly one new Undo step, and exact
target read-back. The unverified-edit recovery control remains available in **Edit**.

The version workflow uses an explicit semantic type: `fix` increments patch, `feature` increments
minor, and `breaking` increments major. The `bump` command updates the Chrome version and its
development label even when another development label is active.

The static Action-selection checks and naming simulations cover:

- Action naming owns a separate **Action Names** workspace and is absent from **Edit**;
- Orbit Action route changes publish a dedicated event, and reinjection restores wrapped browser
  history methods;
- the workspace starts in Normal mode, where map Action clicks do not alter the rename selection;
- only explicit Add Actions mode accepts Action route events, and leaving the workspace or applying
  renames returns to Normal;
- the `A` shortcut toggles the mode only in the visible Action Names workspace and is ignored in
  text-entry controls;
- Action selections are session-only and are not restored from Chrome storage;
- Actions attached to the same waypoint remain separate selections and waypoint names are never
  changed;
- selecting an Action again does not duplicate its ID;
- one first-number value such as `0001` determines both the starting integer and zero-padding,
  replacing separate start and width controls;
- the fixed hyphen-joined structure requires enterprise, site, and area, while blank work center
  and machine/equipment values are omitted without doubled separators;
- selection order controls contiguous, width-bounded Action sequences;
- each Action has an editable `THRM`, `MECQ`, `LEAK`, or `AIVI` selector populated from an explicit
  suffix, Action name, or metadata, and remains blank when no clue matches;
- Action-ID-keyed rows retain their existing DOM and focused selector across repeated graph
  snapshots; only changed names, order, types, additions, and removals are reconciled;
- the Action Names workspace has a persisted, default-on map-label toggle independent of Detailed
  overlay; it composes each Action's `waypointTformBodyOffset` with the waypoint seed transform,
  reports the number of projectable Actions, and keeps multiple Actions on one waypoint spatially
  separate;
- Action-name labels use deterministic, position-based density steps: zoomed-out maps sample
  uniformly across the viewport with no current/selection priority, while zooming in reveals
  progressively more individual Action names and `1.2×` or greater shows every visible Action;
- hierarchy, sequence, and type inputs immediately update the complete multi-Action preview;
- missing types, missing selected Actions, duplicate output names, and existing-name
  collisions prevent applying renames;
- a valid multi-Action batch uses `missionsAndActionsForm/updateActions`, preserves unrecognized
  nested Action fields, advances the Action draft index, creates exactly one Undo step, and is
  reflected by the next read-only snapshot;
- a stale observed Action name is rejected before dispatch and leaves Action history unchanged.

The panel-layout simulation proves that the default right rail, optional left rail, and Float mode
normalize deterministically. Closing or deactivating the panel removes its document-level rail
attribute so Orbit regains the full viewport rather than retaining an empty reserved column.

## 2026-07-27 Action-name adapter discovery

A read-only inspection of the authenticated Orbit 5.1 editor on 2026-07-27 confirmed the native
Action edit contract without dispatching it:

- the native action type is `missionsAndActionsForm/updateActions`;
- the payload contains `updatedActions` and `originalActionsById`;
- unsaved Action entities and their independent history live under
  `mapMissionsEditor.form.data.actions` and `mapMissionsEditor.form`;
- the sampled Action form had no existing unsaved draft before or after the inspection.

Result: **passed** for read-only adapter discovery. A reversible live Action-name mutation probe
remains unqualified until an operator explicitly authorizes a backed-up target, exact selected
Actions, one newest Undo, and restoration to the prior state. Orbit **Save** was not pressed.

## 0.8.1 Migration Assistant mutation-safety probe — passed

The separately loaded `extension/orbit-graph-repair` development build was executed against an
authenticated Orbit 5.1 editor on 2026-07-24. The operator explicitly authorized reversible native
drafts on a backed-up Site Map for this probe. No private Site Map or graph identifiers were
retained.

- Loading a matching B0 baseline produced the expected comparison guide without creating a draft.
- Repeating **Connect in Orbit** for the same exact pair entered a fresh validation cycle and
  received the same explicit native rejection instead of reporting stale success or timing out.
  The failed attempts did not enable Orbit **Undo** or **Save**, create a draft, or set the
  assistant's mutation lock.
- Two Editor-created temporary Connect drafts supplied valid, reversible test edges. With one
  temporary edge removed, a private one-action guide made **Connect in Orbit** recreate that exact
  validated pair. The internal draft index advanced by more than one while Undo depth increased by
  exactly one and exact read-back succeeded.
- After one Undo, importing the same private guide and repeating the same pair exercised the
  `previousMatches` clear-and-reselect path. The second Connect also succeeded without stale
  success, rejection, timeout, or mutation lock, and again created exactly one Undo step.
- With both temporary edges present, the normal B0 comparison exposed three pending Archive items.
  **Archive all pending edges** created one native draft containing all three, changed draft index
  from 2 to 3 and Undo depth from 2 to 3, and passed exact batch read-back. One Undo restored all
  three pending items and reset local completion state.
- An Editor batch temporarily changed three active edge profiles. A settings-bearing B0 then
  exposed 16 pending settings items, including 13 crosswalk profiles. **Restore all pending edge
  settings** updated all 16 in one native draft, changed draft index from 6 to 7 and Undo depth
  from 1 to 2, and passed exact annotation read-back. One Undo restored all 16 pending items; a
  second Undo removed the temporary Editor settings draft.
- A one-shot qualification fault converted one verified Connect success response into an
  ambiguous post-dispatch failure after Orbit had created the draft. The assistant displayed the
  unverified-draft warning with before/after history context, disabled all later mutation
  controls, and left Orbit **Save** and **Undo** available for inspection. The native message
  function was restored immediately.
- One verified newest Undo removed the ambiguous draft while the mutation lock remained latched.
  Only explicit recovery acknowledgement cleared the lock and re-enabled editing.

Result: **passed** for successful and rejected Connect, repeated-pair reselection, multi-edge
Archive, multi-edge settings, and ambiguous post-dispatch mutation-lock paths. Orbit **Save** was
never pressed. Every created draft was removed with the verified newest Undo step, the original B0
comparison was restored to its starting Connect, Archive, and settings item counts, the temporary
private guide was deleted, and the final state showed no selection and no unsaved draft.

## Pending verification

- `scripts/set_editor_build.py` defaults to the Editor manifest. An Assistant development label
  requires an explicit `--manifest extension/orbit-graph-repair/manifest.json`; the default
  invocation cannot statically establish the Assistant build label.

The `previousMatches` clear-and-reselect path, Assistant batch Archive and settings Undo depth, and
the unverified-draft lock UI were pending here until the 0.8.1 probe recorded above executed them
against live Orbit.

## 0.5.0 History workflow removal probe — passed

The unpacked extension and Orbit tab were reloaded without creating a draft:

1. Version 0.5.0 exposed exactly five workflow tabs: **Explore**, **Select**, **Edit**,
   **Validate**, and **Walk**. No **History** tab was present.
2. **Edit** retained Archive, edge settings, presets, Connect mode, and the Connect queue, but
   exposed no Add-to-plan, plan import/export, journal, or draft-monitor controls.
3. **Explore** retained its live graph overlays without a **Proposed edits** toggle.
4. **Walk** still read 1,197 Site View waypoint settings through the mission-independent adapter.
5. Draft index remained 0 and Orbit **Cancel** and **Save** remained disabled.

Result: **passed**. Removing the History workflow did not affect live graph loading, editing
controls, or Site View coverage planning. Internal draft/Undo safety telemetry remains active.

## Development workflow and workspace-module probe — passed

The unpacked extension was given a display-only development build label and qualified without
creating a draft:

1. Reloading the extension updated both the extension card and panel to the same manifest-derived
   build label.
2. Reloading the Orbit tab second reinjected exactly one editor root.
3. The panel exposed exactly **Explore**, **Select**, **Edit**, **Validate**, and **Walk**.
4. The separately loaded Select, Edit, and Validate workspace modules exposed their expected
   controls.
5. Orbit **Save** and **Cancel** remained disabled throughout the read-only probe.

Result: **passed**. The build-label and module boundaries can distinguish a live feature branch
without changing the numeric release or Orbit data.

## 0.3 live read-model shape audit — passed

A read-only inspection of the authenticated Orbit 5.1 Redux model confirmed the adapter paths
without dispatching an action:

- two current SiteWalk mission records each exposed ordered `siteElementIds`;
- mission routes used `route.result.routeResults`, with 176 route results in the sampled SiteWalk;
- each route result exposed `target.from`, `target.to`, `target.siteMapId`, and
  `route.waypointId` / `route.edgeId`;
- the sampled route target contained 84 waypoint IDs and no explicit edge IDs;
- 351 SiteElements exposed the expected Action oneof fields and protobuf Duration shape;
- the live Action inventory contained 346 data-acquisition and 3 Sleep Actions, with 30
  waypointless SiteElements;
- 1,549 SiteWaypoint entities were present; 1,197 exposed visual-eligible
  `sitePanoSettings` with `minTimeBetweenCaptureVisual`;
- three SiteDocks exposed root-level `dockedWaypointId`.

The bridge simulation fixture mirrors these live nested paths. This passes the live data-shape gate,
but the complete 0.3 panel/overlay probe remains pending until the unpacked extension and Orbit tab
are reloaded.

## 0.3 immutable-backup scale probe — passed

The coverage planner was run read-only against an immutable production-shaped backup inventory. No
backup, Site Map, or Orbit resource was modified.

| Evidence | Result |
|---|---:|
| Waypoints | 4,733 |
| Effective edges | 3,845 |
| Connected components | 1,138 |
| Largest component | 3,592 waypoints |
| Isolated components | 1,135 |
| Required waypoints visited | 4,733 / 4,733 |
| Edge traversals | 6,797 |
| Repeated visits | 3,202 |
| Ordered execution targets | 1,183 |
| Maximum waypoint IDs in one NavigateRoute target | 150 |
| Validation errors | 0 |

Result: **passed** in 131 ms on the development machine. This proves offline graph coverage,
component separation, route chunking, and validation at the observed scale. It does not replace the
live 0.3 Orbit UI probe or robot execution qualification.

## 0.3 live Walk probe — passed

The unpacked 0.3.0 extension and Orbit Site Map editor were reloaded, then tested against the live
1,549-waypoint / 1,114-edge Site Map:

1. **Walk** remained selected after asynchronous workspace restoration and a complete snapshot
   refresh interval.
2. The read-only adapter reported two SiteWalks, 175 referenced SiteElements, and 1,197 Site View
   waypoint settings.
3. The selected SiteWalk rendered all 175 Actions in exact order, 63 distinct Action waypoints, 369
   route waypoints, and 357 / 1,197 Site View eligible waypoints covered.
4. Focusing Action 1 showed its numbered Action marker and four visible current-route segments
   without selecting or editing an Orbit object.
5. **All components** produced a graph-valid plan for all 1,549 waypoints: 1,807 edge traversals,
   742 repeated visits, 484 components, 483 component transitions, and 665 ordered targets, of
   which 490 were navigation-only.
6. The plan referenced 175 existing SiteElements and proposed 490 new navigation/Sleep
   SiteElements while reporting zero existing-resource modifications.
7. The visible map viewport showed current-route, coverage-route, and Action overlays together.
8. One optional one-second Sleep at an existing Action waypoint increased the schedule from 175 to
   176 Actions and the proposed-new count from 490 to 491; it remained local to the plan.
9. JSON copy and download controls became enabled; no private plan was downloaded during the
   qualification.
10. Before and after the complete probe, Orbit remained at draft index 0, Undo depth 0, Redo depth
    0, zero selected waypoints/edges, and disabled **Save**.

The live probe exposed and fixed two UI defects before the final pass: an empty validation-card
title caused by a misplaced text argument, and a load-time race that could restore **Explore**
after the operator selected **Walk**.

Result: **passed**. No SiteWalk, SiteElement, Site Map, draft-history, selection, or Save state was
modified.

## 0.3.1 active-reachable Walk probe — passed

The extension and Orbit tab were reloaded and the default operational scope was tested against the
same anonymized 1,549-waypoint / 1,114-active-edge Site Map:

1. Version 0.3.1 loaded with **Reachable from start / Dock — active edges** and
   **Navigation-only targets** selected by default.
2. With no explicit start, the planner chose a Dock waypoint and one 979-waypoint active component.
   It excluded 570 waypoints in other disconnected or isolated components.
3. The graph-valid walk used 1,691 active-edge traversals, 713 repeated visits, 175 existing
   SiteElements, and seven new navigation-only checkpoints. Automatic Sleep count was zero.
4. Enabling the compatibility fallback changed only those seven otherwise actionless checkpoints
   to one-second Sleeps. Waypoint coverage, traversal counts, existing Actions, and total target
   count were unchanged.
5. Restoring the default returned to seven navigation-only checkpoints and zero fallback Sleeps.
6. Throughout the probe, draft index remained 0 and Orbit **Cancel** and **Save** remained disabled.

Result: **passed**. The default ignores non-operational components and adds no Sleep; the fallback
is explicit, minimal, reversible within the local plan, and performs no Orbit write.

## 0.4.0 mission-independent exclusions and numbered targets probe — passed

The extension and Orbit tab were reloaded on the anonymized 1,549-waypoint / 1,115-edge Site Map:

1. Version 0.4.0 loaded 1,197 Site View waypoint settings through `site_view_snapshot`; the Walk UI
   exposed no source-mission selector and reported that no SiteWalk or SiteElement was read.
2. One exact waypoint was selected with **Select**, imported through **Add Orbit selection to
   exclusions**, and shown as one explicit exclusion.
3. Planning removed that waypoint and its two incident active edges before graph traversal. The
   active-reachable result contained 1,065 waypoints, 1,863 traversals, and 799 repeated visits.
4. Site View coverage reported one explicitly excluded eligible waypoint separately from 143
   eligible waypoints outside the planned active scope.
5. Thirteen execution targets appeared as the contiguous sequence `#1` through `#13`; focusing the
   first target moved Orbit to its waypoint. The overlay showed the excluded waypoint as a red
   `×`, the planned route, and numbered target diamonds.
6. The test selection was cleared. Draft index remained 0, Orbit **Cancel** and **Save** remained
   disabled, and the extension performed no write.

Result: **passed**. Exact exclusions, incident-edge removal, route numbering, and mission-independent
Site View planning work against the qualified Orbit 5.1 editor without creating a draft.

## 0.3.2 source-free Site View coverage probe — passed

A fresh Orbit reload was tested before the optional SiteWalk and SiteElement catalogues hydrated:

1. **Source SiteWalk** remained at **No source SiteWalk — Site Map coverage only**.
2. The bounded read retry independently loaded 1,197 visual-eligible SiteWaypoint panorama
   settings while the optional SiteWalk count was still zero.
3. **Plan coverage** produced a graph-valid 979-waypoint route with 1,691 active-edge traversals,
   713 repeated visits, 12 navigation-only checkpoints, zero fallback Sleeps, and zero referenced
   existing SiteElements.
4. Site View route coverage reported 967 / 1,197 eligible waypoints within the active-reachable
   component and 230 eligible waypoints outside it.
5. The plan explicitly reports that this is route reachability, not proof of image capture.
6. Draft index remained 0 and Orbit **Cancel** and **Save** remained disabled.

Result: **passed**. Neither Site View eligibility, planned-route coverage, nor route generation
requires an existing mission. Selecting a source SiteWalk is optional and only adds existing
Actions and current-route comparison.

## 0.2.2 runtime probe — passed

The final probe used a backed-up live Site Map and did not press **Save**:

1. the 0.2.2 panel loaded all five tabs and projected the complete live graph;
2. an exact named edge selection round-tripped through Orbit without changing draft history;
3. a verified non-bridge manual edge produced one batch Archive Undo step, draft-index delta `+1`,
   and active-edge delta `-1`; one native **Undo** restored the baseline;
4. a reviewed cost preset on an edge carrying a crosswalk callback produced one settings Undo step
   and draft-index delta `+2`; exact read-back retained the callback, and one native **Undo**
   restored the original cost and history;
5. a pair accepted by Orbit's native validator produced one Connect Undo step, draft-index delta
   `+3`, and active-edge delta `+1`; one native **Undo** removed it and restored the baseline;
6. after every Undo, the active-edge count, draft index, Undo depth, and disabled **Save** state
   matched the starting state;
7. no uncertainty lock or new Chrome extension error remained.

Result: **passed**. The different draft-index deltas all represented exactly one operator Undo step,
which is the 0.2.2 compatibility rule.
