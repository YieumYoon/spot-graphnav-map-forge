(() => {
  "use strict";

  const edgeSettingsContract = globalThis.OrbitSiteMapEditorEdgeSettingsContract;
  if (!edgeSettingsContract) return;
  const SCHEMA_VERSION = 3;
  const MAX_AREA_CALLBACK_FIELDS = 200;
  const MAX_STORED_AREA_CALLBACK_FIELDS = 1000;
  const VALUE_WRAPPERS = new Set([
    "boolValue",
    "doubleValue",
    "intValue",
    "stringValue",
    "value",
  ]);
  const UNSAFE_KEYS = new Set(["__proto__", "constructor", "prototype"]);
  const MISSING_VALUE = Symbol("missing overlay value");
  const CALLBACK_VALUE_CONTAINERS = Object.freeze([
    Object.freeze(["recordedData", "customParams", "values"]),
    Object.freeze(["recordedData", "parameters", "values", "values"]),
    Object.freeze(["customParams", "values"]),
    Object.freeze(["parameters", "values", "values"]),
  ]);
  const CALLBACK_SCHEMA_PREFIXES = Object.freeze([
    Object.freeze(["recordedData", "customParams", "specs"]),
    Object.freeze(["recordedData", "parameters", "specs"]),
    Object.freeze(["customParams", "specs"]),
    Object.freeze(["parameters", "specs"]),
  ]);
  const CALLBACK_ROOT_METADATA_KEYS = new Set([
    "customParams",
    "description",
    "metadata",
    "parameterSpec",
    "parameterSpecs",
    "parameters",
    "recordedData",
    "serviceName",
    "specs",
    "uiInfo",
  ]);
  const AREA_EDGE_CONTROL_FIELDS = Object.freeze([
    { id: "edgeSpeed", label: "Edge speed", edgeField: "speed" },
    { id: "edgeBodyHeight", label: "Edge body height", edgeField: "bodyHeight" },
    { id: "edgeGait", label: "Edge gait", edgeField: "gait" },
    { id: "edgeAudioVisual", label: "Edge audio/visual", edgeField: "audioVisual" },
    { id: "edgePathFollowing", label: "Edge path mode", edgeField: "pathFollowing" },
    { id: "edgeObstaclePadding", label: "Edge obstacle cushion", edgeField: "obstaclePadding" },
    { id: "edgeHazardDetection", label: "Edge hazard detection", edgeField: "hazardDetection" },
    { id: "edgeGroundFriction", label: "Edge ground friction", edgeField: "groundFriction" },
    { id: "edgeTravelDirection", label: "Edge travel direction", edgeField: "travelDirection" },
    { id: "edgeStairsMode", label: "Edge stair mode", edgeField: "stairsMode" },
    { id: "edgeAutomaticStairs", label: "Edge automatic stairs", edgeField: "automaticStairs" },
    { id: "edgeStairAnnotation", label: "Edge stair annotation", edgeField: "stairAnnotation" },
    { id: "edgeSwingHeight", label: "Edge swing height", edgeField: "swingHeight" },
    { id: "edgeMobilityOverride", label: "Edge override fields", edgeField: "mobilityOverride" },
    { id: "edgeAlternateRoute", label: "Edge alternate route", edgeField: "alternateRoute" },
    { id: "edgeDirectedExploration", label: "Edge directed exploration", edgeField: "directedExploration" },
    { id: "edgeGroundClutter", label: "Edge ground clutter", edgeField: "groundClutter" },
    { id: "edgeAlignment", label: "Edge alignment", edgeField: "alignment" },
    { id: "edgeFlatGround", label: "Edge flat ground", edgeField: "flatGround" },
    { id: "edgeCorridorDistance", label: "Edge corridor distance", edgeField: "corridorDistance" },
    { id: "edgeCost", label: "Edge cost", edgeField: "cost" },
  ]);

  const CONTROL_GROUPS = Object.freeze([
    {
      id: "global",
      label: "Overall",
      masterLabel: "Overlay enabled",
      sections: [
        {
          label: "Highlights",
          fields: [
            { id: "selection", label: "Work selection" },
            { id: "findings", label: "Findings" },
            { id: "components", label: "Components" },
          ],
        },
      ],
    },
    {
      id: "waypoint",
      label: "Waypoints",
      masterLabel: "Show Waypoint markers and labels",
      guidance:
        "Waypoint labels are sampled when zoomed out, so useful values appear before Area labels.",
      sections: [
        {
          label: "Identity",
          fields: [
            { id: "name", label: "Name" },
            { id: "id", label: "ID" },
            { id: "recording", label: "Recording" },
            { id: "degree", label: "Degree" },
            { id: "robot", label: "Robot" },
            { id: "timestamp", label: "Timestamp" },
          ],
        },
        {
          label: "Site View",
          fields: [
            { id: "visualCapture", label: "Visual capture" },
            { id: "visualInterval", label: "Visual interval" },
            { id: "thermalCapture", label: "Thermal capture" },
            { id: "thermalInterval", label: "Thermal interval" },
          ],
        },
      ],
    },
    {
      id: "edge",
      label: "Edges",
      masterLabel: "Show Edge lines and labels",
      guidance:
        "Edge labels are sampled when zoomed out. Selected, work, and finding Edges are always prioritized.",
      sections: [
        {
          label: "Identity & geometry",
          fields: [
            { id: "connectionDirection", label: "Connection direction (arrows)" },
            { id: "id", label: "ID" },
            { id: "from", label: "From waypoint" },
            { id: "to", label: "To waypoint" },
            { id: "source", label: "Source" },
            { id: "length", label: "Length" },
            { id: "crossRecording", label: "Cross-recording" },
          ],
        },
        {
          label: "Mobility",
          fields: [
            { id: "speed", label: "Speed" },
            { id: "bodyHeight", label: "Body height" },
            { id: "gait", label: "Gait" },
            { id: "audioVisual", label: "Audio/visual behavior" },
            { id: "pathFollowing", label: "Strict path following" },
            { id: "obstaclePadding", label: "Obstacle cushion" },
            { id: "hazardDetection", label: "Hazard detection" },
            { id: "groundFriction", label: "Ground friction" },
            { id: "travelDirection", label: "Direction of travel" },
            { id: "stairsMode", label: "Stair mode" },
            { id: "automaticStairs", label: "Automatically detect stairs" },
            { id: "stairAnnotation", label: "Stair annotation" },
            { id: "swingHeight", label: "Swing height" },
            { id: "mobilityOverride", label: "Override fields" },
          ],
        },
        {
          label: "Path & environment",
          fields: [
            { id: "alternateRoute", label: "Alternate route finding" },
            { id: "directedExploration", label: "Directed exploration" },
            { id: "groundClutter", label: "Ground clutter avoidance" },
            { id: "alignment", label: "Require alignment" },
            { id: "flatGround", label: "Flat ground" },
            { id: "corridorDistance", label: "Corridor distance" },
            { id: "cost", label: "Edge cost" },
            { id: "areaCallbacks", label: "Area callbacks" },
          ],
        },
      ],
    },
    {
      id: "area",
      label: "Areas",
      masterLabel: "Show Area labels",
      guidance:
        "Area labels start at 0.8× zoom, later than Waypoint and Edge labels, then remain density-sampled.",
      sections: [
        {
          label: "Area identity",
          description: "Values stored on the Area itself.",
          fields: [
            { id: "name", label: "Name" },
            { id: "id", label: "ID" },
            { id: "type", label: "Type" },
            { id: "service", label: "Callback service" },
            { id: "description", label: "Description" },
            { id: "edgeCount", label: "Associated Edge count" },
          ],
        },
        {
          label: "Same Edge settings, grouped by Area",
          description:
            "These are the same values as the Edges section above, aggregated across every Edge attached to this Area. Different values show mixed (N).",
          fields: AREA_EDGE_CONTROL_FIELDS,
        },
      ],
      dynamicSectionLabel: "Callback parameters",
      dynamicSectionDescription:
        "Current values passed to the Area callback. Orbit form specs, defaults, options, and UI metadata are hidden.",
    },
  ]);

  const DEFAULT_FIELDS = Object.freeze({
    global: Object.freeze({
      selection: true,
      findings: true,
      components: false,
    }),
    waypoint: Object.freeze({
      name: true,
      id: false,
      recording: false,
      degree: true,
      robot: false,
      timestamp: false,
      visualCapture: false,
      visualInterval: false,
      thermalCapture: false,
      thermalInterval: false,
    }),
    edge: Object.freeze(Object.fromEntries(
      CONTROL_GROUPS.find((group) => group.id === "edge")
        .sections.flatMap((section) => section.fields)
        .map((field) => [field.id, false]),
    )),
    area: Object.freeze(Object.fromEntries(
      CONTROL_GROUPS.find((group) => group.id === "area")
        .sections.flatMap((section) => section.fields)
        .map((field) => [field.id, field.id === "name"]),
    )),
  });

  const DEFAULT_ENABLED = Object.freeze({
    global: true,
    waypoint: true,
    edge: true,
    area: false,
  });

  const LEGACY_EDGE_DETAIL_FIELDS = Object.freeze([
    "connectionDirection",
    "source",
    "travelDirection",
    "stairsMode",
    "stairAnnotation",
    "alternateRoute",
    "groundClutter",
    "cost",
    "mobilityOverride",
    "areaCallbacks",
  ]);

  const ENUM_LABELS = Object.freeze({
    gait: Object.freeze({
      0: "Unknown",
      1: "Auto",
      2: "Trot",
      3: "Speed-select trot",
      4: "Crawl",
      5: "Amble",
      6: "Speed-select amble",
      7: "Jog",
      8: "Hop",
      10: "Speed-select crawl",
    }),
    direction: Object.freeze({
      0: "Unknown",
      1: "No turn",
      2: "Forward",
      3: "Reverse",
      4: "None",
    }),
    path: Object.freeze({
      0: "Unknown",
      1: "Default",
      2: "Strict",
    }),
    clutter: Object.freeze({
      0: "Unknown",
      1: "Off",
      2: "From footfalls",
    }),
    hazard: Object.freeze({
      0: "Unknown",
      1: "Off",
      2: "On",
      3: "Cost",
    }),
    stairs: Object.freeze({
      0: "Unknown",
      1: "Off",
      2: "On",
      3: "Auto",
      4: "Prohibited",
    }),
    stairAnnotation: Object.freeze({
      0: "Unknown",
      1: "Set",
      2: "None",
    }),
    swing: Object.freeze({
      0: "Unknown",
      1: "Low",
      2: "Medium",
      3: "High",
      4: "Auto",
    }),
  });

  function isObject(value) {
    return Boolean(value && typeof value === "object" && !Array.isArray(value));
  }

  function own(object, key) {
    return Object.prototype.hasOwnProperty.call(object || {}, key);
  }

  function defaults() {
    const result = { schemaVersion: SCHEMA_VERSION };
    for (const group of CONTROL_GROUPS) {
      result[group.id] = {
        enabled: DEFAULT_ENABLED[group.id],
        fields: { ...DEFAULT_FIELDS[group.id] },
      };
    }
    result.area.callbackFieldDefault = false;
    result.area.callbackFields = {};
    return result;
  }

  function copyKnownGroup(target, source, group) {
    if (!isObject(source)) return;
    if (typeof source.enabled === "boolean") target.enabled = source.enabled;
    if (isObject(source.fields)) {
      for (const key of Object.keys(DEFAULT_FIELDS[group])) {
        if (typeof source.fields[key] === "boolean") {
          target.fields[key] = source.fields[key];
        }
      }
    }
  }

  function copyAreaCallbackFields(target, source) {
    if (!isObject(source)) return;
    if (typeof source.callbackFieldDefault === "boolean") {
      target.callbackFieldDefault = source.callbackFieldDefault;
    }
    if (!isObject(source.callbackFields)) return;
    const entries = Object.entries(source.callbackFields);
    const accepted = [];
    for (
      let index = entries.length - 1;
      index >= 0 && accepted.length < MAX_STORED_AREA_CALLBACK_FIELDS;
      index -= 1
    ) {
      const [path, enabled] = entries[index];
      const segments = callbackPathSegments(path);
      const semanticKey = callbackSemanticKey(path);
      if (
        typeof enabled === "boolean" &&
        enabled !== target.callbackFieldDefault &&
        path.length > 0 &&
        path.length <= 500 &&
        segments &&
        semanticKey &&
        !segments.some((part) => UNSAFE_KEYS.has(part))
      ) {
        accepted.push([path, enabled]);
      }
    }
    for (const [path, enabled] of accepted.reverse()) {
      target.callbackFields[path] = enabled;
    }
  }

  function setCallbackFieldPreference(preferences, path, enabled) {
    const area = preferences?.area;
    const segments = callbackPathSegments(path);
    const semanticKey = callbackSemanticKey(path);
    if (
      !isObject(area?.callbackFields) ||
      typeof enabled !== "boolean" ||
      String(path).length > 500 ||
      !segments ||
      !semanticKey ||
      segments.some((part) => UNSAFE_KEYS.has(part))
    ) return false;
    for (const storedPath of Object.keys(area.callbackFields)) {
      if (callbackSemanticKey(storedPath) === semanticKey) {
        delete area.callbackFields[storedPath];
      }
    }
    if (enabled === area.callbackFieldDefault) return true;
    area.callbackFields[path] = enabled;
    const paths = Object.keys(area.callbackFields);
    for (const stalePath of paths.slice(
      0,
      Math.max(0, paths.length - MAX_STORED_AREA_CALLBACK_FIELDS),
    )) delete area.callbackFields[stalePath];
    return true;
  }

  function migrateLegacy(result, source) {
    const booleanMap = [
      ["detailed", "global", "enabled"],
      ["selection", "global", "selection"],
      ["findings", "global", "findings"],
      ["components", "global", "components"],
      ["names", "waypoint", "name"],
      ["ids", "waypoint", "id"],
      ["recordings", "waypoint", "recording"],
      ["degree", "waypoint", "degree"],
      ["robot", "waypoint", "robot"],
      ["timestamps", "waypoint", "timestamp"],
      ["edges", "edge", "enabled"],
    ];
    for (const [legacyKey, group, field] of booleanMap) {
      if (typeof source[legacyKey] !== "boolean") continue;
      if (field === "enabled") result[group].enabled = source[legacyKey];
      else result[group].fields[field] = source[legacyKey];
    }
    if (source.edgeDetails === true) {
      for (const field of LEGACY_EDGE_DETAIL_FIELDS) {
        result.edge.fields[field] = true;
      }
    }
  }

  function normalizePreferences(source) {
    const result = defaults();
    if (!isObject(source)) return result;
    const nested = CONTROL_GROUPS.some((group) => isObject(source[group.id]));
    if (nested) {
      for (const group of CONTROL_GROUPS) {
        copyKnownGroup(result[group.id], source[group.id], group.id);
      }
      copyAreaCallbackFields(result.area, source.area);
    } else {
      migrateLegacy(result, source);
    }
    return result;
  }

  function fieldEnabled(preferences, group, field) {
    return Boolean(preferences?.[group]?.fields?.[field]);
  }

  function callbackFieldEnabled(preferences, path) {
    const area = preferences?.area || {};
    if (own(area.callbackFields, path)) return Boolean(area.callbackFields[path]);
    const semanticKey = callbackSemanticKey(path);
    if (semanticKey) {
      for (const [storedPath, enabled] of Object.entries(area.callbackFields || {})) {
        if (callbackSemanticKey(storedPath) === semanticKey) return Boolean(enabled);
      }
    }
    return area.callbackFieldDefault !== false;
  }

  function shortId(value, width = 6) {
    const text = String(value || "");
    return text.length > width * 2 + 1
      ? `${text.slice(0, width)}…${text.slice(-width)}`
      : text;
  }

  function scalar(value) {
    let current = value;
    for (let depth = 0; depth < 8; depth += 1) {
      if (!isObject(current)) return current;
      const keys = Object.keys(current);
      if (keys.length !== 1 || !VALUE_WRAPPERS.has(keys[0])) return current;
      current = current[keys[0]];
    }
    return current;
  }

  function finiteScalar(value) {
    const unwrapped = scalar(value);
    return Number.isFinite(unwrapped) ? unwrapped : null;
  }

  function compactText(value, maximum = 80) {
    const text = String(value ?? "");
    return text.length > maximum ? `${text.slice(0, maximum - 1)}…` : text;
  }

  function compactMiddle(value, maximum = 72) {
    const text = String(value ?? "");
    if (text.length <= maximum) return text;
    const left = Math.floor((maximum - 1) / 2);
    return `${text.slice(0, left)}…${text.slice(-(maximum - left - 1))}`;
  }

  function stableTextHash(value) {
    let hash = 2166136261;
    for (const character of String(value || "")) {
      hash ^= character.codePointAt(0);
      hash = Math.imul(hash, 16777619);
    }
    return (hash >>> 0).toString(16).padStart(8, "0");
  }

  function formatNumber(value, digits = 3) {
    if (!Number.isFinite(value)) return "";
    return Number(value.toFixed(digits)).toString();
  }

  function enumLabel(kind, value) {
    const unwrapped = scalar(value);
    if (unwrapped === undefined || unwrapped === null || unwrapped === "") return "";
    if (isObject(unwrapped) || Array.isArray(unwrapped)) return "Configured";
    const labels = ENUM_LABELS[kind];
    return labels && own(labels, unwrapped)
      ? labels[unwrapped]
      : `Value ${compactText(unwrapped, 40)}`;
  }

  function formatDuration(seconds) {
    if (!Number.isFinite(seconds)) return "";
    if (seconds !== 0 && seconds % 3600 === 0) return `${seconds / 3600} h`;
    if (seconds !== 0 && seconds % 60 === 0) return `${seconds / 60} min`;
    return `${formatNumber(seconds)} s`;
  }

  function waypointParts(waypoint, preferences) {
    const fields = preferences?.waypoint?.fields || {};
    const parts = [];
    if (fields.name && waypoint?.name) parts.push(compactText(waypoint.name));
    if (fields.id && waypoint?.id) parts.push(`id ${shortId(waypoint.id)}`);
    if (fields.recording) {
      const recording = waypoint?.recordingName || shortId(waypoint?.recordingId, 5);
      if (recording) parts.push(`recording ${compactText(recording)}`);
    }
    if (fields.degree) parts.push(`degree ${Number(waypoint?.degree) || 0}`);
    if (fields.robot) {
      const robot = waypoint?.robotNickname || waypoint?.robotSerial;
      if (robot) parts.push(`robot ${compactText(robot)}`);
    }
    if (fields.timestamp && waypoint?.creationTime) {
      parts.push(`time ${compactText(waypoint.creationTime)}`);
    }
    const pano = waypoint?.sitePanoSettings;
    if (fields.visualCapture && typeof pano?.allowCaptureVisual === "boolean") {
      parts.push(`visual ${pano.allowCaptureVisual ? "on" : "off"}`);
    }
    if (fields.visualInterval) {
      const interval = formatDuration(pano?.visualCaptureIntervalSeconds);
      if (interval) parts.push(`visual interval ${interval}`);
    }
    if (fields.thermalCapture && typeof pano?.allowCaptureThermal === "boolean") {
      parts.push(`thermal ${pano.allowCaptureThermal ? "on" : "off"}`);
    }
    if (fields.thermalInterval) {
      const interval = formatDuration(pano?.thermalCaptureIntervalSeconds);
      if (interval) parts.push(`thermal interval ${interval}`);
    }
    return parts;
  }

  function speedText(mobility) {
    const maxVelocity = mobility?.velLimit?.maxVel;
    const x = finiteScalar(maxVelocity?.linear?.x);
    const y = finiteScalar(maxVelocity?.linear?.y);
    const yaw = finiteScalar(maxVelocity?.angular);
    if (x === null && y === null && yaw === null) return "";
    const linear = [];
    if (x !== null) linear.push(`x ${formatNumber(x)}`);
    if (y !== null) linear.push(`y ${formatNumber(y)}`);
    let text = linear.length ? `${linear.join(" / ")} m/s` : "";
    if (yaw !== null) {
      text += `${text ? " · " : ""}yaw ${formatNumber(yaw)} rad/s`;
    }
    return `speed ${text}`;
  }

  function bodyHeight(mobility) {
    const bodyControl = mobility?.bodyControl;
    const trajectory = bodyControl?.baseOffsetRtFootprint ||
      bodyControl?.bodyPose?.baseOffsetRtRoot;
    return finiteScalar(
      trajectory?.points?.[0]?.pose?.position?.z ??
      trajectory?.pose?.position?.z ??
      trajectory?.position?.z,
    );
  }

  function booleanSetting(settings, key, label, inverse = false) {
    if (!own(settings, key)) return "";
    const value = scalar(settings[key]);
    if (typeof value !== "boolean") return `${label} configured`;
    const enabled = inverse ? !value : value;
    return `${label} ${enabled ? "on" : "off"}`;
  }

  function effectiveStairsMode(mobility) {
    const mode = scalar(mobility?.stairsMode);
    if (mode !== undefined && mode !== null && mode !== 0 && mode !== "0") {
      return mode;
    }
    if (own(mobility, "stairHint")) {
      const hint = scalar(mobility.stairHint);
      if (typeof hint === "boolean") return hint ? 2 : 1;
    }
    return mode;
  }

  function edgeParts(edge, preferences) {
    const fields = preferences?.edge?.fields || {};
    const settings = edge?.settings || {};
    const mobility = settings.mobilityParams || {};
    const parts = [];
    if (fields.id && edge?.id) parts.push(`id ${shortId(edge.id)}`);
    if (fields.from && edge?.from) parts.push(`from ${shortId(edge.from)}`);
    if (fields.to && edge?.to) parts.push(`to ${shortId(edge.to)}`);
    if (fields.source && edge?.source) parts.push(`source ${compactText(edge.source)}`);
    if (fields.length && Number.isFinite(edge?.length)) {
      parts.push(`length ${formatNumber(edge.length, 2)} m`);
    }
    if (fields.crossRecording && typeof edge?.crossRecording === "boolean") {
      parts.push(`cross-recording ${edge.crossRecording ? "yes" : "no"}`);
    }
    if (fields.speed) {
      const text = speedText(mobility);
      parts.push(text || "speed not set");
    }
    if (fields.bodyHeight) {
      const value = bodyHeight(mobility);
      parts.push(value !== null ? `body height ${formatNumber(value)} m` : "body height not set");
    }
    if (fields.gait) {
      const value = enumLabel("gait", mobility.locomotionHint);
      parts.push(value ? `gait ${value}` : "gait not set");
    }
    if (fields.audioVisual) {
      if (own(settings, "audioVisualSettings")) {
        const behavior = settings.audioVisualSettings?.behaviorName;
        parts.push(`audio/visual ${behavior ? compactText(behavior) : "configured"}`);
      } else {
        parts.push("audio/visual not set");
      }
    }
    if (fields.pathFollowing) {
      const value = enumLabel("path", settings.pathFollowingMode);
      parts.push(value ? `path ${value}` : "path not set");
    }
    if (fields.obstaclePadding) {
      const value = finiteScalar(
        mobility.obstacleParams?.obstacleAvoidancePadding,
      );
      parts.push(
        value !== null
          ? `obstacle cushion ${formatNumber(value)} m`
          : "obstacle cushion not set",
      );
    }
    if (fields.hazardDetection) {
      const value = enumLabel("hazard", mobility.hazardDetectionMode);
      parts.push(value ? `hazard ${value}` : "hazard not set");
    }
    if (fields.groundFriction) {
      const value = finiteScalar(mobility.terrainParams?.groundMuHint);
      parts.push(
        value !== null
          ? `ground friction ${formatNumber(value)}`
          : "ground friction not set",
      );
    }
    if (fields.travelDirection) {
      const value = enumLabel("direction", settings.directionConstraint);
      parts.push(value ? `travel direction ${value}` : "travel direction not set");
    }
    if (fields.stairsMode) {
      const mode = enumLabel("stairs", effectiveStairsMode(mobility));
      parts.push(mode ? `stairs ${mode}` : "stairs not set");
    }
    if (fields.automaticStairs) {
      if (own(mobility, "disallowStairTracker")) {
        const disallowed = scalar(mobility.disallowStairTracker);
        parts.push(
          typeof disallowed === "boolean"
            ? `automatic stairs ${disallowed ? "off" : "on"}`
            : "automatic stairs configured",
        );
      } else {
        parts.push("automatic stairs not set");
      }
    }
    if (fields.stairAnnotation) {
      if (own(settings, "stairs")) {
        if (isObject(settings.stairs) && own(settings.stairs, "state")) {
          const state = enumLabel("stairAnnotation", settings.stairs.state);
          parts.push(state ? `stair annotation ${state}` : "stair annotation not set");
        } else {
          const value = scalar(settings.stairs);
          parts.push(
            typeof value === "boolean"
              ? `stair annotation ${value ? "on" : "off"}`
              : "stair annotation configured",
          );
        }
      } else {
        parts.push("stair annotation not set");
      }
    }
    if (fields.swingHeight) {
      const value = enumLabel("swing", mobility.swingHeight);
      parts.push(value ? `swing height ${value}` : "swing height not set");
    }
    if (fields.mobilityOverride) {
      if (own(settings, "overrideMobilityParams")) {
        const paths = settings.overrideMobilityParams?.paths;
        parts.push(
          Array.isArray(paths) && paths.length
            ? `override ${paths.slice(0, 6).map((path) => compactText(path, 40)).join(", ")}` +
              `${paths.length > 6 ? ", …" : ""}`
            : "mobility override configured",
        );
      } else {
        parts.push("mobility override not set");
      }
    }
    if (fields.alternateRoute) {
      const text = booleanSetting(
        settings,
        "disableAlternateRouteFinding",
        "alternate route",
        true,
      );
      parts.push(text || "alternate route not set");
    }
    if (fields.directedExploration) {
      const text = booleanSetting(
        settings,
        "disableDirectedExploration",
        "directed exploration",
        true,
      );
      parts.push(text || "directed exploration not set");
    }
    if (fields.groundClutter) {
      const value = enumLabel("clutter", settings.groundClutterMode);
      parts.push(value ? `ground clutter ${value}` : "ground clutter not set");
    }
    if (fields.alignment) {
      const text = booleanSetting(settings, "requireAlignment", "alignment");
      parts.push(text || "alignment not set");
    }
    if (fields.flatGround) {
      const text = booleanSetting(settings, "flatGround", "flat ground");
      parts.push(text || "flat ground not set");
    }
    if (fields.corridorDistance) {
      const value = finiteScalar(settings.maxCorridorDistance);
      parts.push(value !== null ? `corridor ${formatNumber(value)} m` : "corridor not set");
    }
    if (fields.cost) {
      const value = finiteScalar(settings.cost);
      parts.push(value !== null ? `cost ${formatNumber(value)}` : "cost not set");
    }
    if (fields.areaCallbacks) {
      const callbacks = Object.keys(settings.areaCallbacks || {});
      parts.push(`Area callbacks ${callbacks.length}`);
    }
    return parts;
  }

  function callbackPath(segments) {
    return `/${segments
      .map((part) => String(part).replace(/~/g, "~0").replace(/\//g, "~1"))
      .join("/")}`;
  }

  function callbackPathSegments(path) {
    const text = String(path || "");
    if (!text.startsWith("/") || /~(?![01])/u.test(text)) return null;
    return text.slice(1).split("/").map((part) =>
      part.replace(/~1/g, "/").replace(/~0/g, "~")
    );
  }

  function pathStartsWith(segments, prefix) {
    return prefix.every((part, index) => segments[index] === part);
  }

  function normalizedCallbackSegment(value) {
    return String(value)
      .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
      .replace(/[\s-]+/g, "_")
      .toLocaleLowerCase();
  }

  function callbackSemanticKey(path) {
    const rawSegments = callbackPathSegments(path);
    if (
      !rawSegments ||
      rawSegments.some((part) => UNSAFE_KEYS.has(part)) ||
      CALLBACK_SCHEMA_PREFIXES.some((prefix) => pathStartsWith(rawSegments, prefix))
    ) return null;
    const prefix = CALLBACK_VALUE_CONTAINERS.find((candidate) =>
      pathStartsWith(rawSegments, candidate)
    );
    const valueSegments = prefix ? rawSegments.slice(prefix.length) : rawSegments;
    if (!valueSegments.length) return null;
    return callbackPath(valueSegments.map(normalizedCallbackSegment));
  }

  function flattenCallback(callback, maximum = 250) {
    const result = new Map();
    const visit = (value, segments, depth) => {
      if (result.size >= maximum || depth > 20) return;
      const unwrapped = scalar(value);
      if (unwrapped !== value) {
        visit(unwrapped, segments, depth + 1);
        return;
      }
      if (Array.isArray(value)) {
        if (value.every((item) => !isObject(item) && !Array.isArray(item))) {
          result.set(callbackPath(segments), value.slice());
          return;
        }
        value.slice(0, 50).forEach((item, index) => {
          visit(item, [...segments, String(index)], depth + 1);
        });
        return;
      }
      if (isObject(value)) {
        for (const key of Object.keys(value).sort()) {
          if (UNSAFE_KEYS.has(key)) continue;
          if (!segments.length && (key === "serviceName" || key === "description")) {
            continue;
          }
          visit(value[key], [...segments, key], depth + 1);
        }
        return;
      }
      if (segments.length && value !== undefined && value !== null) {
        const path = callbackPath(segments);
        const safeSegments = callbackPathSegments(path);
        if (
          path.length <= 500 &&
          safeSegments &&
          !safeSegments.some((part) => UNSAFE_KEYS.has(part))
        ) {
          result.set(path, value);
        }
      }
    };
    visit(callback, [], 0);
    return result;
  }

  function nestedCallbackValue(callback, segments) {
    let current = callback;
    for (const segment of segments) {
      if (!isObject(current) || !own(current, segment)) return undefined;
      current = current[segment];
    }
    return current;
  }

  function callbackParameterValues(callback, maximum = 250) {
    const result = new Map();
    const consider = (rawPath, value, rank) => {
      const semanticKey = callbackSemanticKey(rawPath);
      if (!semanticKey) return;
      const existing = result.get(semanticKey);
      if (
        existing &&
        (existing.rank < rank ||
          (existing.rank === rank && existing.path.localeCompare(rawPath) <= 0))
      ) return;
      result.set(semanticKey, {
        label: pathLabel(rawPath),
        path: rawPath,
        rank,
        value,
      });
    };
    for (const [rank, prefix] of CALLBACK_VALUE_CONTAINERS.entries()) {
      const container = nestedCallbackValue(callback, prefix);
      if (!isObject(container)) continue;
      for (const [relativePath, value] of flattenCallback(container, maximum)) {
        const segments = callbackPathSegments(relativePath);
        if (!segments) continue;
        consider(callbackPath([...prefix, ...segments]), value, rank);
      }
    }
    if (isObject(callback)) {
      for (const key of Object.keys(callback).sort()) {
        if (CALLBACK_ROOT_METADATA_KEYS.has(key) || UNSAFE_KEYS.has(key)) continue;
        for (const [rawPath, value] of flattenCallback({ [key]: callback[key] }, maximum)) {
          consider(rawPath, value, CALLBACK_VALUE_CONTAINERS.length);
        }
      }
    }
    return new Map(
      [...result.entries()]
        .sort(([left], [right]) => left.localeCompare(right))
        .slice(0, maximum),
    );
  }

  function pathLabel(path) {
    const rawSegments = callbackPathSegments(path);
    const segments = rawSegments || [String(path || "")];
    const prefix = CALLBACK_VALUE_CONTAINERS.find((candidate) =>
      pathStartsWith(segments, candidate)
    );
    const labelSegments = prefix ? segments.slice(prefix.length) : segments;
    const label = labelSegments
      .map((part) => part
        .replace(/([a-z])([A-Z])/g, "$1 $2")
        .replace(/_/g, " "))
      .join(" › ");
    if (label) return label;
    if (rawSegments?.length === 1 && rawSegments[0] === "") return "(empty key)";
    return rawSegments?.at(-1) || "(value)";
  }

  function canonicalValue(value, seen = new WeakSet()) {
    if (Array.isArray(value)) {
      if (seen.has(value)) return "[circular]";
      seen.add(value);
      const result = value.map((item) => canonicalValue(item, seen));
      seen.delete(value);
      return result;
    }
    if (isObject(value)) {
      if (seen.has(value)) return "[circular]";
      seen.add(value);
      const result = Object.fromEntries(
        Object.keys(value).sort().map((key) => [key, canonicalValue(value[key], seen)]),
      );
      seen.delete(value);
      return result;
    }
    return value;
  }

  function valueKey(value) {
    if (value === MISSING_VALUE) return "missing";
    if (typeof value === "number") return `number:${value}`;
    if (typeof value === "boolean") return `boolean:${value}`;
    if (typeof value === "string") return `string:${value}`;
    if (Array.isArray(value) || isObject(value)) {
      return `json:${JSON.stringify(canonicalValue(value))}`;
    }
    return `${typeof value}:${String(value)}`;
  }

  function displayValue(value) {
    if (value === MISSING_VALUE) return "not set";
    if (typeof value === "boolean") return value ? "on" : "off";
    if (typeof value === "number") return formatNumber(value);
    if (Array.isArray(value)) {
      if (!value.length) return "[]";
      const preview = value.slice(0, 20)
        .map((item) => compactText(item, 40))
        .join(", ");
      return compactText(`${preview}${value.length > 20 ? ", …" : ""}`, 120);
    }
    if (value === "") return "(empty)";
    return compactText(value, 120);
  }

  function aggregateValues(values) {
    const unique = new Map();
    for (const value of values) unique.set(valueKey(value), value);
    if (!unique.size) return "";
    if (unique.size > 1) return `mixed (${unique.size})`;
    return displayValue(unique.values().next().value);
  }

  function areaCallbackFieldCatalog(
    areas = [],
    maximum = MAX_AREA_CALLBACK_FIELDS,
  ) {
    const catalog = new Map();
    for (const area of areas) {
      for (const callback of area.callbackSettings || []) {
        for (const [semanticKey, entry] of callbackParameterValues(callback)) {
          const existing = catalog.get(semanticKey);
          if (
            existing &&
            (existing.rank < entry.rank ||
              (existing.rank === entry.rank && existing.path.localeCompare(entry.path) <= 0))
          ) continue;
          catalog.set(semanticKey, {
            label: compactText(entry.label, 100),
            path: entry.path,
            rank: entry.rank,
            semanticKey,
          });
        }
      }
    }
    const sorted = [...catalog.values()].sort((left, right) =>
      left.label.localeCompare(right.label) || left.path.localeCompare(right.path)
    );
    const truncated = sorted.length > maximum;
    const result = sorted.slice(0, maximum);
    const labelCounts = new Map();
    for (const field of result) {
      labelCounts.set(field.label, (labelCounts.get(field.label) || 0) + 1);
    }
    const usedLabels = new Set();
    for (const field of result) {
      let label = field.label;
      if (labelCounts.get(field.label) > 1) {
        label = `${compactText(
          `${field.label} — ${compactMiddle(field.path)}`,
          108,
        )} [${stableTextHash(field.path)}]`;
      }
      let uniqueLabel = label;
      for (let suffix = 2; usedLabels.has(uniqueLabel); suffix += 1) {
        uniqueLabel = `${compactText(label, 112)} #${suffix}`;
      }
      field.label = uniqueLabel;
      delete field.rank;
      usedLabels.add(uniqueLabel);
    }
    result.truncated = truncated;
    return result;
  }

  function edgeFieldRawValue(settings, field) {
    const mobility = settings?.mobilityParams || {};
    const scalarOrMissing = (value) => {
      const unwrapped = scalar(value);
      return unwrapped === undefined || unwrapped === null || unwrapped === ""
        ? MISSING_VALUE
        : unwrapped;
    };
    const finiteOrMissing = (value) => {
      const number = finiteScalar(value);
      return number === null ? MISSING_VALUE : number;
    };
    switch (field) {
      case "speed": {
        const maxVelocity = mobility.velLimit?.maxVel;
        const value = {
          x: finiteScalar(maxVelocity?.linear?.x),
          y: finiteScalar(maxVelocity?.linear?.y),
          yaw: finiteScalar(maxVelocity?.angular),
        };
        return Object.values(value).every((item) => item === null)
          ? MISSING_VALUE
          : value;
      }
      case "bodyHeight":
        return bodyHeight(mobility) ?? MISSING_VALUE;
      case "gait":
        return scalarOrMissing(mobility.locomotionHint);
      case "audioVisual":
        return own(settings, "audioVisualSettings")
          ? settings.audioVisualSettings
          : MISSING_VALUE;
      case "pathFollowing":
        return scalarOrMissing(settings.pathFollowingMode);
      case "obstaclePadding":
        return finiteOrMissing(mobility.obstacleParams?.obstacleAvoidancePadding);
      case "hazardDetection":
        return scalarOrMissing(mobility.hazardDetectionMode);
      case "groundFriction":
        return finiteOrMissing(mobility.terrainParams?.groundMuHint);
      case "travelDirection":
        return scalarOrMissing(settings.directionConstraint);
      case "stairsMode":
        return scalarOrMissing(effectiveStairsMode(mobility));
      case "automaticStairs":
        return own(mobility, "disallowStairTracker")
          ? scalarOrMissing(mobility.disallowStairTracker)
          : MISSING_VALUE;
      case "stairAnnotation":
        return own(settings, "stairs")
          ? scalarOrMissing(
              isObject(settings.stairs) && own(settings.stairs, "state")
                ? settings.stairs.state
                : settings.stairs,
            )
          : MISSING_VALUE;
      case "swingHeight":
        return scalarOrMissing(mobility.swingHeight);
      case "mobilityOverride":
        return own(settings, "overrideMobilityParams")
          ? settings.overrideMobilityParams
          : MISSING_VALUE;
      case "alternateRoute":
        return own(settings, "disableAlternateRouteFinding")
          ? scalarOrMissing(settings.disableAlternateRouteFinding)
          : MISSING_VALUE;
      case "directedExploration":
        return own(settings, "disableDirectedExploration")
          ? scalarOrMissing(settings.disableDirectedExploration)
          : MISSING_VALUE;
      case "groundClutter":
        return scalarOrMissing(settings.groundClutterMode);
      case "alignment":
        return own(settings, "requireAlignment")
          ? scalarOrMissing(settings.requireAlignment)
          : MISSING_VALUE;
      case "flatGround":
        return own(settings, "flatGround")
          ? scalarOrMissing(settings.flatGround)
          : MISSING_VALUE;
      case "corridorDistance":
        return finiteOrMissing(settings.maxCorridorDistance);
      case "cost":
        return finiteOrMissing(settings.cost);
      default:
        return MISSING_VALUE;
    }
  }

  function areaParts(area, preferences, allowedCallbackPaths = null) {
    const fields = preferences?.area?.fields || {};
    const callbacks = area?.callbackSettings || [];
    const parts = [];
    if (fields.name) {
      const name = area?.name || shortId(area?.id, 12);
      if (name) parts.push(compactText(name));
    }
    if (fields.id && area?.id) parts.push(`id ${shortId(area.id)}`);
    if (fields.type && area?.type) parts.push(`type ${area.type}`);
    if (fields.service) {
      const fallback = area?.serviceName || MISSING_VALUE;
      const values = callbacks.length
        ? callbacks.map((callback) => callback?.serviceName || fallback)
        : [fallback];
      const service = values.some((value) => value !== MISSING_VALUE)
        ? aggregateValues(values)
        : "";
      if (service) parts.push(`service ${service}`);
    }
    if (fields.description) {
      const fallback = area?.description || MISSING_VALUE;
      const values = callbacks.length
        ? callbacks.map((callback) => callback?.description || fallback)
        : [fallback];
      const description = values.some((value) => value !== MISSING_VALUE)
        ? aggregateValues(values)
        : "";
      if (description) parts.push(`description ${description}`);
    }
    if (fields.edgeCount && Number.isFinite(area?.edgeCount)) {
      parts.push(`edges ${area.edgeCount}`);
    }

    const edgeVariants = area?.edgeSettings || [];
    const areaEdgeFields = CONTROL_GROUPS.find((group) => group.id === "area")
      .sections.flatMap((section) => section.fields)
      .filter((field) => field.edgeField);
    for (const field of areaEdgeFields) {
      if (!fields[field.id] || !edgeVariants.length) continue;
      const edgePreferences = { edge: { fields: { [field.edgeField]: true } } };
      const rawValues = edgeVariants.map((settings) =>
        edgeFieldRawValue(settings, field.edgeField)
      );
      if (rawValues.every((value) => value === MISSING_VALUE)) {
        parts.push(`${field.label.toLocaleLowerCase()} not set`);
        continue;
      }
      const distinct = new Map();
      for (const value of rawValues) distinct.set(valueKey(value), value);
      if (distinct.size > 1) {
        parts.push(`${field.label.toLocaleLowerCase()} mixed (${distinct.size})`);
        continue;
      }
      const value = edgeVariants
        .map((settings) => edgeParts({ settings }, edgePreferences)[0])
        .find(Boolean);
      if (value) parts.push(`edge ${value}`);
    }

    const callbackValues = callbacks.map((callback) => callbackParameterValues(callback));
    const catalog = allowedCallbackPaths === null
      ? areaCallbackFieldCatalog([{ callbackSettings: callbacks }])
      : allowedCallbackPaths instanceof Map
        ? [...allowedCallbackPaths.entries()].map(([path, metadata]) => ({
            label: isObject(metadata) ? metadata.label : String(metadata),
            path,
            semanticKey: isObject(metadata)
              ? metadata.semanticKey || callbackSemanticKey(path)
              : callbackSemanticKey(path),
          }))
        : [...allowedCallbackPaths].map((path) => ({
            label: pathLabel(path),
            path,
            semanticKey: callbackSemanticKey(path),
          }));
    for (const field of catalog.sort((left, right) =>
      left.label.localeCompare(right.label) || left.path.localeCompare(right.path)
    )) {
      if (
        !field.semanticKey ||
        !callbackValues.some((values) => values.has(field.semanticKey))
      ) continue;
      const path = field.path;
      if (!callbackFieldEnabled(preferences, path)) continue;
      const value = aggregateValues(callbackValues.map((values) =>
        values.has(field.semanticKey)
          ? values.get(field.semanticKey).value
          : MISSING_VALUE
      ));
      if (value) parts.push(`callback ${field.label}=${value}`);
    }
    return parts;
  }

  globalThis.OrbitSiteMapEditorOverlaySettings = Object.freeze({
    CONTROL_GROUPS,
    EDGE_SETTING_FIELDS: edgeSettingsContract.FIELDS,
    SCHEMA_VERSION,
    areaCallbackFieldCatalog,
    areaParts,
    callbackFieldEnabled,
    defaults,
    edgeParts,
    fieldEnabled,
    flattenCallback,
    normalizePreferences,
    setCallbackFieldPreference,
    waypointParts,
  });
})();
