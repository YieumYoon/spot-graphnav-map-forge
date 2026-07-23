# Extensions

## Orbit Site Map Assistant

[`orbit-graph-repair`](orbit-graph-repair/README.md) is the primary interactive component of the
recommended same-instance Site Map split workflow.

It runs inside the Orbit Site Map editor and:

- inspects exact waypoint, edge, and recording identity;
- compares a live result Site Map with an immutable B0 baseline;
- visualizes Connect, Archive, edge-settings, and Site Map boundary items;
- creates native unsaved Connect, Archive, and public edge-settings drafts;
- restores edge-scoped crosswalk profiles;
- verifies one native Undo step;
- never presses **Save**.

The directory name is retained for unpacked-extension path stability even though the extension's
display name is **Orbit Site Map Assistant**.

Start with the [Orbit-native Site Map split](../docs/workflows/orbit-native-map-split.md).
