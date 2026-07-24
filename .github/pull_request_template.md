## Summary

Describe the user-visible change and its compatibility boundary.

## Verification

- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run pytest`
- [ ] `uv run python scripts/check_active_boundary.py`
- [ ] `uv run python scripts/check_release_hygiene.py .`

## Data hygiene

- [ ] Tests and examples use only synthetic data.
- [ ] No backup, baseline, report, Walk, screenshot, browser log, UUID, coordinate, hostname,
      credential, absolute local path, or customer/site identifier is included.
- [ ] No active code imports or reintroduces archived clone/import behavior.
