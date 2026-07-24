# Site View coverage route planning

Use the Orbit Site Map Editor extension's **Walk** tab to plan a new SiteWalk route that visits
every operational waypoint reachable from a start or Dock. The planner does not read or reuse an
existing SiteWalk, mission route, or SiteElement.

## Operator workflow

1. Open the target **Site Map** editor and wait for its full waypoint count.
2. Open **Walk** and select **Refresh Site View**.
3. Optionally select one start waypoint and choose **Use Orbit selection**. Otherwise a Dock, then
   the largest active component, is used.
4. To omit a region, select its waypoints with the extension's **Select** tools. Return to **Walk**
   and choose **Add Orbit selection to exclusions**. Exact IDs can also be entered one per line.
5. Keep **Reachable from start / Dock — active edges** for normal planning. Use **Audit all
   components** only when separate localization boundaries are acceptable.
6. Keep **Navigation-only targets** unless the installed Orbit version requires the short-Sleep
   compatibility fallback. Add intentional Sleeps only when the operation actually needs to wait.
7. Select **Plan coverage**.
8. Review:
   - red `×` markers for explicit exclusions;
   - the colored planned route;
   - numbered `#1, #2, …` route targets in the list and on the map;
   - disconnected, repeated-visit, Site View gap, and constrained-edge warnings.
9. Download the private JSON plan. Re-plan after any waypoint or edge change.

The sequence numbers belong to execution targets, not every intermediate waypoint. A single
NavigateRoute target may cover many waypoint visits.

## Exclusion semantics

Exclusions are exact waypoint IDs. Before planning, the extension removes every excluded waypoint
and every active edge incident to it. This can split a connected component.

The result reports separately:

- explicitly excluded waypoints;
- remaining waypoints outside the selected active component;
- Site View-eligible waypoints in each category;
- active edges removed by the exclusions.

An excluded start, unknown ID, or exclusion of every waypoint is rejected. The downloaded plan
retains the exact exclusion list so the decision is auditable.

## Route guarantee

For each selected connected component, the planner builds the effective active graph, computes a
deterministic minimum spanning tree, and walks every branch. Repeated waypoint and edge visits are
allowed. It verifies that every required waypoint appears and every consecutive pair has a current
active edge.

This proves graph adjacency and route coverage only. It does not prove robot traversability or
visual/thermal capture. Edges with stairs, direction, mobility, path-following, alternate-route, or
Area callback settings remain qualification items.

Disconnected components cannot form one continuous NavigateRoute without another edge.
**Audit all components** therefore produces separate routes and relocalization boundaries.

## Route targets and Actions

- a navigation target can cover many intermediate waypoints;
- an intentional Sleep becomes one proposed Action;
- no Action is generated merely because a waypoint is visited;
- the compatibility fallback adds a short Sleep only to required navigation targets;
- target sequence numbers are contiguous and define the proposed execution order.

The output schema is `orbit_site_view_coverage_plan_v2`. It is a local dry-run JSON plan: the
extension does not create, upload, import, update, or save a SiteWalk.

## Compatibility and privacy

- Exact IDs belong to the current Orbit instance and Site Map.
- A plan is stale after a waypoint or edge edit.
- Materialization requires a new SiteWalk through a supported Orbit or public API workflow.
- Requalify the extension after an Orbit upgrade.
- Coverage JSON contains private operational topology and exact IDs; keep it out of Git.
