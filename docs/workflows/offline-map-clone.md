# Experimental offline Site Map clone

This workflow selects a polygon from a backup, rebuilds its GraphNav data, and exports an Autowalk
`.walk.zip`.

Use the [Orbit-native Site Map split](orbit-native-map-split.md) when recordings can be moved in
the same Orbit instance. An exported Walk is not an Orbit-supported Site Map copy.

## When to use it

Use this path only when:

- a separate GraphNav/Walk object is required;
- polygon selection is required instead of whole-recording assignment;
- a disposable import and compatibility test are acceptable;
- loss of Orbit lifecycle and history associations is understood.

Review the [compatibility matrix](../compatibility.md) before continuing.

## 1. Prepare

```bash
uv run spot-map-forge inspect /path/to/backup.tar

uv run spot-map-forge prepare /path/to/backup.tar \
  --map '<Site-Map-name-or-ID>' \
  --out workspace/example
```

The source backup remains read-only. Keep the workspace private.

## 2. Select a zone

Use the loopback editor:

```bash
uv run spot-map-forge serve workspace/example
```

Or provide a polygon:

```bash
uv run spot-map-forge plan workspace/example \
  --polygon examples/zone.example.json \
  --zone-name zone-a \
  --halo-hops 1 \
  --out workspace/example/zone-a.plan.json
```

The halo keeps nearby graph neighbors to avoid cutting directly at a junction.

## 3. Audit

```bash
uv run spot-map-forge audit workspace/example \
  --plan workspace/example/zone-a.plan.json \
  --out workspace/example/zone-a.audit.json
```

Before building, review cut edges, disconnected remnants, Actions, Docks, panorama state,
triggered records, field-3 SiteEdge policy, and identity mode.

## 4. Build and validate

```bash
uv run spot-map-forge build workspace/example \
  --plan workspace/example/zone-a.plan.json \
  --out output/zone-a

uv run spot-map-forge validate output/zone-a
```

## 5. Export

```bash
uv run spot-map-forge export-walk output/zone-a \
  --out output/zone-a.walk.zip \
  --name zone-a

uv run spot-map-forge validate-walk output/zone-a.walk.zip
```

Import only into a disposable test environment.

## Identity modes

| Mode | Use |
| --- | --- |
| `clone` | deterministic new identities; default experimental mode |
| `orbit-native` | Orbit-shaped IDs for representation tests |
| `preserve` | original IDs for same-instance lifecycle tests |

Use a new `--clone-name` when revisions must coexist:

```bash
uv run spot-map-forge build workspace/example \
  --plan workspace/example/zone-a.plan.json \
  --clone-name zone-a-v2 \
  --out output/zone-a-v2
```

`orbit-native` IDs are test identities; they were not allocated by Orbit's recording service.
`preserve` can couple update, deduplication, and deletion behavior with the source. Do not combine
it with recording relabeling.

## Stop conditions

Stop before import if:

- references do not close or required snapshots are missing;
- the audit has an unsupported dependency;
- a Dock crosses the zone boundary;
- identity or transport policy differs from the reviewed plan.

Stop after import if:

- Orbit changes or deduplicates the source unexpectedly;
- the new Site Map does not materialize;
- required Actions or Docks are missing;
- robot behavior or re-export differs from the audited payload.

Upload completion alone does not prove Site Map, Walk, Action, Dock, or robot compatibility.

## References

- [Architecture](../architecture.md)
- [Compatibility](../compatibility.md)
- [Orbit Walk import findings](../orbit-walk-import-findings.md)
- [Disposable import checklist](../import-poc.md)
- [Privacy](../privacy.md)
