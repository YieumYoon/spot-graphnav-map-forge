# Orbit Site Map Editor Assistant: feature research

## Goal

Build a general Orbit **Site Map editing assistant** independently from the existing
migration-oriented extension. The assistant should make large graphs searchable, selectable,
editable in reviewed batches, and verifiable before the operator presses **Save**.

## Product decisions

- All listed editor capabilities remain in scope unless explicitly rejected.
- AI and natural-language automation are out of scope for now.
- Human-operable backup, rollback-plan, checkpoint, and post-Save workflow automation are out of
  scope.
- Orbit-version and active-Site-Map checks remain internal adapter guards, not operator-facing
  features.
- Migration remains in the existing extension. General Site Map editing is a separate extension.
- The first new workflow is **Connect mode** plus a detailed live graph overlay.

Research basis:

- direct inspection of the Orbit 5.1.8 Site Map editor;
- the existing versioned page adapter and controlled native-draft tests;
- Boston Dynamics GraphNav, recording-service, and Orbit API documentation;
- mature GIS/network-editor interaction patterns.

## What Orbit 5.1.8 already provides

### Site Map controls

- Site Map name, Undo, Redo, Cancel, and Save;
- recording selection;
- floor-plan image and height controls;
- waypoint and edge selection modes;
- graph processing for potential merges and loop closures when available;
- Areas, pins, point clouds, fiducials, and panorama settings;
- edge and waypoint filters;
- selected-waypoint and selected-edge property panels.

### Native filters observed

Edge filters:

- extra obstacle avoidance cushion;
- force ground clutter avoidance;
- crawl gait;
- ground friction at or below 0.4;
- ignored hazard detection;
- loop closures;
- manually created;
- no turn;
- stairs;
- fast velocity;
- slow velocity;
- high edge cost.

Waypoint filters:

- update visual panorama;
- update thermal panorama;
- no panorama updates.

Orbit can match any/all filters and limit selection to matches. It also has a height-range filter.

### Important limitations

The inspected editor does not expose:

- a table of all waypoints and edges with sortable fields;
- filtering by exact recording ID, robot, timestamp, edge source, component, degree, or Area;
- saved or named selection sets;
- selection by connected component, shortest path, N-hop neighborhood, polygon, or lasso;
- edge provenance in the selected-edge panel;
- graph-health checks such as isolated waypoints, bridge edges, or unreachable dependencies;
- a reusable edge-settings template;
- a complete diff/preview before a bulk edit;
- a supported Site Map clone or edit-plan import/export workflow.

## Public API boundary

The public Orbit API exposes SiteWalks, SiteElements, SiteDocks, runs, schedules, backups, and
related operational resources. Its published API does not expose Site Map waypoint/edge CRUD.

The public GraphNav recording service can create a waypoint or edge on the robot while recording
and while holding the required lease. It is not a post-recording Orbit Site Map editor API.

Therefore:

- use public APIs for supported operational resources and backup export;
- use Orbit's native editor UI/actions for Site Map drafts;
- keep the page adapter versioned and fail closed after an Orbit upgrade;
- never call private server write endpoints;
- never press **Save** automatically.

## Product jobs

The general assistant should solve four jobs:

1. **Find** an exact Site Map object quickly.
2. **Select** a meaningful set without clicking objects one by one.
3. **Edit** that set through reviewed native Orbit drafts.
4. **Validate** graph and setting consequences before Save.

## Recommended feature backlog

### P0 — useful with the current adapter

| Feature | Operator value | Implementation |
| --- | --- | --- |
| Universal object search | Find waypoint, edge, recording, Area, dock, or fiducial by name or exact ID | Live index over the current editor state |
| Results table | Sort and inspect objects without selecting them on the canvas | Extension-owned virtualized table |
| Named selection sets | Reuse reviewed groups and avoid repetitive clicks | Store exact IDs locally per Site Map |
| Selection algebra | Add, subtract, intersect, invert, and clear sets | Extension model plus native selection actions |
| Graph selection | Select neighbors, N-hop radius, component, path, leaves, or bridge edges | Deterministic live-graph queries |
| Recording selection | Select all waypoints/edges from one exact recording ID | Existing waypoint-to-recording join |
| Canvas overlay | Show the active set, endpoint pairs, and validation findings | Existing exact-anchor SVG overlay |
| Connectable waypoint overlay | After one waypoint is selected, show viable connection candidates | Graph prefilter plus bounded native validation |
| Live detail overlay | Show current waypoint, edge, recording, and settings context on the Site Map | Zoom-gated exact-anchor labels and styles |
| Copy edge settings | Capture supported public settings from one edge | Existing live edge snapshot |
| Paste edge settings | Apply selected fields to a reviewed edge set | Existing native `updateSiteEdges` draft |
| Edge-setting presets | Reuse reviewed stairs, slow, no-turn, high-cost, or crosswalk profiles | Local templates plus field allowlist |
| Archive selected edges | Preview and Archive an exact selected set in one Undo step | Existing batch Archive path |
| Connect queue | Paste or build exact waypoint pairs and process them as a checklist | Existing native Connect path |

### P0 — graph validation

Run these checks continuously or on demand:

- duplicate waypoint names;
- duplicate endpoint pairs;
- isolated waypoints;
- disconnected components;
- leaf waypoints and dead-end branches;
- bridge edges and articulation waypoints;
- edges whose endpoint is missing;
- active/tombstone ambiguity;
- archived or disabled critical connections;
- cross-recording manually created edges;
- inconsistent settings along a selected path;
- missing or stale Area callback references;
- Actions or Docks attached to unreachable waypoints;
- waypoint-count and editor-load completeness warnings.

Every finding should support **Focus**, **Add to selection**, **Copy IDs**, and **Explain**.

### P1 — higher-leverage workflows

| Feature | Purpose |
| --- | --- |
| Query builder | Combine predicates such as `type=edge source=user-request recording=<id>` |
| Spatial selection | Rectangle, polygon, lasso, and current-viewport selection |
| Path inspector | Compare edge settings and direction along an ordered route |
| Reachability test | Check routes from docks or selected start waypoints to Actions and Areas |
| Before/after preview | Show topology, settings, component, and reachability deltas before drafting |
| Edit-plan import/export | Reapply a reviewed exact-ID plan without requiring a migration baseline |
| Crosswalk audit | Find callback Areas, assigned edges, missing approaches, and inconsistent profiles |
| Recording overlay | Color by exact recording ID and expose cross-recording edges |
| Settings matrix | Display mixed values across a selection and edit only chosen fields |
| Preset library | Share organization-approved edge profiles without sharing Site Map data |

### P2 — requires new controlled Orbit action traces

- bulk waypoint name and panorama settings;
- waypoint localization, lost-detector, infrared-light, pin, and point-cloud operations;
- Area creation, geometry editing, naming, and edge assignment;
- floor-plan transform and alignment assistance;
- recording selection assistance;
- graph merge and suggested-loop-closure orchestration.

Each P2 operation needs a disposable Site Map probe, exact native action/state trace, one-Undo-step
verification, stale-state guards, and a post-upgrade capability test before production use.

## Interaction model

Use five tabs:

1. **Explore** — universal search, inspector, live counts.
2. **Select** — query builder, graph/spatial tools, named sets.
3. **Edit** — Connect, Archive, copy/paste settings, presets.
4. **Validate** — findings table, overlays, paths, and reachability checks.
5. **Walk** — mission-independent Site View coverage of the active component reachable from a
   start/Dock, with exact waypoint exclusions, numbered route targets, and disconnected components
   available only as an audit.

The current B0 comparison remains in the migration extension. The general editor extension does not
load B0 or expose migration controls.

## Extension boundary

### Orbit Site Map Editor

New directory: `extension/orbit-site-map-editor`

- live search, filters, selection sets, and overlays;
- Connect mode;
- general Connect, Archive, and edge-settings editing;
- graph validation and internal draft/Undo safety checks;
- no B0 or recording-migration workflow.

### Orbit Site Map Migration Assistant

Existing directory: `extension/orbit-graph-repair`

- B0 baseline loading;
- post-recording-move comparison;
- missing edge, archived edge, and edge-settings reconciliation;
- Site Map boundary review;
- migration operation journal.

The extensions may share tested, build-time source modules, but each must have its own manifest,
storage namespace, UI, release version, and compatibility qualification. Installing one extension
must not require or modify the other.

## Connect mode

When one waypoint is selected:

1. exclude the selected waypoint and existing neighbors;
2. exclude waypoints without a usable live anchor;
3. prefilter by viewport or configurable distance;
4. rank candidates by distance, recording, and graph context;
5. validate a bounded candidate set through Orbit's native edge validator;
6. draw validated candidates in green, rejected candidates in red, and unvalidated candidates in
   gray;
7. show the validation reason, exact ID, recording, distance, and current degree on hover;
8. let the operator select one candidate, preview the pair, and create the existing native Connect
   draft.

Running Orbit validation against every waypoint in a large Site Map would be slow and could disturb
native selection state. Validation should therefore be viewport/radius limited, cached against the
current draft index, and refreshed when the graph changes.

## Live graph overlay

The overlay should provide independent toggles for:

- waypoint name and short/exact ID;
- recording name or color;
- degree, component, and incident edge-source counts;
- waypoint timestamp and robot;
- edge source, direction, and length;
- velocity, stairs, no-turn, high-cost, and other important edge settings;
- manually created, loop-closure, cross-recording, archived, and disabled state;
- crosswalk and Area callback references;
- current selection, named selection sets, and validation findings.

Labels must be zoom-gated, viewport-limited, and capped. At low zoom, use color and compact symbols;
at high zoom or hover, show the detailed text card. Exact IDs remain available without drawing
thousands of full identifiers simultaneously.

## Safety contract

Every mutating feature must:

1. bind to the exact Site Map ID;
2. freeze the exact target IDs and observed state;
3. show a count and visual preview;
4. reject missing, duplicate, foreign, or stale objects;
5. use a verified native Orbit editor action;
6. require exactly one expected Undo step;
7. read back the resulting draft;
8. leave **Save** to the operator.

Do not implement:

- automatic Save;
- arbitrary Redux dispatch;
- private Orbit REST writes;
- raw protobuf replacement inside the live editor;
- automatic waypoint repositioning or deletion;
- automatic graph merge or loop closure without a controlled native-action probe.
- AI or natural-language editing in the current product scope.
- automatic local checkpoints, rollback-plan generation, backup reminders, or post-Save audits.

## Suggested first release

Build **Connect mode** as the first complete vertical workflow:

1. index the live Site Map;
2. select one base waypoint;
3. show prefiltered connection candidates and detailed live context;
4. validate a bounded candidate set through Orbit;
5. choose one candidate and preview the pair;
6. create the existing native Connect draft;
7. verify one Undo step and read-back;
8. refresh the overlay from the changed live graph.

This proves the generic overlay, selection, validation, and editing architecture without requiring
a B0 backup or a new Orbit write action.

## Sources

- [Boston Dynamics: Components of Navigation](https://dev.bostondynamics.com/docs/concepts/autonomy/components_of_autonomous_navigation.html)
- [Boston Dynamics: GraphNav Map Structure](https://dev.bostondynamics.com/docs/concepts/autonomy/graphnav_map_structure.html)
- [Boston Dynamics: Orbit API](https://dev.bostondynamics.com/docs/concepts/orbit/orbit_api.html)
- [Boston Dynamics: Orbit API reference](https://dev.bostondynamics.com/docs/orbit/docs)
- [Boston Dynamics: GraphNav protocol reference](https://dev.bostondynamics.com/protos/bosdyn/api/proto_reference.html)
- [QGIS: feature selection and expressions](https://docs.qgis.org/3.10/en/docs/user_manual/introduction/general_tools.html)
- [QGIS: attribute table and multi-edit](https://docs.qgis.org/3.10/en/docs/user_manual/working_with_vector/attribute_table.html)
- [ArcGIS Pro: network topology validation](https://pro.arcgis.com/en/pro-app/latest/help/data/utility-network/about-network-topology.htm)
- [ArcGIS Pro: topology error inspection](https://pro.arcgis.com/en/pro-app/3.6/help/editing/validate-and-fix-geodatabase-topology.htm)
