# Architecture and data guarantees

## Workflow separation

The repository has two compatibility boundaries:

1. **Recommended same-instance workflow** — the offline tool builds an immutable B0 topology and
   settings baseline; the Orbit Site Map Assistant compares it with a live post-move Site Map and creates
   native unsaved editor drafts. Orbit owns recording assignment, validation, Undo/Redo, and Save.
2. **Experimental offline clone workflow** — the Python package selects and remaps backup objects,
   builds an offline clone, and packages a public Autowalk archive for a disposable import test.

These workflows share the read-only backup adapter and topology analysis, but they must not be
presented as interchangeable:

- the recommended path preserves native recording/waypoint identity by moving recordings;
- the experimental path creates or probes a new transport/object identity and has separate
  lifecycle and history risks.

See the [workflow documentation index](README.md) before using the lower-level architecture below.

## Boundary

The experimental offline clone path has three layers:

1. **Offline forge** — inventory, final-graph reconstruction, polygon selection, cloning, asset
   staging, auditing, and structural validation.
2. **Backup adapter** — a version-sensitive reader for observed fleet-manager backup records.
3. **Autowalk transport adapter** — conversion of an offline clone to the public `.walk.zip`
   interchange shape.

The backup `.tar` is the only required operational input. A pre-existing edited Walk may be used
as a local development fixture, but it is never required by the production workflow.

All network and product lifecycle operations remain outside the CLI. No offline command edits a
recording assignment, source Site Map, robot, or fleet-manager instance.

## Final graph reconstruction

For a selected Site Map:

- map membership comes from the Site Map record;
- a site-level waypoint wrapper is preferred over the raw waypoint record;
- edges come from the site-level edge collection rather than recording-session edges;
- site-edge wrappers with observed field 3 are retained for coordinate propagation and waypoint
  selection because their embedded public Edge still carries useful topology and annotations;
- site-edge wrappers with observed field 4 are excluded as inactive/tombstoned records, including
  wrappers that also have field 3;
- referenced waypoint and edge snapshots are resolved by ID;
- map-layout control points seed a workspace-only coordinate projection;
- edge transforms propagate that projection for polygon selection;
- layout data is never injected into the serialized GraphNav clone;
- components that cannot reach a layout control point are marked unanchored.

Using site-level edge records preserves edits that are not owned by a recording session, including
manual links, loop closures, site-specific annotations, and edges whose public annotations disable
directed exploration or alternate-route finding. Orbit 5.1.8 public Walk import did not recreate
the private field-3 SiteEdge state during verification. Plans therefore record an explicit transport
choice: exclude those edges by default, or experimentally include their public Edge annotations.
In either mode, operators must verify the listed edges and reapply environment/travel settings in
Orbit after import; excluded edges must first be recreated there. Field-3 edges always remain
available to the offline selector so their connected waypoints can be included. This behavior is
based on observed archive semantics and is not a vendor-published backup schema.

## Zone selection and halo

- `core_waypoint_ids` are inside or on the polygon.
- `halo_waypoint_ids` are graph neighbors added by hop count.
- optional unanchored cleanup runs before halo expansion so hidden local-frame remnants cannot
  seed additional selections;
- optional disconnected-remnant cleanup removes only non-largest components with no action, dock,
  or panorama-state dependency;
- an edge is retained only when both endpoints are selected;
- core actions are selected by default;
- halo actions require an explicit opt-in;
- a complete dock is selected only when its docked waypoint and every prep-target waypoint are
  present;
- boundary-cut docks are reported and skipped.

Halo waypoints soften a geometric cut at a graph junction. They do not repair an otherwise
disconnected selection and should remain small.

## Identity model

Copy mode generates deterministic UUIDv5 mappings for:

- waypoint IDs;
- waypoint snapshot IDs;
- edge snapshot IDs;
- ordinary action/SiteElement IDs;
- triggered AI inspection IDs and their parent references in the offline bundle;
- SiteDock record IDs;
- the exported Walk ID.

The exported Walk ID is derived from the validated archive/display name and source Site Map ID.
Using a different `--name` produces a different deterministic Walk ID without changing the cloned
GraphNav object IDs in the bundle.

When two revisions must coexist as independent Orbit maps, `build --clone-name <new-name>`
overrides the plan's zone name as the deterministic clone-ID seed. Rebuilding from the same audited
selection then gives every cloned waypoint, waypoint snapshot, edge snapshot, SiteElement, and
SiteDock record a disjoint identity while preserving topology and payload content. Export naming
alone cannot provide this separation.

GraphNav edge identity is defined by its remapped endpoint pair. Sensor, fiducial, and physical
dock numbers are not object identities and remain unchanged.

Source mission and SiteWalk IDs are never reused. Identity-preserving partition or move semantics
are not implemented because the public product interface does not expose the required lifecycle
operation.

### Experimental Orbit-native-shaped mode

`build --identity-mode orbit-native` remaps the same selected objects as copy mode while changing
their output representation. Waypoint IDs retain the observed word-word prefix and receive a new
22-character Base64-style suffix. Waypoint snapshot and edge snapshot IDs retain their observed
`snapshot_` and `edge_snapshot_id_` prefix families. Walk, SiteElement, and private SiteDock record
IDs carry RFC 4122 UUID version-4 and variant bits.

The mappings remain deterministic under the configured namespace and `--clone-name`; the UUIDv4-
shaped values are therefore not claims that a robot or Orbit allocated those records. A new clone
name produces a fully disjoint probe, while the manifest preserves every source-to-output mapping
for audit. Graph topology, sensor snapshots, action payload semantics, physical fiducial numbers,
and physical Dock numbers are unchanged.

This mode exists to isolate ID representation as one Orbit import variable. It is not a supported
replacement for recording on a robot, and offline validation cannot establish that Orbit will
materialize public Walk Docks or Elements as server-side resources.

### Experimental shared-identity mode

`build --identity-mode preserve` constructs a different experiment from normal copy mode. It keeps
waypoint, waypoint-snapshot, edge-snapshot, SiteElement, and source SiteDock record mappings as
identity mappings. Edge identity is also retained implicitly because a GraphNav edge is identified
by its endpoint waypoint pair. Anchor IDs and navigation targets continue to reference those same
waypoints.

The exported `Walk.id` is always new. Reusing it would identify the transport as the existing Walk
rather than create a disposable container. A fleet-manager recording ID is not present in the
public Walk and remains server-assigned at import. Public `Dock` has no SiteDock record UUID, so the
source record ID is auditable in the bundle but not transported by the public archive.

Preserve mode copies unchanged snapshots byte-for-byte and leaves SiteElement envelopes unchanged
when both their element and waypoint identities are retained. Export-time recording-session
relabeling is rejected because it would change metadata on a shared waypoint identity. The mode
does not transfer Run, RunEvent, RunCapture, anomaly, or Site View history; whether Orbit associates
existing history with a reused SiteElement is an import-time research question.

For a native tablet `.walk` directory, `reissue-walk` is narrower still. It copies every source
file byte-for-byte except the public mission payload and replaces only top-level `Walk` wire field
8 (`id`). It deliberately avoids protobuf reserialization so unknown top-level fields and the raw
Element/Dock submessages remain unchanged. Embedded DAQ `mission_id` values retain source mission
provenance; only the new transport `Walk.id` changes. This intentional mismatch is an import-time
experiment, not a claim of independent result-history ownership.

The optional graph-only control removes top-level Walk fields 5 (Elements) and 6 (Docks) while
also replacing field 8. It preserves the Graph and all source sidecars exactly. This control is
expected to distinguish Orbit's SiteMap/GraphNav duplicate-data gate from SiteElement conflicts;
it is not expected to bypass an all-objects-already-exist policy by itself.

After the graph-only control reproduces the duplicate-data error, the navigation-only sentinel
probe retains that control but inserts one new skipped Element with no action. Its target is copied
from an observed source Element, so no new waypoint or edge is introduced. This distinguishes an
all-objects-duplicate policy that counts SiteElements from one based only on GraphNav/recording
ownership.

If that probe is also treated as entirely duplicate, the disconnected-waypoint sentinel adds one
new Waypoint, WaypointSnapshot ID, and matching Anchor ID while retaining every original GraphNav
object. No edge is added, so the original topology is not extended. The cloned snapshot retains its
source recording metadata; therefore another duplicate-data result is a deliberate stop condition
indicating that a real new recording—not more UUID mutation—is needed.

## Ordinary action conversion

The observed SiteElement record is a private envelope, but selected embedded fields are public
Autowalk messages:

- the action payload is parsed as `bosdyn.api.autowalk.Action`;
- the wrapper is parsed as `ActionWrapper`;
- exact source action and waypoint identity tokens are rewritten recursively;
- unrelated and unknown wire fields are retained;
- waypoint-relative body goals and navigation distance are copied from the observed direct fields;
- the wrapper pose is used only as a fallback when no direct body goal is present;
- DAQ and alignment images are matched to the corresponding public image slots;
- DAQ `element_id` metadata is rewritten to the clone Element ID.

Observed `mission_id` values are retained as source provenance, not treated as current Walk
membership. Existing mission order is intentionally not cloned.

### Observed minimal Orbit materialization profile

A controlled same-version import established one narrower successful profile. The Graph, snapshots,
Dock raw submessage, global settings, and opaque metadata were retained from an earlier archive.
The mission kept one observed DAQ Element as its first and only Element, issued fresh UUIDv4 Walk
and Element IDs, and rewrote DAQ `mission_id` and `element_id` metadata to those identities. Orbit
then materialized the Walk mission, DAQ action, and available Dock in its UI.

The experiment did not change the GraphNav waypoint or snapshot IDs, so UUIDv5 Graph identity is
compatible with this minimal SiteWalk conversion path. Later controls restored the actionless
Localize and Sleep Elements on the full Graph. The all-UUIDv4 Element profile materialized; an
otherwise equivalent archive with only the Localize Element changed to UUIDv5 completed upload but
did not materialize its Site Map. A separate UUIDv5 DAQ profile succeeded. Orbit therefore has an
Element-type-specific conversion boundary: UUIDv5 Graph identities and DAQ IDs can be accepted,
while the observed navigation-only Localize path requires a UUIDv4 Element ID.

An operator may explicitly request one synthetic public Sleep Element during export. It is never
classified as a copied SiteElement: the export report records its source/cloned waypoint IDs,
duration, deterministic Element ID, and insertion position. Its navigation target uses the same
observed public and opaque target profile as copied Elements.

## Recording-session labels

GraphNav waypoints retain public `ClientMetadata`, including the recording-time `session_name`.
With no override, export preserves those labels. `--recording-name` changes only the exported
waypoints' `annotations.client_metadata.session_name`; it does not modify the clone bundle,
waypoint identity, geometry, snapshot identity, recording timestamp, robot identity, or client
identity.

This label is not a fleet-manager recording object or recording UUID. The backup adapter may list
source recording IDs for audit provenance, but it does not have a supported recording-to-waypoint
lifecycle operation. Any new server-side recording identity remains an import-time product
decision outside the offline CLI.

## Triggered AI boundary

Observed triggered AI inspections are separate, waypoint-less SiteElements with a private parent
trigger reference. The offline bundle can preserve and remap each inspection and its parent
reference, but the public Walk `Element` has no equivalent parent-trigger field.

Normal export therefore fails when a selected zone contains a triggered AI inspection. The
experimental `fold-into-parent` mode moves the public network-compute request into its capture
parent, but it cannot encode the private trigger relationship. It is a normalization experiment,
not a supported migration path.

A plan may explicitly omit an exact triggered record only when an operator has independently
confirmed that it is incomplete or orphaned and supplies a reason. The planner validates the ID
and selected parent, and the audit and clone manifest retain the omission. This is an auditable
exclusion, not migration support.

## Site View boundary

Waypoint panorama-state markers are not panorama images. They contain only small state records,
such as a waypoint reference and timestamp.

Historical Site View imagery and capture history are not synthesized. Mission-only panorama
capture Elements are also not reconstructed when no equivalent SiteElement exists in the backup.

## Docks and relocalization

Dock records are deduplicated by physical dock number, docked waypoint, and public prep Target. A
dock is cloned only when all referenced waypoints are present. Its record identity and waypoint
references are remapped; its physical dock number is preserved. The prep target receives the
public travel defaults and retained opaque Target/TravelParams profile observed in the same
backup. Export fails closed when that profile is unavailable instead of emitting an incomplete
Dock that only passes structural validation.

Explicit public `SetLocalizationRequest` payloads are retained and nested initial-guess waypoint
references are remapped. Both features remain experimental until same-instance import, runtime,
and re-export checks pass.

## Validation levels

The project uses explicit evidence levels:

1. **Structural** — protobufs parse, references close, snapshots exist, and source IDs do not leak.
2. **Semantic** — public fields and retained unknown fields match after reverse-ID normalization.
3. **UI import** — a same-version product UI accepts and displays the generated archive.
4. **Runtime** — robot playback and physical action execution match expectations.
5. **Re-export** — a fresh backup or Walk export has no unexplained semantic differences.

The current ordinary-action path has reached UI import with Orbit, Spot robot software, and tablet
software all at version 5.1.8. Both a minimal DAQ-first profile and a full Localize/Sleep/DAQ profile
with UUIDv4 Element IDs materialized their expected Walk resources and available Dock. A
single-variable UUIDv5 Localize control completed upload but did not materialize its Site Map.
The minimal DAQ-only mission was subsequently played on the robot and completed its PTZ capture,
so that exact Action profile has reached the runtime level. Physical Dock return, broader Action
coverage, result association, and re-export remain user-run verification gates. Unsupported data
is never promoted to a higher evidence level by inference. See
[orbit-walk-import-findings.md](orbit-walk-import-findings.md) for the complete evidence chain.

## Privacy model

The repository contains only source code and synthetic fixtures. Local workspaces and clone
bundles intentionally retain source IDs and provenance for auditability, so they are private
artifacts and are excluded from Git.

See [privacy.md](privacy.md) for artifact handling and disclosure rules.
