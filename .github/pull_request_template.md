## Summary

Describe the user-visible change and its compatibility boundary.

## Verification

- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run pytest`
- [ ] `uv run python scripts/check_release_hygiene.py .`

## Data hygiene

- [ ] Tests and examples use only synthetic data.
- [ ] No backup, Walk, workspace, screenshot, inspection result, UUID, coordinate, hostname,
      credential, absolute local path, or customer/site identifier is included.
- [ ] Any new unsupported or experimental behavior is documented.
