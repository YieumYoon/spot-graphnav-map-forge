# Developer environment

- Use `uv` for Python commands and dependency management.
- Never mutate a source backup or a source map.
- Network/server writes must be a separate explicit command with dry-run as the default.
- Do not commit backups, generated `.walk` archives, credentials, or private keys.
