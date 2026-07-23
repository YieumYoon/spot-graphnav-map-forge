(() => {
  "use strict";

  const CHANNEL = "orbit-graph-repair-v1";
  const RESPONSE_TYPE = "orbit-graph-repair-response";
  const FOCUS_ACTION_TYPE = "mapDisplay/updateNeedsZoomToWaypoints";
  const ACTIVATE_TOOL_ACTION_TYPE = "mapEditorInfoSlice/activateTool";
  const SELECT_WAYPOINTS_ACTION_TYPE = "mapEditorInfoSlice/setSelectedWaypoints";
  const SELECT_EDGES_ACTION_TYPE = "mapEditorInfoSlice/setSelectedEdges";
  const ADD_SITE_EDGE_ACTION_TYPE = "mapEditorFormSlice/addSiteEdge";
  const UPDATE_SITE_EDGES_ACTION_TYPE = "mapEditorFormSlice/updateSiteEdges";
  const ARCHIVE_SITE_EDGES_ACTION_TYPE = "mapEditorFormSlice/archiveSiteEdges";
  const EDGE_SELECTION_TOOL = "edge_selection";
  const EDGE_VALIDATION_TIMEOUT_MS = 15000;
  const MAX_ARCHIVE_BATCH_SIZE = 5000;
  const MAX_SETTINGS_BATCH_SIZE = 5000;
  const EDGE_SETTING_FIELDS = [
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
  ];
  const EDGE_SETTING_FIELD_SET = new Set(EDGE_SETTING_FIELDS);
  const UNSAFE_OBJECT_KEYS = new Set(["__proto__", "constructor", "prototype"]);
  const EDGE_SOURCE_NAMES = {
    0: "unknown",
    1: "odometry",
    2: "small loop closure",
    3: "fiducial loop closure",
    4: "alternate route",
    5: "manual",
    6: "localization",
  };

  let catalogCache = null;

  if (globalThis.__orbitGraphRepairBridgeV1) {
    window.postMessage(
      { channel: CHANNEL, type: "orbit-graph-repair-ready" },
      location.origin,
    );
    return;
  }
  globalThis.__orbitGraphRepairBridgeV1 = true;

  function currentMapId() {
    const match = location.pathname.match(/\/control_room\/maps\/([^/]+)\/edit/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function isStore(value) {
    return Boolean(
      value &&
      typeof value === "object" &&
      typeof value.dispatch === "function" &&
      typeof value.getState === "function"
    );
  }

  function storeCandidate(value) {
    if (isStore(value)) return value;
    if (!value || typeof value !== "object") return null;
    for (const key of ["store", "value", "reduxStore"]) {
      try {
        if (isStore(value[key])) return value[key];
      } catch {
        // React values can expose guarded getters. Ignore them and continue.
      }
    }
    return null;
  }

  function findOrbitStore() {
    const root = document.getElementById("root");
    const containerKey = Object.keys(root || {}).find((key) =>
      key.startsWith("__reactContainer$"),
    );
    let fiber = containerKey ? root[containerKey] : null;
    if (fiber?.current) fiber = fiber.current;
    if (!fiber) return null;

    const stack = [fiber];
    const seen = new Set();
    while (stack.length && seen.size < 200000) {
      const current = stack.pop();
      if (!current || seen.has(current)) continue;
      seen.add(current);
      for (const value of [
        current.memoizedProps,
        current.pendingProps,
        current.stateNode,
        current.dependencies?.firstContext?.memoizedValue,
      ]) {
        const store = storeCandidate(value);
        if (store) return store;
      }
      let hook = current.memoizedState;
      for (let index = 0; hook && typeof hook === "object" && index < 30; index += 1) {
        const store = storeCandidate(hook.memoizedState);
        if (store) return store;
        hook = hook.next;
      }
      if (current.sibling) stack.push(current.sibling);
      if (current.child) stack.push(current.child);
    }
    return null;
  }

  function validWaypointIds(value) {
    return Boolean(
      Array.isArray(value) &&
      value.length === 2 &&
      value.every(
        (item) => typeof item === "string" && item.length > 0 && item.length <= 256,
      ) &&
      value[0] !== value[1]
    );
  }

  function validWaypointPairs(value) {
    return Boolean(
      Array.isArray(value) &&
      value.length > 0 &&
      value.length <= MAX_ARCHIVE_BATCH_SIZE &&
      value.every((pair) => validWaypointIds(pair))
    );
  }

  function validSettingsUpdates(value) {
    return Boolean(
      Array.isArray(value) &&
      value.length > 0 &&
      value.length <= MAX_SETTINGS_BATCH_SIZE &&
      value.every(
        (update) =>
          update &&
          validWaypointIds(update.waypointIds) &&
          update.storedFrom === update.waypointIds[0] &&
          update.storedTo === update.waypointIds[1] &&
          update.desiredSettings &&
          typeof update.desiredSettings === "object" &&
          !Array.isArray(update.desiredSettings) &&
          update.observedSettings &&
          typeof update.observedSettings === "object" &&
          !Array.isArray(update.observedSettings),
      )
    );
  }

  function edgeKey(from, to) {
    return from < to ? `${from}|${to}` : `${to}|${from}`;
  }

  function longLike(value) {
    return Boolean(
      value &&
      typeof value === "object" &&
      Number.isInteger(value.low) &&
      Number.isInteger(value.high) &&
      typeof value.unsigned === "boolean"
    );
  }

  function longString(value) {
    const low = BigInt(value.low >>> 0);
    const high = BigInt(value.high >>> 0);
    let combined = (high << 32n) | low;
    if (!value.unsigned && (value.high & 0x80000000) !== 0) {
      combined -= 1n << 64n;
    }
    return combined.toString();
  }

  function normalizeJsonValue(value, label, depth = 0, budget = { nodes: 0 }) {
    budget.nodes += 1;
    if (budget.nodes > 50000) throw new Error(`${label}_too_large`);
    if (depth > 40) throw new Error(`${label}_too_deep`);
    if (value === null || typeof value === "boolean") return value;
    if (typeof value === "number") {
      if (!Number.isFinite(value)) throw new Error(`${label}_non_finite`);
      return value;
    }
    if (typeof value === "bigint") return value.toString();
    if (typeof value === "string") {
      if (value.length > 1000000) throw new Error(`${label}_oversized_string`);
      return value;
    }
    if (longLike(value)) return longString(value);
    if (Array.isArray(value)) {
      if (value.length > 20000) throw new Error(`${label}_oversized_array`);
      return value.map((item, index) =>
        normalizeJsonValue(item, `${label}_${index}`, depth + 1, budget)
      );
    }
    if (!value || typeof value !== "object") throw new Error(`${label}_unsupported`);
    const result = {};
    const keys = Object.keys(value).sort();
    if (keys.length > 5000) throw new Error(`${label}_too_many_fields`);
    for (const key of keys) {
      if (UNSAFE_OBJECT_KEYS.has(key)) throw new Error(`${label}_unsafe_field`);
      result[key] = normalizeJsonValue(
        value[key],
        `${label}_${key}`,
        depth + 1,
        budget,
      );
    }
    return result;
  }

  function edgeSettings(annotations) {
    const result = {};
    for (const key of [...EDGE_SETTING_FIELDS].sort()) {
      if (!Object.prototype.hasOwnProperty.call(annotations || {}, key)) continue;
      const value = annotations[key];
      if (value === undefined) continue;
      result[key] = normalizeJsonValue(value, `edge_settings_${key}`);
    }
    return result;
  }

  function requestedEdgeSettings(value) {
    const result = {};
    for (const key of Object.keys(value).sort()) {
      if (!EDGE_SETTING_FIELD_SET.has(key)) {
        throw new Error("unsupported_edge_setting");
      }
      result[key] = normalizeJsonValue(value[key], `requested_edge_settings_${key}`);
    }
    return result;
  }

  function sameSettings(left, right) {
    return JSON.stringify(left) === JSON.stringify(right);
  }

  function sameWaypointPair(edgeId, waypointIds) {
    const from = edgeId?.fromWaypoint;
    const to = edgeId?.toWaypoint;
    return Boolean(
      from &&
      to &&
      edgeKey(from, to) === edgeKey(waypointIds[0], waypointIds[1])
    );
  }

  function editedEdgeEntity(state, waypointIds) {
    const key = edgeKey(waypointIds[0], waypointIds[1]);
    return state?.mapEditor?.form?.data?.edges?.entities?.[key] || null;
  }

  function editedEdgeOverride(state, waypointIds) {
    const key = edgeKey(waypointIds[0], waypointIds[1]);
    const edges = state?.mapEditor?.form?.data?.edges;
    return edges?.entities?.[key] || edges?.nonEntities?.[key] || null;
  }

  function storedEdgeEntity(state, waypointIds) {
    const key = edgeKey(waypointIds[0], waypointIds[1]);
    const direct = state?.siteEdges?.entities?.[key];
    if (direct) return direct;
    for (const id of state?.siteEdges?.ids || []) {
      const candidate = state?.siteEdges?.entities?.[id];
      if (sameWaypointPair(candidate?.edge?.id, waypointIds)) return candidate;
    }
    return null;
  }

  function effectiveEdgeEntity(state, waypointIds) {
    const edited = editedEdgeOverride(state, waypointIds);
    if (edited) return edited.archived || edited.disabled ? null : edited;
    const stored = storedEdgeEntity(state, waypointIds);
    return stored && !stored.archived && !stored.disabled ? stored : null;
  }

  function wait(milliseconds) {
    return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
  }

  async function validatedEdgeCandidate(store, mapId, waypointIds) {
    const initialState = store.getState();
    const previous = initialState?.mapEditor?.info?.pendingEdgeCreation
      ?.createdEdgeCandidate;
    const previousMatches = sameWaypointPair(previous?.edge?.id, waypointIds);
    store.dispatch({ type: SELECT_WAYPOINTS_ACTION_TYPE, payload: waypointIds });

    const deadline = Date.now() + EDGE_VALIDATION_TIMEOUT_MS;
    let sawValidation = false;
    while (Date.now() < deadline) {
      const state = store.getState();
      if (
        state?.mapDisplay?.siteMapId !== mapId ||
        currentMapId() !== mapId
      ) {
        return { error: "orbit_map_changed" };
      }
      const selected = state?.mapEditor?.info?.selectedWaypointIds;
      if (!validWaypointIds(selected) || edgeKey(...selected) !== edgeKey(...waypointIds)) {
        return { error: "orbit_selection_changed" };
      }
      const pending = state?.mapEditor?.info?.pendingEdgeCreation || {};
      sawValidation ||= Boolean(pending.validating);
      const candidate = pending.createdEdgeCandidate;
      const candidateReady =
        sameWaypointPair(candidate?.edge?.id, waypointIds) &&
        candidate?.siteMapId === mapId &&
        !pending.validating &&
        (candidate !== previous || sawValidation || previousMatches);
      if (candidateReady) {
        if ((pending.errors || []).length) {
          return { error: "edge_validation_failed" };
        }
        if ((pending.warnings || []).length || pending.showModal) {
          return { error: "edge_validation_warning" };
        }
        return { candidate };
      }
      await wait(50);
    }
    return { error: "edge_validation_timeout" };
  }

  async function connectWaypointPair(store, mapId, waypointIds) {
    const initialState = store.getState();
    const map = initialState?.siteMaps?.entities?.[mapId];
    const mapWaypointIds = new Set(map?.waypointIds || []);
    if (!waypointIds.every((id) => mapWaypointIds.has(id))) {
      return { error: "map_or_waypoint_mismatch" };
    }
    if (effectiveEdgeEntity(initialState, waypointIds)) {
      return { error: "edge_already_exists" };
    }

    const validation = await validatedEdgeCandidate(store, mapId, waypointIds);
    if (!validation.candidate) return validation;
    const beforeIndex = store.getState()?.mapEditor?.form?.present?.index;
    store.dispatch({
      type: ADD_SITE_EDGE_ACTION_TYPE,
      payload: validation.candidate,
    });
    const finalState = store.getState();
    const added = editedEdgeEntity(finalState, waypointIds);
    const afterIndex = finalState?.mapEditor?.form?.present?.index;
    if (
      !added ||
      added.archived ||
      added.disabled ||
      !sameWaypointPair(added.edge?.id, waypointIds) ||
      (Number.isInteger(beforeIndex) && afterIndex !== beforeIndex + 1)
    ) {
      return { error: "edge_draft_not_created" };
    }
    return {
      added: true,
      edgeKey: edgeKey(waypointIds[0], waypointIds[1]),
      editIndex: Number.isInteger(afterIndex) ? afterIndex : null,
    };
  }

  function archiveWaypointPairs(store, mapId, waypointPairs) {
    const initialState = store.getState();
    const map = initialState?.siteMaps?.entities?.[mapId];
    const mapWaypointIds = new Set(map?.waypointIds || []);
    const keys = [];
    const activeEdges = [];
    const seenKeys = new Set();

    for (const waypointIds of waypointPairs) {
      if (!waypointIds.every((id) => mapWaypointIds.has(id))) {
        return { error: "map_or_waypoint_mismatch" };
      }
      const key = edgeKey(waypointIds[0], waypointIds[1]);
      if (seenKeys.has(key)) return { error: "duplicate_edge_pair" };
      seenKeys.add(key);
      const edited = editedEdgeOverride(initialState, waypointIds);
      if (edited?.archived) return { error: "edge_already_archived" };
      const active = effectiveEdgeEntity(initialState, waypointIds);
      if (!active) return { error: "edge_not_found" };
      if (
        active.siteMapId !== mapId ||
        !sameWaypointPair(active.edge?.id, waypointIds)
      ) {
        return { error: "map_or_waypoint_mismatch" };
      }
      keys.push(key);
      activeEdges.push(active);
    }

    store.dispatch({ type: ACTIVATE_TOOL_ACTION_TYPE, payload: EDGE_SELECTION_TOOL });
    store.dispatch({ type: SELECT_EDGES_ACTION_TYPE, payload: keys });
    const selected = store.getState()?.mapEditor?.info?.selectedEdgeIds;
    const selectedKeys = new Set(Array.isArray(selected) ? selected : []);
    if (
      !Array.isArray(selected) ||
      selected.length !== keys.length ||
      selectedKeys.size !== keys.length ||
      keys.some((key) => !selectedKeys.has(key))
    ) {
      store.dispatch({ type: SELECT_EDGES_ACTION_TYPE, payload: [] });
      return { error: "orbit_selection_changed" };
    }

    const beforeIndex = store.getState()?.mapEditor?.form?.present?.index;
    store.dispatch({ type: ARCHIVE_SITE_EDGES_ACTION_TYPE, payload: activeEdges });
    const finalState = store.getState();
    const afterIndex = finalState?.mapEditor?.form?.present?.index;
    store.dispatch({ type: SELECT_EDGES_ACTION_TYPE, payload: [] });
    if (
      finalState?.mapDisplay?.siteMapId !== mapId ||
      keys.some((key, index) => {
        const archived = finalState?.mapEditor?.form?.data?.edges?.nonEntities?.[key];
        return (
          !archived?.archived ||
          archived.disabled ||
          archived.siteMapId !== mapId ||
          !sameWaypointPair(archived.edge?.id, waypointPairs[index])
        );
      }) ||
      (Number.isInteger(beforeIndex) && afterIndex !== beforeIndex + 1)
    ) {
      return { error: "edge_archive_batch_not_created" };
    }
    return {
      archived: true,
      archivedCount: keys.length,
      edgeKeys: keys,
      editIndex: Number.isInteger(afterIndex) ? afterIndex : null,
    };
  }

  function archiveWaypointPair(store, mapId, waypointIds) {
    const result = archiveWaypointPairs(store, mapId, [waypointIds]);
    if (!result.archived) {
      return result.error === "edge_archive_batch_not_created"
        ? { error: "edge_archive_not_created" }
        : result;
    }
    return {
      ...result,
      edgeKey: result.edgeKeys[0],
    };
  }

  function updateEdgeSettings(store, mapId, updates) {
    const initialState = store.getState();
    const map = initialState?.siteMaps?.entities?.[mapId];
    const mapWaypointIds = new Set(map?.waypointIds || []);
    const updatedEdges = [];
    const originalEdgesById = {};
    const keys = [];
    const seenKeys = new Set();

    try {
      for (const update of updates) {
        const waypointIds = update.waypointIds;
        if (!waypointIds.every((id) => mapWaypointIds.has(id))) {
          return { error: "map_or_waypoint_mismatch" };
        }
        const key = edgeKey(waypointIds[0], waypointIds[1]);
        if (seenKeys.has(key)) return { error: "duplicate_edge_pair" };
        seenKeys.add(key);
        const active = effectiveEdgeEntity(initialState, waypointIds);
        if (
          !active ||
          active.archived ||
          active.disabled ||
          active.siteMapId !== mapId ||
          !sameWaypointPair(active.edge?.id, waypointIds)
        ) {
          return { error: "edge_not_found" };
        }
        if (
          active.edge.id.fromWaypoint !== update.storedFrom ||
          active.edge.id.toWaypoint !== update.storedTo
        ) {
          return { error: "edge_direction_mismatch" };
        }
        if (
          Number.isInteger(update.observedSourceValue) &&
          active.edge.annotations?.edgeSource !== update.observedSourceValue
        ) {
          return { error: "edge_source_changed" };
        }
        const observed = requestedEdgeSettings(update.observedSettings);
        const current = edgeSettings(active.edge.annotations);
        if (!sameSettings(current, observed)) {
          return { error: "edge_settings_changed" };
        }
        const desired = requestedEdgeSettings(update.desiredSettings);
        const updated = {
          ...active,
          archived: false,
          edge: {
            ...active.edge,
            annotations: {
              ...desired,
              edgeSource: active.edge.annotations?.edgeSource ?? 0,
            },
          },
        };
        keys.push(key);
        updatedEdges.push(updated);
        originalEdgesById[key] = active;
      }
    } catch (error) {
      return { error: error?.message || "invalid_edge_settings" };
    }

    const beforeIndex = initialState?.mapEditor?.form?.present?.index;
    store.dispatch({
      type: UPDATE_SITE_EDGES_ACTION_TYPE,
      payload: { updatedEdges, originalEdgesById },
    });
    const finalState = store.getState();
    const afterIndex = finalState?.mapEditor?.form?.present?.index;
    if (
      finalState?.mapDisplay?.siteMapId !== mapId ||
      keys.some((key, index) => {
        const edited = editedEdgeOverride(finalState, updates[index].waypointIds);
        return (
          !edited ||
          edited.archived ||
          edited.disabled ||
          edited.siteMapId !== mapId ||
          !sameWaypointPair(edited.edge?.id, updates[index].waypointIds) ||
          !sameSettings(edgeSettings(edited.edge?.annotations), requestedEdgeSettings(
            updates[index].desiredSettings,
          ))
        );
      }) ||
      (Number.isInteger(beforeIndex) && afterIndex !== beforeIndex + 1)
    ) {
      return { error: "edge_settings_draft_not_created" };
    }
    return {
      updated: true,
      updatedCount: keys.length,
      edgeKeys: keys,
      editIndex: Number.isInteger(afterIndex) ? afterIndex : null,
    };
  }

  function anchorPositions(state, waypointIds) {
    const anchors = state?.mapDisplay?.anchoring?.anchors;
    if (!Array.isArray(anchors)) return null;
    const wanted = new Set(waypointIds);
    const positions = {};
    for (const anchor of anchors) {
      if (!wanted.has(anchor?.id)) continue;
      const position = anchor.seedTformWaypoint?.position;
      if (
        Number.isFinite(position?.x) &&
        Number.isFinite(position?.y) &&
        Number.isFinite(position?.z)
      ) {
        positions[anchor.id] = { x: position.x, y: position.y, z: position.z };
      }
    }
    return waypointIds.every((id) => positions[id]) ? positions : null;
  }

  function allAnchorPositions(state) {
    const positions = new Map();
    for (const anchor of state?.mapDisplay?.anchoring?.anchors || []) {
      const position = anchor?.seedTformWaypoint?.position;
      if (
        typeof anchor?.id === "string" &&
        Number.isFinite(position?.x) &&
        Number.isFinite(position?.y)
      ) {
        positions.set(anchor.id, {
          x: position.x,
          y: position.y,
          z: Number.isFinite(position.z) ? position.z : 0,
        });
      }
    }
    return positions;
  }

  function edgeSourceName(value) {
    return EDGE_SOURCE_NAMES[value] || `source ${String(value ?? "unknown")}`;
  }

  function mapCatalog(state, mapId) {
    const map = state?.siteMaps?.entities?.[mapId];
    const waypointEntities = state?.siteWaypoints?.entities;
    const edgeEntities = state?.siteEdges?.entities;
    const recordingEntities = state?.recordingSessions?.entities;
    if (!map || !waypointEntities || !edgeEntities || !recordingEntities) return null;

    if (
      catalogCache?.map === map &&
      catalogCache?.waypointEntities === waypointEntities &&
      catalogCache?.edgeEntities === edgeEntities &&
      catalogCache?.recordingEntities === recordingEntities
    ) {
      return catalogCache.value;
    }

    const waypointIds = Array.isArray(map.waypointIds) ? map.waypointIds : [];
    const recordingIds = Array.isArray(map.recordingSessionIds)
      ? map.recordingSessionIds
      : [];
    const sessionByWaypoint = new Map();
    for (const recordingId of recordingIds) {
      const recording = recordingEntities[recordingId];
      for (const waypointId of recording?.waypointIds || []) {
        sessionByWaypoint.set(waypointId, recordingId);
      }
    }

    const edgesByWaypoint = new Map();
    const sourceCounts = {};
    let disabledEdges = 0;
    let archivedEdges = 0;
    let crossRecordingManualEdges = 0;
    for (const edgeId of state?.siteEdges?.ids || []) {
      const entity = edgeEntities[edgeId];
      const edge = entity?.edge;
      const from = edge?.id?.fromWaypoint;
      const to = edge?.id?.toWaypoint;
      if (!from || !to) continue;
      const source = edgeSourceName(edge.annotations?.edgeSource);
      sourceCounts[source] = (sourceCounts[source] || 0) + 1;
      if (entity.disabled) disabledEdges += 1;
      if (entity.archived) archivedEdges += 1;
      const summary = { id: edgeId, from, to, source };
      if (!edgesByWaypoint.has(from)) edgesByWaypoint.set(from, []);
      if (!edgesByWaypoint.has(to)) edgesByWaypoint.set(to, []);
      edgesByWaypoint.get(from).push(summary);
      edgesByWaypoint.get(to).push(summary);
      if (
        edge.annotations?.edgeSource === 5 &&
        sessionByWaypoint.get(from) &&
        sessionByWaypoint.get(to) &&
        sessionByWaypoint.get(from) !== sessionByWaypoint.get(to)
      ) {
        crossRecordingManualEdges += 1;
      }
    }

    const waypointNameCounts = {};
    for (const waypointId of waypointIds) {
      const name = waypointEntities[waypointId]?.waypoint?.annotations?.name;
      if (name) waypointNameCounts[name] = (waypointNameCounts[name] || 0) + 1;
    }

    const value = {
      map,
      waypointIds,
      recordingIds,
      sessionByWaypoint,
      edgesByWaypoint,
      summary: {
        waypointCount: waypointIds.length,
        edgeCount: (state?.siteEdges?.ids || []).length,
        recordingCount: recordingIds.length,
        sourceCounts,
        disabledEdges,
        archivedEdges,
        crossRecordingManualEdges,
        duplicateWaypointNameGroups: Object.values(waypointNameCounts).filter(
          (count) => count > 1,
        ).length,
      },
    };
    catalogCache = { map, waypointEntities, edgeEntities, recordingEntities, value };
    return value;
  }

  function recordingSummary(state, catalog, waypointId) {
    const id = catalog.sessionByWaypoint.get(waypointId);
    const recording = id ? state?.recordingSessions?.entities?.[id] : null;
    if (!recording) return null;
    return {
      id,
      name: recording.name || "",
      startTime: recording.startTime || "",
      endTime: recording.endTime || "",
      robotNickname: recording.robotNickname || "",
      robotSerial: recording.robotSerial || "",
      clientName: recording.clientName || "",
      waypointCount: Array.isArray(recording.waypointIds)
        ? recording.waypointIds.length
        : 0,
    };
  }

  function selectedWaypointSummary(state, catalog, waypointId) {
    const entity = state?.siteWaypoints?.entities?.[waypointId];
    const waypoint = entity?.waypoint;
    if (!waypoint) return null;
    const incidentEdges = catalog.edgesByWaypoint.get(waypointId) || [];
    const edgeSources = {};
    for (const edge of incidentEdges) {
      edgeSources[edge.source] = (edgeSources[edge.source] || 0) + 1;
    }
    const anchor = state?.mapDisplay?.anchoring?.anchors?.find(
      (candidate) => candidate?.id === waypointId,
    );
    return {
      id: waypointId,
      name: waypoint.annotations?.name || "",
      snapshotId: waypoint.snapshotId || "",
      creationTime: waypoint.annotations?.creationTime || null,
      clientMetadata: waypoint.annotations?.clientMetadata || null,
      mapPosition: anchor?.seedTformWaypoint?.position || null,
      rawPosition: waypoint.waypointTformKo?.position || null,
      recording: recordingSummary(state, catalog, waypointId),
      degree: incidentEdges.length,
      edgeSources,
      neighbors: incidentEdges.map((edge) => ({
        id: edge.from === waypointId ? edge.to : edge.from,
        name:
          state?.siteWaypoints?.entities?.[
            edge.from === waypointId ? edge.to : edge.from
          ]?.waypoint?.annotations?.name || "",
        edgeId: edge.id,
        source: edge.source,
      })),
      panoSettings: entity.sitePanoSettings || null,
    };
  }

  function selectedEdgeSummary(state, catalog, edgeId) {
    const entity = state?.siteEdges?.entities?.[edgeId];
    const edge = entity?.edge;
    const from = edge?.id?.fromWaypoint;
    const to = edge?.id?.toWaypoint;
    if (!from || !to) return null;
    const fromRecording = recordingSummary(state, catalog, from);
    const toRecording = recordingSummary(state, catalog, to);
    const position = edge.fromTformTo?.position;
    const length = [position?.x, position?.y, position?.z].every(Number.isFinite)
      ? Math.hypot(position.x, position.y, position.z)
      : null;
    const settings = edgeSettings(edge.annotations);
    const areaCallbacks = Object.entries(settings.areaCallbacks || {}).map(
      ([id, callback]) => ({
        id,
        serviceName: callback?.serviceName || "",
        description: callback?.description || "",
      }),
    );
    return {
      id: edgeId,
      from,
      to,
      fromName: state?.siteWaypoints?.entities?.[from]?.waypoint?.annotations?.name || "",
      toName: state?.siteWaypoints?.entities?.[to]?.waypoint?.annotations?.name || "",
      snapshotId: edge.snapshotId || "",
      source: edgeSourceName(edge.annotations?.edgeSource),
      sourceValue: edge.annotations?.edgeSource ?? null,
      manual: edge.annotations?.edgeSource === 5,
      disabled: Boolean(entity.disabled),
      archived: Boolean(entity.archived),
      length,
      settings,
      areaCallbacks,
      crosswalks: areaCallbacks.filter(
        (callback) => callback.serviceName === "spot-crosswalk",
      ),
      fromRecording,
      toRecording,
      crossRecording: Boolean(
        fromRecording?.id && toRecording?.id && fromRecording.id !== toRecording.id,
      ),
    };
  }

  function inspectionSnapshot(state, mapId) {
    const catalog = mapCatalog(state, mapId);
    if (!catalog) return null;
    const info = state?.mapEditor?.info || {};
    const waypointIds = Array.isArray(info.selectedWaypointIds)
      ? info.selectedWaypointIds
      : [];
    const edgeIds = Array.isArray(info.selectedEdgeIds) ? info.selectedEdgeIds : [];
    return {
      map: {
        id: mapId,
        name: catalog.map.metadata?.displayName || "",
        ...catalog.summary,
      },
      activeTool: info.activeTool || "",
      waypointSelectionCount: waypointIds.length,
      edgeSelectionCount: edgeIds.length,
      waypoints: waypointIds
        .slice(0, 20)
        .map((id) => selectedWaypointSummary(state, catalog, id))
        .filter(Boolean),
      edges: edgeIds
        .slice(0, 20)
        .map((id) => selectedEdgeSummary(state, catalog, id))
        .filter(Boolean),
    };
  }

  function graphSnapshot(state, mapId) {
    const catalog = mapCatalog(state, mapId);
    if (!catalog) return null;
    const waypointEntities = state?.siteWaypoints?.entities || {};
    const edgeEntities = state?.siteEdges?.entities || {};
    const recordingEntities = state?.recordingSessions?.entities || {};
    const waypointIdSet = new Set(catalog.waypointIds);
    const anchorByWaypoint = allAnchorPositions(state);
    const waypoints = [];
    let unresolvedWaypointCount = 0;
    for (const id of catalog.waypointIds) {
      const waypoint = waypointEntities[id]?.waypoint;
      if (!waypoint) {
        unresolvedWaypointCount += 1;
        continue;
      }
      const recordingId = catalog.sessionByWaypoint.get(id) || "";
      waypoints.push({
        id,
        name: waypoint.annotations?.name || "",
        recordingId,
        recordingName: recordingEntities[recordingId]?.name || "",
        position: anchorByWaypoint.get(id) || null,
      });
    }

    const edges = [];
    const effectiveEdges = new Map();
    let unresolvedEdgeCount = 0;
    let foreignEdgeEndpointCount = 0;
    for (const edgeId of state?.siteEdges?.ids || []) {
      const entity = edgeEntities[edgeId];
      const edge = entity?.edge;
      const from = edge?.id?.fromWaypoint;
      const to = edge?.id?.toWaypoint;
      if (!from || !to) {
        unresolvedEdgeCount += 1;
        continue;
      }
      if (!waypointIdSet.has(from) || !waypointIdSet.has(to)) {
        foreignEdgeEndpointCount += 1;
        continue;
      }
      if (entity.archived || entity.disabled) continue;
      effectiveEdges.set(edgeKey(from, to), entity);
    }
    const editedEdges = state?.mapEditor?.form?.data?.edges;
    const applyEditedEdge = (entity) => {
      const from = entity?.edge?.id?.fromWaypoint;
      const to = entity?.edge?.id?.toWaypoint;
      if (!from || !to) {
        unresolvedEdgeCount += 1;
        return;
      }
      if (!waypointIdSet.has(from) || !waypointIdSet.has(to)) {
        foreignEdgeEndpointCount += 1;
        return;
      }
      const key = edgeKey(from, to);
      if (entity.archived || entity.disabled) effectiveEdges.delete(key);
      else effectiveEdges.set(key, entity);
    };
    for (const edgeId of editedEdges?.ids || []) {
      applyEditedEdge(editedEdges?.entities?.[edgeId]);
    }
    for (const entity of Object.values(editedEdges?.nonEntities || {})) {
      applyEditedEdge(entity);
    }
    for (const entity of effectiveEdges.values()) {
      const edge = entity.edge;
      edges.push({
        from: edge.id.fromWaypoint,
        to: edge.id.toWaypoint,
        source: edgeSourceName(edge.annotations?.edgeSource),
        sourceValue: edge.annotations?.edgeSource ?? null,
        disabled: false,
        archived: false,
        settings: edgeSettings(edge.annotations),
      });
    }
    return {
      kind: "orbit_live_graph_snapshot",
      map: {
        id: mapId,
        name: catalog.map.metadata?.displayName || "",
      },
      recordingCount: catalog.recordingIds.length,
      waypoints,
      edges,
      unresolvedWaypointCount,
      unresolvedEdgeCount,
      foreignEdgeEndpointCount,
      anchorCount: anchorByWaypoint.size,
    };
  }

  function respond(requestId, payload) {
    window.postMessage(
      { channel: CHANNEL, type: RESPONSE_TYPE, requestId, ...payload },
      location.origin,
    );
  }

  window.addEventListener("message", async (event) => {
    if (
      event.source !== window ||
      event.origin !== location.origin ||
      event.data?.channel !== CHANNEL ||
      event.data?.type !== "orbit-graph-repair-request"
    ) return;
    const {
      requestId,
      command,
      waypointIds,
      waypointPairs,
      settingsUpdates,
      mapId,
    } = event.data;
    if (
      typeof requestId !== "string" ||
      ![
        "resolve",
        "focus",
        "inspect",
        "snapshot",
        "connect",
        "archive",
        "archive_many",
        "update_settings_many",
      ].includes(command)
    ) return;
    if (mapId !== currentMapId()) {
      respond(requestId, { ok: false, error: "map_or_waypoint_mismatch" });
      return;
    }
    if (["resolve", "focus", "connect", "archive"].includes(command) && !validWaypointIds(waypointIds)) {
      respond(requestId, { ok: false, error: "map_or_waypoint_mismatch" });
      return;
    }
    if (command === "archive_many" && !validWaypointPairs(waypointPairs)) {
      respond(requestId, { ok: false, error: "invalid_archive_batch" });
      return;
    }
    if (command === "update_settings_many" && !validSettingsUpdates(settingsUpdates)) {
      respond(requestId, { ok: false, error: "invalid_settings_batch" });
      return;
    }

    const store = findOrbitStore();
    if (!store) {
      respond(requestId, { ok: false, error: "orbit_store_unavailable" });
      return;
    }
    const orbitState = store.getState();
    if (orbitState?.mapDisplay?.siteMapId !== mapId) {
      respond(requestId, { ok: false, error: "orbit_map_not_loaded" });
      return;
    }
    if (command === "inspect") {
      const inspector = inspectionSnapshot(orbitState, mapId);
      if (!inspector) {
        respond(requestId, { ok: false, error: "orbit_inspector_unavailable" });
        return;
      }
      respond(requestId, {
        ok: true,
        inspector,
        adapter: "orbit-5.1-readonly-map-inspector",
      });
      return;
    }
    if (command === "snapshot") {
      const snapshot = graphSnapshot(orbitState, mapId);
      if (!snapshot) {
        respond(requestId, { ok: false, error: "orbit_snapshot_unavailable" });
        return;
      }
      respond(requestId, {
        ok: true,
        snapshot,
        adapter: "orbit-5.1-readonly-graph-snapshot",
      });
      return;
    }
    if (command === "connect") {
      const result = await connectWaypointPair(store, mapId, waypointIds);
      if (!result.added) {
        respond(requestId, { ok: false, error: result.error });
        return;
      }
      respond(requestId, {
        ok: true,
        added: true,
        edgeKey: result.edgeKey,
        editIndex: result.editIndex,
        adapter: "orbit-5.1-native-edge-draft",
      });
      return;
    }
    if (command === "archive") {
      const result = archiveWaypointPair(store, mapId, waypointIds);
      if (!result.archived) {
        respond(requestId, { ok: false, error: result.error });
        return;
      }
      respond(requestId, {
        ok: true,
        archived: true,
        edgeKey: result.edgeKey,
        editIndex: result.editIndex,
        adapter: "orbit-5.1-native-edge-archive-draft",
      });
      return;
    }
    if (command === "archive_many") {
      const result = archiveWaypointPairs(store, mapId, waypointPairs);
      if (!result.archived) {
        respond(requestId, { ok: false, error: result.error });
        return;
      }
      respond(requestId, {
        ok: true,
        archived: true,
        archivedCount: result.archivedCount,
        edgeKeys: result.edgeKeys,
        editIndex: result.editIndex,
        adapter: "orbit-5.1-native-edge-batch-archive-draft",
      });
      return;
    }
    if (command === "update_settings_many") {
      const result = updateEdgeSettings(store, mapId, settingsUpdates);
      if (!result.updated) {
        respond(requestId, { ok: false, error: result.error });
        return;
      }
      respond(requestId, {
        ok: true,
        updated: true,
        updatedCount: result.updatedCount,
        edgeKeys: result.edgeKeys,
        editIndex: result.editIndex,
        adapter: "orbit-5.1-native-edge-settings-batch-draft",
      });
      return;
    }
    const positions = anchorPositions(orbitState, waypointIds);
    if (!positions) {
      respond(requestId, { ok: false, error: "waypoint_anchor_unavailable" });
      return;
    }
    if (command === "focus") {
      store.dispatch({ type: FOCUS_ACTION_TYPE, payload: waypointIds });
    }
    respond(requestId, {
      ok: true,
      positions,
      adapter: "orbit-5.1-mapDisplay/updateNeedsZoomToWaypoints",
    });
  });

  window.postMessage(
    { channel: CHANNEL, type: "orbit-graph-repair-ready" },
    location.origin,
  );
})();
