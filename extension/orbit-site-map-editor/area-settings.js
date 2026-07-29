(() => {
  "use strict";

  const UNSAFE_KEYS = new Set(["__proto__", "constructor", "prototype"]);
  const VALUE_KEYS = [
    "boolValue",
    "doubleValue",
    "intValue",
    "stringValue",
    "value",
  ];
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

  function isObject(value) {
    return Boolean(value && typeof value === "object" && !Array.isArray(value));
  }

  function clone(value) {
    if (value === undefined) return undefined;
    return JSON.parse(JSON.stringify(value));
  }

  function canonical(value) {
    if (Array.isArray(value)) return value.map(canonical);
    if (!isObject(value)) return value;
    return Object.fromEntries(
      Object.keys(value).sort().map((key) => [key, canonical(value[key])]),
    );
  }

  function same(left, right) {
    return JSON.stringify(canonical(left)) === JSON.stringify(canonical(right));
  }

  function validateObject(value, label = "Area callback patch", depth = 0) {
    if (!isObject(value)) throw new Error(`${label} must be a JSON object.`);
    if (depth > 20) throw new Error(`${label} is nested too deeply.`);
    for (const [key, child] of Object.entries(value)) {
      if (UNSAFE_KEYS.has(key)) throw new Error(`${label} contains an unsafe field.`);
      if (isObject(child)) validateObject(child, label, depth + 1);
      else if (Array.isArray(child)) {
        for (const item of child) {
          if (isObject(item)) validateObject(item, label, depth + 1);
        }
      }
    }
    return value;
  }

  function parsePatch(source) {
    let value;
    try {
      value = JSON.parse(String(source || ""));
    } catch {
      throw new Error("Area callback patch is not valid JSON.");
    }
    validateObject(value);
    if (!Object.keys(value).length) {
      throw new Error("Area callback patch must contain at least one field.");
    }
    return value;
  }

  // JSON Merge Patch semantics: object fields merge recursively and null removes a field.
  function mergePatch(base, patch) {
    validateObject(patch);
    const result = isObject(base) ? clone(base) : {};
    for (const [key, value] of Object.entries(patch)) {
      if (value === null) delete result[key];
      else if (isObject(value)) result[key] = mergePatch(result[key], value);
      else result[key] = clone(value);
    }
    return result;
  }

  function finitePosition(value) {
    return Boolean(Number.isFinite(value?.x) && Number.isFinite(value?.y));
  }

  function areaPosition(area, waypointIds, waypointById) {
    if (finitePosition(area.position)) return { ...area.position };
    const positions = [...new Set(waypointIds)]
      .map((id) => waypointById.get(id)?.position)
      .filter(finitePosition);
    if (!positions.length) return null;
    return {
      x: positions.reduce((sum, item) => sum + item.x, 0) / positions.length,
      y: positions.reduce((sum, item) => sum + item.y, 0) / positions.length,
      z: positions.reduce((sum, item) => sum + (Number(item.z) || 0), 0) /
        positions.length,
    };
  }

  function scalarValue(value) {
    if (!isObject(value)) return value;
    const present = VALUE_KEYS.filter((key) =>
      Object.prototype.hasOwnProperty.call(value, key)
    );
    return present.length === 1 ? value[present[0]] : value;
  }

  function callbackDetails(callback, maximum = 4) {
    const details = [];
    const visit = (value, path, depth) => {
      if (details.length >= maximum || depth > 12) return;
      const unwrapped = scalarValue(value);
      if (unwrapped !== value) {
        visit(unwrapped, path, depth + 1);
        return;
      }
      if (Array.isArray(value)) {
        if (value.length && value.every((item) => !isObject(item))) {
          details.push(`${path}=${value.join(",")}`);
        } else {
          for (const [index, item] of value.slice(0, 6).entries()) {
            visit(item, `${path}[${index}]`, depth + 1);
          }
        }
        return;
      }
      if (isObject(value)) {
        for (const key of Object.keys(value).sort()) {
          if (key === "serviceName" || key === "description") continue;
          visit(value[key], path ? `${path}.${key}` : key, depth + 1);
        }
        return;
      }
      if (value !== undefined && value !== null && path) {
        const shortPath = path
          .replace(/^recordedData\.customParams\.values\./, "")
          .replace(/^customParams\.values\./, "");
        details.push(`${shortPath}=${String(value)}`);
      }
    };
    visit(callback, "", 0);
    return details;
  }

  function callbackSummary(callback) {
    if (!isObject(callback)) return "invalid callback";
    const parts = [];
    if (callback.serviceName) {
      parts.push(
        String(callback.serviceName) === "spot-crosswalk"
          ? "crosswalk"
          : String(callback.serviceName),
      );
    }
    parts.push(...callbackDetails(callback));
    const summary = parts.join(" · ") || "empty callback";
    return summary.length > 150 ? `${summary.slice(0, 149)}…` : summary;
  }

  function modeledEdgeSettings(settings) {
    return Object.fromEntries(
      Object.entries(settings || {})
        .filter(([key]) => EDGE_SETTING_FIELDS.has(key) && key !== "areaCallbacks")
        .map(([key, value]) => [key, clone(value)]),
    );
  }

  function readableValue(value) {
    if (typeof value === "string" || typeof value === "number") return String(value);
    if (typeof value === "boolean") return value ? "on" : "off";
    return "configured";
  }

  function edgeSettingSummary(settings) {
    const values = modeledEdgeSettings(settings);
    const parts = [];
    for (const [key, value] of Object.entries(values)) {
      if (typeof value === "boolean" && !value) continue;
      if (typeof value === "number" && value === 0) continue;
      const label = key
        .replace(/([a-z])([A-Z])/g, "$1 $2")
        .toLocaleLowerCase();
      parts.push(value === true ? label : `${label} ${readableValue(value)}`);
    }
    return parts.join(" · ");
  }

  function uniqueValues(values) {
    const result = [];
    const seen = new Set();
    for (const value of values.filter(Boolean)) {
      const normalized = String(value).trim();
      const key = normalized.toLocaleLowerCase();
      if (!normalized || seen.has(key)) continue;
      seen.add(key);
      result.push(normalized);
    }
    return result;
  }

  function records(snapshot = {}) {
    const edges = snapshot.edges || [];
    const edgeById = new Map();
    for (const edge of edges) {
      edgeById.set(String(edge.id || ""), edge);
      edgeById.set(
        [String(edge.from || ""), String(edge.to || "")].sort().join("|"),
        edge,
      );
    }
    const areasById = new Map(
      (snapshot.areas || []).map((area) => [String(area.id), {
        ...area,
        id: String(area.id),
        callbacks: [],
      }]),
    );
    for (const edge of edges) {
      for (const [areaId, callback] of Object.entries(
        edge.settings?.areaCallbacks || {},
      )) {
        if (!areasById.has(areaId)) {
          areasById.set(areaId, {
            id: areaId,
            name: "",
            waypointIds: [],
            edgeIds: [],
            position: null,
            catalogPresent: false,
            inferredFromEdge: true,
            callbacks: [],
          });
        }
        areasById.get(areaId).callbacks.push({ edge, callback: clone(callback) });
      }
    }
    const waypointById = new Map(
      (snapshot.waypoints || []).map((waypoint) => [waypoint.id, waypoint]),
    );
    return [...areasById.values()].map((area) => {
      const associatedEdgeMap = new Map(
        area.callbacks.map(({ edge }) => [String(edge.id), edge]),
      );
      for (const id of area.edgeIds || []) {
        const edge = edgeById.get(String(id));
        if (edge) associatedEdgeMap.set(String(edge.id), edge);
      }
      const associatedEdges = [...associatedEdgeMap.values()];
      const waypointIds = [...new Set([
        ...(area.waypointIds || []),
        ...associatedEdges.flatMap((edge) => [edge.from, edge.to]),
      ].filter(Boolean))];
      const callbackVariants = new Map();
      for (const { callback } of area.callbacks) {
        const key = JSON.stringify(canonical(callback));
        if (!callbackVariants.has(key)) callbackVariants.set(key, callback);
      }
      const edgeVariants = new Map();
      for (const edge of associatedEdges) {
        const settings = modeledEdgeSettings(edge.settings);
        const key = JSON.stringify(canonical(settings));
        if (!edgeVariants.has(key)) edgeVariants.set(key, settings);
      }
      const summaries = uniqueValues([
        area.type,
        area.serviceName === "spot-crosswalk" ? "crosswalk" : area.serviceName,
        ...[...callbackVariants.values()].map(callbackSummary),
        ...associatedEdges.map((edge) => edgeSettingSummary(edge.settings)),
      ]).filter((value) => value.toLocaleLowerCase() !==
        String(area.name || "").trim().toLocaleLowerCase());
      return {
        ...area,
        associatedEdges,
        waypointIds,
        edgeIds: [...new Set([
          ...(area.edgeIds || []),
          ...associatedEdges.map((edge) => edge.id).filter(Boolean),
        ])],
        position: areaPosition(area, waypointIds, waypointById),
        edgeCount: associatedEdges.length,
        callbackVariantCount: callbackVariants.size,
        edgeVariantCount: edgeVariants.size,
        variantCount: Math.max(callbackVariants.size, edgeVariants.size),
        editable: associatedEdges.length > 0,
        callbackEditable: area.callbacks.length > 0,
        summary: summaries.join(" · ") || "default traversal",
        callbackSettings: [...callbackVariants.values()].map(clone),
        edgeSettings: [...edgeVariants.values()].map(clone),
      };
    }).sort((left, right) =>
      String(left.name || left.id).localeCompare(String(right.name || right.id))
    );
  }

  function updatePlan(snapshot, areaIds, patch, mode = "merge", target = "callback") {
    validateObject(patch);
    if (!Object.keys(patch).length) {
      throw new Error("Area callback patch must contain at least one field.");
    }
    if (!new Set(["merge", "replace"]).has(mode)) {
      throw new Error("Unknown Area callback update mode.");
    }
    if (!new Set(["callback", "edge"]).has(target)) {
      throw new Error("Unknown Area setting target.");
    }
    if (target === "edge") {
      for (const key of Object.keys(patch)) {
        if (!EDGE_SETTING_FIELDS.has(key) || key === "areaCallbacks") {
          throw new Error(`Unsupported Edge setting: ${key}`);
        }
      }
    }
    const targetIds = new Set((areaIds || []).map(String).filter(Boolean));
    if (!targetIds.size) throw new Error("Select at least one editable Area.");
    if (target === "edge") {
      const targetRecords = records(snapshot).filter((area) => targetIds.has(area.id));
      const availableIds = new Set(
        targetRecords.filter((area) => area.associatedEdges.length).map((area) => area.id),
      );
      const missingAreaIds = [...targetIds].filter((id) => !availableIds.has(id));
      if (missingAreaIds.length) {
        throw new Error(
          `${missingAreaIds.length} selected Area(s) have no associated editable Edges.`,
        );
      }
      const targetEdges = new Map();
      for (const area of targetRecords) {
        for (const edge of area.associatedEdges) targetEdges.set(String(edge.id), edge);
      }
      if (targetEdges.size > 5000) {
        throw new Error("Area update exceeds Orbit's 5,000-edge batch limit.");
      }
      const edgeUpdates = [];
      for (const edge of targetEdges.values()) {
        const observedSettings = clone(edge.settings || {});
        const hadAreaCallbacks = Object.prototype.hasOwnProperty.call(
          observedSettings,
          "areaCallbacks",
        );
        const areaCallbacks = clone(observedSettings.areaCallbacks || {});
        const desiredSettings = mode === "replace"
          ? { ...clone(patch), areaCallbacks }
          : mergePatch(observedSettings, patch);
        if (hadAreaCallbacks) desiredSettings.areaCallbacks = areaCallbacks;
        else delete desiredSettings.areaCallbacks;
        if (same(observedSettings, desiredSettings)) continue;
        edgeUpdates.push({ edge, observedSettings, desiredSettings });
      }
      return {
        areaIds: [...targetIds].sort(),
        target,
        mode,
        patch: clone(patch),
        matchedCallbackCount: 0,
        edgeUpdates,
        unchangedEdgeCount: targetEdges.size - edgeUpdates.length,
      };
    }
    const availableIds = new Set();
    const edgeUpdates = [];
    let matchedCallbackCount = 0;
    let matchedEdgeCount = 0;
    for (const edge of snapshot.edges || []) {
      const observedCallbacks = edge.settings?.areaCallbacks || {};
      let desiredCallbacks = null;
      for (const areaId of targetIds) {
        if (!Object.prototype.hasOwnProperty.call(observedCallbacks, areaId)) continue;
        availableIds.add(areaId);
        matchedCallbackCount += 1;
        if (!desiredCallbacks) desiredCallbacks = clone(observedCallbacks);
        desiredCallbacks[areaId] = mode === "replace"
          ? clone(patch)
          : mergePatch(observedCallbacks[areaId], patch);
      }
      if (desiredCallbacks) matchedEdgeCount += 1;
      if (!desiredCallbacks || same(observedCallbacks, desiredCallbacks)) continue;
      edgeUpdates.push({
        edge,
        observedSettings: clone(edge.settings || {}),
        desiredSettings: {
          ...clone(edge.settings || {}),
          areaCallbacks: desiredCallbacks,
        },
      });
    }
    const missingAreaIds = [...targetIds].filter((id) => !availableIds.has(id));
    if (missingAreaIds.length) {
      throw new Error(
        `${missingAreaIds.length} selected Area(s) have no editable Edge callback settings.`,
      );
    }
    if (edgeUpdates.length > 5000) {
      throw new Error("Area update exceeds Orbit's 5,000-edge batch limit.");
    }
    return {
      areaIds: [...targetIds].sort(),
      target,
      mode,
      patch: clone(patch),
      matchedCallbackCount,
      edgeUpdates,
      unchangedEdgeCount: matchedEdgeCount - edgeUpdates.length,
    };
  }

  globalThis.OrbitSiteMapEditorAreaSettings = Object.freeze({
    callbackSummary,
    edgeSettingSummary,
    mergePatch,
    parsePatch,
    records,
    updatePlan,
  });
})();
