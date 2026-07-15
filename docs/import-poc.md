# Same-instance verification checklist

This checklist verifies a generated archive without exposing a production map or relying on
cross-version behavior. Use a disposable clone name and keep the source Site Map untouched.

## Current evidence

The offline graph and ordinary-action conversion paths are structurally and semantically tested.
A corrected small-zone archive has also been accepted and displayed by Orbit 5.1.8 in an
environment where Orbit, the Spot robot software, and the tablet software were all version 5.1.8.
That result verifies archive ingestion and UI representation for the exercised ordinary-action
subset in that exact version combination. It does not establish robot playback, all action types,
cross-version compatibility, or historical-data migration.

## Choose a disposable zone

Select a small area that contains representative but non-sensitive test actions:

- ordinary odometry edges;
- a manual edge when available;
- a loop-closure edge when available;
- an action with no image;
- an action with a DAQ image;
- an action with an alignment/reference image;
- a waypoint-relative capture target;
- a complete dock/prep-waypoint pair only when testing experimental dock support.

Do not include a triggered AI inspection in the ordinary-action test. The default exporter will
block that selection by design.

## Build the disposable archive

```bash
uv run spot-map-forge prepare /path/to/backup.tar \
  --map '<map-name-or-id>' \
  --out workspace/map-forge-poc

# Draw and save a small plan with `serve`, then audit it.
uv run spot-map-forge audit workspace/map-forge-poc \
  --plan workspace/map-forge-poc/plans/poc.plan.json \
  --out workspace/map-forge-poc/poc.audit.json

uv run spot-map-forge build workspace/map-forge-poc \
  --plan workspace/map-forge-poc/plans/poc.plan.json \
  --out output/map-forge-poc

uv run spot-map-forge validate output/map-forge-poc

uv run spot-map-forge export-walk output/map-forge-poc \
  --out output/map-forge-poc-v2.walk.zip \
  --name '<disposable-name>' \
  --recording-name '<disposable-name>'

uv run spot-map-forge validate-walk output/map-forge-poc-v2.walk.zip
```

The generated Walk is a transport container, not a copy of an existing mission. Each ordinary
action targets its remapped waypoint and retains the observed waypoint-relative body goal and
navigation distance.

## Manual import gates

Import through the supported product UI using a disposable name. Pass the UI gate only when:

1. a new Site Map is created and the source map remains unchanged;
2. the visible topology matches the offline clone, including representative manual and loop
   closure edges;
3. every field-3 edge listed by the audit matches the chosen include/exclude mode, and its
   environment and **Allow travel along this edge** settings have been verified and reapplied;
4. selected ordinary actions appear at the expected waypoint-relative locations;
5. action type, parameters, and display names match the source definitions;
6. DAQ and alignment images render in their correct action slots;
7. no action from outside the core selection appears unless halo actions were explicitly enabled;
8. every boundary-cut edge or dock reported by the audit is absent from the imported map.
9. the visible Walk and recording-session labels use the disposable name rather than a retained
   source session label;
10. the product treats the import as a new object where a server-side recording identity is shown.

The offline exporter controls the public Walk ID and waypoint session label, not the product's
recording UUID. Record only whether a new identity was assigned; do not copy that UUID into public
test notes.

Record only pass/fail results in public project documentation. Do not publish the map name,
screenshots, action names, coordinates, IDs, asset counts, or archive itself.

## Runtime gates

Run only in a controlled environment under normal Spot operating and safety procedures.

1. Localize against the cloned map.
2. Navigate across representative automatic, manual, and loop-closure edges.
3. Execute an ordinary no-image action.
4. Execute representative DAQ and alignment-image actions.
5. Confirm that the robot reaches the expected offset from the waypoint before capture.
6. Verify that the captured output is associated with the new action.

UI placement alone does not prove physical capture equivalence.

## Lifecycle and re-export gates

1. Disable or remove the disposable transport mission only after confirming that imported actions
   remain available.
2. Create a fresh private backup or export of the cloned map.
3. Compare graph topology, public action fields, relative targets, images, and retained unknown
   fields after normalizing clone IDs.
4. Treat every unexplained difference as a compatibility failure.

Never upload the fresh backup, comparison report, or source-to-clone ID mapping to a public issue.

## Triggered AI research gate

Triggered AI inspection migration is unsupported. If maintainers perform a private normalization
experiment, keep it separate from an ordinary-action clone. A successful experiment would require
the product to recreate a separate triggered AI inspection whose private trigger reference points
to the newly imported parent, with equivalent public network-compute settings. An inline
network-compute action or a missing triggered AI inspection is a failure.

The default export remains fail-closed regardless of an isolated experiment.

## Cleanup

- Keep the source Site Map unchanged.
- Disable or delete only the disposable clone after collecting private verification results.
- Remove local `workspace/`, `output/`, screenshots, and browser logs when no longer needed.
- Do not commit or publish any generated artifact.
