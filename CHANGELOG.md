# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed

- Made the Migration Assistant report a mutation whose dispatch may have succeeded but whose
  read-back failed as explicitly unverified, latch that state in the panel, and block later edits
  until the operator clears it.
- Proved the one native **Undo** step per accepted batch with the undo-stack depth instead of the
  draft edit index, which can advance by more than one.
- Closed active-boundary gaps: prefix matching for blocked network modules, recursive package-file
  allowlisting, rejection of dynamic import escape hatches, and the complete archived-symbol list.
- Made the release hygiene check inspect symlink members inside tar and zip distributions.

### Changed

- Recorded that the two extensions stay separate no-build packages that duplicate adapter
  contracts locally and compare them with cross-extension behavior tests.
- Replaced extension source-text assertions with behavior tests that load the real modules, and
  replaced the copied manifest listing with structural invariants.
- Shared one Chrome extension version validator between the build-label and qualification scripts.
- Reduced repository hygiene scanning in CI from five runs per push to one.
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
