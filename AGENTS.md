# Developer environment

- Use `uv` for Python commands and dependency management.
- Never mutate a source backup or a source map.
- Network/server writes must be a separate explicit command with dry-run as the default.
- Do not commit backups, generated `.walk` archives, credentials, or private keys.
- Treat `archive/offline-clone-2026-07` as immutable historical evidence. Do not base active
  features on its clone, remap, bundle, Walk-generation, or import paths.
- Active Python code is read-only support for `inspect`, `graph-baseline`, and `reconcile-graph`.
  Run `uv run python scripts/check_active_boundary.py` after changing it.

## Orbit Site Map Editor development

- Use the repo-local `$orbit-extension-dev` skill for changes under
  `extension/orbit-site-map-editor`.
- Run `uv run python scripts/check_editor_extension.py` before live testing and add `--full`
  before handoff or merge.
- Treat the user's Orbit Chrome session as a single-owner resource. Parallel agents may edit and
  run static tests in separate Git worktrees, but only one agent may reload or operate Orbit at a
  time.
- Reload the unpacked extension before reloading the Orbit tab. Confirm the panel build label
  before testing behavior.
- Live tests are read-only by default. Never press Orbit **Save**. Create a native unsaved draft
  only when the user explicitly places that mutation in scope, verify one Undo step, and restore
  the prior state before handoff.
- Keep production URLs, Site Map IDs, waypoint IDs, screenshots, and browser logs out of commits.
