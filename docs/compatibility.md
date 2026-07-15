# Compatibility and support levels

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
| Network writes | None |

The public protobuf package version and the deployed product versions are separate compatibility
inputs. The pinned `bosdyn-api==5.1.4` dependency does not imply compatibility with other Orbit,
robot, or tablet versions. Only the all-5.1.8 product environment above has reached the UI import
gate. Always run `inspect`, `audit`, `validate`, and `validate-walk` before a disposable import test.

## Support matrix

| Capability | Level | Evidence and boundary |
| --- | --- | --- |
| Backup inventory and Site Map listing | Supported | Offline parsing |
| Final Site Map waypoint reconstruction | Supported | Offline structural and semantic checks |
| Active/manual/loop-closure edges | Supported | Final site-level edge records and validation |
| Polygon and halo selection | Supported | Deterministic offline planning |
| Unanchored/remnant cleanup | Supported | Exact exclusions and protected dependencies recorded in plan/audit |
| Waypoint and snapshot cloning | Supported | Closed references and source-ID leak checks |
| Ordinary action payloads | Supported alpha | Offline semantic checks and Orbit 5.1.8 UI import |
| Waypoint-relative action targets | Supported alpha | Exact observed payload copy and UI placement |
| DAQ and alignment images | Supported alpha | Offline slot matching and Orbit 5.1.8 UI display |
| Dock definitions | Experimental | Offline conversion only until UI/runtime/re-export gates pass |
| Explicit relocalization | Experimental | Offline public-message equivalence only |
| Opaque tablet metadata | Experimental | Optional unchanged copy from a user-supplied template |
| Waypoint recording-session relabel | Experimental | Public metadata rewrite verified offline; product display remains an import gate |
| Explicit orphan triggered-record exclusion | Supported audit control | Exact ID, eligible parent, and reason required; no migration claim |
| Triggered AI inspection migration | Unsupported | Public Walk cannot encode the private parent trigger |
| Existing missions and schedules | Unsupported | Intentionally not cloned |
| Site View panorama history | Unsupported | Historical imagery is not available as a transferable action |
| Inspection results and anomalies | Unsupported | No source-to-clone history reassignment |
| Identity-preserving move/split | Unsupported | Clone mode creates new identities |
| Automatic upload or source mutation | Unsupported | Explicitly outside the safety model |

## Fail-closed behavior

The tool stops rather than claiming compatibility when:

- a selected triggered AI inspection cannot be represented;
- required snapshots or action images are missing;
- identity rewriting leaves a source token in a cloned payload;
- dock references cross the selection boundary;
- opaque Target defaults conflict;
- an archive or output path violates structural expectations.

The only triggered-record exception is an exact, reason-bearing plan exclusion for an operator-
confirmed incomplete or orphaned record. It remains visible in the audit and clone manifest.

Changing a waypoint recording-session label does not assign a fleet-manager recording UUID. The
server controls any recording identity created during manual import.

Warnings are not success claims. Read every validation report before import.

## Reporting compatibility

Public reports should contain only:

- tool version;
- public SDK package version;
- generalized product major/minor version;
- the command that failed with private paths replaced by placeholders;
- a synthetic reproduction whenever possible.

Never publish a real backup, Walk, screenshot, map/action name, UUID, coordinate, hostname, or
inspection image.
