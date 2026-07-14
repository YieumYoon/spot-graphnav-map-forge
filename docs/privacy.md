# Privacy and artifact handling

Fleet-manager backups and generated map artifacts can contain sensitive operational data. Treat
them as private even when the tool itself is open source.

## Data the tool may encounter

- Site Map, recording, action, dock, and mission names;
- stable internal IDs and source-to-clone mappings;
- floor-plan geometry and GraphNav coordinates;
- inspection configuration and capture targets;
- DAQ, alignment, and other embedded images;
- local absolute file paths;
- timestamps and operational metadata;
- credential or log directories elsewhere in a source backup.

The tool intentionally avoids extracting credential directories. It cannot make the rest of a map
non-sensitive.

## Local artifacts

| Path or file | Sensitivity |
| --- | --- |
| source backup `.tar` | Private source data; read-only |
| `workspace/` | Original names, IDs, layout, source path, and action inventory |
| `*.audit.json` | Original dependency names and IDs |
| clone bundle | Source-to-clone mappings and cloned action images |
| `.walk.zip` | New map topology, action definitions, and images |
| screenshots/browser logs | May expose map layout, site names, paths, or IDs |

All of these are excluded from Git by default. Exclusion is not encryption or access control.

## Repository rules

- Use only synthetic fixtures and obviously synthetic identifiers.
- Never commit a real `.tar`, `.walk`, `.walk.zip`, image, screenshot, browser log, or generated
  manifest.
- Do not put real site, company, person, robot, map, action, building, or asset names in tests,
  examples, documentation, issues, or commit messages.
- Do not publish exact production counts, coordinates, timestamps, or UUIDs.
- Replace local paths with placeholders such as `/path/to/backup.tar`.
- Review `git status` and run `scripts/check_release_hygiene.py` before every public push.

## No telemetry or upload

The project contains no telemetry client and no product upload command. The local editor serves
static assets and workspace data on loopback. If you change either boundary, document the data flow
and obtain explicit user consent before adding any network write.

## Reporting a bug

Use a synthetic reproduction. If a bug cannot be reproduced synthetically, use the hosting
platform's private security-reporting channel and share the smallest redacted structure possible.
Do not attach a production artifact to a public issue.

## Cleanup

After verification, remove private workspaces, generated archives, screenshots, and browser logs
according to your organization's retention policy. The tool does not delete source backups or
automatically clean output directories.
