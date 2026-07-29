(() => {
  "use strict";

  const CHANNEL = "orbit-site-map-editor-v1";
  const REQUEST_TYPE = "orbit-site-map-editor-request";
  const RESPONSE_TYPE = "orbit-site-map-editor-response";
  const READY_TYPE = "orbit-site-map-editor-ready";
  const ACTION_SELECTION_TYPE = "orbit-site-map-editor-action-selection";
  const REGISTRY_KEY = "__orbitSiteMapEditorBridgeV2";
  const SESSION_ID = String(document.currentScript?.dataset?.osmeSession || "");
  const FOCUS_ACTION_TYPE = "mapDisplay/updateNeedsZoomToWaypoints";
  const ACTIVATE_TOOL_ACTION_TYPE = "mapEditorInfoSlice/activateTool";
  const SELECT_WAYPOINTS_ACTION_TYPE = "mapEditorInfoSlice/setSelectedWaypoints";
  const SELECT_EDGES_ACTION_TYPE = "mapEditorInfoSlice/setSelectedEdges";
  const ADD_SITE_EDGE_ACTION_TYPE = "mapEditorFormSlice/addSiteEdge";
  const UPDATE_SITE_EDGES_ACTION_TYPE = "mapEditorFormSlice/updateSiteEdges";
  const ARCHIVE_SITE_EDGES_ACTION_TYPE = "mapEditorFormSlice/archiveSiteEdges";
  const UPDATE_ACTION_NAMES_ACTION_TYPE = "missionsAndActionsForm/updateActions";
  const EDGE_SELECTION_TOOL = "edge_selection";
  const EDGE_VALIDATION_TIMEOUT_MS = 15000;
  const MAX_SELECTION_SIZE = 5000;
  const MAX_EDGE_BATCH_SIZE = 5000;
  const MAX_ACTION_NAME_BATCH_SIZE = 5000;
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

  const previousBridge = globalThis[REGISTRY_KEY];
  if (previousBridge?.dispose) previousBridge.dispose();
  if (globalThis.__orbitSiteMapEditorBridgeV1 === true && !previousBridge) {
    window.postMessage(
      { channel: CHANNEL, type: READY_TYPE, sessionId: SESSION_ID, legacy: true },
      location.origin,
    );
    return;
  }
  const handledRequestIds = new Set();
  let mutationInFlight = false;
  let validationInFlight = false;
  let disposed = false;
  const historyRestorers = [];
  let lastActionRouteId = searchParameter("action");

  function searchParameter(name) {
    const source = String(location.search || "").replace(/^\?/, "");
    for (const segment of source.split("&")) {
      if (!segment) continue;
      const separator = segment.indexOf("=");
      const rawKey = separator >= 0 ? segment.slice(0, separator) : segment;
      const rawValue = separator >= 0 ? segment.slice(separator + 1) : "";
      try {
        if (decodeURIComponent(rawKey.replaceAll("+", " ")) === name) {
          return decodeURIComponent(rawValue.replaceAll("+", " "));
        }
      } catch {
        // Ignore malformed query segments supplied by the host page.
      }
    }
    return "";
  }

  function isCurrentBridge() {
    return Boolean(
      !disposed &&
      globalThis[REGISTRY_KEY]?.sessionId === SESSION_ID,
    );
  }

  function currentMapId() {
    const match = location.pathname.match(/\/control_room\/maps\/([^/]+)\/edit/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function currentActionRouteId() {
    return searchParameter("action");
  }

  function publishActionRouteChange() {
    if (!isCurrentBridge()) return;
    const actionId = currentActionRouteId();
    if (actionId === lastActionRouteId) return;
    lastActionRouteId = actionId;
    window.postMessage(
      {
        channel: CHANNEL,
        type: ACTION_SELECTION_TYPE,
        ...(SESSION_ID ? { sessionId: SESSION_ID } : {}),
        actionId,
      },
      location.origin,
    );
  }

  function observeHistoryMethod(methodName) {
    const browserHistory = globalThis.history;
    const original = browserHistory?.[methodName];
    if (typeof original !== "function") return;
    function observedHistoryMethod(...args) {
      const result = original.apply(this, args);
      publishActionRouteChange();
      return result;
    }
    browserHistory[methodName] = observedHistoryMethod;
    historyRestorers.push(() => {
      if (browserHistory[methodName] === observedHistoryMethod) {
        browserHistory[methodName] = original;
      }
    });
  }

  observeHistoryMethod("pushState");
  observeHistoryMethod("replaceState");
  window.addEventListener("popstate", publishActionRouteChange);

  function isStore(value) {
    return Boolean(
      value &&
      typeof value === "object" &&
      typeof value.dispatch === "function" &&
      typeof value.getState === "function",
    );
  }

  function storeCandidate(value) {
    if (isStore(value)) return value;
    if (!value || typeof value !== "object") return null;
    for (const key of ["store", "value", "reduxStore"]) {
      try {
        if (isStore(value[key])) return value[key];
      } catch {
        // Some React values expose guarded getters.
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

  function edgeKey(from, to) {
    return from < to ? `${from}|${to}` : `${to}|${from}`;
  }

  function validWaypointPair(value) {
    return Boolean(
      Array.isArray(value) &&
      value.length === 2 &&
      value[0] !== value[1] &&
      value.every(
        (item) => typeof item === "string" && item.length > 0 && item.length <= 256,
      ),
    );
  }

  function validWaypointList(value) {
    return Boolean(
      Array.isArray(value) &&
      value.length > 0 &&
      value.length <= MAX_SELECTION_SIZE &&
      value.every(
        (item) => typeof item === "string" && item.length > 0 && item.length <= 256,
      ),
    );
  }

  function validEdgeIdList(value) {
    return Boolean(
      Array.isArray(value) &&
      value.length <= MAX_SELECTION_SIZE &&
      value.every(
        (item) => typeof item === "string" && item.length > 0 && item.length <= 600,
      ),
    );
  }

  function validWaypointPairs(value) {
    return Boolean(
      Array.isArray(value) &&
      value.length > 0 &&
      value.length <= MAX_EDGE_BATCH_SIZE &&
      value.every((pair) => validWaypointPair(pair)),
    );
  }

  function sameWaypointPair(edgeId, waypointIds) {
    const from = edgeId?.fromWaypoint;
    const to = edgeId?.toWaypoint;
    return Boolean(
      from &&
      to &&
      edgeKey(from, to) === edgeKey(waypointIds[0], waypointIds[1]),
    );
  }

  function longLike(value) {
    return Boolean(
      value &&
      typeof value === "object" &&
      Number.isInteger(value.low) &&
      Number.isInteger(value.high) &&
      typeof value.unsigned === "boolean",
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

  function timestampString(value) {
    if (typeof value === "string") return value;
    if (!value || typeof value !== "object") return "";
    const rawSeconds = longLike(value.seconds)
      ? longString(value.seconds)
      : value.seconds;
    const seconds = Number(rawSeconds);
    const nanos = Number(value.nanos || 0);
    if (!Number.isFinite(seconds) || !Number.isFinite(nanos)) return "";
    const date = new Date(seconds * 1000 + nanos / 1000000);
    return Number.isFinite(date.getTime()) ? date.toISOString() : "";
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

  function unmodeledAnnotations(annotations) {
    const result = {};
    for (const key of Object.keys(annotations || {}).sort()) {
      if (key === "edgeSource" || EDGE_SETTING_FIELD_SET.has(key)) continue;
      const value = annotations[key];
      if (value === undefined) continue;
      result[key] = normalizeJsonValue(value, `edge_annotation_${key}`);
    }
    return result;
  }

  function requestedEdgeSettings(value) {
    const result = {};
    for (const key of Object.keys(value || {}).sort()) {
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

  function validSettingsUpdates(value) {
    return Boolean(
      Array.isArray(value) &&
      value.length > 0 &&
      value.length <= MAX_EDGE_BATCH_SIZE &&
      value.every(
        (update) =>
          update &&
          validWaypointPair(update.waypointIds) &&
          update.storedFrom === update.waypointIds[0] &&
          update.storedTo === update.waypointIds[1] &&
          update.desiredSettings &&
          typeof update.desiredSettings === "object" &&
          !Array.isArray(update.desiredSettings) &&
          update.observedSettings &&
          typeof update.observedSettings === "object" &&
          !Array.isArray(update.observedSettings),
      ),
    );
  }

  function validActionNameUpdates(value) {
    return Boolean(
      Array.isArray(value) &&
      value.length > 0 &&
      value.length <= MAX_ACTION_NAME_BATCH_SIZE &&
      value.every(
        (update) =>
          update &&
          typeof update.id === "string" &&
          update.id.length > 0 &&
          update.id.length <= 600 &&
          typeof update.waypointId === "string" &&
          update.waypointId.length > 0 &&
          update.waypointId.length <= 256 &&
          typeof update.observedName === "string" &&
          update.observedName.length <= 512 &&
          typeof update.desiredName === "string" &&
          update.desiredName.length > 0 &&
          update.desiredName.length <= 512 &&
          /^[A-Z0-9._/-]+$/.test(update.desiredName),
      )
    );
  }

  function edgeSourceName(value) {
    return EDGE_SOURCE_NAMES[value] || `source ${String(value ?? "unknown")}`;
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

  function allAnchorTransforms(state) {
    const transforms = new Map();
    for (const anchor of state?.mapDisplay?.anchoring?.anchors || []) {
      const transform = anchor?.seedTformWaypoint;
      const position = transform?.position;
      if (
        typeof anchor?.id === "string" &&
        Number.isFinite(position?.x) &&
        Number.isFinite(position?.y)
      ) {
        transforms.set(anchor.id, {
          position: {
            x: position.x,
            y: position.y,
            z: Number.isFinite(position.z) ? position.z : 0,
          },
          rotation: transform?.rotation || null,
        });
      }
    }
    return transforms;
  }

  function rotatePosition(position, rotation) {
    if (
      !rotation ||
      ![rotation.x, rotation.y, rotation.z, rotation.w].every(Number.isFinite)
    ) return { ...position };
    const vector = {
      x: position.x,
      y: position.y,
      z: Number.isFinite(position.z) ? position.z : 0,
    };
    const quaternionLength = Math.hypot(
      rotation.x,
      rotation.y,
      rotation.z,
      rotation.w,
    );
    if (!quaternionLength) return vector;
    const x = rotation.x / quaternionLength;
    const y = rotation.y / quaternionLength;
    const z = rotation.z / quaternionLength;
    const w = rotation.w / quaternionLength;
    const dot = x * vector.x + y * vector.y + z * vector.z;
    const cross = {
      x: y * vector.z - z * vector.y,
      y: z * vector.x - x * vector.z,
      z: x * vector.y - y * vector.x,
    };
    const scale = w * w - x * x - y * y - z * z;
    return {
      x: 2 * dot * x + scale * vector.x + 2 * w * cross.x,
      y: 2 * dot * y + scale * vector.y + 2 * w * cross.y,
      z: 2 * dot * z + scale * vector.z + 2 * w * cross.z,
    };
  }

  function actionMapPosition(entity, anchorTransforms) {
    const direct = entityPosition(entity);
    if (direct) return direct;
    const offset = entity?.waypointTformBodyOffset?.position;
    if (!Number.isFinite(offset?.x) || !Number.isFinite(offset?.y)) return null;
    const waypointId = entityWaypointIds(entity).find((id) => anchorTransforms.has(id));
    const anchor = anchorTransforms.get(waypointId);
    if (!anchor) return null;
    const rotated = rotatePosition(offset, anchor.rotation);
    return {
      x: anchor.position.x + rotated.x,
      y: anchor.position.y + rotated.y,
      z: anchor.position.z + rotated.z,
    };
  }

  function effectiveEdges(state, waypointIdSet) {
    const effective = new Map();
    for (const id of state?.siteEdges?.ids || []) {
      const entity = state?.siteEdges?.entities?.[id];
      const from = entity?.edge?.id?.fromWaypoint;
      const to = entity?.edge?.id?.toWaypoint;
      if (!from || !to || !waypointIdSet.has(from) || !waypointIdSet.has(to)) continue;
      if (!entity.archived && !entity.disabled) {
        effective.set(edgeKey(from, to), { id, entity });
      }
    }
    const edited = state?.mapEditor?.form?.data?.edges;
    const apply = (entity, id = "") => {
      const from = entity?.edge?.id?.fromWaypoint;
      const to = entity?.edge?.id?.toWaypoint;
      if (!from || !to || !waypointIdSet.has(from) || !waypointIdSet.has(to)) return;
      const key = edgeKey(from, to);
      if (entity.archived || entity.disabled) effective.delete(key);
      else effective.set(key, { id: id || key, entity });
    };
    for (const id of edited?.ids || []) apply(edited?.entities?.[id], id);
    for (const [id, entity] of Object.entries(edited?.nonEntities || {})) {
      apply(entity, id);
    }
    return effective;
  }

  function entityAdapter(state, sliceNames) {
    for (const name of sliceNames) {
      const slice = state?.[name];
      if (slice?.entities && typeof slice.entities === "object") {
        return { name, entities: slice.entities, ids: slice.ids || Object.keys(slice.entities) };
      }
    }
    return null;
  }

  function entityName(entity) {
    return String(
      entity?.metadata?.displayName ||
      entity?.displayName ||
      entity?.annotations?.name ||
      entity?.name ||
      (Number.isInteger(entity?.dockId) ? `Dock ${entity.dockId}` : "") ||
      "",
    );
  }

  function entityPosition(entity) {
    for (const position of [
      entity?.position,
      entity?.seedTformEntity?.position,
      entity?.seedTformBody?.position,
      entity?.pose?.position,
      entity?.location?.position,
      entity?.action?.position,
      entity?.action?.pose?.position,
      entity?.action?.location?.position,
    ]) {
      if (Number.isFinite(position?.x) && Number.isFinite(position?.y)) {
        return {
          x: position.x,
          y: position.y,
          z: Number.isFinite(position.z) ? position.z : 0,
        };
      }
    }
    return null;
  }

  function entityWaypointIds(entity) {
    const result = [];
    for (const value of [
      entity?.waypointId,
      entity?.associatedWaypointId,
      entity?.dockWaypointId,
      entity?.dockingStationWaypointId,
      entity?.dockedWaypointId,
      entity?.targetPrepPose?.navigateTo?.destinationWaypointId,
      entity?.action?.waypointId,
      entity?.action?.associatedWaypointId,
    ]) {
      if (typeof value === "string" && value) result.push(value);
    }
    for (const values of [
      entity?.waypointIds,
      entity?.associatedWaypointIds,
      entity?.action?.waypointIds,
    ]) {
      if (Array.isArray(values)) {
        result.push(...values.filter((value) => typeof value === "string" && value));
      }
    }
    return [...new Set(result)];
  }

  function entityEdgeIds(entity) {
    const result = [];
    for (const value of [entity?.edgeId, entity?.associatedEdgeId]) {
      if (typeof value === "string" && value) result.push(value);
    }
    for (const values of [entity?.edgeIds, entity?.associatedEdgeIds]) {
      if (Array.isArray(values)) {
        result.push(...values.filter((value) => typeof value === "string" && value));
      }
    }
    return [...new Set(result)];
  }

  function externalCatalog(
    state,
    mapId,
    kind,
    sliceNames,
    positionResolver = entityPosition,
  ) {
    const adapter = entityAdapter(state, sliceNames);
    if (!adapter) return { adapter: "", records: [] };
    const records = [];
    for (const id of adapter.ids) {
      const entity = adapter.entities[id];
      if (!entity || typeof entity !== "object") continue;
      const entityMapId = entity.siteMapId || entity.mapId || entity.siteMap?.id || "";
      if (entityMapId && entityMapId !== mapId) continue;
      const resolvedId = String(entity.id || entity.areaId || entity.actionId || id || "");
      if (!resolvedId) continue;
      records.push({
        kind,
        id: resolvedId,
        name: entityName(entity),
        waypointIds: entityWaypointIds(entity),
        edgeIds: entityEdgeIds(entity),
        position: positionResolver(entity),
        serviceName: String(
          entity.serviceName ||
          entity.callbackServiceName ||
          entity.areaCallback?.serviceName ||
          "",
        ),
        type: String(entity.type || entity.areaType || entity.actionType || ""),
        crosswalk: Boolean(
          entity.crosswalk ||
          String(entity.serviceName || "").includes("crosswalk"),
        ),
        catalogPresent: true,
        inferredFromEdge: false,
        archived: Boolean(entity.archived),
        disabled: Boolean(entity.disabled),
      });
    }
    return { adapter: adapter.name, records };
  }

  function actionEntityId(entity, fallback = "") {
    return String(entity?.uuid || entity?.id || entity?.actionId || fallback || "");
  }

  function actionRecord(entity, fallbackId = "", anchorTransforms = new Map()) {
    const id = actionEntityId(entity, fallbackId);
    if (!id || !entity || typeof entity !== "object") return null;
    return {
      kind: "action",
      id,
      name: entityName(entity),
      waypointIds: entityWaypointIds(entity),
      edgeIds: entityEdgeIds(entity),
      position: actionMapPosition(entity, anchorTransforms),
      serviceName: String(entity.serviceName || entity.callbackServiceName || ""),
      type: String(entity.type || entity.actionType || ""),
      crosswalk: false,
      catalogPresent: true,
      inferredFromEdge: false,
      archived: Boolean(entity.archived),
      disabled: Boolean(entity.disabled),
    };
  }

  function effectiveActionCatalog(state, mapId, waypointIdSet, anchorTransforms) {
    const published = externalCatalog(
      state,
      mapId,
      "action",
      ["siteActions", "siteElements", "autowalkActions", "actions"],
      (entity) => actionMapPosition(entity, anchorTransforms),
    );
    const records = new Map(published.records.map((record) => [record.id, record]));
    const drafts = state?.mapMissionsEditor?.form?.data?.actions;
    for (const id of Object.keys(drafts?.nonEntities || {})) records.delete(String(id));
    for (const id of drafts?.ids || Object.keys(drafts?.entities || {})) {
      const entity = drafts?.entities?.[id];
      const record = actionRecord(entity, id, anchorTransforms);
      if (!record) continue;
      const entityMapId = entity.siteMapId || entity.mapId || entity.siteMap?.id || "";
      if (entityMapId && entityMapId !== mapId) continue;
      if (
        record.waypointIds.length &&
        !record.waypointIds.some((waypointId) => waypointIdSet.has(waypointId))
      ) continue;
      records.set(record.id, record);
    }
    return {
      adapter: drafts
        ? `${published.adapter}+mapMissionsEditor.form.actions`
        : published.adapter,
      records: [...records.values()],
    };
  }

  function edgeStateSnapshot(state, waypointIdSet) {
    const groups = new Map();
    const add = (id, entity) => {
      const from = entity?.edge?.id?.fromWaypoint;
      const to = entity?.edge?.id?.toWaypoint;
      if (!from || !to || !waypointIdSet.has(from) || !waypointIdSet.has(to)) return;
      const key = edgeKey(from, to);
      if (!groups.has(key)) {
        groups.set(key, {
          key,
          from,
          to,
          ids: [],
          activeCount: 0,
          tombstoneCount: 0,
          wasCritical: false,
        });
      }
      const row = groups.get(key);
      row.ids.push(String(id || key));
      if (entity.archived || entity.disabled) row.tombstoneCount += 1;
      else row.activeCount += 1;
    };
    for (const id of state?.siteEdges?.ids || []) {
      add(id, state?.siteEdges?.entities?.[id]);
    }
    const edited = state?.mapEditor?.form?.data?.edges;
    for (const id of edited?.ids || []) add(id, edited?.entities?.[id]);
    for (const [id, entity] of Object.entries(edited?.nonEntities || {})) add(id, entity);
    return [...groups.values()]
      .map((row) => ({ ...row, ids: [...new Set(row.ids)].sort() }))
      .sort((left, right) => left.key.localeCompare(right.key));
  }

  function inferredAreas(edges, catalog) {
    const records = new Map(catalog.records.map((area) => [area.id, area]));
    for (const edge of edges) {
      for (const [id, callback] of Object.entries(edge.settings?.areaCallbacks || {})) {
        if (!records.has(id)) {
          records.set(id, {
            kind: "area",
            id,
            name: String(callback?.description || callback?.serviceName || ""),
            waypointIds: [edge.from, edge.to],
            edgeIds: [edge.id],
            position: null,
            serviceName: String(callback?.serviceName || ""),
            type: "edge area callback",
            crosswalk: callback?.serviceName === "spot-crosswalk",
            catalogPresent: false,
            inferredFromEdge: true,
            archived: false,
            disabled: false,
          });
        } else {
          const area = records.get(id);
          area.waypointIds = [...new Set([...area.waypointIds, edge.from, edge.to])];
          area.edgeIds = [...new Set([...area.edgeIds, edge.id])];
        }
      }
    }
    return {
      adapter: catalog.adapter || (records.size ? "siteEdges.areaCallbacks" : ""),
      records: [...records.values()].sort((left, right) => left.id.localeCompare(right.id)),
    };
  }

  function anchoredFiducials(state, catalog) {
    if (catalog.records.length) return catalog;
    const records = [];
    for (const object of state?.mapDisplay?.anchoring?.objects || []) {
      const position = object?.seedTformObject?.position;
      if (
        typeof object?.id !== "string" ||
        !object.id ||
        !Number.isFinite(position?.x) ||
        !Number.isFinite(position?.y)
      ) continue;
      records.push({
        kind: "fiducial",
        id: object.id,
        name: "",
        waypointIds: [],
        edgeIds: [],
        position: {
          x: position.x,
          y: position.y,
          z: Number.isFinite(position.z) ? position.z : 0,
        },
        serviceName: "",
        type: "anchored world object",
        crosswalk: false,
        catalogPresent: true,
        inferredFromEdge: false,
        archived: false,
        disabled: false,
      });
    }
    return {
      adapter: records.length ? "mapDisplay.anchoring.objects" : "",
      records,
    };
  }

  function filterCatalogToMap(catalog, waypointIdSet) {
    return {
      ...catalog,
      records: catalog.records.filter(
        (record) =>
          !record.waypointIds.length ||
          record.waypointIds.some((id) => waypointIdSet.has(id)),
      ),
    };
  }

  function graphSnapshot(state, mapId) {
    const map = state?.siteMaps?.entities?.[mapId];
    const waypointEntities = state?.siteWaypoints?.entities;
    const recordingEntities = state?.recordingSessions?.entities;
    if (!map || !waypointEntities || !recordingEntities) return null;

    const waypointIds = Array.isArray(map.waypointIds) ? map.waypointIds : [];
    const waypointIdSet = new Set(waypointIds);
    const recordingIds = Array.isArray(map.recordingSessionIds)
      ? map.recordingSessionIds
      : [];
    const recordingByWaypoint = new Map();
    for (const recordingId of recordingIds) {
      for (const waypointId of recordingEntities[recordingId]?.waypointIds || []) {
        recordingByWaypoint.set(waypointId, recordingId);
      }
    }
    const anchorTransforms = allAnchorTransforms(state);
    const edgeRecords = effectiveEdges(state, waypointIdSet);
    const edgeStates = edgeStateSnapshot(state, waypointIdSet);
    const degree = new Map(waypointIds.map((id) => [id, 0]));
    const sourceCounts = new Map(waypointIds.map((id) => [id, {}]));
    const edges = [];

    for (const { id, entity } of edgeRecords.values()) {
      const edge = entity.edge;
      const from = edge.id.fromWaypoint;
      const to = edge.id.toWaypoint;
      const source = edgeSourceName(edge.annotations?.edgeSource);
      degree.set(from, (degree.get(from) || 0) + 1);
      degree.set(to, (degree.get(to) || 0) + 1);
      for (const waypointId of [from, to]) {
        const counts = sourceCounts.get(waypointId) || {};
        counts[source] = (counts[source] || 0) + 1;
        sourceCounts.set(waypointId, counts);
      }
      const transform = edge.fromTformTo?.position;
      const length = [transform?.x, transform?.y, transform?.z].every(Number.isFinite)
        ? Math.hypot(transform.x, transform.y, transform.z)
        : null;
      const fromRecordingId = recordingByWaypoint.get(from) || "";
      const toRecordingId = recordingByWaypoint.get(to) || "";
      edges.push({
        id: String(id || edgeKey(from, to)),
        from,
        to,
        source,
        sourceValue: edge.annotations?.edgeSource ?? null,
        manual: edge.annotations?.edgeSource === 5,
        length,
        settings: edgeSettings(edge.annotations),
        crossRecording: Boolean(
          fromRecordingId &&
          toRecordingId &&
          fromRecordingId !== toRecordingId,
        ),
      });
    }

    const waypoints = [];
    for (const id of waypointIds) {
      const waypointEntity = waypointEntities[id];
      const waypoint = waypointEntity?.waypoint;
      if (!waypoint) continue;
      const recordingId = recordingByWaypoint.get(id) || "";
      const recording = recordingEntities[recordingId];
      waypoints.push({
        id,
        name: waypoint.annotations?.name || "",
        snapshotId: waypoint.snapshotId || "",
        creationTime: timestampString(waypoint.annotations?.creationTime),
        position: anchorTransforms.get(id)?.position || null,
        rawPosition: waypoint.waypointTformKo?.position || null,
        recordingId,
        recordingName: recording?.name || "",
        recordingStartTime: timestampString(recording?.startTime),
        recordingEndTime: timestampString(recording?.endTime),
        robotNickname: recording?.robotNickname || "",
        robotSerial: recording?.robotSerial || "",
        degree: degree.get(id) || 0,
        edgeSources: sourceCounts.get(id) || {},
        sitePanoSettings: waypointPanoSettings(waypointEntity),
      });
    }

    const info = state?.mapEditor?.info || {};
    const areas = inferredAreas(
      edges,
      externalCatalog(
        state,
        mapId,
        "area",
        ["siteAreas", "siteMapAreas", "areas"],
      ),
    );
    const docks = filterCatalogToMap(
      externalCatalog(
        state,
        mapId,
        "dock",
        ["siteDocks", "dockConfigurations", "docks"],
      ),
      waypointIdSet,
    );
    const fiducials = anchoredFiducials(
      state,
      externalCatalog(
        state,
        mapId,
        "fiducial",
        ["siteFiducials", "fiducialConfigurations", "fiducials"],
      ),
    );
    const actions = filterCatalogToMap(
      effectiveActionCatalog(state, mapId, waypointIdSet, anchorTransforms),
      waypointIdSet,
    );
    const form = state?.mapEditor?.form;
    const actionForm = state?.mapMissionsEditor?.form;
    const expectedWaypointCount = waypointIds.length;
    return {
      kind: "orbit_site_map_editor_live_snapshot",
      map: {
        id: mapId,
        name: map.metadata?.displayName || "",
      },
      editIndex: Number.isInteger(state?.mapEditor?.form?.present?.index)
        ? state.mapEditor.form.present.index
        : null,
      history: {
        undoDepth: Array.isArray(form?.past) ? form.past.length : null,
        redoDepth: Array.isArray(form?.future) ? form.future.length : null,
        hasDraft: Number.isInteger(form?.present?.index)
          ? form.present.index > 0
          : null,
      },
      actionEditIndex: Number.isInteger(actionForm?.present?.index)
        ? actionForm.present.index
        : null,
      actionHistory: {
        undoDepth: Array.isArray(actionForm?.past) ? actionForm.past.length : null,
        redoDepth: Array.isArray(actionForm?.future) ? actionForm.future.length : null,
        hasDraft: Number.isInteger(actionForm?.present?.index)
          ? actionForm.present.index > 0
          : null,
      },
      activeTool: info.activeTool || "",
      currentActionId: safeText(searchParameter("action"), 600),
      selectedWaypointIds: Array.isArray(info.selectedWaypointIds)
        ? [...info.selectedWaypointIds]
        : [],
      selectedEdgeIds: Array.isArray(info.selectedEdgeIds)
        ? [...info.selectedEdgeIds]
        : [],
      recordingCount: recordingIds.length,
      anchorCount: anchorTransforms.size,
      load: {
        expectedWaypointCount,
        resolvedWaypointCount: waypoints.length,
        complete: expectedWaypointCount === waypoints.length,
      },
      capabilities: {
        areas: areas.adapter,
        docks: docks.adapter,
        fiducials: fiducials.adapter,
        actions: actions.adapter,
      },
      waypoints,
      edges,
      edgeStates,
      areas: areas.records,
      docks: docks.records,
      fiducials: fiducials.records,
      actions: actions.records,
    };
  }

  function safeText(value, maximumLength = 512) {
    if (
      typeof value !== "string" &&
      typeof value !== "number" &&
      typeof value !== "bigint"
    ) return "";
    return String(value).slice(0, maximumLength);
  }

  function finiteNumber(value) {
    if (typeof value === "number") return Number.isFinite(value) ? value : null;
    if (typeof value === "bigint") return Number(value);
    if (typeof value === "string" && value.trim()) {
      const converted = Number(value);
      return Number.isFinite(converted) ? converted : null;
    }
    try {
      if (value && typeof value.toString === "function") {
        const converted = Number(value.toString());
        return Number.isFinite(converted) ? converted : null;
      }
    } catch {
      // Protobuf Long-like values can expose guarded conversion helpers.
    }
    return null;
  }

  function durationSeconds(value) {
    if (value === null || value === undefined) return null;
    const direct = finiteNumber(value);
    if (direct !== null) return direct;
    const seconds = finiteNumber(value?.seconds ?? value?.secs);
    const nanos = finiteNumber(value?.nanos ?? value?.nanoseconds) || 0;
    if (seconds === null && !nanos) return null;
    return (seconds || 0) + nanos / 1e9;
  }

  function waypointPanoSettings(entity) {
    const settings =
      entity?.sitePanoSettings ||
      entity?.siteWaypoint?.sitePanoSettings ||
      entity?.waypoint?.sitePanoSettings ||
      entity?.annotations?.sitePanoSettings;
    if (!settings || typeof settings !== "object") return null;
    return {
      allowCaptureVisual: Boolean(settings.allowCaptureVisual),
      allowCaptureThermal: Boolean(settings.allowCaptureThermal),
      visualCaptureIntervalSeconds:
        durationSeconds(
          settings.minTimeBetweenCaptureVisual ??
          settings.visualCaptureInterval,
        ),
      thermalCaptureIntervalSeconds:
        durationSeconds(
          settings.minTimeBetweenCaptureThermal ??
          settings.thermalCaptureInterval,
        ),
    };
  }

  function siteViewPlanningSnapshot(state, mapId) {
    const map = state?.siteMaps?.entities?.[mapId];
    if (!map) return null;
    const mapWaypointIds = new Set(
      Array.isArray(map.waypointIds) ? map.waypointIds : [],
    );
    const panoAdapter = entityAdapter(state, ["siteWaypoints"]);
    const dockAdapter = entityAdapter(
      state,
      ["siteDocks", "dockConfigurations", "docks"],
    );

    const sitePanoWaypoints = [];
    for (const id of panoAdapter?.ids || []) {
      if (!mapWaypointIds.has(id)) continue;
      const entity = panoAdapter.entities[id];
      const settings = waypointPanoSettings(entity);
      if (!settings) continue;
      sitePanoWaypoints.push({
        waypointId: safeText(id, 256),
        ...settings,
      });
    }
    sitePanoWaypoints.sort((left, right) =>
      left.waypointId.localeCompare(right.waypointId)
    );

    const siteDocks = [];
    for (const id of dockAdapter?.ids || []) {
      const entity = dockAdapter.entities[id];
      if (!entity || typeof entity !== "object") continue;
      const dock = entity.siteDock || entity.dock || entity;
      const waypointIds = entityWaypointIds(dock).filter((waypointId) =>
        mapWaypointIds.has(waypointId)
      );
      if (!waypointIds.length) continue;
      siteDocks.push({
        id: safeText(dock.uuid || dock.id || entity.uuid || id, 600),
        name: safeText(entityName(dock), 512),
        waypointIds,
      });
    }
    siteDocks.sort((left, right) => left.id.localeCompare(right.id));

    return {
      kind: "orbit_site_view_planning_snapshot",
      map: {
        id: mapId,
        name: safeText(map.metadata?.displayName, 512),
      },
      capabilities: {
        siteWaypoints: panoAdapter?.name || "",
        siteDocks: dockAdapter?.name || "",
      },
      sitePanoWaypoints,
      siteDocks,
    };
  }

  function wait(milliseconds) {
    return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
  }

  function historyState(form) {
    return {
      editIndex: Number.isInteger(form?.present?.index)
        ? form.present.index
        : null,
      undoDepth: Array.isArray(form?.past) ? form.past.length : null,
    };
  }

  function oneUndoDraftCreated(before, after) {
    const hasEditIndex =
      Number.isInteger(before.editIndex) &&
      Number.isInteger(after.editIndex);
    const hasUndoDepth =
      Number.isInteger(before.undoDepth) &&
      Number.isInteger(after.undoDepth);
    if (!hasEditIndex || !hasUndoDepth) return false;
    return (
      after.editIndex > before.editIndex &&
      after.undoDepth === before.undoDepth + 1
    );
  }

  function sameHistoryState(before, after) {
    return Boolean(
      Number.isInteger(before?.editIndex) &&
      Number.isInteger(after?.editIndex) &&
      Number.isInteger(before?.undoDepth) &&
      Number.isInteger(after?.undoDepth) &&
      before.editIndex === after.editIndex &&
      before.undoDepth === after.undoDepth
    );
  }

  function safeHistoryState(store) {
    try {
      return historyState(store.getState()?.mapEditor?.form);
    } catch {
      return { editIndex: null, undoDepth: null };
    }
  }

  function safeActionHistoryState(store) {
    try {
      return historyState(store.getState()?.mapMissionsEditor?.form);
    } catch {
      return { editIndex: null, undoDepth: null };
    }
  }

  function mutationFailure(
    error,
    before,
    after,
    {
      dispatchAttempted = true,
      writeObserved = false,
      targetKeys = [],
    } = {},
  ) {
    const historyChanged = Boolean(
      (
        Number.isInteger(before?.editIndex) &&
        Number.isInteger(after?.editIndex) &&
        after.editIndex !== before.editIndex
      ) ||
      (
        Number.isInteger(before?.undoDepth) &&
        Number.isInteger(after?.undoDepth) &&
        after.undoDepth !== before.undoDepth
      )
    );
    return {
      error,
      // Every caller reaches this helper only after a native mutation
      // dispatch was attempted. Redux reducers can mutate and then throw, so
      // missing read-back evidence must never be presented as "no mutation".
      mutationMayExist: true,
      dispatchAttempted: Boolean(dispatchAttempted),
      writeObserved: Boolean(writeObserved),
      historyChanged,
      beforeEditIndex: before?.editIndex ?? null,
      afterEditIndex: after?.editIndex ?? null,
      beforeUndoDepth: before?.undoDepth ?? null,
      afterUndoDepth: after?.undoDepth ?? null,
      targetKeys,
    };
  }

  function mutationHistoryResult(before, after) {
    return {
      editIndex: after.editIndex,
      undoDepth: after.undoDepth,
      draftIndexDelta:
        Number.isInteger(before.editIndex) && Number.isInteger(after.editIndex)
          ? after.editIndex - before.editIndex
          : null,
    };
  }

  function executeNativeMutation({
    store,
    beforeHistory,
    targetKeys,
    dispatch,
    historyFromState = (state) => historyState(state?.mapEditor?.form),
    safeHistory = safeHistoryState,
    readback,
    failureError,
    readbackError = failureError,
  }) {
    let finalState;
    let afterHistory;
    try {
      dispatch();
      finalState = store.getState();
      afterHistory = historyFromState(finalState);
    } catch {
      return mutationFailure(
        "native_mutation_exception",
        beforeHistory,
        safeHistory(store),
        {dispatchAttempted: true, targetKeys},
      );
    }

    let evidence;
    try {
      evidence = readback(finalState) || {};
    } catch {
      return mutationFailure(readbackError, beforeHistory, afterHistory, {
        writeObserved: false,
        targetKeys,
      });
    }
    if (!evidence.verified || !oneUndoDraftCreated(beforeHistory, afterHistory)) {
      return mutationFailure(
        evidence.error || failureError,
        beforeHistory,
        afterHistory,
        {
          writeObserved: Boolean(evidence.writeObserved),
          targetKeys,
        },
      );
    }
    return {
      finalState,
      afterHistory,
      evidence,
      history: mutationHistoryResult(beforeHistory, afterHistory),
    };
  }

  const VALIDATION_MESSAGE_KEYS = [
    "defaultMessage",
    "message",
    "detail",
    "reason",
    "description",
    "title",
    "text",
    "error",
  ];

  function cleanValidationMessage(value) {
    return String(value || "")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 300);
  }

  function formatValidationDistance(value) {
    return Number(value).toFixed(2).replace(/\.00$/, "");
  }

  function knownValidationDetails(value) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return [];
    const details = [];
    if (value.alreadyExists) {
      details.push("An edge already exists between these waypoints.");
    }
    if (value.bridgesDisconnectedSubgraphs) {
      details.push("This edge would bridge disconnected subgraphs.");
    }
    if (value.collisionCheckFailed) {
      details.push("Orbit's collision check failed.");
    }
    if (value.edgeLength) {
      const length = Number(value.edgeLength.length);
      const maxLength = Number(value.edgeLength.maxLength);
      details.push(
        Number.isFinite(length) && Number.isFinite(maxLength)
          ? `Edge length ${formatValidationDistance(length)} m exceeds Orbit's ` +
            `${formatValidationDistance(maxLength)} m limit.`
          : "Edge length exceeds Orbit's limit.",
      );
    }
    if (value.gravityAlignmentFailed) {
      details.push("Gravity alignment check failed.");
    }
    if (value.heightChange) {
      details.push("Height change exceeds Orbit's limit.");
    }
    if (value.icpFailed) {
      details.push("ICP alignment failed.");
    }
    return details;
  }

  function validationDetails(value) {
    const details = [];
    const seen = new WeakSet();

    function collect(item) {
      if (details.length >= 3 || item === null || item === undefined) return;
      if (typeof item === "string") {
        const detail = cleanValidationMessage(item);
        if (detail && !details.includes(detail)) details.push(detail);
        return;
      }
      if (Array.isArray(item)) {
        for (const child of item) collect(child);
        return;
      }
      if (typeof item !== "object" || seen.has(item)) return;
      seen.add(item);

      for (const detail of knownValidationDetails(item)) {
        if (details.length >= 3) return;
        if (!details.includes(detail)) details.push(detail);
      }

      const detailCount = details.length;
      for (const key of VALIDATION_MESSAGE_KEYS) {
        if (Object.prototype.hasOwnProperty.call(item, key)) collect(item[key]);
      }
      if (details.length === detailCount) collect(item.props?.children);
      if (details.length === detailCount) collect(item.code);
      if (details.length === detailCount) collect(item.id);
    }

    collect(value);
    return details;
  }

  async function validatedEdgeCandidate(store, mapId, waypointIds) {
    if (!isCurrentBridge()) return { error: "bridge_disposed" };
    const initialState = store.getState();
    const previous = initialState?.mapEditor?.info?.pendingEdgeCreation
      ?.createdEdgeCandidate;
    const previousMatches = sameWaypointPair(previous?.edge?.id, waypointIds);
    if (previousMatches) {
      store.dispatch({ type: SELECT_WAYPOINTS_ACTION_TYPE, payload: [] });
      await wait(0);
      if (!isCurrentBridge()) return { error: "bridge_disposed" };
    }
    if (!isCurrentBridge()) return { error: "bridge_disposed" };
    store.dispatch({ type: SELECT_WAYPOINTS_ACTION_TYPE, payload: waypointIds });

    const deadline = Date.now() + EDGE_VALIDATION_TIMEOUT_MS;
    let sawValidation = false;
    while (Date.now() < deadline) {
      if (!isCurrentBridge()) return { error: "bridge_disposed" };
      const state = store.getState();
      if (state?.mapDisplay?.siteMapId !== mapId || currentMapId() !== mapId) {
        return { error: "orbit_map_changed" };
      }
      const selected = state?.mapEditor?.info?.selectedWaypointIds;
      if (
        !validWaypointPair(selected) ||
        edgeKey(...selected) !== edgeKey(...waypointIds)
      ) {
        return { error: "orbit_selection_changed" };
      }
      const pending = state?.mapEditor?.info?.pendingEdgeCreation || {};
      sawValidation ||= Boolean(pending.validating);
      const candidate = pending.createdEdgeCandidate;
      const validationFinished = sawValidation && !pending.validating;
      const candidateReady =
        sameWaypointPair(candidate?.edge?.id, waypointIds) &&
        candidate?.siteMapId === mapId &&
        !pending.validating &&
        (candidate !== previous || sawValidation);
      if (candidateReady || validationFinished) {
        if (!isCurrentBridge()) return { error: "bridge_disposed" };
        const errors = Array.isArray(pending.errors)
          ? pending.errors
          : pending.errors
            ? [pending.errors]
            : [];
        const warnings = Array.isArray(pending.warnings)
          ? pending.warnings
          : pending.warnings
            ? [pending.warnings]
            : [];
        if (errors.length) {
          return {
            error: "edge_validation_failed",
            details: validationDetails(errors),
          };
        }
        if (warnings.length || pending.showModal) {
          return {
            error: "edge_validation_warning",
            details: validationDetails(warnings),
          };
        }
        if (candidateReady) return { candidate };
      }
      await wait(50);
      if (!isCurrentBridge()) return { error: "bridge_disposed" };
    }
    return { error: "edge_validation_timeout" };
  }

  function pairPrecondition(state, mapId, waypointIds) {
    const map = state?.siteMaps?.entities?.[mapId];
    const mapWaypointIds = new Set(map?.waypointIds || []);
    if (!waypointIds.every((id) => mapWaypointIds.has(id))) {
      return "map_or_waypoint_mismatch";
    }
    if (effectiveEdgeEntity(state, waypointIds)) return "edge_already_exists";
    return "";
  }

  async function validateConnectPair(store, mapId, waypointIds) {
    const initialState = store.getState();
    const precondition = pairPrecondition(initialState, mapId, waypointIds);
    if (precondition) return { valid: false, error: precondition };
    const originalSelection = Array.isArray(
      initialState?.mapEditor?.info?.selectedWaypointIds,
    )
      ? [...initialState.mapEditor.info.selectedWaypointIds]
      : [];
    const beforeHistory = historyState(initialState?.mapEditor?.form);
    const validation = await validatedEdgeCandidate(store, mapId, waypointIds);
    if (!isCurrentBridge()) {
      return { valid: false, error: "bridge_disposed" };
    }
    const currentState = store.getState();
    if (
      currentMapId() === mapId &&
      currentState?.mapDisplay?.siteMapId === mapId
    ) {
      store.dispatch({
        type: SELECT_WAYPOINTS_ACTION_TYPE,
        payload: originalSelection,
      });
    }
    const finalState = store.getState();
    const afterHistory = historyState(finalState?.mapEditor?.form);
    if (!sameHistoryState(beforeHistory, afterHistory)) {
      return {
        valid: false,
        error: "validation_changed_draft",
        mutationMayExist: true,
        beforeEditIndex: beforeHistory.editIndex,
        afterEditIndex: afterHistory.editIndex,
        beforeUndoDepth: beforeHistory.undoDepth,
        afterUndoDepth: afterHistory.undoDepth,
        targetKeys: [edgeKey(waypointIds[0], waypointIds[1])],
      };
    }
    if (finalState?.mapDisplay?.siteMapId !== mapId || currentMapId() !== mapId) {
      return { valid: false, error: "orbit_map_changed" };
    }
    if (!validation.candidate) {
      return {
        valid: false,
        error: validation.error || "edge_validation_failed",
        details: validation.details || [],
      };
    }
    return { valid: true };
  }

  async function connectWaypointPair(store, mapId, waypointIds) {
    const initialState = store.getState();
    const precondition = pairPrecondition(initialState, mapId, waypointIds);
    if (precondition) return { error: precondition };
    const validation = await validatedEdgeCandidate(store, mapId, waypointIds);
    if (!isCurrentBridge()) return { error: "bridge_disposed" };
    if (!validation.candidate) return validation;
    const refreshedPrecondition = pairPrecondition(
      store.getState(),
      mapId,
      waypointIds,
    );
    if (refreshedPrecondition) return { error: refreshedPrecondition };
    const beforeHistory = historyState(store.getState()?.mapEditor?.form);
    const targetKeys = [edgeKey(waypointIds[0], waypointIds[1])];
    if (!isCurrentBridge()) return { error: "bridge_disposed" };
    const execution = executeNativeMutation({
      store,
      beforeHistory,
      targetKeys,
      dispatch: () => store.dispatch({
        type: ADD_SITE_EDGE_ACTION_TYPE,
        payload: validation.candidate,
      }),
      readback: (finalState) => {
        const added = editedEdgeOverride(finalState, waypointIds);
        return {
          added,
          writeObserved: Boolean(added),
          verified: Boolean(
            added &&
            !added.archived &&
            !added.disabled &&
            added.siteMapId === mapId &&
            sameWaypointPair(added.edge?.id, waypointIds) &&
            finalState?.mapDisplay?.siteMapId === mapId &&
            currentMapId() === mapId
          ),
        };
      },
      failureError: "edge_draft_not_created",
    });
    if (execution.error) return execution;
    return {
      added: true,
      edgeKey: edgeKey(waypointIds[0], waypointIds[1]),
      ...execution.history,
    };
  }

  function selectEntities(store, mapId, waypointIds, edgeIds, focus) {
    const state = store.getState();
    const mapWaypointIds = new Set(state?.siteMaps?.entities?.[mapId]?.waypointIds || []);
    if (!waypointIds.every((id) => mapWaypointIds.has(id))) {
      return { error: "map_or_waypoint_mismatch" };
    }
    const graph = graphSnapshot(state, mapId);
    const canonicalByAlias = new Map();
    const endpointsByCanonical = new Map();
    for (const edge of graph?.edges || []) {
      const canonical = edgeKey(edge.from, edge.to);
      canonicalByAlias.set(edge.id, canonical);
      canonicalByAlias.set(canonical, canonical);
      endpointsByCanonical.set(canonical, [edge.from, edge.to]);
    }
    const canonicalEdgeIds = edgeIds.map((id) => canonicalByAlias.get(id) || "");
    if (canonicalEdgeIds.some((id) => !id)) {
      return { error: "edge_not_found" };
    }
    if (new Set(canonicalEdgeIds).size !== canonicalEdgeIds.length) {
      return { error: "duplicate_edge_selection" };
    }
    const selectingEdges = canonicalEdgeIds.length > 0;
    const expectedWaypointIds = selectingEdges ? [] : waypointIds;
    if (selectingEdges) {
      store.dispatch({ type: ACTIVATE_TOOL_ACTION_TYPE, payload: EDGE_SELECTION_TOOL });
      store.dispatch({ type: SELECT_WAYPOINTS_ACTION_TYPE, payload: [] });
      store.dispatch({ type: SELECT_EDGES_ACTION_TYPE, payload: canonicalEdgeIds });
    } else {
      // Orbit's waypoint reducer is reliable without switching tools. Some
      // Orbit 5.1 builds clear the next waypoint selection when the waypoint
      // tool is activated first.
      store.dispatch({ type: SELECT_EDGES_ACTION_TYPE, payload: [] });
      store.dispatch({
        type: SELECT_WAYPOINTS_ACTION_TYPE,
        payload: expectedWaypointIds,
      });
    }
    const focusWaypointIds = waypointIds.length
      ? waypointIds
      : [...new Set(
        canonicalEdgeIds.flatMap((id) => endpointsByCanonical.get(id) || []),
      )];
    if (focus && focusWaypointIds.length) {
      store.dispatch({ type: FOCUS_ACTION_TYPE, payload: focusWaypointIds });
    }
    const finalInfo = store.getState()?.mapEditor?.info || {};
    const selectedWaypointIds = Array.isArray(finalInfo.selectedWaypointIds)
      ? finalInfo.selectedWaypointIds
      : [];
    const selectedEdgeIds = Array.isArray(finalInfo.selectedEdgeIds)
      ? finalInfo.selectedEdgeIds
      : [];
    if (
      selectedWaypointIds.length !== expectedWaypointIds.length ||
      selectedEdgeIds.length !== canonicalEdgeIds.length ||
      expectedWaypointIds.some((id) => !selectedWaypointIds.includes(id)) ||
      canonicalEdgeIds.some((id) => !selectedEdgeIds.includes(id))
    ) return { error: "orbit_selection_changed" };
    return {
      selected: true,
      waypointCount: expectedWaypointIds.length,
      edgeCount: canonicalEdgeIds.length,
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
      if (
        !active ||
        active.siteMapId !== mapId ||
        !sameWaypointPair(active.edge?.id, waypointIds)
      ) return { error: "edge_not_found" };
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

    const beforeHistory = historyState(store.getState()?.mapEditor?.form);
    const execution = executeNativeMutation({
      store,
      beforeHistory,
      targetKeys: keys,
      dispatch: () => store.dispatch({
        type: ARCHIVE_SITE_EDGES_ACTION_TYPE,
        payload: activeEdges,
      }),
      readback: (finalState) => {
        const archivedKeys = keys.filter((key, index) => {
          const archived = finalState?.mapEditor?.form?.data?.edges?.nonEntities?.[key];
          return (
            archived?.archived &&
            !archived.disabled &&
            archived.siteMapId === mapId &&
            sameWaypointPair(archived.edge?.id, waypointPairs[index])
          );
        });
        return {
          archivedKeys,
          writeObserved: archivedKeys.length > 0,
          verified: Boolean(
            finalState?.mapDisplay?.siteMapId === mapId &&
            currentMapId() === mapId &&
            archivedKeys.length === keys.length
          ),
        };
      },
      failureError: "edge_archive_batch_not_created",
    });
    try {
      store.dispatch({ type: SELECT_EDGES_ACTION_TYPE, payload: [] });
    } catch {
      // Selection cleanup cannot change the native graph draft.
    }
    if (execution.error) return execution;
    return {
      archived: true,
      archivedCount: keys.length,
      edgeKeys: keys,
      ...execution.history,
    };
  }

  function updateEdgeSettings(store, mapId, updates) {
    const initialState = store.getState();
    const mapWaypointIds = new Set(
      initialState?.siteMaps?.entities?.[mapId]?.waypointIds || [],
    );
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
        ) return { error: "edge_not_found" };
        if (
          active.edge.id.fromWaypoint !== update.storedFrom ||
          active.edge.id.toWaypoint !== update.storedTo
        ) return { error: "edge_direction_mismatch" };
        if (
          Number.isInteger(update.observedSourceValue) &&
          active.edge.annotations?.edgeSource !== update.observedSourceValue
        ) return { error: "edge_source_changed" };
        const observed = requestedEdgeSettings(update.observedSettings);
        const current = edgeSettings(active.edge.annotations);
        if (!sameSettings(current, observed)) return { error: "edge_settings_changed" };
        const desired = requestedEdgeSettings(update.desiredSettings);
        const updated = {
          ...active,
          archived: false,
          edge: {
            ...active.edge,
            annotations: {
              ...(active.edge.annotations || {}),
              ...desired,
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

    const beforeHistory = historyState(initialState?.mapEditor?.form);
    const execution = executeNativeMutation({
      store,
      beforeHistory,
      targetKeys: keys,
      dispatch: () => store.dispatch({
        type: UPDATE_SITE_EDGES_ACTION_TYPE,
        payload: { updatedEdges, originalEdgesById },
      }),
      readback: (finalState) => {
        const observedEditedKeys = keys.filter((key, index) =>
          Boolean(editedEdgeOverride(finalState, updates[index].waypointIds))
        );
        const annotationLossKeys = keys.filter((key, index) => {
        const edited = editedEdgeOverride(finalState, updates[index].waypointIds);
        const original = originalEdgesById[key];
        return Boolean(
          edited &&
          original &&
          !sameSettings(
            unmodeledAnnotations(edited.edge?.annotations),
            unmodeledAnnotations(original.edge?.annotations),
          )
        );
        });
        const verifiedUpdatedKeys = keys.filter((key, index) => {
        const edited = editedEdgeOverride(finalState, updates[index].waypointIds);
        const original = originalEdgesById[key];
        return Boolean(
          edited &&
          original &&
          !edited.archived &&
          !edited.disabled &&
          edited.siteMapId === mapId &&
          sameWaypointPair(edited.edge?.id, updates[index].waypointIds) &&
          edited.edge?.annotations?.edgeSource ===
            original.edge?.annotations?.edgeSource &&
          sameSettings(
            edgeSettings(edited.edge?.annotations),
            requestedEdgeSettings(updates[index].desiredSettings),
          ) &&
          sameSettings(
            unmodeledAnnotations(edited.edge?.annotations),
            unmodeledAnnotations(original.edge?.annotations),
          )
        );
        });
        return {
          error: annotationLossKeys.length
            ? "edge_annotation_readback_failed"
            : "edge_settings_batch_not_created",
          writeObserved: observedEditedKeys.length > 0,
          verified: Boolean(
            !annotationLossKeys.length &&
            finalState?.mapDisplay?.siteMapId === mapId &&
            currentMapId() === mapId &&
            verifiedUpdatedKeys.length === keys.length
          ),
        };
      },
      failureError: "edge_settings_batch_not_created",
      readbackError: "edge_annotation_readback_failed",
    });
    if (execution.error) return execution;
    return {
      updated: true,
      updatedCount: keys.length,
      edgeKeys: keys,
      ...execution.history,
    };
  }

  function rawActionEntities(state) {
    const publishedAdapter = entityAdapter(
      state,
      ["siteActions", "siteElements", "autowalkActions", "actions"],
    );
    const published = new Map();
    for (const id of publishedAdapter?.ids || []) {
      const entity = publishedAdapter.entities[id];
      const resolvedId = actionEntityId(entity, id);
      if (resolvedId && entity) published.set(resolvedId, entity);
    }
    const effective = new Map(published);
    const drafts = state?.mapMissionsEditor?.form?.data?.actions;
    for (const id of Object.keys(drafts?.nonEntities || {})) {
      effective.delete(String(id));
    }
    for (const id of drafts?.ids || Object.keys(drafts?.entities || {})) {
      const entity = drafts?.entities?.[id];
      const resolvedId = actionEntityId(entity, id);
      if (resolvedId && entity) effective.set(resolvedId, entity);
    }
    return { published, effective };
  }

  function comparableAction(entity) {
    const result = {};
    for (const key of Object.keys(entity || {}).sort()) {
      if (key === "name" || entity[key] === undefined) continue;
      result[key] = normalizeJsonValue(entity[key], `action_${key}`);
    }
    return result;
  }

  function sameActionExceptName(left, right) {
    return JSON.stringify(comparableAction(left)) === JSON.stringify(comparableAction(right));
  }

  function renameActions(store, mapId, updates) {
    const initialState = store.getState();
    const mapWaypointIds = new Set(
      initialState?.siteMaps?.entities?.[mapId]?.waypointIds || [],
    );
    const { published, effective } = rawActionEntities(initialState);
    const updatedActions = [];
    const originalActionsById = {};
    const targetIds = [];
    const seenIds = new Set();
    const desiredNames = new Map();

    for (const update of updates) {
      if (seenIds.has(update.id)) return { error: "duplicate_action_id" };
      seenIds.add(update.id);
      if (!mapWaypointIds.has(update.waypointId)) {
        return { error: "map_or_waypoint_mismatch" };
      }
      const active = effective.get(update.id);
      if (!active || typeof active.name !== "string") return { error: "action_not_found" };
      if (active.name !== update.observedName) return { error: "action_name_changed" };
      if (!entityWaypointIds(active).includes(update.waypointId)) {
        return { error: "action_waypoint_changed" };
      }
      const previousOwner = desiredNames.get(update.desiredName);
      if (previousOwner && previousOwner !== update.id) {
        return { error: "duplicate_action_name" };
      }
      desiredNames.set(update.desiredName, update.id);
      targetIds.push(update.id);
      updatedActions.push({ ...active, name: update.desiredName });
      originalActionsById[update.id] = published.get(update.id) || active;
    }

    for (const [id, action] of effective) {
      if (seenIds.has(id)) continue;
      const owner = desiredNames.get(String(action?.name || ""));
      if (owner) return { error: "duplicate_action_name" };
    }

    const actionForm = initialState?.mapMissionsEditor?.form;
    if (!actionForm) return { error: "orbit_action_form_unavailable" };
    const beforeHistory = historyState(actionForm);
    const execution = executeNativeMutation({
      store,
      beforeHistory,
      targetKeys: targetIds,
      dispatch: () => store.dispatch({
        type: UPDATE_ACTION_NAMES_ACTION_TYPE,
        payload: { updatedActions, originalActionsById },
      }),
      historyFromState: (state) => historyState(state?.mapMissionsEditor?.form),
      safeHistory: safeActionHistoryState,
      readback: (finalState) => {
        const drafts = finalState?.mapMissionsEditor?.form?.data?.actions?.entities || {};
        const writtenIds = targetIds.filter((id) => Boolean(drafts[id]));
        const verifiedIds = targetIds.filter((id, index) => {
          const edited = drafts[id];
          return Boolean(
            edited &&
            edited.name === updates[index].desiredName &&
            entityWaypointIds(edited).includes(updates[index].waypointId) &&
            sameActionExceptName(edited, updatedActions[index])
          );
        });
        return {
          writeObserved: writtenIds.length > 0,
          verified: Boolean(
            finalState?.mapDisplay?.siteMapId === mapId &&
            currentMapId() === mapId &&
            verifiedIds.length === targetIds.length
          ),
        };
      },
      failureError: "action_name_batch_not_created",
      readbackError: "action_name_readback_failed",
    });
    if (execution.error) return execution;
    return {
      renamed: true,
      updatedCount: targetIds.length,
      actionIds: targetIds,
      ...execution.history,
    };
  }

  function respond(requestId, payload) {
    if (disposed) return;
    window.postMessage(
      {
        channel: CHANNEL,
        type: RESPONSE_TYPE,
        requestId,
        ...(SESSION_ID ? { sessionId: SESSION_ID } : {}),
        ...payload,
      },
      location.origin,
    );
  }

  async function handleMessage(event) {
    if (disposed) return;
    if (
      event.source !== window ||
      event.origin !== location.origin ||
      event.data?.channel !== CHANNEL ||
      event.data?.type !== REQUEST_TYPE ||
      SESSION_ID && event.data?.sessionId !== SESSION_ID
    ) return;
    const {
      requestId,
      command,
      mapId,
      waypointIds = [],
      edgeIds = [],
      waypointPairs,
      settingsUpdates,
      actionNameUpdates,
      focus = false,
    } = event.data;
    if (
      typeof requestId !== "string" ||
      ![
        "snapshot",
        "site_view_snapshot",
        "focus",
        "select_waypoint",
        "select_entities",
        "validate_connect",
        "connect",
        "archive_edges",
        "update_edge_settings",
        "rename_actions",
      ].includes(command)
    ) return;
    if (handledRequestIds.has(requestId)) {
      respond(requestId, { ok: false, error: "duplicate_request" });
      return;
    }
    handledRequestIds.add(requestId);
    if (handledRequestIds.size > 2000) {
      handledRequestIds.delete(handledRequestIds.values().next().value);
    }
    if (mapId !== currentMapId()) {
      respond(requestId, { ok: false, error: "map_or_waypoint_mismatch" });
      return;
    }
    if (
      command === "select_entities" &&
      (!validEdgeIdList(edgeIds) || !validWaypointList(waypointIds) && waypointIds.length)
    ) {
      respond(requestId, { ok: false, error: "invalid_selection" });
      return;
    }
    if (command === "archive_edges" && !validWaypointPairs(waypointPairs)) {
      respond(requestId, { ok: false, error: "invalid_archive_batch" });
      return;
    }
    if (
      command === "update_edge_settings" &&
      !validSettingsUpdates(settingsUpdates)
    ) {
      respond(requestId, { ok: false, error: "invalid_settings_batch" });
      return;
    }
    if (command === "rename_actions" && !validActionNameUpdates(actionNameUpdates)) {
      respond(requestId, { ok: false, error: "invalid_action_name_batch" });
      return;
    }
    if (
      ["validate_connect", "connect"].includes(command) &&
      !validWaypointPair(waypointIds)
    ) {
      respond(requestId, { ok: false, error: "map_or_waypoint_mismatch" });
      return;
    }
    if (
      ["focus", "select_waypoint"].includes(command) &&
      !validWaypointList(waypointIds)
    ) {
      respond(requestId, { ok: false, error: "map_or_waypoint_mismatch" });
      return;
    }

    const store = findOrbitStore();
    if (!store) {
      respond(requestId, { ok: false, error: "orbit_store_unavailable" });
      return;
    }
    const state = store.getState();
    if (state?.mapDisplay?.siteMapId !== mapId) {
      respond(requestId, { ok: false, error: "orbit_map_not_loaded" });
      return;
    }

    if (command === "snapshot") {
      const snapshot = graphSnapshot(state, mapId);
      if (!snapshot) {
        respond(requestId, { ok: false, error: "orbit_snapshot_unavailable" });
        return;
      }
      respond(requestId, {
        ok: true,
        snapshot,
        adapter: "orbit-5.1-readonly-editor-snapshot",
      });
      return;
    }
    if (command === "site_view_snapshot") {
      const snapshot = siteViewPlanningSnapshot(state, mapId);
      if (!snapshot) {
        respond(requestId, {
          ok: false,
          error: "orbit_site_view_snapshot_unavailable",
        });
        return;
      }
      respond(requestId, {
        ok: true,
        snapshot,
        adapter: "orbit-5.1-readonly-site-view-planning-snapshot",
      });
      return;
    }
    if (command === "focus" || command === "select_waypoint") {
      const mapWaypointIds = new Set(state?.siteMaps?.entities?.[mapId]?.waypointIds || []);
      if (!waypointIds.every((id) => mapWaypointIds.has(id))) {
        respond(requestId, { ok: false, error: "map_or_waypoint_mismatch" });
        return;
      }
      if (command === "select_waypoint") {
        store.dispatch({
          type: SELECT_WAYPOINTS_ACTION_TYPE,
          payload: [waypointIds[0]],
        });
      }
      store.dispatch({ type: FOCUS_ACTION_TYPE, payload: waypointIds });
      respond(requestId, {
        ok: true,
        adapter: "orbit-5.1-native-waypoint-selection",
      });
      return;
    }
    if (command === "select_entities") {
      const result = selectEntities(store, mapId, waypointIds, edgeIds, Boolean(focus));
      if (!result.selected) {
        respond(requestId, { ok: false, error: result.error });
        return;
      }
      respond(requestId, {
        ok: true,
        ...result,
        adapter: "orbit-5.1-native-object-selection",
      });
      return;
    }
    if (command === "validate_connect") {
      if (mutationInFlight || validationInFlight) {
        respond(requestId, { ok: false, error: "native_operation_in_progress" });
        return;
      }
      validationInFlight = true;
      const validationBeforeHistory = safeHistoryState(store);
      try {
        const result = await validateConnectPair(store, mapId, waypointIds);
        if (disposed) return;
        if (result.mutationMayExist) {
          respond(requestId, { ok: false, ...result });
          return;
        }
        respond(requestId, {
          ok: true,
          valid: result.valid,
          reason: result.valid ? "" : result.error,
          details: result.valid ? [] : result.details || [],
          adapter: "orbit-5.1-native-connect-validation",
        });
      } catch {
        const validationAfterHistory = safeHistoryState(store);
        const mutationMayExist = !sameHistoryState(
          validationBeforeHistory,
          validationAfterHistory,
        );
        respond(requestId, {
          ok: false,
          error: "native_validation_exception",
          mutationMayExist,
          beforeEditIndex: validationBeforeHistory.editIndex,
          afterEditIndex: validationAfterHistory.editIndex,
          beforeUndoDepth: validationBeforeHistory.undoDepth,
          afterUndoDepth: validationAfterHistory.undoDepth,
          targetKeys: [edgeKey(waypointIds[0], waypointIds[1])],
        });
      } finally {
        validationInFlight = false;
      }
      return;
    }
    if (mutationInFlight || validationInFlight) {
      respond(requestId, { ok: false, error: "native_mutation_in_progress" });
      return;
    }
    mutationInFlight = true;
    try {
      if (command === "archive_edges") {
        const result = archiveWaypointPairs(store, mapId, waypointPairs);
        if (!result.archived) {
          respond(requestId, { ok: false, ...result });
          return;
        }
        respond(requestId, {
          ok: true,
          ...result,
          adapter: "orbit-5.1-native-edge-batch-archive-draft",
        });
        return;
      }
      if (command === "update_edge_settings") {
        const result = updateEdgeSettings(store, mapId, settingsUpdates);
        if (!result.updated) {
          respond(requestId, { ok: false, ...result });
          return;
        }
        respond(requestId, {
          ok: true,
          ...result,
          adapter: "orbit-5.1-native-edge-settings-batch-draft",
        });
        return;
      }
      if (command === "rename_actions") {
        const result = renameActions(store, mapId, actionNameUpdates);
        if (!result.renamed) {
          respond(requestId, { ok: false, ...result });
          return;
        }
        respond(requestId, {
          ok: true,
          ...result,
          adapter: "orbit-5.1-native-action-name-batch-draft",
        });
        return;
      }
      const connectResult = await connectWaypointPair(store, mapId, waypointIds);
      if (disposed) return;
      if (!connectResult.added) {
        respond(requestId, { ok: false, ...connectResult });
        return;
      }
      respond(requestId, {
        ok: true,
        added: true,
        edgeKey: connectResult.edgeKey,
        editIndex: connectResult.editIndex,
        undoDepth: connectResult.undoDepth,
        draftIndexDelta: connectResult.draftIndexDelta,
        adapter: "orbit-5.1-native-edge-draft",
      });
    } catch {
      const targetKeys = command === "archive_edges"
        ? (waypointPairs || []).map((pair) => edgeKey(pair[0], pair[1]))
        : command === "update_edge_settings"
          ? (settingsUpdates || []).map((update) =>
              edgeKey(update.waypointIds[0], update.waypointIds[1])
            )
          : command === "rename_actions"
            ? (actionNameUpdates || []).map((update) => String(update?.id || ""))
          : validWaypointPair(waypointIds)
            ? [edgeKey(waypointIds[0], waypointIds[1])]
            : [];
      respond(requestId, {
        ok: false,
        error: "native_mutation_exception",
        mutationMayExist: true,
        targetKeys,
      });
    } finally {
      mutationInFlight = false;
    }
  }

  window.addEventListener("message", handleMessage);
  globalThis[REGISTRY_KEY] = Object.freeze({
    sessionId: SESSION_ID,
    dispose() {
      disposed = true;
      window.removeEventListener("message", handleMessage);
      window.removeEventListener("popstate", publishActionRouteChange);
      for (const restore of historyRestorers.splice(0).reverse()) restore();
      handledRequestIds.clear();
      mutationInFlight = false;
      validationInFlight = false;
      if (globalThis[REGISTRY_KEY]?.sessionId === SESSION_ID) {
        delete globalThis[REGISTRY_KEY];
      }
    },
  });
  window.postMessage(
    {
      channel: CHANNEL,
      type: READY_TYPE,
      ...(SESSION_ID ? { sessionId: SESSION_ID } : {}),
    },
    location.origin,
  );
})();
