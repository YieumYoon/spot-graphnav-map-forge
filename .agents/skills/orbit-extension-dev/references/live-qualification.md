# Live Orbit qualification

Use this procedure only after `scripts/check_editor_extension.py` passes.

## Acquire the browser

- Treat the user's configured Chrome session as shared mutable state.
- Confirm no other agent is qualifying an Orbit branch.
- Use the Chrome/Computer Use capability attached to the existing session. Do not open a separate
  browser that cannot reach Orbit.
- Keep private Orbit URLs, map names, IDs, screenshots, and logs out of the repository.

## Reload and re-inject

1. Save the source files.
2. Run `uv run python scripts/set_editor_build.py dev`.
3. Open `chrome://extensions`.
4. Find **Orbit Site Map Editor** and activate **Reload** once.
5. Return to the existing Orbit Site Map editor tab and reload it once.
6. Wait for Orbit and the extension panel to settle.
7. Confirm the panel displays the expected `version_name` development label.
8. Confirm exactly one editor panel is present and inspect the extension error list.

Reloading the unpacked extension invalidates content scripts already injected into an Orbit page.
Reloading Orbit second is what injects the new content scripts and page bridge.

## Test in safety tiers

1. Read-only smoke:
   - panel tabs render;
   - the live Site Map identity and counts settle;
   - Explore and overlays respond;
   - the changed control is present;
   - no unexpected Orbit draft or Undo entry appears.
2. Feature-specific read-only behavior:
   - use synthetic inputs or non-mutating selection where possible;
   - capture exact observed behavior without storing private IDs.
3. Native mutation only when explicitly authorized:
   - confirm the intended Site Map and exact target count;
   - ensure no unrelated unsaved draft exists;
   - create one unsaved native draft;
   - verify exact read-back and exactly one new Orbit Undo step;
   - never press **Save**;
   - use the verified newest Undo entry or Orbit Cancel to restore the prior state;
   - reload only after confirming no draft remains.

## Recover failures

- **Extension context invalidated**: stop interacting with the stale panel, reload Orbit once, and
  confirm the development label.
- **Wrong or missing label**: reload the extension, then Orbit, in that order.
- **Duplicate panel**: stop, reload Orbit, and confirm only one extension version is enabled.
- **Unverified mutation**: do not Save and do not create another mutation. Inspect the exact target
  and newest Undo entry. Restore only when the rollback is unambiguous.
- **Orbit or adapter mismatch**: stop live mutation testing and update the qualification evidence
  before changing the adapter.

## Release the browser

Restore the transient manifest label with:

```bash
uv run python scripts/set_editor_build.py release --keep-version
```

Run the full static gate and leave Orbit with no extension-created unsaved draft.
