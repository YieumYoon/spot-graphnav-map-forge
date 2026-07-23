# Orbit-native Site Map split

Use this workflow to split one Orbit **Site Map** by moving whole **recordings** to another Site
Map in the same Orbit instance.

Verified environment: Orbit 5.1.8. Requalify the extension after an Orbit upgrade.

## Before you start

You need:

- a Source Site Map and Destination Site Map;
- a complete backup made before changing **Select recordings**;
- exact Site Map and recording IDs;
- the Orbit Site Map Assistant loaded in the Chrome profile that opens Orbit.

Copy the [operation journal template](orbit-native-operation-journal-template.md) into a private
workspace.

## 1. Create B0

The immutable pre-change backup is called **B0**.

```bash
uv run spot-map-forge inspect /path/to/B0.tar

uv run spot-map-forge graph-baseline /path/to/B0.tar \
  --map '<Source-Site-Map-name-or-ID>' \
  --out workspace/source-site-map/graph-baseline.json
```

Do not commit B0 or `graph-baseline.json`.

## 2. Plan recording membership

Record:

- Source and Destination Site Map IDs;
- exact recording IDs to move;
- expected waypoint totals;
- manually created edges that stay inside each Site Map;
- edges that will cross the Site Map boundary;
- Areas, Actions, Docks, or other dependencies requiring separate review.

Move recordings, not individual waypoints.

## 3. Move one recording

For each exact recording ID:

1. Open the Source Site Map and confirm **Save** is disabled.
2. Open **Select recordings**.
3. Identify the recording by its exact ID.
4. Remove it, apply the dialog, review, and press **Save**.
5. Reopen **Select recordings** and confirm it is absent.
6. Open the Destination Site Map.
7. Add the same recording, apply the dialog, review, and press **Save**.
8. Reopen both Site Maps and verify membership.

Finish and verify one recording before moving the next.

If Orbit asks whether to discard changes, remain on the page unless discarding was intentional.

## 4. Compare a result Site Map

1. Wait for recordings, waypoints, edges, and anchors to finish loading.
2. Open the Orbit Site Map Assistant.
3. Select **Load B0 baseline**.
4. Choose `graph-baseline.json`.
5. Review the counts.

| Item | Meaning |
| --- | --- |
| **Connect** | an edge whose two B0 endpoints are in this Site Map is missing |
| **Archive** | a live edge should remain archived according to B0 |
| **Edge settings** | an existing edge's supported settings differ from B0 |
| **Crosswalk** | an edge-settings item contains a Spot Crosswalk callback |
| **Site Map boundary** | only one endpoint is in this Site Map; no edit is offered |
| **Ignored extra scope** | a waypoint was not in B0; it and incident edges are ignored |

Stop if the counts do not match the recording plan or if Orbit has not finished loading.

## 5. Repair edges

Use this order:

1. Select **Show edges pending Archive**.
2. Review the complete overlay.
3. Select **Archive all pending edges**.
4. Verify one **Undo** step, then press **Save**.
5. Use **Connect in Orbit** for missing internal edges.
6. Verify each draft, then press **Save**.
7. Select **Refresh**.

A newly connected edge can require edge-settings restoration after Refresh.

## 6. Restore edge settings

For a large Site Map:

1. Select **Restore pending crosswalk settings**.
2. Verify the count and one **Undo** step.
3. Review and press **Save**.
4. Select **Restore all pending edge settings**.
5. Verify the remaining count and one **Undo** step.
6. Review and press **Save**.
7. Select **Refresh**.

The crosswalk batch restores each edge's complete B0 public settings profile.

The assistant rejects a batch if an endpoint, stored direction, edge source, current setting, or
Site Map ID changed.

## 7. Verify both Site Maps

For Source and Destination Site Maps:

- Connect = 0, unless explicitly deferred;
- Archive = 0, unless explicitly deferred;
- Edge settings = 0, unless explicitly deferred;
- Site Map boundary count matches the approved split;
- ignored extra scope matches known newer recordings;
- recording membership matches the plan.

Create a final backup when formal persistence or wrapper-level evidence is required.

Optional backup comparison:

```bash
uv run spot-map-forge reconcile-graph workspace/source-site-map \
  /path/to/B0.tar /path/to/final-backup.tar \
  --before-map '<Source-Site-Map-name-or-ID>' \
  --after-map '<Result-Site-Map-name-or-ID>' \
  --out workspace/source-site-map/final-reconciliation.json
```

## Rollback

Moving a recording back restores recording membership, not necessarily Site Map edits. Some
SiteWaypoint and SiteEdge wrappers did not survive the controlled Orbit 5.1.8 round trip.

Rollback options:

- move the exact recording ID back and replay missing edits from B0;
- restore B0, understanding that unrelated post-B0 changes can also be reverted.

Never claim a lossless rollback from recording reassignment alone.

## Required safety rules

- Use exact IDs, not names or row order.
- Never modify B0.
- Never recreate a Site Map boundary edge.
- Review every Archive overlay before creating a draft.
- Require exactly one Undo step per batch.
- The extension never presses **Save**.
- Extension **done** means “draft verified,” not “saved.”

## References

- [Orbit Site Map Assistant](../../extension/orbit-graph-repair/README.md)
- [Operation journal](orbit-native-operation-journal-template.md)
- [Engineering reference](../orbit-map-assistant-knowledge-base.md)
- [Compatibility](../compatibility.md)
