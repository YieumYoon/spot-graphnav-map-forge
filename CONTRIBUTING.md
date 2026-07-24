# Contributing

Thank you for improving the Orbit Site Map extensions and their read-only support tools.

## Before opening an issue

- Read the [compatibility matrix](docs/compatibility.md).
- Reproduce the problem with synthetic data whenever possible.
- Remove site names, paths, IDs, coordinates, counts, timestamps, screenshots, logs, and images.
- Never attach a real backup, baseline, reconciliation report, or browser capture.

Use private security reporting when a problem cannot be described safely in public.

## Development setup

```bash
uv sync --extra dev
uv run python scripts/check_active_boundary.py
uv run python scripts/check_editor_extension.py --full --release
uv build --offline
uv run python scripts/check_release_hygiene.py dist/*.tar.gz dist/*.whl
```

Use the repo-local `$orbit-extension-dev` Skill for extension changes.

## Pull requests

1. Keep source backups immutable.
2. Keep Orbit Save, uploads, private REST writes, and other product persistence outside the code.
3. Add synthetic tests for every behavior change.
4. Fail closed when identity, current state, native validation, read-back, or Undo cannot be proven.
5. Update compatibility evidence and the changelog when a boundary changes.
6. Keep active Python imports inside the allowlisted read-only package boundary.
7. Do not modify the archived offline-clone branch or tag.

## Live Orbit tests

Static checks run first. The live Chrome session has one owner at a time, and live checks are
read-only by default. A disposable native draft requires explicit scope, exact read-back, one Undo
step, and restoration before handoff. Never press Orbit **Save** during qualification.

## Synthetic data only

Do not include company, facility, person, robot, production map, recording, Action, or asset names;
real UUIDs or exact counts; customer screenshots; credentials; hostnames; private IP addresses; or
local absolute paths.

## Licensing

Contributions are distributed under Apache License 2.0. Do not copy third-party or vendor example
code without reviewing and documenting its license.
