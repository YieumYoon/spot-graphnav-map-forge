# Documentation

The repository contains two intentionally separate workflows. Choose one before running any
command or changing an Orbit Site Map.

## Recommended same-instance workflow

Use this when the Source and Destination Site Maps live in the same Orbit instance and recordings can be
moved with Orbit's native UI.

1. [Orbit-native Site Map split](workflows/orbit-native-map-split.md) — operator-facing,
   end-to-end procedure.
2. [Operation journal template](workflows/orbit-native-operation-journal-template.md) — private
   exact-ID move, draft, Save, and verification record.
3. [Orbit Site Map Assistant extension](../extension/orbit-graph-repair/README.md) — installation and
   controls.
4. [Orbit Site Map Assistant knowledge base](orbit-map-assistant-knowledge-base.md) — identity model,
   native draft semantics, safety gates, AI-agent contract, and troubleshooting.
5. [Orbit-native recording move research](orbit-native-recording-move.md) — detailed evidence,
   rollback findings, and backup-level analysis.
6. [Orbit editor extension research](orbit-editor-extension-research.md) — observed Orbit editor
   capabilities and the extension boundary.

This workflow keeps recording and waypoint identity native to Orbit. The extension compares the
result Site Maps with an immutable B0 backup and creates reviewable, unsaved native Orbit drafts. It
never presses **Save**.

## Experimental offline clone workflow

Use this only when the same-instance native move is not suitable and a separately identified
GraphNav/Autowalk clone is intentionally being tested.

1. [Experimental offline map clone workflow](workflows/offline-map-clone.md) — command sequence and
   stop conditions.
2. [Architecture and data guarantees](architecture.md) — clone, identity, payload, and transport
   model.
3. [Compatibility and support levels](compatibility.md) — evidence-based support matrix.
4. [Orbit Walk import findings](orbit-walk-import-findings.md) — controlled import evidence.
5. [Same-instance import checklist](import-poc.md) — disposable import and runtime gates.

This path remaps or reuses GraphNav/Walk identities and packages a `.walk.zip`. It is experimental
and is not the default way to split a Site Map in the same Orbit instance.

## Shared references

- [Python package workflow boundaries](../src/spot_graphnav_map_forge/README.md)
- [Privacy guide](privacy.md)
- [Security policy](../SECURITY.md)
- [Contributing guide](../CONTRIBUTING.md)
- [Changelog](../CHANGELOG.md)

## Private artifacts

Backups, baselines, reconciliation guides, workspaces, Walk archives, screenshots, browser logs,
and exact site identifiers are private operational artifacts. Keep them under ignored
`workspace/`, `output/`, or another private location. Do not commit or attach them to public issues.
