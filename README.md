# Spot GraphNav Map Forge

Offline-first tooling for splitting a large Boston Dynamics Spot GraphNav map into smaller,
polygon-selected zone maps while preserving the final edited topology and ordinary inspection
actions.

The project reads a compatible fleet-manager backup, reconstructs the final Site Map graph, clones
the selected zone to new deterministic identities, and exports a validated public Autowalk
`.walk.zip`. The source backup and source map are never modified.

> **Alpha software.** A corrected small-zone archive has been imported through Orbit 5.1.8 and
> displayed with its final graph and ordinary inspection actions. Orbit, the Spot robot software,
> and the tablet software were all version 5.1.8 in that verification environment. Robot playback,
> cross-version compatibility, and re-export equivalence are still explicit verification gates.

This is an independent community project. It is not affiliated with or endorsed by Boston
Dynamics.

## Why this exists

Spot inspection setup commonly starts by recording a comprehensive GraphNav map and then adding
inspection points throughout that map. This works well until the map becomes too large for the
authoring workflow around it.

In the field deployments that motivated this project, sufficiently large maps have taken more than
20 minutes to upload or open on a tablet. In worse cases, the map does not finish loading reliably,
which makes adding or editing inspection points impractical. Maps assembled from many recording
sessions can also retain branches, waypoints, and edges that are no longer needed but still add to
the amount of data every authoring session must load.

The authors could not find a supported product workflow that could select a region of the final
edited Site Map and create a smaller independent map while retaining its useful topology and
ordinary inspection actions. Map Forge was created to fill that offline tooling gap.

It supports three main workflows:

- **Split before inspection authoring:** partition a large GraphNav map into manageable zone maps,
  then add inspection points to each zone.
- **Extract after partial authoring:** clone a region that already contains ordinary inspection
  actions so work completed in that region does not have to be recreated manually.
- **Exclude unused map data:** select only the operational area and omit unused branches,
  waypoints, and edges left by numerous recording sessions.

Map Forge creates a new, smaller map; it never trims or deletes the source map in place. After a
clone has been imported and verified, operators can separately decide whether and how to retire or
reorganize the oversized source map.

## Who it is for

The primary users are:

- engineers and technicians who build detailed Spot GraphNav maps;
- Spot inspection deployment teams and robotics integrators;
- operators setting up inspections in medium- and large-scale plants or facilities;
- teams whose maps contain many recording sessions, manual edges, or loop closures that must be
  preserved in the selected zones;
- users who are comfortable validating and manually importing an alpha-generated `.walk.zip`.

It is not an identity-preserving migration or inspection-history transfer tool. Teams that need to
move existing results, anomalies, Site View history, schedules, or triggered AI inspections should
review the [compatibility matrix](docs/compatibility.md) before using it.

## What it does

- inventories Site Maps directly from a backup `.tar` without extracting the complete archive;
- reconstructs the final edited `map_pb2.Graph` from Site Map waypoint and edge records;
- retains active manual edges, loop closures, graph annotations, and referenced snapshots;
- identifies Orbit field-3 edges as an explicit transport decision while still using them for
  coordinate propagation and waypoint selection;
- selects a zone with a polygon and an optional graph-neighbor halo;
- can exclude unanchored remnants and dependency-free disconnected components with an auditable
  plan;
- assigns reproducible UUIDv5 identities to cloned map objects and actions;
- preserves ordinary action payloads, waypoint-relative capture targets, and embedded images;
- clones complete dock definitions when every referenced waypoint is selected;
- can replace exported waypoint recording-session labels without changing geometry or capture
  timestamps;
- audits cut edges and unsupported dependencies before export;
- validates both the offline clone bundle and the generated `.walk.zip`;
- provides a local browser UI for drawing polygons.

## What it does not do

- mutate, trim, or delete the source Site Map;
- preserve source waypoint, action, mission, or Site Map identities;
- assign or migrate a fleet-manager recording UUID;
- migrate existing inspection results, anomalies, or capture history;
- migrate Site View panorama history;
- clone existing mission ordering or schedules;
- guarantee triggered AI inspection migration;
- upload anything to a robot or fleet manager.

Triggered AI inspections are fail-closed: normal Walk export stops instead of silently dropping or
flattening a dependency that the public Walk schema cannot represent. An experimental normalization
probe exists for research, but it is not a supported migration path.

See [compatibility and support levels](docs/compatibility.md) for the full matrix.

## Safety and privacy

- Backups are opened read-only.
- Offline commands perform no network requests and collect no telemetry.
- Credential directories in source backups are never extracted.
- The editor binds to `127.0.0.1` by default.
- Generated IDs are deterministic for a selected clone namespace.
- No command uploads a Walk, removes a recording, or modifies a source map.

Prepared workspaces, audit reports, clone manifests, screenshots, and `.walk.zip` files can contain
site names, original IDs, local paths, inspection definitions, and images. They are ignored by Git
and must not be attached to public issues. Read the [privacy guide](docs/privacy.md) before sharing
artifacts.

## Requirements

- Python 3.11 or newer
- [`uv`](https://docs.astral.sh/uv/)
- separately licensed [Boston Dynamics Spot SDK](https://github.com/boston-dynamics/spot-sdk/blob/master/LICENSE)
  Python packages
- a compatible backup `.tar`

The project depends on `bosdyn-api` but does not vendor Boston Dynamics SDK source or binaries.

## Install for development

```bash
git clone <repository-url>
cd spot-graphnav-map-forge
uv sync --extra dev
```

## Quick start

```bash
# List maps without extracting the complete backup.
uv run spot-map-forge inspect /path/to/backup.tar

# Reconstruct one final Site Map into a private, ignored workspace.
uv run spot-map-forge prepare /path/to/backup.tar \
  --map '<map-name-or-id>' \
  --out workspace/example-map

# Draw a polygon in the loopback-only editor.
uv run spot-map-forge serve workspace/example-map

# Or create a plan from polygon coordinates.
uv run spot-map-forge plan workspace/example-map \
  --polygon examples/zone.example.json \
  --zone-name zone-a \
  --halo-hops 1 \
  --out workspace/example-map/zone-a.plan.json

# Review retained and cut dependencies before building.
uv run spot-map-forge audit workspace/example-map \
  --plan workspace/example-map/zone-a.plan.json \
  --out workspace/example-map/zone-a.audit.json

# Build and validate an offline clone bundle.
uv run spot-map-forge build workspace/example-map \
  --plan workspace/example-map/zone-a.plan.json \
  --out output/zone-a
uv run spot-map-forge validate output/zone-a

# Export and validate a public Autowalk archive.
uv run spot-map-forge export-walk output/zone-a \
  --out output/zone-a.walk.zip
uv run spot-map-forge validate-walk output/zone-a.walk.zip
```

To give an exported copy a fresh Walk identity and replace the recording-session label retained
on every waypoint, supply both names explicitly. `--name` sets the archive, map, mission, and group
labels and drives the deterministic Walk UUID. `--recording-name` replaces only
`Waypoint.annotations.client_metadata.session_name`; waypoint geometry, timestamps, IDs, and
client identity remain unchanged:

```bash
uv run spot-map-forge export-walk output/zone-a \
  --out output/zone-a-clean-v2.walk.zip \
  --name zone-a-clean-v2 \
  --recording-name zone-a-clean-v2
```

This does not create or choose a fleet-manager recording UUID. Any server-side recording identity
is assigned during manual import. The export summary lists the source session-label distribution
for auditability, so treat captured CLI output as private operational data.

One explicit public Sleep action can be added without pretending it came from a copied
SiteElement. The waypoint may be supplied using its source or cloned ID; the export summary
records both identities, the duration, generated Element ID, and insertion position:

```bash
uv run spot-map-forge export-walk output/zone-a \
  --out output/zone-a-sleep.walk.zip \
  --name zone-a-sleep \
  --sleep-waypoint-id '<waypoint-id>' \
  --sleep-duration-seconds 0.25 \
  --sleep-after-element 'Localize - 1'
```

Dock export is fail-closed when the bundle has no same-backup observed target profile. The
exporter applies the observed public travel defaults and retained opaque target/travel fields to
the dock prep target; it no longer emits a structurally valid but incomplete Dock.

Upload remains a deliberate manual step. Follow the
[same-instance verification checklist](docs/import-poc.md) with a disposable clone name.

## Core and halo waypoints

`core` waypoints are inside or on the polygon. A `halo` adds neighboring waypoints outside the
polygon by graph hop count so a boundary does not cut directly through an important junction.

```text
core only:     C -- C -- C
one-hop halo:  H -- C -- C -- C -- H
```

Actions on halo waypoints are excluded by default to avoid duplicating inspections across adjacent
zone maps. Use `--clone-halo-actions` only when those boundary actions intentionally belong to the
new zone.

The editor can exclude unanchored local-frame remnants before computing the halo, then remove
smaller disconnected components that contain no actions, docks, or panorama state. The equivalent
CLI flags are:

```bash
uv run spot-map-forge plan workspace/example-map \
  --polygon examples/zone.example.json \
  --zone-name zone-a \
  --exclude-unanchored-waypoints \
  --exclude-dependency-free-components \
  --out workspace/example-map/zone-a.plan.json
```

Unanchored cleanup is enabled by default in the editor but remains explicit in saved plans. Empty
component cleanup is opt-in. Exact excluded IDs, component sizes, and protected dependency-bearing
components are recorded in the plan, audit, and clone manifest.

## Orbit field-3 edge transport

Observed Orbit SiteEdge field-3 records cannot be assumed to round-trip through the public Walk
format with their private UI state intact. The selector draws them as dashed amber edges and uses
them for coordinate propagation, halo expansion, and waypoint selection. Each plan then makes the
transport choice explicit:

- default: exclude field-3 edges from the bundle and Walk; their waypoints and other selected edges
  remain, but the excluded edges must be recreated in Orbit;
- `--include-selection-only-edges`: include their public `Edge.annotations` experimentally; Orbit
  may still display reset environment or travel settings.

After either mode is imported, verify every field-3 edge listed by the plan/audit and reapply its
environment and **Allow travel along this edge** settings in Orbit. The editor shows both the Walk
edge count and the component count expected after the chosen transport mode.

```bash
uv run spot-map-forge plan workspace/example-map \
  --polygon examples/zone.example.json \
  --zone-name zone-a \
  --include-selection-only-edges \
  --out workspace/example-map/zone-a.plan.json
```

Triggered AI SiteElements remain fail-closed by default. If a backup contains a confirmed
incomplete or orphaned triggered record, exclude only that exact ID and record the evidence in the
plan:

```bash
uv run spot-map-forge plan workspace/example-map \
  --polygon examples/zone.example.json \
  --zone-name zone-a \
  --exclude-triggered-action '<site-element-id>' \
  --triggered-action-exclusion-reason 'confirmed incomplete backup record' \
  --out workspace/example-map/zone-a.plan.json
```

Unknown IDs, duplicate IDs, exclusions outside the selected action set, and exclusions without a
reason are rejected. The omission is retained in the audit and clone manifest; the source backup
is never changed.

## Optional tablet metadata template

Some tablet-created archives contain an opaque `autowalk_metadata` file that is outside the public
Walk protobuf. A same-version template archive can supply only that file:

```bash
uv run spot-map-forge export-walk output/zone-a \
  --out output/zone-a.walk.zip \
  --template-archive /path/to/tablet-created.walk.zip
```

The template graph, mission, actions, images, and identities are never reused. Copying opaque
metadata removes only a structural warning; it does not prove compatibility.

## Output layout

```text
output/zone-a/
  graph
  waypoint_snapshots/
  edge_snapshots/
  action_payloads/
  dock_payloads/
  clone_manifest.json
  validation_report.json

output/zone-a.walk.zip
  zone-a.walk/
    graph
    waypoint_snapshots/
    edge_snapshots/
    missions/zone-a.walk
    missions/readme.txt
```

The intermediate bundle is intentionally auditable and contains source-to-clone mappings. The
exported Walk uses clone-only identities.

## Development

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run python scripts/check_release_hygiene.py
uv build
```

Only synthetic fixtures belong in tests. Never commit a real backup, Walk, map screenshot,
inspection image, credential, site name, hostname, or customer identifier. See
[CONTRIBUTING.md](CONTRIBUTING.md).

## License and trademarks

Project-authored code is available under the [Apache License 2.0](LICENSE). The Boston Dynamics
Spot SDK is distributed under its own license and must be obtained separately. Boston Dynamics,
Spot, Orbit, and related marks are trademarks of their respective owner; see [NOTICE](NOTICE) and
the vendor's [terms of use](https://bostondynamics.com/terms/).
