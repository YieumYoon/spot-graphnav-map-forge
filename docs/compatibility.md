# Compatibility and support levels

## Workflow support

| Workflow | Current support | Required gate |
| --- | --- | --- |
| Orbit-native recording split plus Map Assistant | Supported alpha for the verified Orbit 5.1.8 environment | exact-ID plan, B0 baseline, operator review, native Save, final Refresh/backup |
| Offline GraphNav/Walk clone and import | Experimental | structural and semantic validation plus disposable UI/runtime/re-export gates |

The extension workflow is the recommended same-instance split because Orbit retains native
recording and waypoint identity and creates every persisted edit through its own editor. This does
not make the in-page adapter cross-version stable: requalify it after every Orbit upgrade.

The offline clone workflow remains available for cases that intentionally require a separately
identified polygon-selected archive. It is not a substitute for an official map-copy operation.

The backup adapter reads an observed private archive format, not a vendor-published interchange
schema. Compatibility is therefore scoped by evidence, not assumed from a filename or product
version.

## Environment

| Component | Current project baseline |
| --- | --- |
| Python | 3.11+ |
| Public protobuf dependency | `bosdyn-api==5.1.4` |
| Verified Orbit version | 5.1.8 |
| Verified Spot robot version | 5.1.8 |
| Verified tablet version | 5.1.8 |
| Import mechanism | Manual `.walk.zip` upload through Orbit 5.1.8 |
| Network writes | None from the CLI or extension; Orbit Save remains an explicit operator action |

The public protobuf package version and the deployed product versions are separate compatibility
inputs. The pinned `bosdyn-api==5.1.4` dependency does not imply compatibility with other Orbit,
robot, or tablet versions. Only the all-5.1.8 product environment above has reached the UI import
gate, including a minimal DAQ-first profile whose Walk mission, action, and available Dock were
materialized. That mission was later executed on the robot and completed its PTZ capture. Always
run `inspect`, `audit`, `validate`, and `validate-walk` before a disposable import test.

## Support matrix

| Capability | Level | Evidence and boundary |
| --- | --- | --- |
| Backup inventory and Site Map listing | Supported | Offline parsing |
| Final Site Map waypoint reconstruction | Supported | Offline structural and semantic checks |
| Active/manual/loop-closure edges | Supported | Final site-level edge records and validation |
| Orbit field-3 edge UI settings | Experimental | Explicit include/exclude choice; verify and reapply environment/travel settings in Orbit after import |
| Polygon and halo selection | Supported | Deterministic offline planning |
| Unanchored/remnant cleanup | Supported | Exact exclusions and protected dependencies recorded in plan/audit |
| Waypoint and snapshot cloning | Supported | Closed references and source-ID leak checks |
| Orbit-native-shaped identity probe | Experimental | Same audited graph with tablet-shaped GraphNav IDs and deterministic UUIDv4-shaped Orbit object IDs; disposable Orbit import required |
| Ordinary action payloads | Supported alpha | Offline semantic checks, Orbit 5.1.8 UI import, and one minimal PTZ capture runtime |
| Waypoint-relative action targets | Supported alpha | Exact observed payload copy and UI placement |
| DAQ and alignment images | Supported alpha | Offline slot matching, Orbit 5.1.8 UI display, and one PTZ DAQ runtime capture |
| Dock definitions | Experimental | Offline conversion plus Orbit 5.1.8 UI materialization for a minimal DAQ-first profile; runtime and re-export gates remain |
| Recording-compatible Dock/Action profile | Experimental | Minimal DAQ mission reached PTZ runtime; full UUIDv4 profile reached Orbit UI; public-CLI equivalence, Dock runtime, and re-export remain |
| Explicit relocalization | Experimental | Offline public-message equivalence only |
| Opaque tablet metadata | Experimental | Optional unchanged copy from a user-supplied template |
| Waypoint recording-session relabel | Experimental | Public metadata rewrite verified offline; product display remains an import gate |
| Explicit orphan triggered-record exclusion | Supported audit control | Exact ID, eligible parent, and reason required; no migration claim |
| Triggered AI inspection migration | Unsupported | Public Walk cannot encode the private parent trigger |
| Existing missions and schedules | Unsupported | Intentionally not cloned |
| Site View panorama history | Unsupported | Historical imagery is not available as a transferable action |
| Inspection results and anomalies | Unsupported | No source-to-clone history reassignment |
| Identity-preserving move/split | Unsupported | Clone mode creates new identities |
| Same-instance native recording move | Supported alpha on Orbit 5.1.8 | Recording, waypoint IDs, byte-identical waypoint snapshots, and all three candidate connections survived a controlled round trip; two SiteWaypoint wrappers and three SiteEdge override wrappers did not, so the extension/B0 reconciliation step is mandatory |
| Orbit Site Map Assistant | Supported alpha on Orbit 5.1.8 | Exact-ID inspection and comparison, native Connect/Archive, 112-edge crosswalk restore, and a 2,316-edge remaining-settings restore were verified as separate one-step drafts and saved by the operator; no REST or automatic Save; requalify after upgrades |
| Shared waypoint/SiteElement identity archive | Experimental | Offline validation only; new Walk container, server-assigned recording identity, and same-instance lifecycle POC required |
| Automatic upload or source mutation | Unsupported | Explicitly outside the safety model |

## Fail-closed behavior

The tool stops rather than claiming compatibility when:

- a selected triggered AI inspection cannot be represented;
- required snapshots or action images are missing;
- identity rewriting leaves a source token in a cloned payload;
- dock references cross the selection boundary;
- a recording template route, referenced Anchor, or anchored Dock object cannot be matched exactly;
- opaque Target defaults conflict;
- a workspace field-3 edge policy does not match the saved plan;
- an archive or output path violates structural expectations.

The only triggered-record exception is an exact, reason-bearing plan exclusion for an operator-
confirmed incomplete or orphaned record. It remains visible in the audit and clone manifest.

Changing a waypoint recording-session label does not assign a fleet-manager recording UUID. The
server controls any recording identity created during manual import.

Preserve identity mode rejects waypoint recording-session relabeling. It does not claim that Orbit
will create an independent copy, preserve inspection history, or safely garbage-collect shared
objects when either Site Map or SiteWalk is deleted.

Orbit-native mode validates representation and reference closure only. Its UUIDv4-shaped IDs are
deterministic test identities, not proof that a robot recording service created the objects or that
Orbit will register Docks and Actions from them.

A controlled minimal import retained a UUIDv5-identified Graph while using a fresh UUIDv4 Walk and
DAQ Element with matching membership metadata. Orbit materialized its Walk mission, DAQ action, and
available Dock. A later full-map control also materialized Localize, Sleep, DAQ, and Dock when all
three Element IDs were UUIDv4. Changing only the actionless Localize Element ID to UUIDv5 allowed
the upload stage to complete but prevented Site Map materialization. A separate UUIDv5 DAQ control
succeeded, so Orbit-targeted exports should use UUIDv4 for navigation-only Localize Elements and
must not treat upload completion as import success.

Warnings are not success claims. Read every validation report before import.

The full controlled evidence chain and the distinction between upload completion and server-side
materialization are documented in [orbit-walk-import-findings.md](orbit-walk-import-findings.md).
The separate [Orbit-native recording move workflow](orbit-native-recording-move.md) documents the
same-instance exact-ID state machine, rollback rules, and remaining live compatibility gates.

## Reporting compatibility

Public reports should contain only:

- tool version;
- public SDK package version;
- generalized product major/minor version;
- the command that failed with private paths replaced by placeholders;
- a synthetic reproduction whenever possible.

Never publish a real backup, Walk, screenshot, map/action name, UUID, coordinate, hostname, or
inspection image.
