# Privacy and artifact handling

Orbit backups and live editor state can reveal sensitive operational data even when no mutation is
performed.

## Sensitive data

- Site Map, recording, waypoint, edge, Action, Dock, Area, and mission names;
- stable internal IDs and graph relationships;
- floor-plan geometry, coordinates, and traversal settings;
- inspection configuration and images;
- timestamps, browser logs, hostnames, and local paths.

## Private local artifacts

| Artifact | Contents |
| --- | --- |
| source backup `.tar` | Private source data; always read-only |
| `graph-baseline.json` | Exact Site Map, recording, waypoint, edge, and settings identities |
| reconciliation report | Exact differences and affected endpoint IDs |
| extension preset/plan export or operation journal | Selections, findings, plans, and live object details |
| screenshots or browser logs | Layout, names, IDs, paths, and UI state |

Keep these under ignored `workspace/`, `output/`, or another access-controlled location. Git
exclusion is not encryption.

## Repository rules

- Use only synthetic fixtures and obviously synthetic identifiers.
- Never commit a real backup, baseline, report, screenshot, browser log, image, credential, or
  generated Walk artifact.
- Do not publish exact production counts, coordinates, timestamps, IDs, names, or local paths.
- Build the wheel and sdist, then run `scripts/check_release_hygiene.py` on those release
  artifacts before every public release.

## No telemetry, upload, or automatic Save

The active project has no telemetry, generated-map upload, private REST write, or automatic Save
path. If any of those boundaries changes, document the data flow, perform a threat review, and
obtain explicit user consent.

## Archived artifacts

The historical offline-clone code could create workspaces, bundles, and Walk archives. Those
artifacts remain private even though the generator is no longer active. The archive refs contain
source and synthetic tests only, not production artifacts.

## Reporting a bug

Use a synthetic reproduction. If that is impossible, use private security reporting and share the
smallest redacted structure necessary.
