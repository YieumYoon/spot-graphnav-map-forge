(() => {
  "use strict";

  const model = globalThis.OrbitSiteMapEditorModel;
  const selection = globalThis.OrbitSiteMapEditorSelection;
  if (!model || !selection) return;

  function edgeId(edge) {
    return edge.id || model.edgeKey(edge.from, edge.to);
  }

  function topology(snapshot) {
    const graph = model.buildGraph(snapshot || {});
    const components = [];
    const componentByWaypoint = new Map();
    for (const id of graph.waypointById.keys()) {
      if (componentByWaypoint.has(id)) continue;
      const componentIndex = components.length;
      const ids = [];
      const queue = [id];
      componentByWaypoint.set(id, componentIndex);
      for (let index = 0; index < queue.length; index += 1) {
        const current = queue[index];
        ids.push(current);
        for (const neighbor of graph.neighbors.get(current) || []) {
          if (!componentByWaypoint.has(neighbor)) {
            componentByWaypoint.set(neighbor, componentIndex);
            queue.push(neighbor);
          }
        }
      }
      components.push(ids.sort());
    }

    const discovery = new Map();
    const low = new Map();
    const parent = new Map();
    const bridges = new Set();
    const articulations = new Set();
    let time = 0;
    function visit(id) {
      discovery.set(id, time);
      low.set(id, time);
      time += 1;
      let children = 0;
      for (const neighbor of graph.neighbors.get(id) || []) {
        if (!discovery.has(neighbor)) {
          parent.set(neighbor, id);
          children += 1;
          visit(neighbor);
          low.set(id, Math.min(low.get(id), low.get(neighbor)));
          if (low.get(neighbor) > discovery.get(id)) {
            bridges.add(model.edgeKey(id, neighbor));
          }
          if (
            (!parent.has(id) && children > 1) ||
            (parent.has(id) && low.get(neighbor) >= discovery.get(id))
          ) articulations.add(id);
        } else if (parent.get(id) !== neighbor) {
          low.set(id, Math.min(low.get(id), discovery.get(neighbor)));
        }
      }
    }
    for (const id of graph.waypointById.keys()) {
      if (!discovery.has(id)) visit(id);
    }

    return {
      graph,
      components: components.sort((left, right) => right.length - left.length),
      componentByWaypoint,
      bridges,
      articulations,
      isolated: [...graph.neighbors]
        .filter(([, neighbors]) => neighbors.size === 0)
        .map(([id]) => id)
        .sort(),
      leaves: [...graph.neighbors]
        .filter(([, neighbors]) => neighbors.size === 1)
        .map(([id]) => id)
        .sort(),
    };
  }

  function finding({
    id,
    severity = "warning",
    type,
    title,
    explanation,
    waypointIds = [],
    edgeIds = [],
    details = {},
  }) {
    return {
      id,
      severity,
      type,
      title,
      explanation,
      waypointIds: [...new Set(waypointIds)].sort(),
      edgeIds: [...new Set(edgeIds)].sort(),
      details,
    };
  }

  function callbackIds(edge) {
    return Object.keys(edge.settings?.areaCallbacks || {});
  }

  function hasAuthoritativeAreaCatalog(snapshot) {
    const adapter = String(snapshot?.capabilities?.areas || "");
    return Boolean(adapter && adapter !== "siteEdges.areaCallbacks");
  }

  function validateGraph(snapshot, { waypointLimit = 3000 } = {}) {
    const result = [];
    const topologyResult = topology(snapshot);
    const { graph } = topologyResult;
    const edgePairCounts = new Map();
    const nameGroups = new Map();
    const areaIds = new Set(
      (snapshot?.areas || [])
        .filter((area) => area.catalogPresent !== false && !area.inferredFromEdge)
        .map((area) => area.id),
    );
    const areaCatalogAvailable = hasAuthoritativeAreaCatalog(snapshot);

    for (const waypoint of snapshot?.waypoints || []) {
      const name = String(waypoint.name || "").trim().toLocaleLowerCase();
      if (name) {
        if (!nameGroups.has(name)) nameGroups.set(name, []);
        nameGroups.get(name).push(waypoint.id);
      }
    }
    for (const [name, ids] of nameGroups) {
      if (ids.length > 1) {
        result.push(finding({
          id: `duplicate-waypoint-name:${name}`,
          severity: "info",
          type: "duplicate_waypoint_name",
          title: `Duplicate waypoint name (${ids.length})`,
          explanation: `The name “${name}” is used by multiple exact waypoint IDs.`,
          waypointIds: ids,
        }));
      }
    }

    for (const edge of snapshot?.edges || []) {
      const key = model.edgeKey(edge.from, edge.to);
      if (!edgePairCounts.has(key)) edgePairCounts.set(key, []);
      edgePairCounts.get(key).push(edgeId(edge));
      const missing = [edge.from, edge.to].filter((id) => !graph.waypointById.has(id));
      if (missing.length) {
        result.push(finding({
          id: `missing-endpoint:${edgeId(edge)}`,
          severity: "error",
          type: "missing_endpoint",
          title: "Edge endpoint is missing",
          explanation: "The edge references a waypoint that is not loaded in this Site Map.",
          waypointIds: [edge.from, edge.to],
          edgeIds: [edgeId(edge)],
          details: { missing },
        }));
      }
      if ((edge.manual ?? edge.source === "manual") && edge.crossRecording) {
        result.push(finding({
          id: `cross-recording-manual:${edgeId(edge)}`,
          severity: "info",
          type: "cross_recording_manual",
          title: "Manually created cross-recording edge",
          explanation:
            "This manually created edge joins waypoints from different recording sessions.",
          waypointIds: [edge.from, edge.to],
          edgeIds: [edgeId(edge)],
        }));
      }
      const staleCallbacks = callbackIds(edge).filter(
        (id) => areaCatalogAvailable && !areaIds.has(id),
      );
      if (staleCallbacks.length) {
        result.push(finding({
          id: `stale-area-callback:${edgeId(edge)}`,
          severity: "warning",
          type: "stale_area_callback",
          title: "Area callback reference is missing",
          explanation:
            "At least one edge callback references an Area not present in the loaded catalog.",
          waypointIds: [edge.from, edge.to],
          edgeIds: [edgeId(edge)],
          details: { callbackIds: staleCallbacks },
        }));
      }
    }
    for (const [key, ids] of edgePairCounts) {
      if (ids.length > 1) {
        result.push(finding({
          id: `duplicate-edge-pair:${key}`,
          severity: "error",
          type: "duplicate_edge_pair",
          title: `Duplicate endpoint pair (${ids.length})`,
          explanation: "More than one active edge uses the same unordered waypoint pair.",
          waypointIds: key.split("|"),
          edgeIds: ids,
        }));
      }
    }

    if (topologyResult.components.length > 1) {
      for (const [index, ids] of topologyResult.components.entries()) {
        result.push(finding({
          id: `component:${index}`,
          severity: index === 0 ? "info" : "warning",
          type: "disconnected_component",
          title: `Disconnected component ${index + 1} (${ids.length})`,
          explanation:
            index === 0
              ? "This is the largest connected component."
              : "These waypoints cannot be reached from the largest component.",
          waypointIds: ids,
        }));
      }
    }
    for (const id of topologyResult.isolated) {
      result.push(finding({
        id: `isolated:${id}`,
        severity: "error",
        type: "isolated_waypoint",
        title: "Isolated waypoint",
        explanation: "This waypoint has no active incident edge.",
        waypointIds: [id],
      }));
    }
    if (topologyResult.leaves.length) {
      result.push(finding({
        id: "leaf-waypoints",
        severity: "info",
        type: "leaf_waypoint",
        title: `Leaf/dead-end waypoints (${topologyResult.leaves.length})`,
        explanation: "Each listed waypoint has exactly one active incident edge.",
        waypointIds: topologyResult.leaves,
      }));
    }
    for (const key of topologyResult.bridges) {
      const edge = graph.edgeByKey.get(key);
      result.push(finding({
        id: `bridge:${key}`,
        severity: "info",
        type: "bridge_edge",
        title: "Bridge edge",
        explanation: "Archiving this edge would increase the number of connected components.",
        waypointIds: key.split("|"),
        edgeIds: edge ? [edgeId(edge)] : [],
      }));
    }
    if (topologyResult.articulations.size) {
      result.push(finding({
        id: "articulation-waypoints",
        severity: "info",
        type: "articulation_waypoint",
        title: `Articulation waypoints (${topologyResult.articulations.size})`,
        explanation:
          "Removing one of these waypoints and its incident edges would split its component.",
        waypointIds: [...topologyResult.articulations],
      }));
    }

    for (const edgeState of snapshot?.edgeStates || []) {
      if (edgeState.activeCount && edgeState.tombstoneCount) {
        result.push(finding({
          id: `active-tombstone:${edgeState.key}`,
          severity: "warning",
          type: "active_tombstone_ambiguity",
          title: "Active/tombstone edge ambiguity",
          explanation:
            "Orbit state contains both an active and archived/disabled representation for this pair.",
          waypointIds: [edgeState.from, edgeState.to],
          edgeIds: edgeState.ids || [],
        }));
      }
      const endpointsNowDisconnected =
        topologyResult.componentByWaypoint.has(edgeState.from) &&
        topologyResult.componentByWaypoint.has(edgeState.to) &&
        topologyResult.componentByWaypoint.get(edgeState.from) !==
          topologyResult.componentByWaypoint.get(edgeState.to);
      if (
        edgeState.tombstoneCount &&
        !edgeState.activeCount &&
        (edgeState.wasCritical || endpointsNowDisconnected)
      ) {
        result.push(finding({
          id: `archived-critical:${edgeState.key}`,
          severity: "warning",
          type: "archived_critical_connection",
          title: "Archived or disabled critical connection",
          explanation:
            "The archived/disabled pair was a bridge in the stored graph context.",
          waypointIds: [edgeState.from, edgeState.to],
          edgeIds: edgeState.ids || [],
        }));
      }
    }

    for (const dependencyKind of ["actions", "docks"]) {
      for (const dependency of snapshot?.[dependencyKind] || []) {
        const dependencyWaypoints = [
          ...(dependency.waypointIds || []),
          ...(dependency.waypointId ? [dependency.waypointId] : []),
        ].filter((id) => graph.waypointById.has(id));
        if (!dependencyWaypoints.length) {
          result.push(finding({
            id: `unattached-${dependencyKind}:${dependency.id}`,
            severity: "warning",
            type: `unattached_${dependencyKind.slice(0, -1)}`,
            title: `${dependencyKind === "docks" ? "Dock" : "Action"} has no reachable waypoint`,
            explanation:
              "The object does not reference a waypoint present in the loaded graph.",
            waypointIds: dependency.waypointIds || [],
            details: { dependencyId: dependency.id },
          }));
        }
      }
    }
    const dockStartIds = (snapshot?.docks || []).flatMap((dock) => [
      ...(dock.waypointIds || []),
      ...(dock.waypointId ? [dock.waypointId] : []),
    ]).filter((id) => graph.waypointById.has(id));
    if (dockStartIds.length) {
      const dockReachable = reachable(snapshot, dockStartIds);
      for (const [kind, dependencies] of [
        ["action", snapshot?.actions || []],
        ["area", snapshot?.areas || []],
      ]) {
        for (const dependency of dependencies) {
          const ids = [
            ...(dependency.waypointIds || []),
            ...(dependency.waypointId ? [dependency.waypointId] : []),
          ].filter((id) => graph.waypointById.has(id));
          if (ids.length && !ids.some((id) => dockReachable.has(id))) {
            result.push(finding({
              id: `dock-unreachable-${kind}:${dependency.id}`,
              severity: "warning",
              type: `dock_unreachable_${kind}`,
              title: `${kind === "action" ? "Action" : "Area"} is unreachable from Docks`,
              explanation:
                "No active graph path connects this object to any loaded Dock waypoint.",
              waypointIds: ids,
              details: { dependencyId: dependency.id },
            }));
          }
        }
      }
    }

    const waypointCount = (snapshot?.waypoints || []).length;
    const expectedCount = snapshot?.load?.expectedWaypointCount;
    if (
      Number.isInteger(expectedCount) &&
      expectedCount !== waypointCount
    ) {
      result.push(finding({
        id: "incomplete-waypoint-load",
        severity: "error",
        type: "load_incomplete",
        title: `Only ${waypointCount}/${expectedCount} waypoints loaded`,
        explanation: "Do not draft edits until Orbit finishes loading the full Site Map.",
      }));
    }
    if (waypointCount >= waypointLimit) {
      result.push(finding({
        id: "waypoint-count-limit",
        severity: "warning",
        type: "waypoint_count_limit",
        title: `Waypoint count is ${waypointCount}`,
        explanation:
          `This meets or exceeds the configured ${waypointLimit}-waypoint operational warning.`,
      }));
    }

    const severityRank = { error: 0, warning: 1, info: 2 };
    return result.sort((left, right) =>
      severityRank[left.severity] - severityRank[right.severity] ||
      left.type.localeCompare(right.type) ||
      left.id.localeCompare(right.id)
    );
  }

  function reachable(snapshot, startIds) {
    const result = new Set();
    for (const startId of startIds || []) {
      for (const id of selection.component(snapshot, startId).waypointIds) result.add(id);
    }
    return result;
  }

  function reachability(snapshot, startIds, targets = []) {
    const reachableIds = reachable(snapshot, startIds);
    return targets.map((target) => {
      const waypointIds = [...new Set([
        ...(target.waypointIds || []),
        ...(target.waypointId ? [target.waypointId] : []),
      ])];
      return {
        kind: target.kind || "target",
        id: target.id,
        name: target.name || "",
        waypointIds,
        reachable: waypointIds.some((id) => reachableIds.has(id)),
      };
    });
  }

  function settingsMatrix(edges) {
    const fields = new Set(
      (edges || []).flatMap((edge) => Object.keys(edge.settings || {})),
    );
    const rows = [];
    for (const field of [...fields].sort()) {
      const groups = new Map();
      for (const edge of edges || []) {
        const serialized = JSON.stringify(edge.settings?.[field] ?? null);
        if (!groups.has(serialized)) groups.set(serialized, []);
        groups.get(serialized).push(edgeId(edge));
      }
      rows.push({
        field,
        mixed: groups.size > 1,
        values: [...groups].map(([serialized, edgeIds]) => ({
          value: JSON.parse(serialized),
          edgeIds,
          count: edgeIds.length,
        })),
      });
    }
    return rows;
  }

  function pathInspector(snapshot, startId, endId) {
    const path = selection.shortestPath(snapshot, startId, endId);
    const edgeIds = new Set(path.edgeIds);
    const edges = (snapshot?.edges || []).filter((edge) => edgeIds.has(edgeId(edge)));
    return {
      ...path,
      reachable: path.waypointIds.length > 0,
      edgeCount: edges.length,
      totalLength: edges.reduce(
        (total, edge) => total + (Number.isFinite(edge.length) ? edge.length : 0),
        0,
      ),
      settings: settingsMatrix(edges),
      edges: edges.map((edge) => ({
        id: edgeId(edge),
        from: edge.from,
        to: edge.to,
        source: edge.source,
        settings: edge.settings || {},
      })),
    };
  }

  function crosswalkAudit(snapshot) {
    const result = [];
    const areas = new Map((snapshot?.areas || []).map((area) => [area.id, area]));
    const areaCatalogAvailable = hasAuthoritativeAreaCatalog(snapshot);
    for (const edge of snapshot?.edges || []) {
      const callbacks = Object.entries(edge.settings?.areaCallbacks || {});
      const crosswalks = callbacks.filter(([, callback]) =>
        callback?.serviceName === "spot-crosswalk"
      );
      for (const [areaId, callback] of crosswalks) {
        result.push({
          edgeId: edgeId(edge),
          waypointIds: [edge.from, edge.to],
          areaId,
          areaName: areas.get(areaId)?.name || "",
          areaPresent:
            !areaCatalogAvailable ||
            Boolean(areas.get(areaId) && areas.get(areaId).catalogPresent !== false),
          serviceName: callback.serviceName,
          description: callback.description || "",
          settings: edge.settings || {},
        });
      }
    }
    const byArea = new Map();
    for (const item of result) {
      if (!byArea.has(item.areaId)) byArea.set(item.areaId, []);
      byArea.get(item.areaId).push(item);
    }
    for (const items of byArea.values()) {
      const signatures = new Set(
        items.map((item) => JSON.stringify(
          Object.fromEntries(
            Object.entries(item.settings || {}).filter(([key]) => key !== "areaCallbacks"),
          ),
        )),
      );
      for (const item of items) item.inconsistentProfile = signatures.size > 1;
    }
    for (const area of snapshot?.areas || []) {
      const likelyCrosswalk =
        area.crosswalk ||
        String(area.serviceName || "").includes("crosswalk") ||
        String(area.type || "").toLocaleLowerCase().includes("crosswalk");
      if (likelyCrosswalk && !byArea.has(area.id)) {
        result.push({
          edgeId: "",
          waypointIds: area.waypointIds || [],
          areaId: area.id,
          areaName: area.name || "",
          areaPresent: true,
          serviceName: area.serviceName || "spot-crosswalk",
          description: "No approach edge has a spot-crosswalk callback.",
          settings: {},
          missingApproach: true,
          inconsistentProfile: false,
        });
      }
    }
    return result.sort((left, right) =>
      left.areaId.localeCompare(right.areaId) ||
      left.edgeId.localeCompare(right.edgeId)
    );
  }

  function graphSummary(snapshot) {
    const topologyResult = topology(snapshot);
    const edges = snapshot?.edges || [];
    const dockIds = (snapshot?.docks || []).flatMap((dock) => [
      ...(dock.waypointIds || []),
      ...(dock.waypointId ? [dock.waypointId] : []),
    ]);
    const reachableFromDocks = reachable(snapshot, dockIds);
    const dependencies = [
      ...(snapshot?.actions || []),
      ...(snapshot?.areas || []),
    ];
    return {
      waypoints: (snapshot?.waypoints || []).length,
      edges: edges.length,
      components: topologyResult.components.length,
      isolated: topologyResult.isolated.length,
      leaves: topologyResult.leaves.length,
      bridges: topologyResult.bridges.size,
      articulations: topologyResult.articulations.size,
      configuredEdges: edges.filter(
        (edge) => Object.keys(edge.settings || {}).length > 0,
      ).length,
      crosswalkEdges: crosswalkAudit(snapshot).filter((item) => item.edgeId).length,
      crossRecordingManualEdges: edges.filter(
        (edge) => (edge.manual ?? edge.source === "manual") && edge.crossRecording,
      ).length,
      reachableDependencies: dependencies.filter((dependency) => {
        const ids = [
          ...(dependency.waypointIds || []),
          ...(dependency.waypointId ? [dependency.waypointId] : []),
        ];
        return ids.some((id) => reachableFromDocks.has(id));
      }).length,
    };
  }

  globalThis.OrbitSiteMapEditorValidation = Object.freeze({
    crosswalkAudit,
    graphSummary,
    pathInspector,
    reachability,
    reachable,
    settingsMatrix,
    topology,
    validateGraph,
  });
})();
