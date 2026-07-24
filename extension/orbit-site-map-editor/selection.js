(() => {
  "use strict";

  const model = globalThis.OrbitSiteMapEditorModel;
  if (!model) return;

  function unique(values) {
    return [...new Set((values || []).filter((value) => typeof value === "string" && value))];
  }

  function normalize(selection = {}) {
    return {
      waypointIds: unique(selection.waypointIds).sort(),
      edgeIds: unique(selection.edgeIds).sort(),
    };
  }

  function setOperation(leftValues, rightValues, mode) {
    const left = new Set(leftValues || []);
    const right = new Set(rightValues || []);
    if (mode === "replace") return [...right];
    if (mode === "add") return [...new Set([...left, ...right])];
    if (mode === "subtract") return [...left].filter((value) => !right.has(value));
    if (mode === "intersect") return [...left].filter((value) => right.has(value));
    throw new Error("unknown_selection_operation");
  }

  function combine(current, incoming, mode = "replace") {
    return normalize({
      waypointIds: setOperation(current?.waypointIds, incoming?.waypointIds, mode),
      edgeIds: setOperation(current?.edgeIds, incoming?.edgeIds, mode),
    });
  }

  function invert(snapshot, selection) {
    const current = normalize(selection);
    return normalize({
      waypointIds: (snapshot?.waypoints || [])
        .map((item) => item.id)
        .filter((id) => !current.waypointIds.includes(id)),
      edgeIds: (snapshot?.edges || [])
        .map((item) => item.id || model.edgeKey(item.from, item.to))
        .filter((id) => !current.edgeIds.includes(id)),
    });
  }

  function edgeId(edge) {
    return edge.id || model.edgeKey(edge.from, edge.to);
  }

  function incidentEdges(snapshot, waypointIds, internalOnly = false) {
    const selected = new Set(waypointIds || []);
    return normalize({
      waypointIds,
      edgeIds: (snapshot?.edges || [])
        .filter((edge) =>
          internalOnly
            ? selected.has(edge.from) && selected.has(edge.to)
            : selected.has(edge.from) || selected.has(edge.to)
        )
        .map(edgeId),
    });
  }

  function nHop(snapshot, startIds, hops = 1) {
    const graph = model.buildGraph(snapshot);
    const visited = new Set(
      unique(startIds).filter((id) => graph.waypointById.has(id)),
    );
    let frontier = new Set(visited);
    const count = Math.max(0, Math.min(1000, Math.floor(Number(hops) || 0)));
    for (let depth = 0; depth < count && frontier.size; depth += 1) {
      const next = new Set();
      for (const id of frontier) {
        for (const neighbor of graph.neighbors.get(id) || []) {
          if (!visited.has(neighbor)) {
            visited.add(neighbor);
            next.add(neighbor);
          }
        }
      }
      frontier = next;
    }
    return incidentEdges(snapshot, [...visited], true);
  }

  function component(snapshot, startId) {
    const graph = model.buildGraph(snapshot);
    if (!graph.waypointById.has(startId)) return normalize();
    const visited = new Set([startId]);
    const queue = [startId];
    for (let index = 0; index < queue.length; index += 1) {
      for (const neighbor of graph.neighbors.get(queue[index]) || []) {
        if (!visited.has(neighbor)) {
          visited.add(neighbor);
          queue.push(neighbor);
        }
      }
    }
    return incidentEdges(snapshot, [...visited], true);
  }

  function recording(snapshot, recordingId) {
    const waypointIds = (snapshot?.waypoints || [])
      .filter((waypoint) => waypoint.recordingId === recordingId)
      .map((waypoint) => waypoint.id);
    return incidentEdges(snapshot, waypointIds, true);
  }

  function fromRecords(records) {
    return normalize({
      waypointIds: (records || []).flatMap((record) => record.waypointIds || []),
      edgeIds: (records || []).flatMap((record) => record.edgeIds || []),
    });
  }

  function pointInPolygon(point, polygon) {
    if (!model.finitePosition(point) || !Array.isArray(polygon) || polygon.length < 3) {
      return false;
    }
    let inside = false;
    for (let index = 0, previous = polygon.length - 1;
      index < polygon.length;
      previous = index, index += 1) {
      const currentPoint = polygon[index];
      const previousPoint = polygon[previous];
      const intersects =
        currentPoint.y > point.y !== previousPoint.y > point.y &&
        point.x <
          ((previousPoint.x - currentPoint.x) * (point.y - currentPoint.y)) /
            (previousPoint.y - currentPoint.y || Number.EPSILON) +
          currentPoint.x;
      if (intersects) inside = !inside;
    }
    return inside;
  }

  function polygon(snapshot, points) {
    const waypointIds = (snapshot?.waypoints || [])
      .filter((waypoint) => pointInPolygon(waypoint.position, points))
      .map((waypoint) => waypoint.id);
    return incidentEdges(snapshot, waypointIds, true);
  }

  function rectangle(snapshot, bounds) {
    const left = Math.min(bounds?.x1, bounds?.x2);
    const right = Math.max(bounds?.x1, bounds?.x2);
    const bottom = Math.min(bounds?.y1, bounds?.y2);
    const top = Math.max(bounds?.y1, bounds?.y2);
    if (![left, right, bottom, top].every(Number.isFinite)) return normalize();
    return polygon(snapshot, [
      { x: left, y: bottom },
      { x: right, y: bottom },
      { x: right, y: top },
      { x: left, y: top },
    ]);
  }

  function shortestPath(snapshot, startId, endId) {
    const graph = model.buildGraph(snapshot);
    if (!graph.waypointById.has(startId) || !graph.waypointById.has(endId)) {
      return normalize();
    }
    const previous = new Map([[startId, null]]);
    const queue = [startId];
    for (let index = 0; index < queue.length && !previous.has(endId); index += 1) {
      for (const neighbor of graph.neighbors.get(queue[index]) || []) {
        if (!previous.has(neighbor)) {
          previous.set(neighbor, queue[index]);
          queue.push(neighbor);
        }
      }
    }
    if (!previous.has(endId)) return normalize();
    const waypointIds = [];
    for (let cursor = endId; cursor !== null; cursor = previous.get(cursor)) {
      waypointIds.push(cursor);
    }
    waypointIds.reverse();
    const edgeIds = [];
    for (let index = 1; index < waypointIds.length; index += 1) {
      const edge = graph.edgeByKey.get(
        model.edgeKey(waypointIds[index - 1], waypointIds[index]),
      );
      if (edge) edgeIds.push(edgeId(edge));
    }
    return normalize({ waypointIds, edgeIds });
  }

  function serializeNamedSet(name, mapId, selection) {
    const trimmed = String(name || "").trim();
    if (!trimmed || trimmed.length > 120) throw new Error("invalid_selection_set_name");
    return {
      schema: "orbit_site_map_editor_selection_set_v1",
      name: trimmed,
      mapId: String(mapId || ""),
      selection: normalize(selection),
      updatedAt: new Date().toISOString(),
    };
  }

  function validateNamedSet(value, mapId) {
    if (
      value?.schema !== "orbit_site_map_editor_selection_set_v1" ||
      value.mapId !== mapId ||
      typeof value.name !== "string"
    ) throw new Error("invalid_or_foreign_selection_set");
    return serializeNamedSet(value.name, mapId, value.selection);
  }

  globalThis.OrbitSiteMapEditorSelection = Object.freeze({
    combine,
    component,
    fromRecords,
    incidentEdges,
    invert,
    nHop,
    normalize,
    pointInPolygon,
    polygon,
    recording,
    rectangle,
    serializeNamedSet,
    shortestPath,
    validateNamedSet,
  });
})();
