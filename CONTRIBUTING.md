# Contributing

Thank you for helping improve Spot GraphNav Map Forge. The project prioritizes deterministic
offline behavior, fail-closed compatibility, and strict handling of operational data.

## Before opening an issue

- Read the [compatibility matrix](docs/compatibility.md).
- Run the failing command again with a synthetic fixture when possible.
- Remove site names, local paths, UUIDs, coordinates, counts, timestamps, screenshots, and images.
- Never attach a real backup, Walk, workspace, audit report, clone manifest, or generated archive.

Use private security reporting for vulnerabilities or bugs that cannot be described safely in a
public issue. See [SECURITY.md](SECURITY.md).

## Development setup

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run python scripts/check_release_hygiene.py
```

## Pull requests

1. Keep source backups read-only.
2. Keep upload and other network writes outside the CLI.
3. Add or update synthetic tests for every behavior change.
4. Preserve unknown wire fields unless a documented compatibility rule requires otherwise.
5. Fail closed when a dependency cannot be represented faithfully.
6. Update the support matrix and changelog when evidence levels change.
7. Run the complete verification suite before requesting review.

## Synthetic data only

Fixtures must use generic names such as `Example Map`, `zone-a`, and `source-waypoint`. UUID-shaped
values must be obviously synthetic and must not be copied from a real deployment. Do not include:

- company, facility, building, asset, robot, person, or map names;
- production action names or inspection questions;
- exact production counts, coordinates, timestamps, or IDs;
- customer screenshots or images;
- credentials, hostnames, IP addresses, tokens, or local user paths;
- generated `.tar`, `.walk`, or `.walk.zip` files.

## Licensing

By submitting a contribution, you agree that it may be distributed under the Apache License 2.0.
Do not copy Boston Dynamics SDK example code or third-party source into this repository unless its
license and attribution requirements have been reviewed and documented.
