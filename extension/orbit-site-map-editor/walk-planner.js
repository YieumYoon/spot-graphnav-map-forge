(() => {
  "use strict";

  const SCHEMA_VERSION = "orbit_site_view_coverage_plan_v2";
  const DEFAULT_SCOPE = "reachable";
  const DEFAULT_MAX_ROUTE_WAYPOINTS = 150;
  const MIN_ROUTE_WAYPOINTS = 2;
  const MAX_ROUTE_WAYPOINTS = 1000;

  function edgeKey(from, to) {
    return from < to ? `${from}|${to}` : `${to}|${from}`;
  }

  function finitePosition(value) {
    return Boolean(
      value &&
      Number.isFinite(value.x) &&
      Number.isFinite(value.y),
    );
  }

  function edgeWeight(edge, waypointById) {
    if (Number.isFinite(edge?.length) && edge.length > 0) return edge.length;
    const from = waypointById.get(edge?.from)?.position;
    const to = waypointById.get(edge?.to)?.position;
    if (finitePosition(from) && finitePosition(to)) {
      const dz =
        Number.isFinite(from.z) && Number.isFinite(to.z)
          ? from.z - to.z
          : 0;
      const distance = Math.hypot(from.x - to.x, from.y - to.y, dz);
      if (Number.isFinite(distance) && distance > 0) return distance;
    }
    return 1;
  }

  function inactiveEdge(edge) {
    const status = String(edge?.status || "").toLowerCase();
    return Boolean(
      edge?.archived ||
      edge?.disabled ||
      edge?.deactivated ||
      edge?.active === false ||
      status === "archived" ||
      status === "disabled" ||
      status === "deactivated"
    );
  }

  function buildGraph(snapshot) {
    const waypointById = new Map();
    const adjacency = new Map();
    const edgeByKey = new Map();

    for (const waypoint of snapshot?.waypoints || []) {
      const id = typeof waypoint?.id === "string" ? waypoint.id : "";
      if (!id || waypointById.has(id)) continue;
      waypointById.set(id, waypoint);
      adjacency.set(id, []);
    }

    for (const sourceEdge of snapshot?.edges || []) {
      if (inactiveEdge(sourceEdge)) continue;
      const from = typeof sourceEdge?.from === "string" ? sourceEdge.from : "";
      const to = typeof sourceEdge?.to === "string" ? sourceEdge.to : "";
      if (
        !from ||
        !to ||
        from === to ||
        !waypointById.has(from) ||
        !waypointById.has(to)
      ) continue;
      const key = edgeKey(from, to);
      const edge = {
        ...sourceEdge,
        id: String(sourceEdge.id || key),
        from,
        to,
        key,
        weight: edgeWeight(sourceEdge, waypointById),
      };
      const existing = edgeByKey.get(key);
      if (
        existing &&
        (
          existing.weight < edge.weight ||
          existing.weight === edge.weight && existing.id.localeCompare(edge.id) <= 0
        )
      ) continue;
      edgeByKey.set(key, edge);
    }

    for (const edge of edgeByKey.values()) {
      adjacency.get(edge.from).push({ to: edge.to, edge });
      adjacency.get(edge.to).push({ to: edge.from, edge });
    }
    for (const neighbors of adjacency.values()) {
      neighbors.sort((left, right) =>
        left.to.localeCompare(right.to) ||
        left.edge.id.localeCompare(right.edge.id)
      );
    }
    return { waypointById, adjacency, edgeByKey };
  }

  function filteredPlanningSnapshot(snapshot, excludedWaypointIds) {
    const excluded = new Set(excludedWaypointIds);
    return {
      ...snapshot,
      waypoints: (snapshot?.waypoints || []).filter(
        (waypoint) => !excluded.has(waypoint?.id),
      ),
      edges: (snapshot?.edges || []).filter(
        (edge) => !excluded.has(edge?.from) && !excluded.has(edge?.to),
      ),
    };
  }

  function connectedComponents(snapshotOrGraph) {
    const graph = snapshotOrGraph?.waypointById
      ? snapshotOrGraph
      : buildGraph(snapshotOrGraph);
    const seen = new Set();
    const components = [];

    for (const start of [...graph.waypointById.keys()].sort()) {
      if (seen.has(start)) continue;
      seen.add(start);
      const waypointIds = [];
      const queue = [start];
      for (let index = 0; index < queue.length; index += 1) {
        const waypointId = queue[index];
        waypointIds.push(waypointId);
        for (const neighbor of graph.adjacency.get(waypointId) || []) {
          if (seen.has(neighbor.to)) continue;
          seen.add(neighbor.to);
          queue.push(neighbor.to);
        }
      }
      waypointIds.sort();
      const waypointSet = new Set(waypointIds);
      const edgeIds = [...graph.edgeByKey.values()]
        .filter((edge) => waypointSet.has(edge.from) && waypointSet.has(edge.to))
        .map((edge) => edge.id)
        .sort();
      components.push({
        id: waypointIds[0],
        waypointIds,
        edgeIds,
        waypointCount: waypointIds.length,
        edgeCount: edgeIds.length,
        isolated: waypointIds.length === 1,
        hasCycle: edgeIds.length >= waypointIds.length,
      });
    }
    return components.sort((left, right) =>
      right.waypointCount - left.waypointCount ||
      left.id.localeCompare(right.id)
    );
  }

  class DisjointSet {
    constructor(ids) {
      this.parent = new Map(ids.map((id) => [id, id]));
      this.rank = new Map(ids.map((id) => [id, 0]));
    }

    find(id) {
      let root = id;
      while (this.parent.get(root) !== root) root = this.parent.get(root);
      let current = id;
      while (current !== root) {
        const parent = this.parent.get(current);
        this.parent.set(current, root);
        current = parent;
      }
      return root;
    }

    union(left, right) {
      let leftRoot = this.find(left);
      let rightRoot = this.find(right);
      if (leftRoot === rightRoot) return false;
      const leftRank = this.rank.get(leftRoot);
      const rightRank = this.rank.get(rightRoot);
      if (
        leftRank < rightRank ||
        leftRank === rightRank && leftRoot.localeCompare(rightRoot) > 0
      ) {
        [leftRoot, rightRoot] = [rightRoot, leftRoot];
      }
      this.parent.set(rightRoot, leftRoot);
      if (leftRank === rightRank) this.rank.set(leftRoot, leftRank + 1);
      return true;
    }
  }

  function minimumSpanningTree(graph, waypointIds) {
    if (waypointIds.length <= 1) return [];
    const waypointSet = new Set(waypointIds);
    const edges = [...graph.edgeByKey.values()]
      .filter((edge) => waypointSet.has(edge.from) && waypointSet.has(edge.to))
      .sort((left, right) =>
        left.weight - right.weight ||
        left.key.localeCompare(right.key) ||
        left.id.localeCompare(right.id)
      );
    const disjointSet = new DisjointSet(waypointIds);
    const tree = [];
    for (const edge of edges) {
      if (!disjointSet.union(edge.from, edge.to)) continue;
      tree.push(edge);
      if (tree.length === waypointIds.length - 1) break;
    }
    if (tree.length !== waypointIds.length - 1) {
      throw new Error("component_not_connected");
    }
    return tree;
  }

  function treeAdjacency(waypointIds, treeEdges) {
    const adjacency = new Map(waypointIds.map((id) => [id, []]));
    for (const edge of treeEdges) {
      adjacency.get(edge.from).push({ to: edge.to, edge });
      adjacency.get(edge.to).push({ to: edge.from, edge });
    }
    for (const neighbors of adjacency.values()) {
      neighbors.sort((left, right) =>
        left.to.localeCompare(right.to) ||
        left.edge.id.localeCompare(right.edge.id)
      );
    }
    return adjacency;
  }

  function rootedTree(tree, startWaypointId) {
    const parent = new Map([[startWaypointId, ""]]);
    const parentEdge = new Map();
    const distance = new Map([[startWaypointId, 0]]);
    const stack = [startWaypointId];
    while (stack.length) {
      const waypointId = stack.pop();
      const neighbors = [...(tree.get(waypointId) || [])].reverse();
      for (const neighbor of neighbors) {
        if (parent.has(neighbor.to)) continue;
        parent.set(neighbor.to, waypointId);
        parentEdge.set(neighbor.to, neighbor.edge);
        distance.set(
          neighbor.to,
          distance.get(waypointId) + neighbor.edge.weight,
        );
        stack.push(neighbor.to);
      }
    }
    return { parent, parentEdge, distance };
  }

  function farthestWaypoint(distance) {
    let result = "";
    let maximum = -Infinity;
    for (const [waypointId, value] of distance.entries()) {
      if (
        value > maximum ||
        value === maximum && waypointId.localeCompare(result) < 0
      ) {
        result = waypointId;
        maximum = value;
      }
    }
    return result;
  }

  function treeWalk(tree, startWaypointId, endWaypointId, returnToStart) {
    const rooted = rootedTree(tree, startWaypointId);
    const pathChild = new Map();
    if (!returnToStart) {
      let current = endWaypointId;
      while (current && current !== startWaypointId) {
        const parent = rooted.parent.get(current);
        if (!parent) throw new Error("coverage_end_not_reachable");
        pathChild.set(parent, current);
        current = parent;
      }
    }

    const orderedChildren = (waypointId) => {
      const children = (tree.get(waypointId) || [])
        .filter((neighbor) => rooted.parent.get(neighbor.to) === waypointId);
      const finalPathChild = pathChild.get(waypointId);
      return children.sort((left, right) => {
        const leftLast = left.to === finalPathChild ? 1 : 0;
        const rightLast = right.to === finalPathChild ? 1 : 0;
        return leftLast - rightLast || left.to.localeCompare(right.to);
      });
    };

    const waypointWalk = [startWaypointId];
    const edgeWalk = [];
    const stack = [{
      waypointId: startWaypointId,
      parentId: "",
      arrivalEdge: null,
      returnOnExit: false,
      children: orderedChildren(startWaypointId),
      childIndex: 0,
    }];

    while (stack.length) {
      const frame = stack[stack.length - 1];
      if (frame.childIndex < frame.children.length) {
        const child = frame.children[frame.childIndex];
        frame.childIndex += 1;
        waypointWalk.push(child.to);
        edgeWalk.push({
          id: child.edge.id,
          from: frame.waypointId,
          to: child.to,
          storedFromWaypoint: child.edge.from,
          storedToWaypoint: child.edge.to,
          key: child.edge.key,
          distanceMeters: child.edge.weight,
        });
        stack.push({
          waypointId: child.to,
          parentId: frame.waypointId,
          arrivalEdge: child.edge,
          returnOnExit:
            returnToStart || pathChild.get(frame.waypointId) !== child.to,
          children: orderedChildren(child.to),
          childIndex: 0,
        });
        continue;
      }
      stack.pop();
      if (!frame.returnOnExit || !frame.arrivalEdge) continue;
      waypointWalk.push(frame.parentId);
      edgeWalk.push({
        id: frame.arrivalEdge.id,
        from: frame.waypointId,
        to: frame.parentId,
        storedFromWaypoint: frame.arrivalEdge.from,
        storedToWaypoint: frame.arrivalEdge.to,
        key: frame.arrivalEdge.key,
        distanceMeters: frame.arrivalEdge.weight,
      });
    }
    return { waypointWalk, edgeWalk };
  }

  function clampRouteWaypointLimit(value) {
    if (!Number.isInteger(value)) return DEFAULT_MAX_ROUTE_WAYPOINTS;
    return Math.max(
      MIN_ROUTE_WAYPOINTS,
      Math.min(MAX_ROUTE_WAYPOINTS, value),
    );
  }

  function routeCheckpoints(
    waypointWalk,
    edgeWalk,
    {
      maxRouteWaypoints = DEFAULT_MAX_ROUTE_WAYPOINTS,
      checkpointMode = "navigation_only",
      sleepDurationSeconds = 1,
    } = {},
  ) {
    const limit = clampRouteWaypointLimit(maxRouteWaypoints);
    const sleepSeconds =
      Number.isFinite(sleepDurationSeconds) && sleepDurationSeconds >= 0
        ? sleepDurationSeconds
        : 1;
    const mode =
      checkpointMode === "sleep" || checkpointMode === "compatibility_sleep"
        ? "compatibility_sleep"
        : "navigation_only";
    const checkpoints = [];
    if (!waypointWalk.length) return checkpoints;
    if (waypointWalk.length === 1) {
      checkpoints.push({
        index: 0,
        kind: "component_entry",
        targetWaypointId: waypointWalk[0],
        routeWaypointIds: [waypointWalk[0]],
        routeEdges: [],
        action: mode === "compatibility_sleep"
          ? { kind: "sleep", durationSeconds: sleepSeconds }
          : null,
      });
      return checkpoints;
    }
    let start = 0;
    while (start < waypointWalk.length - 1) {
      const end = Math.min(start + limit - 1, waypointWalk.length - 1);
      checkpoints.push({
        index: checkpoints.length,
        kind: "navigate_route",
        targetWaypointId: waypointWalk[end],
        routeWaypointIds: waypointWalk.slice(start, end + 1),
        routeEdges: edgeWalk.slice(start, end),
        action: mode === "compatibility_sleep"
          ? { kind: "sleep", durationSeconds: sleepSeconds }
          : null,
      });
      start = end;
    }
    return checkpoints;
  }

  function chooseComponentStart(component, preferredStart, dockWaypointIds) {
    if (preferredStart && component.waypointIds.includes(preferredStart)) {
      return preferredStart;
    }
    const dock = component.waypointIds.find((id) => dockWaypointIds.has(id));
    return dock || component.waypointIds[0];
  }

  function planComponent(graph, component, options, componentIndex) {
    const dockWaypointIds = new Set(options.dockWaypointIds || []);
    const startWaypointId = chooseComponentStart(
      component,
      options.startWaypointId,
      dockWaypointIds,
    );
    const treeEdges = minimumSpanningTree(graph, component.waypointIds);
    const tree = treeAdjacency(component.waypointIds, treeEdges);
    const rooted = rootedTree(tree, startWaypointId);
    const endWaypointId = options.returnToStart
      ? startWaypointId
      : options.endWaypointId &&
          component.waypointIds.includes(options.endWaypointId)
        ? options.endWaypointId
        : farthestWaypoint(rooted.distance);
    const route = treeWalk(
      tree,
      startWaypointId,
      endWaypointId,
      options.returnToStart,
    );
    const visitedUnique = new Set(route.waypointWalk);
    const checkpoints = routeCheckpoints(route.waypointWalk, route.edgeWalk, options);
    const hasDock = component.waypointIds.some((id) => dockWaypointIds.has(id));
    const estimatedDistanceMeters = route.edgeWalk.reduce(
      (total, edge) => total + edge.distanceMeters,
      0,
    );
    const reviewEdgeKeys = [...new Set(
      route.edgeWalk
        .map((edge) => graph.edgeByKey.get(edge.key))
        .filter((edge) => {
          const settings = edge?.settings || {};
          return Boolean(
            settings.stairs ||
            settings.directionConstraint ||
            settings.overrideMobilityParams ||
            settings.pathFollowingMode ||
            settings.disableAlternateRouteFinding ||
            Object.keys(settings.areaCallbacks || {}).length
          );
        })
        .map((edge) => edge.key),
    )].sort();
    return {
      componentIndex,
      componentId: component.id,
      startWaypointId,
      endWaypointId,
      returnToStart: Boolean(options.returnToStart),
      requiredWaypointIds: [...component.waypointIds],
      waypointWalk: route.waypointWalk,
      edgeWalk: route.edgeWalk,
      visitedUniqueCount: visitedUnique.size,
      repeatedVisitCount: route.waypointWalk.length - visitedUnique.size,
      traversalCount: route.edgeWalk.length,
      estimatedDistanceMeters,
      spanningTreeDistanceMeters: treeEdges.reduce(
        (total, edge) => total + edge.weight,
        0,
      ),
      checkpointCount: checkpoints.length,
      checkpoints,
      hasDock,
      requiresManualLocalization: !hasDock,
      requiresRelocalizationBeforeStart: componentIndex > 0,
      isolated: component.isolated,
      reviewEdgeKeys,
    };
  }

  function dockWaypointInComponent(component, dockWaypointIds) {
    return component.waypointIds.find((id) => dockWaypointIds.has(id)) || "";
  }

  function selectCoverageScope(
    components,
    scope,
    startWaypointId,
    dockWaypointIds = [],
  ) {
    const requested = scope === "all" || scope === "largest"
      ? scope
      : DEFAULT_SCOPE;
    if (!components.length) {
      return {
        scope: requested,
        components: [],
        anchorWaypointId: "",
        anchorSource: "none",
      };
    }
    const dockIds = new Set(dockWaypointIds);
    const startComponent = startWaypointId
      ? components.find((component) =>
          component.waypointIds.includes(startWaypointId)
        )
      : null;
    if (requested === "all") {
      const selected = startComponent
        ? [
            startComponent,
            ...components.filter((component) => component !== startComponent),
          ]
        : [...components];
      const dockWaypointId = dockWaypointInComponent(selected[0], dockIds);
      return {
        scope: requested,
        components: selected,
        anchorWaypointId:
          startWaypointId && startComponent
            ? startWaypointId
            : dockWaypointId || selected[0].waypointIds[0],
        anchorSource:
          startWaypointId && startComponent
            ? "start_waypoint"
            : dockWaypointId
              ? "dock"
              : "largest_component_fallback",
      };
    }
    if (requested === "largest") {
      const component = components[0];
      const dockWaypointId = dockWaypointInComponent(component, dockIds);
      const startIsInComponent = Boolean(
        startWaypointId && component.waypointIds.includes(startWaypointId),
      );
      return {
        scope: requested,
        components: [component],
        anchorWaypointId:
          startIsInComponent
            ? startWaypointId
            : dockWaypointId || component.waypointIds[0],
        anchorSource:
          startIsInComponent
            ? "start_waypoint"
            : dockWaypointId
              ? "dock"
              : "largest_component_fallback",
      };
    }
    if (startComponent) {
      if (!startComponent.edgeCount) {
        throw new Error("start_waypoint_has_no_active_edges");
      }
      return {
        scope: requested,
        components: [startComponent],
        anchorWaypointId: startWaypointId,
        anchorSource: "start_waypoint",
      };
    }
    const dockComponent = components.find(
      (component) =>
        component.edgeCount && dockWaypointInComponent(component, dockIds),
    );
    if (dockComponent) {
      return {
        scope: requested,
        components: [dockComponent],
        anchorWaypointId: dockWaypointInComponent(dockComponent, dockIds),
        anchorSource: "dock",
      };
    }
    const activeComponent = components.find((component) => component.edgeCount);
    if (!activeComponent) throw new Error("site_map_has_no_active_edges");
    return {
      scope: requested,
      components: [activeComponent],
      anchorWaypointId: activeComponent.waypointIds[0],
      anchorSource: "largest_component_fallback",
    };
  }

  function reconstructCheckpointWalk(checkpoints) {
    const waypointIds = [];
    const routeEdges = [];
    for (const checkpoint of checkpoints || []) {
      const chunk = checkpoint.routeWaypointIds || [];
      if (!chunk.length) continue;
      if (!waypointIds.length) waypointIds.push(...chunk);
      else waypointIds.push(...chunk.slice(1));
      routeEdges.push(...(checkpoint.routeEdges || []));
    }
    return { waypointIds, routeEdges };
  }

  function validateComponentPlan(graph, component) {
    const errors = [];
    const warnings = [];
    const required = new Set(component.requiredWaypointIds || []);
    const waypointWalk = component.waypointWalk || [];
    const edgeWalk = component.edgeWalk || [];

    if (!waypointWalk.length) errors.push("empty_waypoint_walk");
    if (edgeWalk.length !== Math.max(0, waypointWalk.length - 1)) {
      errors.push("edge_waypoint_count_mismatch");
    }
    for (const id of required) {
      if (!graph.waypointById.has(id)) errors.push(`required_waypoint_missing:${id}`);
      if (!waypointWalk.includes(id)) errors.push(`required_waypoint_unvisited:${id}`);
    }
    for (const id of waypointWalk) {
      if (!required.has(id)) errors.push(`foreign_waypoint_in_walk:${id}`);
    }
    for (let index = 0; index < waypointWalk.length - 1; index += 1) {
      const from = waypointWalk[index];
      const to = waypointWalk[index + 1];
      const activeEdge = graph.edgeByKey.get(edgeKey(from, to));
      if (!activeEdge) {
        errors.push(`non_traversable_step:${index}:${from}:${to}`);
        continue;
      }
      const plannedEdge = edgeWalk[index];
      if (
        plannedEdge?.from !== from ||
        plannedEdge?.to !== to ||
        plannedEdge?.key !== activeEdge.key
      ) errors.push(`edge_step_mismatch:${index}`);
    }
    if (waypointWalk[0] !== component.startWaypointId) {
      errors.push("start_waypoint_mismatch");
    }
    if (waypointWalk.at(-1) !== component.endWaypointId) {
      errors.push("end_waypoint_mismatch");
    }
    if (
      component.returnToStart &&
      component.startWaypointId !== component.endWaypointId
    ) errors.push("closed_walk_end_mismatch");

    const reconstructed = reconstructCheckpointWalk(component.checkpoints);
    if (
      reconstructed.waypointIds.length !== waypointWalk.length ||
      reconstructed.waypointIds.some((id, index) => id !== waypointWalk[index])
    ) errors.push("checkpoint_waypoint_reconstruction_mismatch");
    if (
      reconstructed.routeEdges.length !== edgeWalk.length ||
      reconstructed.routeEdges.some(
        (edge, index) =>
          edge.from !== edgeWalk[index]?.from ||
          edge.to !== edgeWalk[index]?.to,
      )
    ) errors.push("checkpoint_edge_reconstruction_mismatch");
    if (component.requiresRelocalizationBeforeStart) {
      warnings.push("relocalization_required_before_component");
    }
    if (component.requiresManualLocalization) {
      warnings.push("component_has_no_known_dock");
    }
    if (component.isolated) warnings.push("isolated_waypoint_has_no_route_edge");
    return {
      valid: errors.length === 0,
      errors: [...new Set(errors)],
      warnings: [...new Set(warnings)],
    };
  }

  function validateCoveragePlan(snapshot, plan) {
    const excludedWaypointIds = plan?.exclusions?.waypointIds || [];
    const excluded = new Set(excludedWaypointIds);
    const graph = buildGraph(filteredPlanningSnapshot(
      snapshot,
      excludedWaypointIds,
    ));
    const components = (plan?.components || []).map((component) => ({
      componentIndex: component.componentIndex,
      ...validateComponentPlan(graph, component),
    }));
    const executionErrors = [];
    for (const component of plan?.components || []) {
      for (const waypointId of [
        ...(component.requiredWaypointIds || []),
        ...(component.waypointWalk || []),
      ]) {
        if (excluded.has(waypointId)) {
          executionErrors.push(
            `${component.componentIndex}:excluded_waypoint_in_route:${waypointId}`,
          );
        }
      }
    }
    if (plan?.executionSequence) {
      for (const component of plan.components || []) {
        const entries = plan.executionSequence.entries.filter(
          (entry) => entry.componentIndex === component.componentIndex,
        );
        const reconstructed = reconstructCheckpointWalk(entries);
        if (
          reconstructed.waypointIds.length !== component.waypointWalk.length ||
          reconstructed.waypointIds.some(
            (id, index) => id !== component.waypointWalk[index],
          )
        ) {
          executionErrors.push(
            `${component.componentIndex}:execution_waypoint_reconstruction_mismatch`,
          );
        }
        if (
          reconstructed.routeEdges.length !== component.edgeWalk.length ||
          reconstructed.routeEdges.some(
            (edge, index) =>
              edge.from !== component.edgeWalk[index]?.from ||
              edge.to !== component.edgeWalk[index]?.to,
          )
        ) {
          executionErrors.push(
            `${component.componentIndex}:execution_edge_reconstruction_mismatch`,
          );
        }
      }
    }
    return {
      valid:
        components.every((component) => component.valid) &&
        executionErrors.length === 0,
      components,
      errors: [
        ...components.flatMap((component) =>
          component.errors.map((error) => `${component.componentIndex}:${error}`)
        ),
        ...executionErrors,
      ],
      warnings: components.flatMap((component) =>
        component.warnings.map((warning) =>
          `${component.componentIndex}:${warning}`
        )
      ),
    };
  }

  function siteViewCoverage(
    snapshot,
    plan,
    sitePanoWaypoints = [],
  ) {
    const mapWaypointIds = new Set(
      (snapshot?.waypoints || []).map((waypoint) => waypoint.id).filter(Boolean),
    );
    const eligibleSettingIds = [...new Set(
      (sitePanoWaypoints || [])
        .filter((item) => item?.allowCaptureVisual)
        .map((item) => String(item?.waypointId || ""))
        .filter(Boolean),
    )].sort();
    const eligibleWaypointIds = eligibleSettingIds.filter(
      (id) => mapWaypointIds.has(id),
    );
    const missingMapWaypointIds = eligibleSettingIds.filter(
      (id) => !mapWaypointIds.has(id),
    );
    const plannedVisited = new Set(
      (plan?.components || []).flatMap(
        (component) => component.waypointWalk || [],
      ),
    );
    const plannedCoveredEligibleWaypointIds = eligibleWaypointIds.filter(
      (id) => plannedVisited.has(id),
    );
    const explicitlyExcluded = new Set(
      plan?.exclusions?.waypointIds || [],
    );
    const explicitlyExcludedEligibleWaypointIds = eligibleWaypointIds.filter(
      (id) => explicitlyExcluded.has(id),
    );
    const disconnectedEligibleWaypointIds = eligibleWaypointIds.filter(
      (id) => !plannedVisited.has(id) && !explicitlyExcluded.has(id),
    );
    const excludedEligibleWaypointIds = eligibleWaypointIds.filter(
      (id) => !plannedVisited.has(id),
    );
    return {
      basis: "site_waypoint_pano_settings_and_planned_active_route",
      provesCapture: false,
      eligibleWaypointIds,
      eligibleWaypointCount: eligibleWaypointIds.length,
      plannedCoveredEligibleWaypointIds,
      plannedCoveredEligibleWaypointCount:
        plannedCoveredEligibleWaypointIds.length,
      explicitlyExcludedEligibleWaypointIds,
      explicitlyExcludedEligibleWaypointCount:
        explicitlyExcludedEligibleWaypointIds.length,
      disconnectedEligibleWaypointIds,
      disconnectedEligibleWaypointCount:
        disconnectedEligibleWaypointIds.length,
      excludedEligibleWaypointIds,
      excludedEligibleWaypointCount: excludedEligibleWaypointIds.length,
      missingMapWaypointIds,
    };
  }

  function scheduleActions(plan, supplementalSleepActions = []) {
    const firstVisit = new Map();
    for (const component of plan?.components || []) {
      for (const [visitIndex, waypointId] of component.waypointWalk.entries()) {
        if (firstVisit.has(waypointId)) continue;
        firstVisit.set(waypointId, {
          componentIndex: component.componentIndex,
          visitIndex,
        });
      }
    }

    const supplemental = supplementalSleepActions.map((action, index) => {
      const waypointId = String(action?.waypointId || "");
      const duration =
        Number.isFinite(action?.durationSeconds) &&
        action.durationSeconds >= 0
          ? action.durationSeconds
          : null;
      const visit = firstVisit.get(waypointId);
      return {
        name: String(action?.name || `Sleep ${index + 1}`),
        waypointId,
        actionKind: "sleep",
        actionDurationSeconds: duration,
        componentIndex: visit?.componentIndex ?? null,
        routeVisitIndex: visit?.visitIndex ?? null,
        schedulable: Boolean(visit && duration !== null),
        reason: !visit
          ? "waypoint_outside_planned_scope"
          : duration === null
            ? "invalid_sleep_duration"
            : "",
      };
    });
    const schedulable = supplemental
      .filter((item) => item.schedulable)
      .sort((left, right) =>
        left.componentIndex - right.componentIndex ||
        left.routeVisitIndex - right.routeVisitIndex ||
        left.name.localeCompare(right.name)
      )
      .map((item, index) => ({ ...item, recommendedSequence: index + 1 }));
    return {
      basis: "first_visit_of_intentional_sleep_waypoint_in_coverage_route",
      scheduled: schedulable,
      unscheduled: supplemental.filter(
        (item) => !item.schedulable,
      ),
    };
  }

  function buildExecutionSequence(plan) {
    const scheduledByVisit = new Map();
    for (const action of plan?.actionSchedule?.scheduled || []) {
      const key = `${action.componentIndex}:${action.routeVisitIndex}`;
      if (!scheduledByVisit.has(key)) scheduledByVisit.set(key, []);
      scheduledByVisit.get(key).push(action);
    }
    const sequence = [];
    const limit = plan?.checkpointPolicy?.maxRouteWaypoints ||
      DEFAULT_MAX_ROUTE_WAYPOINTS;
    const checkpointAction = () =>
      plan?.checkpointPolicy?.mode === "compatibility_sleep"
        ? {
            kind: "sleep",
            durationSeconds: plan.checkpointPolicy.sleepDurationSeconds,
          }
        : null;

    const appendActions = (
      component,
      visitIndex,
      routeWaypointIds,
      routeEdges,
    ) => {
      const actions =
        scheduledByVisit.get(`${component.componentIndex}:${visitIndex}`) || [];
      for (const [index, action] of actions.entries()) {
        sequence.push({
          sequence: sequence.length + 1,
          componentIndex: component.componentIndex,
          kind: "intentional_sleep",
          targetWaypointId: action.waypointId,
          routeVisitIndex: visitIndex,
          routeWaypointIds:
            index === 0 ? routeWaypointIds : [action.waypointId],
          routeEdges: index === 0 ? routeEdges : [],
          action: {
            kind: action.actionKind,
            durationSeconds: action.actionDurationSeconds,
            name: action.name,
          },
        });
      }
      return actions.length;
    };

    for (const component of plan?.components || []) {
      const finalVisitIndex = component.waypointWalk.length - 1;
      let currentVisitIndex = 0;
      const startActionCount = appendActions(
        component,
        0,
        [component.waypointWalk[0]],
        [],
      );
      if (finalVisitIndex === 0 && !startActionCount) {
        sequence.push({
          sequence: sequence.length + 1,
          componentIndex: component.componentIndex,
          kind: "component_entry",
          targetWaypointId: component.waypointWalk[0],
          routeVisitIndex: 0,
          routeWaypointIds: [component.waypointWalk[0]],
          routeEdges: [],
          action: checkpointAction(),
        });
      }
      while (currentVisitIndex < finalVisitIndex) {
        const maximumEnd = Math.min(
          currentVisitIndex + limit - 1,
          finalVisitIndex,
        );
        let targetVisitIndex = maximumEnd;
        for (
          let candidate = currentVisitIndex + 1;
          candidate <= maximumEnd;
          candidate += 1
        ) {
          if (
            scheduledByVisit.has(
              `${component.componentIndex}:${candidate}`,
            )
          ) {
            targetVisitIndex = candidate;
            break;
          }
        }
        const routeWaypointIds = component.waypointWalk.slice(
          currentVisitIndex,
          targetVisitIndex + 1,
        );
        const routeEdges = component.edgeWalk.slice(
          currentVisitIndex,
          targetVisitIndex,
        );
        const actionCount = appendActions(
          component,
          targetVisitIndex,
          routeWaypointIds,
          routeEdges,
        );
        if (!actionCount) {
          sequence.push({
            sequence: sequence.length + 1,
            componentIndex: component.componentIndex,
            kind: "navigate_route_checkpoint",
            targetWaypointId: component.waypointWalk[targetVisitIndex],
            routeVisitIndex: targetVisitIndex,
            routeWaypointIds,
            routeEdges,
            action: checkpointAction(),
          });
        }
        currentVisitIndex = targetVisitIndex;
      }
    }
    const checkpointEntries = sequence.filter(
      (entry) =>
        entry.kind === "navigate_route_checkpoint" ||
        entry.kind === "component_entry",
    );
    return {
      semantics:
        "ordered_targets_split_at_action_waypoints_and_route_size_limit",
      actionAtEveryWaypoint: false,
      entries: sequence,
      entryCount: sequence.length,
      intentionalSleepCount: sequence.filter(
        (entry) => entry.kind === "intentional_sleep",
      ).length,
      navigationCheckpointCount: checkpointEntries.length,
      navigationOnlyCheckpointCount: checkpointEntries.filter(
        (entry) => !entry.action,
      ).length,
      compatibilitySleepCheckpointCount: checkpointEntries.filter(
        (entry) => entry.action?.kind === "sleep",
      ).length,
    };
  }

  function planCoverage(snapshot, rawOptions = {}) {
    const sourceGraph = buildGraph(snapshot);
    if (!sourceGraph.waypointById.size) {
      throw new Error("site_map_has_no_waypoints");
    }
    const excludedWaypointIds = [...new Set(
      Array.isArray(rawOptions.excludedWaypointIds)
        ? rawOptions.excludedWaypointIds
          .map((id) => String(id || "").trim())
          .filter(Boolean)
        : [],
    )].sort();
    const unknownExcludedWaypointIds = excludedWaypointIds.filter(
      (id) => !sourceGraph.waypointById.has(id),
    );
    if (unknownExcludedWaypointIds.length) {
      throw new Error(
        `excluded_waypoint_not_found:${unknownExcludedWaypointIds[0]}`,
      );
    }
    const excluded = new Set(excludedWaypointIds);
    const startWaypointId = String(rawOptions.startWaypointId || "");
    const endWaypointId = String(rawOptions.endWaypointId || "");
    if (startWaypointId && excluded.has(startWaypointId)) {
      throw new Error("start_waypoint_excluded");
    }
    if (endWaypointId && excluded.has(endWaypointId)) {
      throw new Error("end_waypoint_excluded");
    }
    const planningSnapshot = filteredPlanningSnapshot(
      snapshot,
      excludedWaypointIds,
    );
    const graph = buildGraph(planningSnapshot);
    const components = connectedComponents(graph);
    const options = {
      scope: rawOptions.scope === "all" || rawOptions.scope === "largest"
        ? rawOptions.scope
        : DEFAULT_SCOPE,
      startWaypointId,
      endWaypointId,
      returnToStart: Boolean(rawOptions.returnToStart),
      maxRouteWaypoints: clampRouteWaypointLimit(rawOptions.maxRouteWaypoints),
      checkpointMode:
        rawOptions.checkpointMode === "sleep" ||
        rawOptions.checkpointMode === "compatibility_sleep"
          ? "compatibility_sleep"
          : "navigation_only",
      sleepDurationSeconds:
        Number.isFinite(rawOptions.sleepDurationSeconds) &&
        rawOptions.sleepDurationSeconds >= 0
          ? rawOptions.sleepDurationSeconds
          : 1,
      dockWaypointIds: Array.isArray(rawOptions.dockWaypointIds)
        ? [...new Set(rawOptions.dockWaypointIds)]
        : [],
    };
    if (
      options.startWaypointId &&
      !graph.waypointById.has(options.startWaypointId)
    ) throw new Error("start_waypoint_not_found");
    if (!graph.waypointById.size) throw new Error("all_waypoints_excluded");

    const selection = selectCoverageScope(
      components,
      options.scope,
      options.startWaypointId,
      options.dockWaypointIds,
    );
    const componentOptions = {
      ...options,
      startWaypointId: selection.anchorWaypointId,
    };
    const plannedComponents = selection.components.map((component, index) =>
      planComponent(graph, component, componentOptions, index)
    );
    const plan = {
      schemaVersion: SCHEMA_VERSION,
      kind: "orbit_site_view_coverage_plan",
      createdAt: rawOptions.createdAt || new Date().toISOString(),
      map: {
        id: String(snapshot?.map?.id || ""),
        name: String(snapshot?.map?.name || ""),
        editIndex: Number.isInteger(snapshot?.editIndex)
          ? snapshot.editIndex
          : null,
      },
      missionIndependent: true,
      coverageGoal: options.scope === "all"
        ? "audit_visit_each_map_waypoint_at_least_once"
        : "visit_each_active_reachable_waypoint_at_least_once",
      routeSemantics: "effective_active_bidirectional_edges_only",
      algorithm: "deterministic_open_or_closed_doubled_mst_walk",
      scope: selection.scope,
      coverageAnchor: {
        waypointId: plannedComponents[0]?.startWaypointId || "",
        source: selection.anchorSource,
      },
      returnToStart: options.returnToStart,
      checkpointPolicy: {
        mode: options.checkpointMode,
        maxRouteWaypoints: options.maxRouteWaypoints,
        sleepDurationSeconds:
          options.checkpointMode === "compatibility_sleep"
            ? options.sleepDurationSeconds
            : null,
        compatibilityFallbackEnabled:
          options.checkpointMode === "compatibility_sleep",
        actionAtEveryWaypoint: false,
      },
      exclusions: {
        semantics:
          "remove_waypoints_and_incident_edges_before_route_planning",
        waypointIds: excludedWaypointIds,
        waypointCount: excludedWaypointIds.length,
        removedActiveEdgeCount: [...sourceGraph.edgeByKey.values()].filter(
          (edge) => excluded.has(edge.from) || excluded.has(edge.to),
        ).length,
      },
      graphSummary: {
        mapWaypointCount: sourceGraph.waypointById.size,
        mapEdgeCount: sourceGraph.edgeByKey.size,
        planningWaypointCount: graph.waypointById.size,
        planningEdgeCount: graph.edgeByKey.size,
        explicitlyExcludedWaypointCount: excludedWaypointIds.length,
        mapComponentCount: components.length,
        activeConnectedComponentCount: components.filter(
          (component) => component.edgeCount,
        ).length,
        isolatedWaypointCount: components.filter(
          (component) => component.isolated,
        ).length,
        plannedComponentCount: plannedComponents.length,
        unplannedWaypointCount:
          graph.waypointById.size -
          plannedComponents.reduce(
            (total, component) => total + component.requiredWaypointIds.length,
            0,
          ),
        excludedDisconnectedWaypointCount:
          selection.scope === "all"
            ? 0
            : graph.waypointById.size -
              plannedComponents.reduce(
                (total, component) =>
                  total + component.requiredWaypointIds.length,
                0,
              ),
        totalExcludedWaypointCount:
          excludedWaypointIds.length +
          (
            selection.scope === "all"
              ? 0
              : graph.waypointById.size -
                plannedComponents.reduce(
                  (total, component) =>
                    total + component.requiredWaypointIds.length,
                  0,
                )
          ),
      },
      components: plannedComponents,
      totals: {
        requiredWaypointCount: plannedComponents.reduce(
          (total, component) => total + component.requiredWaypointIds.length,
          0,
        ),
        traversalCount: plannedComponents.reduce(
          (total, component) => total + component.traversalCount,
          0,
        ),
        repeatedVisitCount: plannedComponents.reduce(
          (total, component) => total + component.repeatedVisitCount,
          0,
        ),
        checkpointCount: plannedComponents.reduce(
          (total, component) => total + component.checkpointCount,
          0,
        ),
        componentTransitions: Math.max(0, plannedComponents.length - 1),
      },
      compatibility: {
        readOnlyPlan: true,
        topologyValidationOnly: true,
        provesRobotTraversability: false,
        existingSiteWalkModified: false,
        existingSiteElementModified: false,
        existingSiteWalkRead: false,
        existingSiteElementRead: false,
        requiresNewSiteWalk: true,
        requiresQualificationInTargetOrbitVersion: true,
        automaticSleepFallbackEnabled:
          options.checkpointMode === "compatibility_sleep",
      },
    };
    plan.actionSchedule = scheduleActions(
      plan,
      Array.isArray(rawOptions.supplementalSleepActions)
        ? rawOptions.supplementalSleepActions
        : [],
    );
    plan.executionSequence = buildExecutionSequence(plan);
    plan.siteViewCoverage = siteViewCoverage(
      snapshot,
      plan,
      Array.isArray(rawOptions.sitePanoWaypoints)
        ? rawOptions.sitePanoWaypoints
        : [],
    );
    plan.compatibility.reusedExistingSiteElementCount = 0;
    plan.compatibility.requiredNewSiteElementCount =
      plan.executionSequence.navigationCheckpointCount +
      plan.executionSequence.intentionalSleepCount;
    plan.compatibility.navigationOnlyCheckpointCount =
      plan.executionSequence.navigationOnlyCheckpointCount;
    plan.compatibility.automaticSleepFallbackCount =
      plan.executionSequence.compatibilitySleepCheckpointCount;
    plan.validation = validateCoveragePlan(snapshot, plan);
    return plan;
  }

  globalThis.OrbitSiteMapEditorWalkPlanner = Object.freeze({
    DEFAULT_MAX_ROUTE_WAYPOINTS,
    DEFAULT_SCOPE,
    MAX_ROUTE_WAYPOINTS,
    MIN_ROUTE_WAYPOINTS,
    SCHEMA_VERSION,
    buildGraph,
    buildExecutionSequence,
    connectedComponents,
    edgeKey,
    filteredPlanningSnapshot,
    minimumSpanningTree,
    planCoverage,
    reconstructCheckpointWalk,
    routeCheckpoints,
    scheduleActions,
    selectCoverageScope,
    siteViewCoverage,
    validateCoveragePlan,
  });
})();
