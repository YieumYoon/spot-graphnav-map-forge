# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

- Made the Orbit Site Map Editor the primary product and retained the Migration Assistant as a
  separate same-instance workflow.
- Reduced the Python CLI to read-only `inspect`, `graph-baseline`, and `reconcile-graph` commands.
- Changed final-backup reconciliation to consume the immutable B0 baseline directly instead of a
  clone workspace.
- Added an active-boundary check that rejects legacy generators, commands, imports, and network
  clients from the active Python package.

### Archived

- Preserved the offline GraphNav/Walk clone, ID-remapping, bundle-generation, Walk-packaging,
  loopback-editor, and import-probe implementation at branch and annotated tag
  `archive/offline-clone-2026-07`.
- Removed that implementation and its operator workflow from the default branch and package.

### Added

- Orbit Site Map Editor with Explore, Select, Edit, Validate, and Walk workspaces.
- Orbit Site Map Migration Assistant for B0-based Connect, Archive, and edge-settings recovery.
- Repo-local extension development Skill, transient build labels, deterministic qualification,
  and serialized live-Chrome rules.
- Read-only backup inventory, effective topology, B0 baseline, and final-backup comparison.

## [0.1.0a1] - Archived

The experimental offline clone research state is preserved at
`archive/offline-clone-2026-07`. See [the archive summary](docs/legacy/offline-clone.md).
