# Orbit-native Site Map split journal

Copy this template to a private ignored workspace. Record exact IDs; names are notes only.

## Operation

| Field | Value |
| --- | --- |
| operation ID | `<private-operation-id>` |
| operator | `<name-or-team>` |
| date/time | `<ISO-8601>` |
| Orbit version | `<exact-version>` |
| extension version | `<exact-version>` |
| Source Site Map name / ID | `<private-name>` / `<exact-site-map-id>` |
| Destination Site Map name / ID | `<private-name>` / `<exact-site-map-id>` |

## Evidence

| Artifact | Private path | SHA-256 | Created |
| --- | --- | --- | --- |
| B0 backup | `<path>` | `<sha256>` | `<ISO-8601>` |
| B0 graph baseline | `<path>` | `<sha256>` | `<ISO-8601>` |
| optional final backup | `<path>` | `<sha256>` | `<ISO-8601>` |

## Recording plan

| Sequence | Exact recording ID | Display label | Expected waypoints | Final state |
| ---: | --- | --- | ---: | --- |
| 1 | `<exact-recording-id>` | `<label>` | `<count>` | `<Source absent / Destination selected>` |

## Boundary review

| Check | Expected | Reviewed |
| --- | ---: | --- |
| Source Site Map waypoint total | `<count>` | `<yes/no>` |
| Destination Site Map waypoint total | `<count>` | `<yes/no>` |
| manually created edges internal to Source | `<count>` | `<yes/no>` |
| manually created edges internal to Destination | `<count>` | `<yes/no>` |
| Site Map boundary edges | `<count>` | `<yes/no>` |
| Source / Destination crosswalks | `<count>` / `<count>` | `<yes/no>` |
| unsupported dependency blockers | `<count>` | `<yes/no>` |

## Recording moves

Add one row after each Orbit transition.

| Time | Site Map ID | Recording ID | Action | Draft reviewed | Saved | Membership verified |
| --- | --- | --- | --- | --- | --- | --- |
| `<time>` | `<source-site-map-id>` | `<recording-id>` | remove | yes | yes | absent |
| `<time>` | `<destination-site-map-id>` | `<recording-id>` | add | yes | yes | selected |

## Initial comparison

| Site Map ID | Waypoints | Recordings | Connect | Archive | Edge settings | Crosswalk settings | Site Map boundary | Ignored extra WP / edges |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `<site-map-id>` | `<count>` | `<count>` | `<count>` | `<count>` | `<count>` | `<count>` | `<count>` | `<count>` / `<count>` |

## Native drafts

The extension verifies a draft; only the operator can verify **Save**.

| Time | Site Map ID | Operation | Reviewed | One Undo step | Read-back | Saved | Refresh result |
| --- | --- | --- | ---: | --- | ---: | --- | --- |
| `<time>` | `<site-map-id>` | Archive | `<count>` | yes | `<count>` | `<yes/no>` | `<remaining>` |
| `<time>` | `<site-map-id>` | Connect | 1 | yes | 1 | `<yes/no>` | `<remaining>` |
| `<time>` | `<site-map-id>` | Crosswalk edge settings | `<count>` | yes | `<count>` | `<yes/no>` | `<remaining>` |
| `<time>` | `<site-map-id>` | Remaining edge settings | `<count>` | yes | `<count>` | `<yes/no>` | `<remaining>` |

## Intentional differences

Every nonzero final item needs a reason.

| Site Map ID | Type | Exact IDs or count | Reason | Approved by |
| --- | --- | --- | --- | --- |
| `<site-map-id>` | Site Map boundary | `<pair or count>` | endpoints assigned to different Site Maps | `<operator>` |
| `<site-map-id>` | ignored extra scope | `<count>` | newer recording absent from B0 | `<operator>` |
| `<site-map-id>` | deferred repair | `<exact IDs>` | `<reason>` | `<operator>` |

## Final verification

- [ ] Source and Destination recording membership matches the plan.
- [ ] No unexplained Connect, Archive, or edge-settings items remain.
- [ ] Site Map boundary edges match the approved split.
- [ ] Ignored extra scope matches known newer recordings.
- [ ] Every draft was saved or intentionally canceled.
- [ ] Required final backup was created.
- [ ] This journal and its evidence remain private.

## Incident notes

```text
<timestamp> <site-map-id> <observation> <decision> <result>
```
