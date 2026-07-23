# Orbit-native recording move workflow

For the concise operator procedure, start with the
[Orbit-native map split workflow](workflows/orbit-native-map-split.md). This document retains the
detailed investigation, backup-level evidence, and rollback analysis.

## Purpose and current evidence

This workflow partitions an existing edited Site Map without synthesizing a copied recording or
changing GraphNav data. It uses Orbit's own recording assignment UI to move an existing recording
from one Site Map to another in the same Orbit instance, then reconciles map-owned edits against an
immutable backup.

This is the recommended operator-assisted same-instance split workflow for the verified Orbit 5.1.8
environment. It remains alpha and version-bound: it is not a vendor-published migration feature and
must be requalified after an Orbit upgrade. The current investigation has established the
following:

- the source Site Map's 54 selected recording IDs exactly match the 54 recording IDs stored in the
  backup Site Map record;
- every UI row can be joined to exactly one backup recording group using recording start time,
  recording-session label, and waypoint count;
- the UI tooltip exposes the exact server recording ID, start/end time, waypoint count, and robot;
- the backup contains 4,733 unique waypoint IDs and 4,733 unique waypoint-snapshot IDs for those
  recording groups;
- manual and edited SiteEdge state is map-owned rather than recording-owned and must be reconciled
  explicitly after assignment. A missing SiteEdge wrapper does not by itself prove that the
  connection disappeared: Orbit can fall back to the raw recording edge while losing the
  SiteEdge's resolved settings. A backup wrapper has no provenance proving whether a value came
  from an operator edit, a bulk operation, or Orbit's own Site Map normalization.

The controlled Orbit 5.1.8 pilot established that assigning the same recording to another Site Map
retains its exact waypoint IDs. The in-page assistant can therefore use the live waypoint-ID set as
the identity gate for graph-only reconciliation. A post-move backup is still required to verify
waypoint-snapshot payload hashes or map-owned wrapper settings. Do not generalize either invariant
to another Orbit version until the adapter is revalidated.

Private map names, IDs, hostnames, recording IDs, waypoint IDs, coordinates, and screenshots belong
only in ignored `output/analysis/` evidence. They must not be committed or published.

## Identity model

| Object | Stable key used by the workflow | Role |
| --- | --- | --- |
| Orbit Site Map | exact server map ID plus operator-checked display name | source/target allowlist |
| Orbit recording | exact 32-character tooltip ID | atomic move unit |
| Backup recording group | `(recording_started_on, session_name)` plus waypoint count | UI-to-backup join |
| Waypoint | exact case-sensitive GraphNav waypoint ID | edge endpoint and invariant |
| Waypoint snapshot | exact snapshot ID referenced by the waypoint | recording-data invariant |
| Edge | canonical unordered endpoint pair, with stored direction retained as payload evidence | topology diff key |
| SiteEdge edit | map ID plus endpoint pair and wrapper state | add/delete/update reconciliation |
| Action, Dock, panorama state | exact record ID and referenced waypoint IDs | dependency/blocker report |

Names, coordinates, and nearest-neighbor geometry are evidence only. An agent must never use them
as the primary identity when an exact ID is available.

## Immutable inputs and generated artifacts

Use these conceptual artifacts for every run:

| Artifact | Contents | Mutability |
| --- | --- | --- |
| `B0` | source Orbit backup and SHA-256 before any move | immutable |
| `catalog.json` | recording groups, exact waypoint/snapshot sets, dependencies, edges | generated read-only |
| `partition-plan.json` | source/target map allowlist and exact recording IDs chosen by the operator | reviewed, then frozen |
| `move-journal.json` | expected state, every UI action, observed state, and rollback state | append/update after each transition |
| `B1` | optional backup after assignment for payload/wrapper audit | immutable evidence |
| `edge-plan.json` | desired-versus-observed add/delete/update operations for both maps | reviewed, then frozen |
| `B2` | final backup after reconciliation | immutable evidence |

Backups, journals, catalogs, generated Walks, and evidence screenshots are private and ignored by
Git. The source backup and workspace are never edited.

## Preflight catalog and partition rules

For each waypoint in `B0`, read its referenced `WaypointSnapshot.recording_started_on` and the
waypoint's `annotations.client_metadata.session_name`. Group waypoints by that pair and compute:

- exact waypoint and snapshot ID sets and deterministic hashes;
- active internal and boundary edges by source type;
- active user-request/manually created edges;
- field-3 SiteEdge wrappers and field-4 tombstones;
- Area callback edges and other edge annotations;
- Actions, Dock references, panorama state, map-layout control points, and triggered records.

Join each backup group to one Orbit recording row using start time, session label, and waypoint
count, then read the exact recording ID from its tooltip. Fail closed if the join is missing,
ambiguous, or if the resulting ID set differs from the Site Map's backup recording IDs.

A partition plan selects recording IDs, never waypoint IDs individually. Classify each desired
edge after the selection:

- **target internal** — both endpoints move; eligible for preservation or recreation in target;
- **source internal** — neither endpoint moves; must remain in source;
- **cut/boundary** — exactly one endpoint moves; cannot exist in either separated map and must be
  reported as an intentional loss;
- **cross-target** — endpoints are assigned to two different targets; same treatment as a cut.

The first identity pilot should have no manually created edges, tombstones, field-3 state, Areas, Actions,
Docks, panorama state, or layout control points. A second, separately reviewed pilot may exercise
one internal manually created edge after identity stability is established.

## State machine and UI transaction

Treat a move as a journaled state machine:

```text
source-only -> unassigned -> target-only -> verified -> reconciled
                  |              |
                  +---- rollback-+
```

The normal UI transaction is:

1. Confirm Orbit version, low-disk condition, source/target map IDs, display names, and that neither
   map has unsaved edits.
2. In the source map's **Select recordings** dialog, locate the selected row by its exact tooltip
   recording ID. Do not rely on name or visible order.
3. Move only that allowlisted row to **Available**, apply the dialog, and save the source map.
4. Reopen the source dialog and verify the recording ID is no longer selected.
5. In the target map, locate the now-available row by the same tooltip ID, move only that row to
   **Selected**, apply, and save.
6. Reopen both dialogs and verify `source-only -> target-only`. Record UI counts and screenshots.
7. Verify the target shows the expected waypoint count. If exact waypoint IDs are exposed by the
   UI, compare the set immediately; otherwise stop before edge edits and obtain `B1`.

Each save is a separate server mutation and journal entry. UI automation may perform one allowlisted
mutation at a time; it must re-read the resulting state before continuing.

Orbit 5.1.8 UI details observed during the controlled pilot:

- dialog **Apply** changes the current Site Map draft; the top-level **Save** commits it;
- the recording-row action beside the info control removes that recording from the draft; it is not
  a zoom-to-fit action, so automation must not use unlabeled row icons;
- switching Site Maps with a recording-assignment draft opens a browser confirmation dialog that
  can also block automation; do not navigate until the top-level save has completed and the current
  membership has been re-read;
- after a Site Map switch, a late anchoring result from the previous map can leave the current map
  looking dirty even though server membership is already correct. If Save remains enabled without
  completing and Orbit reports that anchoring belongs to a different Site Map, cancel only that
  stale draft, reload the current map, and re-read recording membership before applying anything;
- use **Ctrl+A** with the waypoint-selection tool to verify waypoint count, then `E` followed by
  **Ctrl+A** to select all edges and read their exact endpoint IDs; these are read-only checks;
- do not equate the number of `graph_nav/site_edges` wrappers with Orbit's displayed edge count.
  In the verified source map, Orbit displayed 3,845 edges while the current adapter reconstructed
  only 3,525 SiteEdge wrappers. Raw `graph_nav/edges` records participate in the effective graph.

## Live identity gate and optional B1 payload audit

For graph-only reconciliation on the verified Orbit version, the read-only extension must prove all
of the following before it emits any pair:

- the current Site Map ID is the exact map open in Orbit;
- every current waypoint ID exists in `B0`;
- the live edge state resolves entirely within the current waypoint set;
- the desired graph is induced only from B0 edges with both endpoints in that set;
- B0 edges with exactly one endpoint in the set are reported only as boundary cuts.

Obtain a fresh B1 and additionally require all of the following when snapshot identity, wrapper
settings, or a formal backup audit matters:

- source recording set is `B0 source - moved IDs` and target recording set is exactly the moved IDs;
- target waypoint ID set equals the expected `B0` group set;
- every target waypoint references the same waypoint-snapshot ID as `B0`;
- every referenced snapshot exists and its deterministic payload hash is unchanged;
- no waypoint or snapshot from an unrelated recording entered the target;
- the source and target Site Map records remain distinct.

Any mismatch in the selected gate is an abort. Do not guess an ID mapping. Reassign the recording to the source using the
same exact ID only to recover membership, then obtain `R1` and compare it with `B0`. Reassignment is
not evidence that SiteWaypoint wrappers or SiteEdges were restored.

## R1 round-trip gate

If a pilot recording is returned to the source, treat the resulting backup as `R1`. Require a
set-based comparison because Orbit may append the returned recording and waypoints at the end of
their Site Map lists. Verify separately that:

- source recording and waypoint ID sets equal `B0`;
- candidate raw waypoint and waypoint-snapshot payloads equal `B0`;
- every expected SiteWaypoint wrapper still exists and its payload equals `B0`, or its raw
  fallback is compared field by field and the difference is explicitly classified;
- the raw edge set, SiteEdge override set, and effective Orbit-visible edge set are compared
  separately; every shared SiteEdge wrapper must equal `B0`;
- Actions, Docks, Areas, panorama state, map layout, and other scoped dependencies equal `B0`.

UI membership is not sufficient. The controlled Orbit 5.1.8 pilot restored recording and waypoint
membership but omitted two candidate SiteWaypoint wrappers and three incident SiteEdge wrappers.
Direct Orbit selection subsequently proved that all three connections still existed through raw
edge fallback. Their wrapper-level edits did not survive.

## Edge reconciliation

Recordings do not encode the final edited Site Map. Build desired graphs from `B0`, then compare
them with `B1` independently for source and target:

```text
ADD    = desired endpoint pairs - observed endpoint pairs
DELETE = observed endpoint pairs - desired endpoint pairs
UPDATE = shared endpoint pairs whose public annotations or map-owned settings differ
```

`ADD` includes every genuinely missing B0 connection whose endpoints belong together in the final
partition, not only manually created edges. Before emitting `ADD`, check for an identical raw edge:
the pilot's odometry, localization, and small-loop-closure connections remained visible after their
SiteEdge wrappers disappeared. Those cases are `UPDATE`, because Orbit fell back to the raw edge.
`DELETE` is equally important: attaching a recording may expose an original edge that the operator
deleted in the edited source. `UPDATE` includes public edge annotations, Areas/callbacks, and
observed private field-3 environment/travel state that the native assignment did not carry.

Apply operations only when both exact endpoint IDs exist in that map. Preserve the stored direction
and transform as payload evidence even though GraphNav treats the connection as traversable in both
directions. A cut edge is never recreated across two Site Maps.

After every small batch, re-read the UI. Obtain `B2` and require exact desired/observed agreement for
both maps before declaring success.

### Graph-only waypoint-pair guide

When only topology matters, the local reconciliation command implements the endpoint part of this
procedure without writing to Orbit:

Before moving any recording, freeze an auditable B0 inventory directly from the source backup:

```bash
uv run spot-map-forge graph-baseline /path/to/B0.tar \
  --map '<original-map-name-or-id>' \
  --out workspace/original-map/graph-baseline.json
```

This inventory contains the complete effective graph, including raw fallbacks, active SiteEdge
overrides, SiteEdge-only connections, edge-source classification, and every deletion tombstone.
The backup does not identify whether a tombstone came from a human deletion or Orbit
normalization, so all tombstones are preserved by exact endpoint IDs. The workspace-oriented
`edge-inventory` is useful for waypoint matching but is not a replacement for this complete B0
inventory.

After the recording move, open the resulting source or target Site Map in Orbit, load
`graph-baseline.json` in the extension, and run **Refresh**. No B1 file is required for this live
graph-only comparison. The extension reads the current waypoint and edge state through its narrow
read-only Orbit 5.1 adapter and constructs the guide in memory.

If a fresh B1 backup is available for audit purposes, the existing offline command can still create
an equivalent prebuilt guide:

```bash
uv run spot-map-forge reconcile-graph workspace/original-map \
  /path/to/B0.tar /path/to/B1.tar \
  --before-map '<original-map-name-or-id>' \
  --after-map '<source-or-target-map-name-or-id>' \
  --out workspace/original-map/map-reconciliation.json
```

Load [`extension/orbit-graph-repair`](../extension/orbit-graph-repair/README.md) as an unpacked
extension in the same `chrome-tablet-proxy` profile used to access Orbit. Use **Load B0 baseline**
for the live path, or open the exact `--after-map` and use **Import prebuilt guide** for the optional
B1 path. The standalone `serve --reconciliation` screen is only an offline diagnostic fallback;
the operator workflow stays in Orbit.

The baseline must come from the original `B0` Site Map. Run the live comparison once for each
post-move source or target map. For the current Orbit waypoint set, the extension constructs the
desired induced subgraph from the effective `B0` topology:

```text
effective topology = (raw recording edges union active SiteEdges) minus SiteEdge tombstones
desired topology   = effective B0 edges whose two endpoints exist in the current Orbit map
CONNECT            = desired topology minus live Orbit topology
DELETE             = live Orbit topology minus desired topology
```

The extension focuses one exact waypoint pair at a time with Orbit's own two-waypoint fit action.
`CONNECT` pairs use a dashed turquoise line and `DELETE` pairs use a solid red line over Orbit's
canvas; A/B markers use the current Orbit anchor positions rather than the backup projection. The
two endpoint IDs, names, and recording-session labels remain visible beside the Orbit map. A
`DELETE` pair is labeled `resurrected_deleted_edge` when the same endpoints have a `B0` SiteEdge
tombstone. All edges with only one endpoint in the selected map are counted as intentional
partition cuts and never become an action.

Version 0.8 additionally compares public `Edge.annotations` on every shared edge. This includes
edge-scoped `spot-crosswalk` callbacks, mobility parameters and override mask, stairs, direction,
path-following, ground, alternate-route and directed-exploration behavior, cost, and audio/visual
settings. A confirmed UPDATE uses Orbit's native `updateSiteEdges` draft, preserves the live
identity/transform/snapshot/source/wrapper, verifies exact read-back, and creates one Undo step.
Stored direction, source, current settings, endpoints, and map ID are stale-state guards; any
mismatch stops the complete batch. Private wrapper fields and SiteWaypoint payloads remain outside
this restore. The extension treats a raw edge as a valid connection but emits UPDATE if its public
profile differs from B0.

If a result map legitimately contains recordings added after B0, their waypoint IDs are absent from
the baseline by definition. The extension counts those exact IDs and every incident edge as
`ignored extra scope`; it does not emit CONNECT, DELETE, or UPDATE actions for them. Only edges whose
two endpoints are both in B0 participate in restoration.

The in-page focus adapter is intentionally narrow and version-sensitive. It reads the loaded
waypoint anchors and dispatches Orbit 5.1's UI-only
`mapDisplay/updateNeedsZoomToWaypoints` action; it never calls a REST endpoint. If that private UI
action changes after an Orbit update, focus fails closed while the pair list and **Copy IDs** remain
usable. Revalidate the adapter after every Orbit upgrade before operational use.

## Dependencies that are not edge replay

The following are separate migration decisions and must never be silently counted as preserved:

- Actions/SiteElements, Walk missions, schedules, triggered AI inspections, and inspection history;
- Dock records and Dock prep targets;
- Site View panorama state and historical imagery;
- map-layout/floor-plan control points;
- map-level Areas and non-edge Area configuration (edge-scoped public callbacks are restorable);
- field-3 private SiteEdge settings;
- anomalies, results, run events, and capture history.

If a selected recording references one of these, the catalog must mark it as a blocker or require a
dedicated, evidence-backed sub-workflow.

## Abort and rollback rules

Stop immediately when any of these occurs:

- source/target map ID or display name differs from the allowlist;
- an unexpected recording is selected or becomes unassigned;
- Orbit reports an error, the page reloads unexpectedly, or a Save remains pending;
- waypoint/snapshot identity changes or a referenced snapshot is missing;
- observed edge state cannot be represented by the planned add/delete/update operation;
- storage pressure prevents creation of the required verification backup.

Recording reassignment is only a **membership rollback**: remove the exact recording ID from target,
save, reassign it to source, save, and verify membership. It is not an edit-state rollback. Orbit
5.1.8 did not restore the pilot recording's SiteWaypoint wrappers or its three incident SiteEdge
override wrappers. It did expose all three underlying raw connections again.

An exact rollback therefore requires either a separately approved full `B0` restore or a verified
replay of every missing/changed map-owned edit from `B0`. Do not recreate a connection that Orbit
already exposes through its raw edge; reapply only the lost settings. A full restore may revert
unrelated post-`B0` operational data, while UI editing may not expose every original annotation.
Present both consequences to the operator and never select one automatically.

## Automation boundary

Version 1 should use only read-only backup analysis plus Orbit's official UI. The published Orbit
REST API does not document Site Map recording-assignment or SiteEdge-edit endpoints. Undocumented
internal requests are version-sensitive, may violate support/licensing expectations, and are not a
stable automation contract.

An eventual agent or skill should therefore expose four explicit phases:

1. `analyze` — produce catalog and candidate scores without network writes;
2. `plan` — render the recording partition and cut/edit/dependency report for human approval;
3. `move-one` — perform one exact-ID UI transaction with dry-run as the default;
4. `verify/reconcile` — validate `B1`, generate edge operations, and execute only approved batches.

No phase should infer authority for the next. Server writes remain separate commands, exact-ID
allowlists are mandatory, and every operation must be idempotently checkable from current state.

## Current controlled pilot

Offline scoring found a two-waypoint, four-second recording with one internal recorded edge and two
ordinary boundary edges. It has zero manually created edges, tombstones, field-3 edges, Area callbacks,
Actions, Dock references, panorama states, or layout control points. Its exact tooltip recording ID
is present in `B0` and its UI start time/session/count join is unique.

The source-to-target half of the live pilot passed: Orbit displayed the same exact recording ID,
two waypoints, one internal edge, and the two expected exact waypoint endpoint IDs in the target.
The target was then saved empty again. A clean source reload showed all 54 recordings selected,
the candidate present exactly once in **Selected** and absent from **Available**, and the top-level
**Save** disabled. The earlier unsavable dirty state was a stale client draft caused by a late
target-map anchoring result.

The `R1` backup initially appeared to show topology loss because the existing adapter reconstructs
edges only from SiteEdge wrappers: it counted 3,528 wrappers in `B0` and 3,525 in `R1`. That was an
adapter limitation, not proof of three missing Orbit connections. The raw odometry, localization,
and small-loop-closure edge records remained byte-identical in `R1`. Direct Orbit 5.1.8 checks then
selected all three exact endpoint pairs, proving that Orbit falls back to those raw edges.

What did not survive was SiteEdge wrapper state. The localization connection reverted from the B0
wrapper's medium velocity to raw **Slow**; the odometry connection reverted from medium to raw
**Fast**; and the small-loop-closure connection lost `internal_alert` and the disabled
alternate-route setting, showing **(none)** and alternate-route finding enabled in Orbit. This does
not by itself prove that a human edit was lost. Across B0, all 3,502 active SiteEdge wrappers with
a raw counterpart differed from that raw payload; 1,703 edges followed the same Slow-to-Medium
pattern and 60 followed Fast-to-Medium. The velocity differences are therefore likely systematic
Site Map normalization. Alert and alternate-route values may be operator, bulk, or system state;
the backup has no author/change provenance to distinguish them.

The two candidate SiteWaypoint wrappers also disappeared, but the selected waypoints retained
their exact names and IDs; their only decoded fallback difference was an explicitly encoded
protobuf-default lost-detector value. All 26 classified manually created edges elsewhere and every shared
SiteEdge wrapper remained unchanged.

A complete member-by-member hash comparison found no other payload changes: the only shared files
that changed were the source Site Map and the two expected aggregate indexes; the only added file
was the empty test map, and the only removed files were the two SiteWaypoint wrappers and three
SiteEdge override wrappers described above. The pilot therefore proves identity and candidate
connection retention, but disproves lossless restoration of map-owned edits.

The analyzer now models raw-edge fallback, SiteEdge overrides, tombstones, and public annotation
profiles. A manual CONNECT draft and an odometry Archive tombstone were created and undone through
Orbit 5.1.8's native editor path with exact endpoint and history verification.

The settings adapter subsequently completed a production-scale staged restore on a result map:

- 112 crosswalk-bearing profiles created one native unsaved draft and one Undo step, then the
  operator reviewed and saved it;
- the remaining 2,316 public profiles created a second native unsaved draft and one Undo step, then
  the operator reviewed and saved it;
- no stored-direction block occurred, and the extension reported zero pending settings after the
  second draft;
- 8 CONNECT items and 6 intentional boundary cuts remained visibly separate from settings work.

This closes the live public-settings draft gate for that version and scale. SiteWaypoint edit
migration, private wrapper reconstruction, cross-version compatibility, and a final backup proof
remain separate gates. The public support level is therefore **supported alpha on Orbit 5.1.8**,
with mandatory B0 reconciliation and operator-controlled Save.
