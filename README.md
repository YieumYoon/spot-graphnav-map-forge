# Orbit Site Map Extensions

Extend Orbit's native **Site Map** editor without importing, rewriting, or directly mutating
GraphNav data outside Orbit.

| Component | Purpose | Persistence boundary |
| --- | --- | --- |
| [Orbit Site Map Editor](extension/orbit-site-map-editor/README.md) | Search, selection, overlays, validation, reviewed editing, and Site View coverage planning | Creates native unsaved Orbit drafts; never presses **Save** |
| [Orbit Site Map Migration Assistant](extension/orbit-graph-repair/README.md) | Restore edges and edge settings after recordings are moved between Site Maps | Compares B0 with live Orbit and creates native unsaved drafts |
| `spot-map-forge` | Read-only backup inventory, B0 baseline creation, and optional final-backup comparison | Reads private local files and writes JSON reports only |

The extensions deliberately leave validation, Undo/Redo, persistence, and server-side lifecycle
ownership with Orbit. This lowers data-compatibility risk compared with externally generated
imports, but the in-page adapter can still break when Orbit changes. Requalify after every Orbit
upgrade.

This is an independent community project. It is not affiliated with or endorsed by Boston
Dynamics.

## Install the Site Map Editor

In the Chrome profile that opens Orbit:

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Select **Load unpacked**.
4. Choose `extension/orbit-site-map-editor`.
5. Reload the Orbit Site Map editor.

The Editor adds five workspaces:

- **Explore** — live catalog search, Inspector, and overlays;
- **Select** — exact-ID selections and graph/recording/spatial tools;
- **Edit** — reviewed Connect, Archive, and edge-setting drafts;
- **Validate** — topology, reachability, path, settings, and crosswalk checks;
- **Walk** — mission-independent Site View coverage planning.

It never presses Orbit **Save**.

## Split a Site Map

When recordings must move between Site Maps in the same Orbit instance, use the
[Orbit-native Site Map split](docs/workflows/orbit-native-map-split.md). Orbit performs every
recording assignment and every saved edit.

Create the immutable private B0 baseline before changing **Select recordings**:

```bash
uv sync --extra dev

uv run spot-map-forge inspect /path/to/B0.tar

uv run spot-map-forge graph-baseline /path/to/B0.tar \
  --map '<Source-Site-Map-name-or-ID>' \
  --out workspace/source-site-map/graph-baseline.json
```

Load `extension/orbit-graph-repair`, move recordings with Orbit, then use the baseline to review
Connect, Archive, Site Map boundary, and edge-settings items. The extension may create a native
draft only after review; the operator remains responsible for **Save**.

An optional final backup can be compared without using an intermediate reconstruction workspace:

```bash
uv run spot-map-forge reconcile-graph \
  workspace/source-site-map/graph-baseline.json \
  /path/to/final-backup.tar \
  --after-map '<Result-Site-Map-name-or-ID>' \
  --out workspace/source-site-map/final-reconciliation.json
```

## Compatibility and safety

- Never modify a source backup.
- Never call private Orbit REST endpoints to write map data.
- Never automatically press **Save**.
- Use exact Site Map, recording, waypoint, and edge endpoint IDs.
- Review the affected objects and require one native Undo step for each draft batch.
- Disable mutation controls when the Orbit adapter cannot prove the expected capability.
- Keep backups, baselines, screenshots, browser logs, and generated reports out of Git.

See [compatibility](docs/compatibility.md), [architecture](docs/architecture.md), and
[privacy](docs/privacy.md).

## Archived offline clone research

The former polygon clone, ID remapping, GraphNav bundle builder, `.walk.zip` generator, and import
probes are no longer part of the supported or packaged product. They are preserved for historical
research at:

- branch `archive/offline-clone-2026-07`;
- annotated tag `archive/offline-clone-2026-07`;
- summary [docs/legacy/offline-clone.md](docs/legacy/offline-clone.md).

Do not treat that archive as an Orbit-supported Site Map copy or migration path.

## Development

```bash
uv run python scripts/check_active_boundary.py
uv run python scripts/check_editor_extension.py --full --release
uv build --offline
uv run python scripts/check_release_hygiene.py dist/*.tar.gz dist/*.whl
```

Use the repo-local `$orbit-extension-dev` Skill for extension changes. Parallel code work belongs
in separate Worktrees; the live Orbit Chrome session has one owner at a time.

See [documentation](docs/README.md), [contributing](CONTRIBUTING.md), and
[security](SECURITY.md).

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

Boston Dynamics, Spot, Orbit, GraphNav, and Autowalk are trademarks of their respective owners.
