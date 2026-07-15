# Architecture and data guarantees

## Boundary

The project has three layers:

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
- wrappers with observed suppression flags are excluded;
- referenced waypoint and edge snapshots are resolved by ID;
- map-layout control points seed a workspace-only coordinate projection;
- edge transforms propagate that projection for polygon selection;
- layout data is never injected into the serialized GraphNav clone;
- components that cannot reach a layout control point are marked unanchored.

Using site-level edge records preserves edits that are not owned by a recording session, including
manual links, loop closures, and site-specific annotations. This behavior is based on observed
Orbit 5.1.8 archive semantics and is guarded by offline validation; it is not a vendor-published
backup schema.

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

GraphNav edge identity is defined by its remapped endpoint pair. Sensor, fiducial, and physical
dock numbers are not object identities and remain unchanged.

Source mission and SiteWalk IDs are never reused. Identity-preserving partition or move semantics
are not implemented because the public product interface does not expose the required lifecycle
operation.

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
references are remapped; its physical dock number is preserved.

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
software all at version 5.1.8. Runtime and re-export remain user-run verification gates. Unsupported
data is never promoted to a higher evidence level by inference.

## Privacy model

The repository contains only source code and synthetic fixtures. Local workspaces and clone
bundles intentionally retain source IDs and provenance for auditability, so they are private
artifacts and are excluded from Git.

See [privacy.md](privacy.md) for artifact handling and disclosure rules.
