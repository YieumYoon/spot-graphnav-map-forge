# Documentation

The active project is Extension-first: Orbit owns every recording assignment, editor draft,
Undo/Redo operation, validation result, and persisted Save.

## Orbit Site Map Editor

1. [Editor extension](../extension/orbit-site-map-editor/README.md) — installation and operator
   controls.
2. [Feature research](orbit-site-map-editor-assistant-feature-research.md) — scoped editor backlog
   and safety contract.
3. [Qualification](orbit-site-map-editor-qualification.md) — anonymized evidence and the
   post-upgrade runtime checklist.
4. [Site View coverage planning](orbit-sitewalk-coverage-planning.md) — active-reachable waypoint
   coverage and optional short-Sleep compatibility fallback.

## Orbit-native Site Map split

1. [Site Map split workflow](workflows/orbit-native-map-split.md) — operator-facing procedure.
2. [Operation journal](workflows/orbit-native-operation-journal-template.md) — private exact-ID
   move, draft, Save, and verification record.
3. [Migration Assistant](../extension/orbit-graph-repair/README.md) — B0 reconciliation controls.
4. [Engineering knowledge base](orbit-map-assistant-knowledge-base.md) — topology, native draft,
   rollback, and AI-agent boundaries.
5. [Recording move evidence](orbit-native-recording-move.md) — controlled same-instance findings.

## Shared boundaries

- [Architecture](architecture.md)
- [Compatibility](compatibility.md)
- [Python read-only module boundaries](../src/spot_graphnav_map_forge/README.md)
- [Privacy](privacy.md)
- [Security](../SECURITY.md)
- [Contributing](../CONTRIBUTING.md)
- [Changelog](../CHANGELOG.md)

## Archived research

The offline GraphNav/Walk clone implementation is not shipped or supported on the default branch.
Its purpose, findings, and immutable Git references are recorded in
[legacy/offline-clone.md](legacy/offline-clone.md).

## Private artifacts

Backups, baselines, reconciliation reports, screenshots, browser logs, and exact site identifiers
are private operational artifacts. Keep them under ignored `workspace/`, `output/`, or another
private location. Do not commit or attach them to public issues.
