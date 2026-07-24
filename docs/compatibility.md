# Compatibility and support levels

## Supported paths

| Capability | Level | Boundary |
| --- | --- | --- |
| Orbit Site Map Editor read-only search, Inspector, selection, overlays, and validation | Supported alpha on the qualified Orbit environment | Live Orbit page adapter; no persistence |
| Native Connect, Archive, and edge-settings assistance | Supported alpha on the qualified Orbit environment | Reviewed unsaved draft, exact read-back, one Undo step |
| Site View coverage planning | Supported alpha | Read-only active/reachable graph planning |
| Same-instance recording move plus Migration Assistant | Supported alpha | Recording identity remains native to Orbit |
| Backup inventory and B0 baseline | Supported read-only | Observed private backup format |
| B0 versus final-backup comparison | Supported read-only | JSON report only |
| Automatic Save, private REST writes, generated map import, or recording-object synthesis | Unsupported | Outside the persistence model |
| Offline GraphNav/Walk clone | Archived | Historical research only |

## Qualified environment

| Component | Current evidence |
| --- | --- |
| Orbit | 5.1.8 |
| Spot robot software | 5.1.8 where runtime evidence was required |
| Tablet software | 5.1.8 where runtime evidence was required |
| Public protobuf dependency | `bosdyn-api==5.1.4` |
| Extension persistence | None; Orbit Save remains an operator action |
| CLI network writes | None |

The protobuf dependency and deployed product versions are separate compatibility inputs. A
matching public SDK version does not prove that Orbit's private backup envelope or editor adapter
is unchanged.

## Upgrade gate

After every Orbit upgrade:

1. run the full static qualification;
2. reload the unpacked extension, then reload Orbit;
3. confirm the displayed build label and exactly one panel root;
4. run read-only catalog, selection, overlay, and validation checks;
5. on a disposable Site Map, test each native mutation adapter separately;
6. require exact read-back and one Undo step;
7. restore the draft and leave the Site Map unchanged.

Do not enable a mutation control merely because a selector returned an object. The adapter must
prove the complete capability it needs.

## Fail-closed conditions

Disable the affected operation when:

- the Orbit version or adapter capability is unknown;
- exact waypoint, edge, recording, Area, Dock, or Action identity is ambiguous;
- a draft, stored direction, endpoint set, or settings fingerprint changed;
- Orbit's native validator returns a warning or cannot be observed;
- the expected read-back or Undo delta is not exact;
- a backup record is missing, duplicated, contradictory, or cannot be parsed.

Warnings are not success claims.

## Archived research

Public Walk import, cloned identities, private wrapper behavior, and related controlled probes are
recorded in the immutable archive, not supported by the active project. See
[legacy/offline-clone.md](legacy/offline-clone.md).

## Reporting compatibility

Public reports may include only generalized product versions, extension release/build labels, and
synthetic reproductions. Never publish a real backup, screenshot, map/action name, ID, coordinate,
hostname, inspection image, or browser log.
