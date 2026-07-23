(() => {
  "use strict";

  const BASELINE_KIND = "orbit_graph_baseline_inventory";
  const SNAPSHOT_KIND = "orbit_live_graph_snapshot";
  const GUIDE_KIND = "orbit_graph_reconciliation_guide";
  const MANUAL_SOURCE = "EDGE_SOURCE_USER_REQUEST";
  const EDGE_SETTING_FIELDS = new Set([
    "stairs",
    "directionConstraint",
    "requireAlignment",
    "flatGround",
    "overrideMobilityParams",
    "mobilityParams",
    "cost",
    "disableAlternateRouteFinding",
    "pathFollowingMode",
    "maxCorridorDistance",
    "disableDirectedExploration",
    "areaCallbacks",
    "groundClutterMode",
    "audioVisualSettings",
  ]);
  const UNSAFE_OBJECT_KEYS = new Set(["__proto__", "constructor", "prototype"]);

  function objectValue(value, label) {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw new Error(`${label} must be a JSON object.`);
    }
    return value;
  }

  function exactId(value, label) {
    if (
      typeof value !== "string" ||
      !value ||
      value.length > 1024 ||
      value.includes("\u0000")
    ) {
      throw new Error(`${label} is not a valid exact ID.`);
    }
    return value;
  }

  function canonicalEndpoints(from, to) {
    return from <= to ? [from, to] : [to, from];
  }

  function edgeKey(from, to) {
    return canonicalEndpoints(from, to).join("\u0000");
  }

  function normalizeJsonValue(value, label, depth = 0, budget = { nodes: 0 }) {
    budget.nodes += 1;
    if (budget.nodes > 50000) throw new Error(`${label} is too large.`);
    if (depth > 40) throw new Error(`${label} is nested too deeply.`);
    if (value === null || typeof value === "boolean") return value;
    if (typeof value === "number") {
      if (!Number.isFinite(value)) throw new Error(`${label} has a non-finite number.`);
      return value;
    }
    if (typeof value === "string") {
      if (value.length > 1000000) throw new Error(`${label} has an oversized string.`);
      return value;
    }
    if (Array.isArray(value)) {
      if (value.length > 20000) throw new Error(`${label} has an oversized array.`);
      return value.map((item, index) =>
        normalizeJsonValue(item, `${label}[${index}]`, depth + 1, budget)
      );
    }
    if (!value || typeof value !== "object") {
      throw new Error(`${label} has an unsupported value.`);
    }
    const keys = Object.keys(value).sort();
    if (keys.length > 5000) throw new Error(`${label} has too many fields.`);
    const result = {};
    for (const key of keys) {
      if (UNSAFE_OBJECT_KEYS.has(key)) throw new Error(`${label} has an unsafe field.`);
      result[key] = normalizeJsonValue(
        value[key],
        `${label}.${key}`,
        depth + 1,
        budget,
      );
    }
    return result;
  }

  function normalizeEdgeSettings(value, label) {
    if (value === undefined || value === null) return null;
    const row = objectValue(value, label);
    const result = {};
    for (const key of Object.keys(row).sort()) {
      if (!EDGE_SETTING_FIELDS.has(key)) {
        throw new Error(`${label} contains unsupported Edge annotation field ${key}.`);
      }
      result[key] = normalizeJsonValue(row[key], `${label}.${key}`);
    }
    return result;
  }

  function stableSettings(value) {
    return value === undefined ? "__undefined__" : JSON.stringify(value);
  }

  function hasCrosswalk(settings) {
    return Object.values(settings?.areaCallbacks || {}).some(
      (callback) => callback?.serviceName === "spot-crosswalk",
    );
  }

  function settingsCategories(desired, observed) {
    const categories = [];
    const changed = (fields) => fields.some(
      (field) => stableSettings(desired?.[field]) !== stableSettings(observed?.[field]),
    );
    if (changed(["areaCallbacks"])) {
      categories.push(hasCrosswalk(desired) || hasCrosswalk(observed) ? "crosswalk" : "area");
    }
    if (changed(["mobilityParams", "overrideMobilityParams"])) categories.push("mobility");
    if (changed(["stairs"])) categories.push("stairs");
    if (changed(["directionConstraint"])) categories.push("direction");
    if (changed(["pathFollowingMode", "requireAlignment", "maxCorridorDistance"])) {
      categories.push("path following");
    }
    if (changed(["flatGround", "groundClutterMode"])) categories.push("ground");
    if (changed(["cost"])) categories.push("cost");
    if (changed(["disableAlternateRouteFinding"])) categories.push("alternate route");
    if (changed(["disableDirectedExploration"])) categories.push("directed exploration");
    if (changed(["audioVisualSettings"])) categories.push("audio/visual");
    return categories;
  }

  function normalizeBaselineEdge(value, waypointIds, label) {
    const row = objectValue(value, label);
    const from = exactId(row.from, `${label} from waypoint`);
    const to = exactId(row.to, `${label} to waypoint`);
    if (from === to) throw new Error(`${label} is a self-edge.`);
    if (!waypointIds.has(from) || !waypointIds.has(to)) {
      throw new Error(`${label} references a waypoint outside the B0 Site Map.`);
    }
    return {
      from,
      to,
      edge_source: typeof row.edge_source === "string" ? row.edge_source : "",
      provenance: typeof row.provenance === "string" ? row.provenance : "",
      has_raw_counterpart: Boolean(row.has_raw_counterpart),
      settings: normalizeEdgeSettings(row.settings, `${label} settings`),
      settings_fingerprint:
        typeof row.settings_fingerprint === "string" ? row.settings_fingerprint : "",
      has_crosswalk: Boolean(row.has_crosswalk),
    };
  }

  function uniqueRows(values, waypointIds, label) {
    if (!Array.isArray(values)) throw new Error(`${label} must be an array.`);
    const result = [];
    const keys = new Set();
    for (let index = 0; index < values.length; index += 1) {
      const row = normalizeBaselineEdge(values[index], waypointIds, `${label}[${index}]`);
      const key = edgeKey(row.from, row.to);
      if (keys.has(key)) throw new Error(`${label} contains a duplicate endpoint pair.`);
      keys.add(key);
      result.push(row);
    }
    return { rows: result, keys };
  }

  function normalizeBaseline(value) {
    const baseline = objectValue(value, "The B0 baseline");
    if (baseline.kind !== BASELINE_KIND) {
      throw new Error("This file is not a complete graph-baseline inventory.");
    }
    const siteMap = objectValue(baseline.site_map, "The B0 Site Map");
    const siteMapId = exactId(siteMap.id, "The B0 Site Map ID");
    if (!Array.isArray(baseline.waypoint_ids) || !baseline.waypoint_ids.length) {
      throw new Error("The B0 baseline has no waypoint IDs.");
    }
    const waypointIds = [];
    const waypointIdSet = new Set();
    for (let index = 0; index < baseline.waypoint_ids.length; index += 1) {
      const id = exactId(baseline.waypoint_ids[index], `B0 waypoint_ids[${index}]`);
      if (waypointIdSet.has(id)) throw new Error("The B0 baseline has duplicate waypoint IDs.");
      waypointIdSet.add(id);
      waypointIds.push(id);
    }
    const effective = uniqueRows(
      baseline.effective_edges,
      waypointIdSet,
      "B0 effective_edges",
    );
    const tombstones = uniqueRows(baseline.tombstones, waypointIdSet, "B0 tombstones");
    for (const key of effective.keys) {
      if (tombstones.keys.has(key)) {
        throw new Error("The B0 baseline marks one endpoint pair active and deleted.");
      }
    }
    return {
      schema_version: 1,
      kind: BASELINE_KIND,
      site_map: {
        id: siteMapId,
        name: typeof siteMap.name === "string" ? siteMap.name : "",
      },
      waypoint_ids: waypointIds,
      effective_edges: effective.rows,
      tombstones: tombstones.rows,
      counts: {
        waypoints: waypointIds.length,
        effective_edges: effective.rows.length,
        site_edge_tombstones: tombstones.rows.length,
      },
    };
  }

  function normalizePosition(value) {
    if (!value || typeof value !== "object") return null;
    if (!Number.isFinite(value.x) || !Number.isFinite(value.y)) return null;
    return {
      x: value.x,
      y: value.y,
      z: Number.isFinite(value.z) ? value.z : 0,
    };
  }

  function normalizeSnapshot(value) {
    const snapshot = objectValue(value, "The live Orbit snapshot");
    if (snapshot.kind !== SNAPSHOT_KIND) {
      throw new Error("Orbit did not return a live graph snapshot.");
    }
    const siteMap = objectValue(snapshot.map, "The live Orbit Site Map");
    const siteMapId = exactId(siteMap.id, "The live Orbit Site Map ID");
    if (!Array.isArray(snapshot.waypoints) || !snapshot.waypoints.length) {
      throw new Error("The current Orbit map has no loaded waypoints.");
    }
    if (Number(snapshot.unresolvedWaypointCount || 0) > 0) {
      throw new Error("Orbit has not resolved every waypoint in the current map yet.");
    }
    if (Number(snapshot.unresolvedEdgeCount || 0) > 0) {
      throw new Error("Orbit has not resolved every edge in the current map yet.");
    }
    if (Number(snapshot.foreignEdgeEndpointCount || 0) > 0) {
      throw new Error("Orbit returned edge state outside the current Site Map; comparison stopped.");
    }
    const waypoints = [];
    const waypointIds = new Set();
    for (let index = 0; index < snapshot.waypoints.length; index += 1) {
      const row = objectValue(snapshot.waypoints[index], `Live waypoint[${index}]`);
      const id = exactId(row.id, `Live waypoint[${index}] ID`);
      if (waypointIds.has(id)) throw new Error("Orbit returned duplicate live waypoint IDs.");
      waypointIds.add(id);
      waypoints.push({
        id,
        name: typeof row.name === "string" ? row.name : "",
        recordingId: typeof row.recordingId === "string" ? row.recordingId : "",
        recordingName: typeof row.recordingName === "string" ? row.recordingName : "",
        position: normalizePosition(row.position),
      });
    }
    if (!Array.isArray(snapshot.edges)) throw new Error("Orbit returned no live edge list.");
    const edges = [];
    const edgeKeys = new Set();
    for (let index = 0; index < snapshot.edges.length; index += 1) {
      const row = objectValue(snapshot.edges[index], `Live edge[${index}]`);
      const from = exactId(row.from, `Live edge[${index}] from waypoint`);
      const to = exactId(row.to, `Live edge[${index}] to waypoint`);
      if (from === to) throw new Error("Orbit returned a live self-edge.");
      if (!waypointIds.has(from) || !waypointIds.has(to)) {
        throw new Error("Orbit returned a live edge outside the current waypoint set.");
      }
      const key = edgeKey(from, to);
      if (edgeKeys.has(key)) {
        throw new Error("Orbit returned duplicate live edges for one endpoint pair.");
      }
      edgeKeys.add(key);
      edges.push({
        from,
        to,
        source: typeof row.source === "string" ? row.source : "",
        sourceValue: Number.isInteger(row.sourceValue) ? row.sourceValue : null,
        disabled: Boolean(row.disabled),
        archived: Boolean(row.archived),
        settings: normalizeEdgeSettings(row.settings, `Live edge[${index}] settings`),
      });
    }
    return {
      kind: SNAPSHOT_KIND,
      map: {
        id: siteMapId,
        name: typeof siteMap.name === "string" ? siteMap.name : "",
      },
      recordingCount: Number(snapshot.recordingCount || 0),
      waypoints,
      edges,
    };
  }

  function waypointLabel(row) {
    return row?.recordingName || row?.recordingId || "";
  }

  function actionCoordinates(row) {
    return {
      from_x: row.fromWaypoint?.position?.x ?? null,
      from_y: row.fromWaypoint?.position?.y ?? null,
      to_x: row.toWaypoint?.position?.x ?? null,
      to_y: row.toWaypoint?.position?.y ?? null,
    };
  }

  function isManualEdge(row) {
    return row.edge_source === MANUAL_SOURCE || row.provenance === "site_only";
  }

  function currentWaypointScope(baseline, snapshot) {
    const baselineWaypointIds = new Set(baseline.waypoint_ids);
    const currentWaypoints = new Map(snapshot.waypoints.map((row) => [row.id, row]));
    const extraWaypointIds = [...currentWaypoints.keys()]
      .filter((id) => !baselineWaypointIds.has(id))
      .sort();
    return { baselineWaypointIds, currentWaypoints, extraWaypointIds };
  }

  function buildDeletedEdgeOverlay(baselineValue, snapshotValue) {
    const baseline = normalizeBaseline(baselineValue);
    const snapshot = normalizeSnapshot(snapshotValue);
    const { currentWaypoints } = currentWaypointScope(baseline, snapshot);
    const edges = [];
    let internalEdges = 0;
    let boundaryEdges = 0;
    let excludedOutsideEdges = 0;
    let missingPositionEdges = 0;

    for (const row of baseline.tombstones) {
      const fromWaypoint = currentWaypoints.get(row.from);
      const toWaypoint = currentWaypoints.get(row.to);
      if (fromWaypoint && toWaypoint) {
        internalEdges += 1;
        const coordinates = actionCoordinates({ fromWaypoint, toWaypoint });
        if (
          !Number.isFinite(coordinates.from_x) ||
          !Number.isFinite(coordinates.from_y) ||
          !Number.isFinite(coordinates.to_x) ||
          !Number.isFinite(coordinates.to_y)
        ) {
          missingPositionEdges += 1;
          continue;
        }
        edges.push({
          from: row.from,
          to: row.to,
          edge_source: row.edge_source,
          ...coordinates,
        });
      } else if (Boolean(fromWaypoint) !== Boolean(toWaypoint)) {
        boundaryEdges += 1;
      } else {
        excludedOutsideEdges += 1;
      }
    }

    return {
      schema_version: 1,
      kind: "orbit_deleted_edge_overlay",
      map: snapshot.map,
      edges,
      counts: {
        internal_edges: internalEdges,
        drawable_edges: edges.length,
        boundary_edges: boundaryEdges,
        excluded_outside_edges: excludedOutsideEdges,
        missing_position_edges: missingPositionEdges,
      },
    };
  }

  function buildGuide(baselineValue, snapshotValue) {
    const baseline = normalizeBaseline(baselineValue);
    const snapshot = normalizeSnapshot(snapshotValue);
    const {
      baselineWaypointIds,
      currentWaypoints,
      extraWaypointIds,
    } = currentWaypointScope(baseline, snapshot);

    const desiredEdges = new Map();
    const cuts = [];
    let excludedOutsideEdges = 0;
    for (const row of baseline.effective_edges) {
      const fromPresent = currentWaypoints.has(row.from);
      const toPresent = currentWaypoints.has(row.to);
      if (fromPresent && toPresent) {
        desiredEdges.set(edgeKey(row.from, row.to), row);
      } else if (fromPresent !== toPresent) {
        cuts.push({
          from: row.from,
          to: row.to,
          edge_source: row.edge_source,
          provenance: row.provenance,
          manual: isManualEdge(row),
          present_endpoint: fromPresent ? row.from : row.to,
          missing_endpoint: fromPresent ? row.to : row.from,
        });
      } else {
        excludedOutsideEdges += 1;
      }
    }
    const scopedObservedRows = snapshot.edges.filter(
      (row) => baselineWaypointIds.has(row.from) && baselineWaypointIds.has(row.to),
    );
    const ignoredExtraEdges = snapshot.edges.length - scopedObservedRows.length;
    if (desiredEdges.size > 0 && scopedObservedRows.length === 0) {
      throw new Error(
        "Orbit currently reports zero edges although B0 expects internal edges. " +
        "Wait for the map graph to finish loading, then refresh the comparison.",
      );
    }

    const observedEdges = new Map(
      scopedObservedRows.map((row) => [edgeKey(row.from, row.to), row]),
    );
    const tombstoneKeys = new Set(
      baseline.tombstones.map((row) => edgeKey(row.from, row.to)),
    );
    const pending = [];
    for (const [key, row] of desiredEdges) {
      if (observedEdges.has(key)) continue;
      const fromWaypoint = currentWaypoints.get(row.from);
      const toWaypoint = currentWaypoints.get(row.to);
      pending.push({
        operation: "connect",
        reason: isManualEdge(row) ? "missing_manual_edge" : "missing_expected_edge",
        from: row.from,
        to: row.to,
        from_name: fromWaypoint?.name || "",
        to_name: toWaypoint?.name || "",
        from_session: waypointLabel(fromWaypoint),
        to_session: waypointLabel(toWaypoint),
        from_recording_id: fromWaypoint?.recordingId || "",
        to_recording_id: toWaypoint?.recordingId || "",
        edge_source: row.edge_source,
        provenance: row.provenance,
        coordinate_scope: "orbit_live",
        ...actionCoordinates({ fromWaypoint, toWaypoint }),
      });
    }
    for (const [key, row] of observedEdges) {
      if (desiredEdges.has(key)) continue;
      const fromWaypoint = currentWaypoints.get(row.from);
      const toWaypoint = currentWaypoints.get(row.to);
      pending.push({
        operation: "delete",
        reason: tombstoneKeys.has(key) ? "resurrected_deleted_edge" : "unexpected_edge",
        from: row.from,
        to: row.to,
        from_name: fromWaypoint?.name || "",
        to_name: toWaypoint?.name || "",
        from_session: waypointLabel(fromWaypoint),
        to_session: waypointLabel(toWaypoint),
        from_recording_id: fromWaypoint?.recordingId || "",
        to_recording_id: toWaypoint?.recordingId || "",
        edge_source: row.source,
        coordinate_scope: "orbit_live",
        ...actionCoordinates({ fromWaypoint, toWaypoint }),
      });
    }
    let settingsProfileEdges = 0;
    for (const [key, row] of desiredEdges) {
      const observed = observedEdges.get(key);
      if (!observed || row.settings === null || observed.settings === null) continue;
      settingsProfileEdges += 1;
      if (stableSettings(row.settings) === stableSettings(observed.settings)) continue;
      const fromWaypoint = currentWaypoints.get(row.from);
      const toWaypoint = currentWaypoints.get(row.to);
      const storedDirectionMatches = row.from === observed.from && row.to === observed.to;
      const categories = settingsCategories(row.settings, observed.settings);
      pending.push({
        operation: "update",
        reason: "edge_settings_mismatch",
        from: row.from,
        to: row.to,
        from_name: fromWaypoint?.name || "",
        to_name: toWaypoint?.name || "",
        from_session: waypointLabel(fromWaypoint),
        to_session: waypointLabel(toWaypoint),
        from_recording_id: fromWaypoint?.recordingId || "",
        to_recording_id: toWaypoint?.recordingId || "",
        edge_source: row.edge_source,
        observed_source_value: observed.sourceValue,
        provenance: row.provenance,
        desired_settings: row.settings,
        observed_settings: observed.settings,
        settings_fingerprint: row.settings_fingerprint,
        settings_categories: categories,
        crosswalk: categories.includes("crosswalk") || row.has_crosswalk,
        stored_direction_matches: storedDirectionMatches,
        coordinate_scope: "orbit_live",
        ...actionCoordinates({ fromWaypoint, toWaypoint }),
      });
    }
    const priority = {
      missing_manual_edge: 0,
      resurrected_deleted_edge: 1,
      missing_expected_edge: 2,
      unexpected_edge: 3,
      edge_settings_mismatch: 4,
    };
    pending.sort((left, right) =>
      (priority[left.reason] - priority[right.reason]) ||
      edgeKey(left.from, left.to).localeCompare(edgeKey(right.from, right.to)),
    );
    const actions = pending.map((row, index) => ({ index: index + 1, ...row }));
    cuts.sort((left, right) =>
      Number(right.manual) - Number(left.manual) ||
      edgeKey(left.from, left.to).localeCompare(edgeKey(right.from, right.to)),
    );
    const connectEdges = actions.filter((row) => row.operation === "connect").length;
    const deleteEdges = actions.filter((row) => row.operation === "delete").length;
    const updateEdges = actions.filter((row) => row.operation === "update").length;
    return {
      schema_version: 1,
      kind: GUIDE_KIND,
      comparison_source: "live_orbit_vs_b0_baseline",
      baseline_site_map: baseline.site_map,
      after_site_map: snapshot.map,
      graph_reconciled: connectEdges === 0 && deleteEdges === 0,
      settings_reconciled: updateEdges === 0,
      fully_reconciled: actions.length === 0,
      settings_comparison_available: baseline.effective_edges.some(
        (row) => row.settings !== null,
      ),
      counts: {
        baseline_waypoints: baseline.waypoint_ids.length,
        current_waypoints: snapshot.waypoints.length,
        current_b0_waypoints: snapshot.waypoints.length - extraWaypointIds.length,
        ignored_extra_waypoints: extraWaypointIds.length,
        current_recordings: snapshot.recordingCount,
        baseline_effective_edges: baseline.effective_edges.length,
        desired_internal_edges: desiredEdges.size,
        observed_edges: observedEdges.size,
        observed_edges_total: snapshot.edges.length,
        ignored_extra_edges: ignoredExtraEdges,
        connect_edges: connectEdges,
        delete_edges: deleteEdges,
        update_edges: updateEdges,
        crosswalk_update_edges: actions.filter(
          (row) => row.operation === "update" && row.crosswalk,
        ).length,
        direction_blocked_update_edges: actions.filter(
          (row) => row.operation === "update" && !row.stored_direction_matches,
        ).length,
        settings_profile_edges: settingsProfileEdges,
        intentional_cut_edges: cuts.length,
        excluded_outside_edges: excludedOutsideEdges,
      },
      actions,
      intentional_cuts: cuts,
      comparison_policy: {
        identity: "exact waypoint ID and canonical unordered endpoint pair",
        desired_graph: "B0 effective induced subgraph for current Orbit waypoint set",
        current_graph: "Orbit in-page siteEdges state, including disabled/archived rows",
        boundary_edges: "reported only; never emitted as edit actions",
        public_edge_settings:
          "compared from B0 and restored only through Orbit's native updateSiteEdges draft",
        stored_direction:
          "exact B0/live direction required before automatic settings replay",
        extra_scope:
          "waypoints absent from B0 and every incident edge are counted but ignored",
        ignored: [
          "private SiteEdge wrapper fields",
          "SiteEdge/raw wrapper provenance equality",
          "extra recording scope absent from B0",
        ],
      },
    };
  }

  globalThis.OrbitGraphBaseline = Object.freeze({
    normalizeBaseline,
    normalizeSnapshot,
    buildGuide,
    buildDeletedEdgeOverlay,
    edgeKey,
    normalizeEdgeSettings,
  });
})();
