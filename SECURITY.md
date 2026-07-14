# Security policy

## Supported versions

Only the latest alpha release and the default branch receive security fixes.

## Reporting a vulnerability

Use the repository host's private vulnerability-reporting feature. Do not open a public issue for
a vulnerability that could expose a backup, map, action, image, local path, credential, or product
instance.

Include only:

- the affected project version;
- a minimal synthetic reproduction;
- the security impact;
- suggested mitigations, if known.

Do not attach production artifacts. Maintainers will coordinate a private disclosure and release
timeline through the hosting platform.

## Security boundaries

- The CLI is offline and does not upload to a robot or fleet manager.
- The source backup is opened read-only.
- The editor binds to loopback by default and serves only the selected workspace.
- Workspaces and generated archives remain sensitive local artifacts.
- Structural validation does not make an archive safe to run on a robot; normal operational and
  physical safety procedures still apply.

Changes that add telemetry, remote binding, upload, source mutation, or automatic cleanup require a
separate threat review and explicit user consent.
