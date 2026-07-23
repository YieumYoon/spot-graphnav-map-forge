# Changelog

All notable project changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses semantic versioning
with prerelease labels while compatibility remains alpha.

## [Unreleased]

### Added

- Public release hygiene checker and privacy guidance.
- Compatibility matrix with explicit evidence levels.
- Apache License 2.0, contribution guidance, and security policy.
- Same-instance verification checklist for disposable imports.
- An anonymized Orbit Walk import findings report covering controlled probes, identity rules,
  recording boundaries, Dock/Action requirements, edge transport, and triggered AI handling.
- Project motivation, primary user groups, and map-partitioning use cases.
- Optional unanchored and dependency-free disconnected-component cleanup with plan/audit records.
- Exact, reason-bearing exclusion for operator-confirmed incomplete or orphaned triggered records.
- Export-time waypoint recording-session relabeling and archive-name-derived deterministic Walk
  identities.
- Experimental preserve-identity build mode for shared GraphNav objects and SiteElements inside a
  new Walk transport container.
- Experimental Orbit-native-shaped identity mode that keeps clone topology and payloads while
  emitting tablet-shaped GraphNav IDs and deterministic UUIDv4-shaped Walk/Orbit object IDs.
- Byte-preserving `reissue-walk` experiment for tablet recording directories that changes only the
  top-level public Walk ID while retaining GraphNav, Element, Dock, opaque, and DAQ provenance data.
- Graph-only reissue control that strips Walk Elements and Docks to isolate Orbit SiteMap duplicate
  handling from action identity conflicts.
- Minimal skipped navigation-only Element probe for distinguishing SiteElement-aware duplicate
  handling from GraphNav/recording-only SiteMap novelty checks.
- Disconnected waypoint/snapshot/anchor sentinel probe with an explicit stop condition when Orbit
  deduplicates underlying recording data despite fresh GraphNav object IDs.
- Read-only graph reconciliation for Orbit-native recording moves, including raw-edge fallback,
  SiteEdge tombstones, intentional partition cuts, and an interactive waypoint-pair connect/delete
  guide.
- Unpacked Manifest V3 Orbit overlay that imports the reconciliation guide, focuses exact waypoint
  pairs with Orbit's in-page fit action, resolves current anchor coordinates, and draws CONNECT or
  DELETE markers without calling server APIs or saving map changes.
- Read-only Orbit selected-entity inspector and map-health summary with exact waypoint, edge, and
  recording ID joins; edge provenance, disabled/archive and cross-recording status; coordinates,
  degree, neighbor context, and copy controls.
- One-at-a-time native Orbit CONNECT assistance that selects exact waypoint IDs, waits for Orbit's
  own edge validator, rejects warnings and duplicates, adds only an unsaved editor draft, verifies
  the edit-history increment, and never presses Save.
- One-at-a-time native Orbit Archive assistance that selects the exact canonical edge in edge mode,
  repeats Orbit's anchoring warning, creates and verifies the same `nonEntities` tombstone as the
  native UI, and never presses Save.
- Complete B0 public edge-annotation capture, including edge-scoped crosswalk callbacks, mobility
  profiles, direction/path/ground/route behavior, cost, and audio/visual settings.
- Native Orbit edge-settings reconciliation with per-edge, crosswalk-only, and all-pending restore
  controls; stale-state and stored-direction guards; one verified Undo step; and no automatic Save.
- Local unlimited-storage permission and explicit storage-error handling for large private B0
  setting inventories; no network or host permission is added.
- Reusable Orbit Site Map Assistant knowledge base covering the effective-topology model, exact-ID
  induced-subgraph comparison, native draft semantics, staged operator runbook, AI-agent contract,
  compatibility qualification, privacy boundary, and production-scale settings validation.
- Separate workflow documentation and repository navigation that makes the Orbit-native recording
  split plus Site Map Assistant the recommended same-instance path while isolating offline
  GraphNav/Walk cloning and import probes as an experimental workflow.

### Changed

- Aligned operator-facing terminology with Orbit (**Site Map**, **recording**, **Archive**, and
  **edge settings**) and shortened the public workflow guides into direct procedures. Internal
  reconciliation operation values remain unchanged for guide-file compatibility.
- Positioned the project as an offline zone-map clone tool rather than an identity-preserving
  migration utility.
- Documented a successful UI import for an anonymized ordinary-action zone with Orbit, Spot robot
  software, and tablet software all at version 5.1.8.
- Documented full-map single-variable controls: Localize, Sleep, DAQ, and Dock materialized with
  UUIDv4 Element IDs, while changing only the navigation-only Localize ID to UUIDv5 completed
  upload but prevented Site Map materialization; a separate UUIDv5 DAQ control succeeded.
- Documented successful robot playback and PTZ capture for the minimal UUIDv4 DAQ-only profile,
  while retaining Dock return, broader Action coverage, result association, and re-export as gates.
- Replaced deployment-specific documentation and identifiers with synthetic examples.
- Preserved fail-closed triggered AI behavior while making explicit omissions auditable.

### Removed

- Generated Walk archives, map screenshots, browser logs, caches, and build artifacts from the
  public source tree.

## [0.1.0a1] - Unreleased

### Added

- Backup inventory and final Site Map graph reconstruction.
- Polygon and halo planning with a loopback-only editor.
- Deterministic GraphNav, snapshot, action, and dock identity cloning.
- Ordinary action, relative target, and image conversion to public Autowalk archives.
- Structural validation, preservation audit, and fail-closed triggered AI handling.
