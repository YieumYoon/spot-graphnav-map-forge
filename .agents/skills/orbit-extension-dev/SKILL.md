---
name: orbit-extension-dev
description: Develop and qualify the repo's unpacked Orbit Site Map Editor Chrome extension. Use when changing files under extension/orbit-site-map-editor, adding editor features, handling Extension context invalidated failures, reloading the unpacked extension and Orbit page, updating extension releases or development build labels, validating live Orbit behavior, or coordinating parallel feature branches and worktrees.
---

# Orbit Extension Development

Keep code work parallel and deterministic while serializing access to the user's live Orbit Chrome
session.

## Start

1. Read the repository `AGENTS.md`, `extension/orbit-site-map-editor/README.md`, and the relevant
   portion of `docs/orbit-site-map-editor-qualification.md`.
2. Inspect `git status`, the current branch, and the worktree path. Do not switch a shared checkout
   for another agent.
3. Classify the task:
   - code-only: implement and run static qualification;
   - live read-only: also reload and inspect Orbit;
   - live mutation: require explicit user scope and a rollback plan.
4. For parallel work or integration, read
   [parallel-development.md](references/parallel-development.md).

## Implement

1. Keep the change inside the owning module where possible:
   - base Explore, Inspector, overlay, and bridge lifecycle: `content.js`;
   - Select workspace: `workspace-select.js`, `selection.js`, and Select-specific wiring;
   - Edit workspace: `workspace-edit.js`, `workflow.js`, and Edit-specific wiring;
   - Validate workspace: `workspace-validate.js`, `validation.js`, and Validate-specific wiring;
   - Walk workspace: `walk-ui.js` and `walk-planner.js`;
   - native Orbit adapter: `page-bridge.js`, changed only with exact read-back tests.
2. Add or update automated tests with the implementation.
3. Do not import or reintroduce code from `archive/offline-clone-2026-07`. Active Python support
   remains read-only and is checked by `scripts/check_active_boundary.py`.
4. Do not hardcode the displayed extension version. Read it through
   `OrbitSiteMapEditorExtensionContext.getVersionLabel()`.
5. Use a descriptive development label before a live reload:

   ```bash
   uv run python scripts/set_editor_build.py dev
   ```

   Do not commit a transient `version_name`. Restore it after live qualification:

   ```bash
   uv run python scripts/set_editor_build.py release --keep-version
   ```

6. Change the numeric release only at an integration or release boundary:

   ```bash
   uv run python scripts/set_editor_build.py release 0.6.0
   ```

   Update current-release documentation in the same change.

## Qualify

Run the targeted gate during implementation:

```bash
uv run python scripts/check_editor_extension.py
```

Run the full gate before handoff, commit, or merge:

```bash
uv run python scripts/check_editor_extension.py --full
```

For a live check, read and follow
[live-qualification.md](references/live-qualification.md). Use Chrome or Computer Use only after
the static gate passes. Keep the exact order: extension reload, Orbit reload, build-label check,
read-only smoke test, then any explicitly authorized mutation.

## Finish

1. Restore a transient development label.
2. Run the full gate again.
3. Inspect `git diff --check` and `git status`.
4. Record new Orbit-version or adapter evidence in the qualification document without including
   private URLs or IDs.
5. Report the branch, release/build label, checks run, live actions performed, and rollback state.
   Never claim a live test that was not actually executed.
