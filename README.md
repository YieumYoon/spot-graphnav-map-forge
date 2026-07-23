# Spot GraphNav Map Forge

Split a large Orbit **Site Map** by moving **recordings**, then restore its edited **edges** with
the Orbit Site Map Assistant.

| Workflow | Status |
| --- | --- |
| [Orbit-native Site Map split](docs/workflows/orbit-native-map-split.md) | recommended; verified on Orbit 5.1.8 |
| [Offline GraphNav/Walk clone](docs/workflows/offline-map-clone.md) | experimental |

The recommended workflow keeps recording and waypoint identity native to Orbit. The extension
compares each result Site Map with a baseline backup, creates native unsaved edits, verifies one
**Undo** step, and never presses **Save**.

> Requalify the extension on a disposable Site Map after every Orbit upgrade.

This is an independent community project. It is not affiliated with or endorsed by Boston
Dynamics.

## Quick start

### 1. Create the baseline

Before changing **Select recordings**, create a backup. This immutable backup is called **B0**.

```bash
uv sync --extra dev

uv run spot-map-forge inspect /path/to/B0.tar

uv run spot-map-forge graph-baseline /path/to/B0.tar \
  --map '<Source-Site-Map-name-or-ID>' \
  --out workspace/source-site-map/graph-baseline.json
```

Keep B0 and `graph-baseline.json` private.

### 2. Load the Orbit Site Map Assistant

In the Chrome profile that opens Orbit:

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Select **Load unpacked**.
4. Choose `extension/orbit-graph-repair`.
5. Reload the Site Map editor.

### 3. Move recordings in Orbit

For each exact recording ID:

1. Open the **Source Site Map**.
2. Use **Select recordings** to remove the recording.
3. Apply the dialog, review the draft, and press **Save**.
4. Open the **Destination Site Map**.
5. Use **Select recordings** to add the same recording.
6. Apply the dialog, review the draft, and press **Save**.
7. Reopen both dialogs and verify membership.

Move one recording at a time. Do not identify a recording only by its display name or row
position.

### 4. Compare and repair each Site Map

Open a result Site Map and load `graph-baseline.json`.

| Assistant item | Meaning | Orbit action |
| --- | --- | --- |
| **Connect** | an internal B0 edge is missing | **Connect in Orbit** |
| **Archive** | an edge should remain archived | **Archive in Orbit** |
| **Edge settings** | an existing edge differs from B0 | **Restore edge settings** |
| **Site Map boundary** | the endpoints are in different Site Maps | review only |
| **Ignored extra scope** | a newer waypoint was not present in B0 | review only |

Recommended order:

1. Show and review edges pending **Archive**.
2. Archive the reviewed batch and press **Save**.
3. Connect missing internal edges and press **Save**.
4. Select **Refresh**.
5. Restore crosswalk edge settings, review, and press **Save**.
6. Restore the remaining edge settings, review, and press **Save**.
7. Select **Refresh** again.

The extension never presses **Save**.

### 5. Verify

For both Source and Destination Site Maps:

- no unexplained Connect, Archive, or edge-settings items remain;
- Site Map boundary edges match the approved split;
- ignored extra waypoints and edges match known newer recordings;
- recording membership matches the plan.

Create a final backup when backup-level evidence is required.

Use the [private operation journal template](docs/workflows/orbit-native-operation-journal-template.md)
to record exact IDs, Undo steps, Saves, and final counts.

## What the assistant restores

- missing internal edges, including manually created edges;
- B0 archived-edge state;
- edge-scoped Spot Crosswalk callbacks;
- mobility, stairs, direction, path following, ground, route, cost, and audio/visual edge settings.

It does not restore:

- an edge whose endpoints are in different Site Maps;
- map-level Area geometry;
- private SiteEdge or SiteWaypoint wrapper equality;
- missions, schedules, results, anomalies, or Site View history.

## Safety rules

- Never modify the B0 backup.
- Use exact Site Map, recording, waypoint, and edge endpoint IDs.
- Wait for the Site Map to finish loading before **Refresh**.
- Review every batch count before creating a draft.
- Require exactly one Orbit **Undo** step per batch.
- Treat extension **done** as “draft verified,” not “saved.”
- Keep backups, baselines, guides, screenshots, and Walk archives out of Git.

## Experimental offline clone

The Python package also supports polygon selection, ID remapping, clone auditing, and `.walk.zip`
generation. This is a separate experimental workflow:

```bash
uv run spot-map-forge prepare /path/to/backup.tar \
  --map '<Site-Map-name-or-ID>' \
  --out workspace/example

uv run spot-map-forge plan workspace/example \
  --polygon examples/zone.example.json \
  --zone-name zone-a \
  --out workspace/example/zone-a.plan.json

uv run spot-map-forge audit workspace/example \
  --plan workspace/example/zone-a.plan.json

uv run spot-map-forge build workspace/example \
  --plan workspace/example/zone-a.plan.json \
  --out output/zone-a
```

Do not treat a generated `.walk.zip` as an Orbit-supported Site Map copy. Follow the
[experimental workflow](docs/workflows/offline-map-clone.md) and
[compatibility matrix](docs/compatibility.md).

## Documentation

- [Documentation index](docs/README.md)
- [Orbit-native Site Map split](docs/workflows/orbit-native-map-split.md)
- [Operation journal template](docs/workflows/orbit-native-operation-journal-template.md)
- [Orbit Site Map Assistant](extension/orbit-graph-repair/README.md)
- [Engineering reference](docs/orbit-map-assistant-knowledge-base.md)
- [Python module boundaries](src/spot_graphnav_map_forge/README.md)

## Development

```bash
uv run pytest
uv run ruff check .
```

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and the
[privacy guide](docs/privacy.md).

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

Boston Dynamics, Spot, Orbit, GraphNav, and Autowalk are trademarks of their respective owners.
