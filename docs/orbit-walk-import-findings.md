# Orbit Walk import findings and exporter rules

This document consolidates the import investigation that produced the current Map Forge safety and
compatibility rules. It is intentionally anonymized: private archive names, Site Map names, UUIDs,
waypoint IDs, coordinates, paths, and inspection content belong only in ignored local reports.

The `v1` through `v16` labels below identify private experimental archives, not product releases.
The observations apply only to the same-version environment listed in
[compatibility.md](compatibility.md). They do not establish cross-version behavior.

## Final result

The final controlled comparison isolated an Element-type-specific identity incompatibility:

- a full Walk containing actionless Localize, Sleep, DAQ, and an available Dock materialized when
  the Walk and all three Element IDs were fresh UUIDv4 values;
- an otherwise equivalent archive changed only the actionless Localize Element ID to UUIDv5;
  upload completed, but Orbit did not materialize the Site Map;
- a separate DAQ-only control using a UUIDv5 DAQ Element materialized successfully.

The evidence therefore does **not** support a blanket “Orbit rejects UUIDv5” rule. UUIDv5 GraphNav
waypoint and snapshot IDs and a UUIDv5 DAQ Element were accepted in successful controls. The
observed failure is the conversion path for a navigation-only Localize Element whose ID is UUIDv5.

For Orbit-targeted output, Map Forge should:

1. issue a fresh UUIDv4 Walk ID;
2. issue UUIDv4 IDs for every emitted Walk Element, including actionless Localize and Sleep;
3. make DAQ metadata `mission_id` and `element_id` refer to the current Walk and DAQ Element;
4. keep GraphNav identity policy separate from Walk/SiteElement identity policy;
5. count an import as successful only after the Site Map, Walk, expected Actions, and available Dock
   have materialized.

Upload completion, recording-session visibility, or an offline-valid ZIP is not sufficient.

## Evidence chain

| Probe | Controlled profile | Orbit observation | Meaning |
| --- | --- | --- | --- |
| v1–v5 | Evolving full-map clones with multiple identity, metadata, and Dock-anchor defects | Failed | Confounded; useful for finding missing structure, not for a single-cause conclusion |
| v6–v7 | Structural defects corrected; Localize and Sleep still used UUIDv5 Element IDs | Graph/recording data appeared, but Walk resources did not materialize | Reduced the remaining cause to the Walk conversion boundary |
| v8 | Prepared all-UUIDv4 full profile | Not uploaded | No result may be inferred; later recording associations overlapped an uploaded probe |
| v9 | Same full Graph as v7; one fresh UUIDv4 DAQ Element and retained Dock | Mission, DAQ Action, and available Dock materialized; later mission playback completed a PTZ capture | Graph, snapshots, Dock payload, and the minimal DAQ runtime profile are valid |
| v10 | Small connected path with fresh Graph/recording identities, UUIDv4 DAQ, and Dock | Materialized | Established a cheap reusable control |
| v11 | v10 with only DAQ Element ID changed to UUIDv5 | Materialized | Orbit does not reject every UUIDv5 Element |
| v12 | v10 plus actionless Localize using UUIDv4 | Materialized | Localize payload, route, first position, and lack of Action are valid with UUIDv4 |
| v13 | v10 plus Sleep using UUIDv4 | Materialized | Sleep payload and duration are valid with UUIDv4 |
| v14 | Small Localize → Sleep → DAQ all-UUIDv4 combination | Not uploaded | Prepared control only; no Orbit result |
| v15 | Full Localize → Sleep → DAQ profile, all Element IDs UUIDv4 | Site Map, mission, Action, and Dock materialized | Excluded full-Graph size, combination, ordering, and payloads as causes |
| v16 | v15 profile with only Localize Element ID changed to UUIDv5 | Upload completed; Site Map did not materialize | Isolated UUIDv5 navigation-only Localize as a sufficient failure condition |

v17, which would change only Sleep to UUIDv5, is not required to explain the original failure. It
would answer the narrower question of whether Sleep has the same identity limitation and should be
run only if that extra compatibility boundary is useful.

## What the early failures taught us

The initial archives were not one repeated bug. They exposed several independent requirements:

- early Walk IDs used the wrong identity profile;
- DAQ membership metadata still referred to source Walk/Element identities;
- some archives lacked the tablet metadata pairing used by the selected recording-shaped profile;
- Graph anchors and the anchored Dock object were initially absent;
- Dock target, Localize route, and Sleep/DAQ references had to close over the exported Graph;
- changing display names alone did not make an independent recording association;
- normal structural validation could pass even when Orbit later failed to create SiteMap/Walk
  resources.

By v6/v7 those structural issues were corrected. The later v15/v16 single-variable comparison is
what established the Localize identity result; the earlier failures alone could not.

## Walk archive anatomy

A usable archive is more than a `Graph` protobuf. The observed package can contain:

- `graph`;
- one file per referenced waypoint snapshot;
- one file per referenced edge snapshot;
- one public Autowalk `Walk` mission;
- embedded action images;
- optional `autowalk_metadata`, readme, and topography sidecars.

The observed public `Walk` wire fields include global parameters, playback mode, repeated Elements,
repeated Docks, mission/map display names, the Walk ID, choreography, interrupts, and an optional
private metadata envelope. Sidecar presence and outer ZIP-root layout varied across valid tablet
and Orbit exports, so neither should be treated as a universal Dock/Action requirement.

Offline validation has two distinct jobs:

- structural closure: protobuf parsing, graph references, snapshot files, routes, Dock targets,
  image files, and ID-membership checks;
- semantic preservation: after reversing new identities, retained public and unknown payloads must
  equal their source payloads.

Neither predicts server-side materialization on its own.

## Identity and recording model

Several values called “recording” or “ID” belong to different layers:

| Value | Role | Can the offline exporter assign it? |
| --- | --- | --- |
| `Walk.id` | Public Autowalk container identity | Yes |
| `Element.id` | Public Walk Element / SiteElement conversion identity | Yes |
| waypoint and snapshot IDs | GraphNav object identity | Yes, when cloning |
| waypoint `session_name` | Display/provenance label in client metadata | Yes |
| snapshot `recording_started_on` | Association key grouping snapshots by recording start | It can be rewritten only with corresponding fresh snapshot IDs and audit evidence |
| server recording resource UUID | Fleet-manager-owned recording object | No public Walk field was found for assigning it |

Changing only `session_name` changes a label, not the server recording UUID. Reusing the same
`recording_started_on` groups can cause a new probe to overlap a recording association already seen
by Orbit. The controlled probes therefore used disjoint snapshot identities and disjoint recording
start groups. This is test hygiene, not an assertion that a timestamp is the server recording ID.

`robot_id` and `client_id` describe real capture provenance and were retained. Replacing them with
synthetic values would falsify provenance rather than create a clean recording identity.

## Dock and Action materialization

The later structurally corrected failed archive did contain public Dock and Action protobufs. Their
absence in Orbit was caused by the enclosing Walk conversion failing, not by silently missing
top-level fields.

The successful Dock profile retained all of the following:

- one public `Walk.Dock` with its physical dock number;
- docked and prep waypoint references;
- the prep navigation Target and prompt behavior;
- Graph anchors for referenced waypoints;
- a matching anchored Dock WorldObject;
- Dock/fiducial sensor evidence in the relevant waypoint snapshots.

The Dock raw submessage was unchanged between one failed probe and the first successful minimal
probe. This ruled out “copy a different Dock” as the fix.

The successful DAQ profile retained its Target, ActionWrapper, capture configuration, capability
descriptors, failure behavior, battery monitor, duration, and embedded images. The required
identity change was to issue a current Element ID and rewrite both DAQ membership fields to the
current Walk/Element identities.

The operator later executed this minimal mission on the robot and confirmed that its PTZ capture
completed. Localize and Sleep were not operational requirements for that Walk, so this DAQ-only
archive is the current immutable golden artifact. This runtime evidence does not cover physical
Dock return/charging, result association, other Action kinds, or re-export equivalence.

## Connectivity cleanup

Polygon selection can include a large operational component plus many small local-frame remnants.
“Remainder” does not mean another valid route. In the investigated map, nearly all remainder
waypoints were unanchored, and the only anchored singleton had no Action or other protected
dependency.

The cleanup controls are therefore opt-in and dependency-aware:

- `--exclude-unanchored-waypoints` removes waypoints whose display coordinate could be derived only
  in an unanchored local frame, before halo expansion;
- `--exclude-dependency-free-components` removes non-largest components only when they contain no
  Action, Dock, panorama state, or other protected dependency;
- exact excluded IDs, component sizes, and protected components remain in plan/audit records.

The UI checkboxes and CLI flags must produce the same saved plan. Cleanup never mutates the source
Map and must never remove a dependency-bearing component just because it is small.

## Orbit field-3 edge boundary

Observed SiteEdge field 3 contains Orbit-side edge state that the public GraphNav `Edge` does not
fully represent. In particular, environment settings such as **Allow travel along this edge** did
not reliably survive Walk transport.

Field-3 edges remain useful for coordinate propagation, polygon selection, halo expansion, and
connectivity analysis. The export decision is explicit:

- exclude them from the bundle/Walk by default and recreate their environment/travel settings in
  Orbit; or
- include their public GraphNav annotations experimentally, then still verify and reapply the
  Orbit settings.

Excluding these edges can split one selected coordinate network into many Walk components even
though the waypoints and all other selected edges remain. The editor and audit therefore report
both selection connectivity and post-policy Walk connectivity. An operator must review this before
import; a structurally valid archive can still be operationally disconnected.

## Triggered AI inspection boundary

The initial AI warning was data-driven, not invented from the current UI. The backup contained a
separate waypoint-less SiteElement with a private parent link to an ordinary capture Element, even
though the operator did not expect a current AI inspection on the Map.

The public Walk `Element` schema has no equivalent field for that private parent-trigger relation.
Normal export therefore fails closed instead of silently dropping the record or pretending it is
an ordinary Action. The investigated record was independently confirmed to be incomplete/orphaned,
so the plan used an exact ID plus a written reason to omit only that record. The plan, audit, and
clone manifest retain the omission.

The experimental `fold-into-parent` mode can place a public network-compute request in the parent
DAQ Element only under strict payload checks. It does not preserve the private trigger relationship
and is not a supported triggered-inspection migration path.

## Safe import workflow

1. Prepare from a read-only backup and inspect the complete inventory.
2. Select the polygon and halo.
3. Review unanchored waypoints and disconnected components; enable cleanup only with dependency
   protection.
4. Choose the field-3 edge policy and review resulting Walk connectivity.
5. Resolve every triggered inspection explicitly; default to blocking export.
6. Build under a new clone namespace when an independent Map must coexist with earlier probes.
7. Export with fresh UUIDv4 Walk/Element identities and closed DAQ membership.
8. Run `audit`, bundle validation, Walk validation, ZIP CRC, and source-archive hash checks.
9. Import only into a disposable same-version environment.
10. Require materialized Map, mission, expected Actions, and available Dock. Recording visibility or
    upload completion alone is a failure.
11. Reapply and verify field-3 edge environment/travel settings in Orbit.
12. Verify runtime for the exact intended profile. The minimal DAQ control passed mission playback
    and PTZ capture; physical Dock use and re-export remain separate gates.

## Remaining work

- enforce the Orbit-targeted UUIDv4 Walk Element policy in the public exporter rather than only in
  private experiment builders;
- reject or strongly warn on UUIDv5 navigation-only Localize Elements during validation;
- verify the public CLI's full recording-compatible profile with the same single-variable rigor;
- test physical Dock return/charging and expand runtime coverage beyond the minimal PTZ DAQ profile;
- verify inspection-result association for the cloned Action;
- re-export a successful imported Walk and compare normalized semantics;
- repeat compatibility tests before claiming support for another Orbit/robot/tablet version;
- test Sleep UUIDv5 only if its exact compatibility boundary is needed.

Detailed private evidence, hashes, identity mappings, archive names, and operator receipts remain
under ignored `output/analysis/` files and must not be committed or shared.
