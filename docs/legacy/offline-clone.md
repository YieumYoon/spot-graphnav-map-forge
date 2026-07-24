# Archived offline GraphNav/Walk clone research

## Status

Frozen historical research. It is not built, packaged, tested, documented as an operator
workflow, or supported on the default branch.

The complete implementation and detailed evidence were preserved before the Extension-first
transition:

- commit `6843453d22895034c15a27bd2c661bf3f5d5c512`;
- branch `archive/offline-clone-2026-07`;
- annotated tag `archive/offline-clone-2026-07`.

To inspect the immutable tag without changing the active branch:

```bash
git worktree add ../spot-map-forge-offline-archive \
  refs/tags/archive/offline-clone-2026-07
```

Do not run archived import experiments against an operational Orbit instance.

## What was archived

- polygon and halo selection;
- deterministic waypoint, snapshot, edge, SiteElement, Dock, and Walk identity remapping;
- offline GraphNav bundle construction and validation;
- public `.walk.zip` packaging;
- shared-identity and Orbit-shaped ID probes;
- tablet Walk reissue and sentinel experiments;
- loopback polygon editor;
- controlled import and limited runtime evidence.

## Why it was archived

The public Walk transport is not a supported Site Map copy operation. A payload can parse and
upload while still failing to materialize the expected Site Map, recording, Action, Dock, private
SiteWaypoint/SiteEdge wrapper, history, or lifecycle association.

Externally generated identities also cannot prove that Orbit's recording service allocated the
objects. Reusing identities can couple deduplication, update, and deletion behavior with existing
server-owned data. Private backup envelopes and internal REST behavior are not stable public
contracts.

The active project therefore keeps Orbit as the only writer and uses extensions to create
reviewable native drafts.

## Findings retained as design constraints

- upload completion is not import success;
- a public GraphNav/Autowalk archive is not a Site Map lifecycle copy;
- manual edges and public annotations do not reproduce every private SiteEdge wrapper;
- missions, schedules, results, anomalies, and Site View history are not transferable by
  inference;
- generated IDs that resemble Orbit IDs are not Orbit-issued identities;
- same-version success does not establish cross-version compatibility;
- source backups must remain immutable and operational imports require disposable validation.

These findings explain the active Extension-first safety model. They do not constitute support for
the archived implementation.
