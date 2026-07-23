# Orbit Site Map Assistant

Use this extension after moving **recordings** between Site Maps in Orbit. It compares the open
Site Map with an immutable **B0** baseline and creates native, unsaved Orbit edits.

Verified with Orbit 5.1.8. Requalify it on a disposable Site Map after an Orbit upgrade.

## Install

Use the Chrome profile that opens Orbit:

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Select **Load unpacked**.
4. Choose `extension/orbit-graph-repair`.
5. Reload the Orbit Site Map editor.

Reload the extension and the Site Map page after pulling code changes.

## Create B0

Create the baseline before changing **Select recordings**:

```bash
uv run spot-map-forge graph-baseline /path/to/B0.tar \
  --map '<Source-Site-Map-name-or-ID>' \
  --out workspace/source-site-map/graph-baseline.json
```

Keep the backup and baseline private.

## Repair a Site Map

1. Open the result Site Map and wait for recordings, waypoints, edges, and anchors to load.
2. Select **Load B0 baseline** and choose `graph-baseline.json`.
3. Review the counts and the Site Map ID.
4. Select **Show edges pending Archive** and inspect the overlay.
5. Select **Archive all pending edges**, verify one **Undo** step, then press **Save**.
6. Use **Connect in Orbit** for missing internal edges; review and press **Save**.
7. Select **Refresh**.
8. Select **Restore pending crosswalk settings**; review and press **Save**.
9. Select **Restore all pending edge settings**; review and press **Save**.
10. Select **Refresh** and verify that no unexplained items remain.

The extension never presses **Save**.

## Comparison terms

| Assistant item | Meaning |
| --- | --- |
| **Connect** | an internal B0 edge is missing |
| **Archive** | a live edge should remain archived according to B0 |
| **Edge settings** | an existing edge's supported settings differ from B0 |
| **Crosswalk** | the edge-settings item includes a Spot Crosswalk callback |
| **Site Map boundary** | only one endpoint is in this Site Map; review only |
| **Ignored extra scope** | the waypoint was not in B0; it and incident edges are ignored |

The extension compares exact waypoint IDs. It does not infer identity from names or coordinates.

## Controls

| Control | Result |
| --- | --- |
| **Focus in Orbit** | fits the exact waypoint pair in the Orbit view |
| **Copy IDs** | copies exact waypoint IDs |
| **Connect in Orbit** | creates one native unsaved edge draft |
| **Archive in Orbit** | creates one native unsaved Archive draft |
| **Archive all pending edges** | creates one validated multi-edge Archive draft |
| **Restore settings in Orbit** | restores one edge's supported B0 settings |
| **Restore pending crosswalk settings** | restores the reviewed crosswalk-settings batch |
| **Restore all pending edge settings** | restores the reviewed remaining settings batch |
| **Refresh** | rereads the open Site Map and rebuilds the comparison |
| **Mark done** | records local progress; it does not mean the Site Map was saved |

Select a waypoint or edge with Orbit's editor to inspect its exact IDs, recording, source,
coordinates, neighbors, Archive state, crosswalk callbacks, and supported edge settings.

## What is restored

- missing internal edges, including manually created edges;
- B0 Archive state;
- Spot Crosswalk callbacks;
- mobility, stairs, direction, path following, ground, route, cost, and audio/visual edge settings.

The extension does not recreate a Site Map boundary edge, restore map-level Area geometry, or
synthesize private SiteEdge/SiteWaypoint wrapper fields.

## Safety and compatibility

- The extension has no host permission and does not call Orbit REST or server APIs.
- All write assistance uses Orbit's native editor actions and creates unsaved drafts.
- A mismatch in Site Map ID, endpoint, edge source, direction, settings, selection, or edit history
  fails closed.
- Each accepted batch must create exactly one **Undo** step.
- B0 and imported guides remain in this Chrome profile until removed.
- Internal guide values remain `connect`, `delete`, and `update` for file compatibility; the UI uses
  Orbit terms **Connect**, **Archive**, and **Edge settings**.

## More detail

- [Site Map split workflow](../../docs/workflows/orbit-native-map-split.md)
- [Operation journal](../../docs/workflows/orbit-native-operation-journal-template.md)
- [Engineering reference](../../docs/orbit-map-assistant-knowledge-base.md)
- [Compatibility matrix](../../docs/compatibility.md)
