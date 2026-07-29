(() => {
  "use strict";

  const DEFAULT_RADIUS_METERS = 2;
  const DEFAULT_CANDIDATE_LIMIT = 30;

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

  function shortId(value, size = 9) {
    const text = String(value || "");
    if (text.length <= size * 2 + 1) return text;
    return `${text.slice(0, size)}…${text.slice(-size)}`;
  }

  function searchable(value) {
    return String(value ?? "").trim().toLocaleLowerCase();
  }

  function buildGraph(snapshot) {
    const waypointById = new Map();
    const neighbors = new Map();
    const edgeByKey = new Map();
    const recordingById = new Map();

    for (const waypoint of snapshot?.waypoints || []) {
      waypointById.set(waypoint.id, waypoint);
      neighbors.set(waypoint.id, new Set());
      if (waypoint.recordingId && !recordingById.has(waypoint.recordingId)) {
        recordingById.set(waypoint.recordingId, {
          id: waypoint.recordingId,
          name: waypoint.recordingName || "",
          robotNickname: waypoint.robotNickname || "",
          robotSerial: waypoint.robotSerial || "",
          waypointCount: 0,
        });
      }
      const recording = recordingById.get(waypoint.recordingId);
      if (recording) recording.waypointCount += 1;
    }

    for (const edge of snapshot?.edges || []) {
      if (!waypointById.has(edge.from) || !waypointById.has(edge.to)) continue;
      const key = edgeKey(edge.from, edge.to);
      edgeByKey.set(key, edge);
      neighbors.get(edge.from).add(edge.to);
      neighbors.get(edge.to).add(edge.from);
    }

    return { waypointById, neighbors, edgeByKey, recordingById };
  }

  function searchSnapshot(snapshot, query, kind = "all", limit = 100) {
    const normalized = searchable(query);
    if (!normalized) return [];
    const graph = buildGraph(snapshot);
    const results = [];
    const add = (result, fields) => {
      const normalizedFields = fields.map(searchable);
      const exactId = searchable(result.id) === normalized;
      const exact = normalizedFields.some((field) => field === normalized);
      const prefix = normalizedFields.some((field) => field.startsWith(normalized));
      const contains = normalizedFields.some((field) => field.includes(normalized));
      if (!contains) return;
      results.push({ ...result, rank: exactId ? -1 : exact ? 0 : prefix ? 1 : 2 });
    };

    if (kind === "all" || kind === "waypoint") {
      for (const waypoint of snapshot?.waypoints || []) {
        add(
          {
            kind: "waypoint",
            id: waypoint.id,
            label: waypoint.name || shortId(waypoint.id),
            detail:
              `${waypoint.recordingName || shortId(waypoint.recordingId)} · ` +
              `degree ${graph.neighbors.get(waypoint.id)?.size || 0}`,
            waypointIds: [waypoint.id],
          },
          [
            waypoint.id,
            waypoint.name,
            waypoint.recordingId,
            waypoint.recordingName,
            waypoint.robotNickname,
            waypoint.robotSerial,
          ],
        );
      }
    }

    if (kind === "all" || kind === "edge") {
      for (const edge of snapshot?.edges || []) {
        const from = graph.waypointById.get(edge.from);
        const to = graph.waypointById.get(edge.to);
        add(
          {
            kind: "edge",
            id: edge.id || edgeKey(edge.from, edge.to),
            label:
              `${from?.name || shortId(edge.from)} ↔ ` +
              `${to?.name || shortId(edge.to)}`,
            detail: `${edge.source || "unknown"} · ${formatDistance(edge.length)}`,
            waypointIds: [edge.from, edge.to],
          },
          [
            edge.id,
            edge.from,
            edge.to,
            from?.name,
            to?.name,
            edge.source,
          ],
        );
      }
    }

    if (kind === "all" || kind === "recording") {
      for (const recording of graph.recordingById.values()) {
        add(
          {
            kind: "recording",
            id: recording.id,
            label: recording.name || shortId(recording.id),
            detail:
              `${recording.waypointCount} waypoints` +
              (recording.robotNickname ? ` · ${recording.robotNickname}` : ""),
            waypointIds: [],
          },
          [
            recording.id,
            recording.name,
            recording.robotNickname,
            recording.robotSerial,
          ],
        );
      }
    }

    return results
      .sort((left, right) =>
        left.rank - right.rank ||
        left.kind.localeCompare(right.kind) ||
        left.label.localeCompare(right.label) ||
        left.id.localeCompare(right.id)
      )
      .slice(0, Math.max(1, limit));
  }

  function connectionCandidates(
    snapshot,
    baseId,
    {
      radiusMeters = DEFAULT_RADIUS_METERS,
      limit = DEFAULT_CANDIDATE_LIMIT,
    } = {},
  ) {
    const graph = buildGraph(snapshot);
    const base = graph.waypointById.get(baseId);
    if (!base || !finitePosition(base.position)) return [];
    const radius = Number.isFinite(radiusMeters) && radiusMeters > 0
      ? radiusMeters
      : DEFAULT_RADIUS_METERS;
    const cappedLimit = Number.isInteger(limit) && limit > 0
      ? Math.min(limit, 100)
      : DEFAULT_CANDIDATE_LIMIT;
    const existingNeighbors = graph.neighbors.get(baseId) || new Set();
    const candidates = [];

    for (const waypoint of graph.waypointById.values()) {
      if (
        waypoint.id === baseId ||
        existingNeighbors.has(waypoint.id) ||
        !finitePosition(waypoint.position)
      ) continue;
      const dx = waypoint.position.x - base.position.x;
      const dy = waypoint.position.y - base.position.y;
      const dz =
        Number.isFinite(waypoint.position.z) && Number.isFinite(base.position.z)
          ? waypoint.position.z - base.position.z
          : 0;
      const distance = Math.hypot(dx, dy, dz);
      if (distance > radius) continue;
      const sameRecording = Boolean(
        base.recordingId &&
        waypoint.recordingId &&
        base.recordingId === waypoint.recordingId,
      );
      const degree = graph.neighbors.get(waypoint.id)?.size || 0;
      candidates.push({
        id: waypoint.id,
        name: waypoint.name || "",
        recordingId: waypoint.recordingId || "",
        recordingName: waypoint.recordingName || "",
        position: waypoint.position,
        distance,
        degree,
        sameRecording,
        score: distance + (sameRecording ? 0 : 0.75) + (degree === 0 ? 0.25 : 0),
      });
    }

    return candidates
      .sort((left, right) =>
        left.score - right.score ||
        left.distance - right.distance ||
        left.id.localeCompare(right.id)
      )
      .slice(0, cappedLimit);
  }

  function formatDistance(value) {
    return Number.isFinite(value) ? `${value.toFixed(2)} m` : "—";
  }

  function importantSettings(settings) {
    const annotations = settings || {};
    const result = [];
    if (annotations.stairs) result.push("stairs");
    if (annotations.directionConstraint) {
      result.push(`direction ${String(annotations.directionConstraint)}`);
    }
    if (annotations.disableAlternateRouteFinding) result.push("no alternate route");
    if (Number.isFinite(annotations.cost) && annotations.cost !== 0) {
      result.push(`cost ${annotations.cost}`);
    }
    if (annotations.overrideMobilityParams) result.push("mobility override");
    if (annotations.groundClutterMode) result.push("ground clutter");
    if (Object.keys(annotations.areaCallbacks || {}).length) {
      result.push(`${Object.keys(annotations.areaCallbacks).length} Area callback`);
    }
    return result;
  }

  globalThis.OrbitSiteMapEditorModel = Object.freeze({
    DEFAULT_CANDIDATE_LIMIT,
    DEFAULT_RADIUS_METERS,
    buildGraph,
    connectionCandidates,
    edgeKey,
    finitePosition,
    formatDistance,
    importantSettings,
    searchSnapshot,
    shortId,
  });
})();
