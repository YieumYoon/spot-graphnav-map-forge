(() => {
  "use strict";

  const model = globalThis.OrbitSiteMapEditorModel;
  if (!model) return;

  const SETTING_FIELDS = Object.freeze([
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
  const SETTING_FIELD_SET = new Set(SETTING_FIELDS);

  const BUILTIN_PRESETS = Object.freeze([
    {
      id: "stairs",
      name: "Stairs",
      settings: { stairs: true },
    },
    {
      id: "avoid-alternate",
      name: "No alternate route",
      settings: { disableAlternateRouteFinding: true },
    },
    {
      id: "high-cost",
      name: "High cost",
      settings: { cost: 100 },
    },
    {
      id: "flat-ground",
      name: "Flat ground",
      settings: { flatGround: true },
    },
  ]);

  function jsonClone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function exactPair(value) {
    return Boolean(
      Array.isArray(value) &&
      value.length === 2 &&
      value[0] !== value[1] &&
      value.every((id) => typeof id === "string" && id.length > 0 && id.length <= 256),
    );
  }

  function sanitizeSettings(settings) {
    if (!settings || typeof settings !== "object" || Array.isArray(settings)) {
      throw new Error("invalid_edge_settings");
    }
    const result = {};
    for (const key of Object.keys(settings).sort()) {
      if (!SETTING_FIELD_SET.has(key)) throw new Error("unsupported_edge_setting");
      const value = jsonClone(settings[key]);
      result[key] = value;
    }
    return result;
  }

  function parseConnectQueue(source) {
    const pairs = [];
    const seen = new Set();
    for (const line of String(source || "").split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      const ids = trimmed.split(/[\s,|↔]+/).filter(Boolean);
      if (!exactPair(ids)) throw new Error("invalid_connect_queue_line");
      const key = model.edgeKey(ids[0], ids[1]);
      if (seen.has(key)) continue;
      seen.add(key);
      pairs.push({ id: `connect:${key}`, waypointIds: ids, status: "pending" });
    }
    return pairs;
  }

  function makePreset({ id = "", name, settings }) {
    const trimmed = String(name || "").trim();
    if (!trimmed || trimmed.length > 120) throw new Error("invalid_preset_name");
    return {
      schema: "orbit_site_map_editor_edge_preset_v1",
      id: String(id || `preset-${Date.now()}`),
      name: trimmed,
      settings: sanitizeSettings(settings),
    };
  }

  function presetLibrary(presets) {
    return {
      schema: "orbit_site_map_editor_preset_library_v1",
      exportedAt: new Date().toISOString(),
      presets: (presets || []).map((preset) => makePreset(preset)),
    };
  }

  function parsePresetLibrary(source) {
    let value;
    try {
      value = typeof source === "string" ? JSON.parse(source) : source;
    } catch {
      throw new Error("invalid_preset_library_json");
    }
    if (
      value?.schema !== "orbit_site_map_editor_preset_library_v1" ||
      !Array.isArray(value.presets)
    ) throw new Error("invalid_preset_library");
    return presetLibrary(value.presets);
  }

  globalThis.OrbitSiteMapEditorWorkflow = Object.freeze({
    BUILTIN_PRESETS,
    SETTING_FIELDS,
    makePreset,
    parseConnectQueue,
    parsePresetLibrary,
    presetLibrary,
    sanitizeSettings,
  });
})();
