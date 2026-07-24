# Security policy

## Supported versions

Only the latest alpha release and the default branch receive security fixes. The
`archive/offline-clone-2026-07` refs are immutable historical records and receive no fixes.

## Reporting a vulnerability

Use the repository host's private vulnerability-reporting feature. Include the affected version,
a minimal synthetic reproduction, impact, and suggested mitigation. Do not attach production
backups, screenshots, browser logs, IDs, map data, credentials, or local paths.

## Active security boundaries

- Extensions run only on the configured Orbit page and do not add telemetry.
- Orbit remains the only writer and the operator remains the only Save authority.
- Native mutation assistance fails closed without exact identity, validation, read-back, and Undo.
- The CLI reads backups locally and has no product upload or network-write command.
- Source backups are never modified.
- Private artifacts are excluded from Git but are not encrypted by this project.

Changes that add telemetry, remote communication, automatic Save, private REST writes, generated
map import, or source mutation require a separate threat review and explicit user consent.

## Archived research

The offline clone archive generated importable payloads and is intentionally outside the supported
security model. Do not report archived behavior as an active vulnerability unless the same path is
reachable from the default branch.
