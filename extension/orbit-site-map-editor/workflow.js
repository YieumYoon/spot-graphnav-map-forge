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
  const ACTION_NAME_SUFFIXES = Object.freeze(["THRM", "MECQ", "LEAK", "AIVI"]);
  const ACTION_NAME_SUFFIX_SET = new Set(ACTION_NAME_SUFFIXES);

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

  function explicitInspectionType(name) {
    const normalized = String(name || "").trim();
    const existing = normalized.match(/-(THRM|MECQ|LEAK|AIVI)(?:\s+\(AI\))?$/i);
    return existing && ACTION_NAME_SUFFIX_SET.has(existing[1].toUpperCase())
      ? existing[1].toUpperCase()
      : "";
  }

  function suggestInspectionType(action) {
    const source = typeof action === "string" ? { name: action } : action || {};
    const explicit = explicitInspectionType(source.name);
    if (explicit) return explicit;
    const text = [
      source.name,
      source.type,
      source.actionType,
      source.serviceName,
      source.callbackServiceName,
    ].filter(Boolean).join(" ");
    for (const [type, pattern] of [
      ["THRM", /\b(thermal|thermography|thermographic|infrared|radiometric|temperature|heat)\b/i],
      ["MECQ", /\b(mechanical|mechanic|mech|vibration|vibrational)\b/i],
      ["LEAK", /\b(leak|ultrasonic|ultrasound|acoustic)\b/i],
      ["AIVI", /\b(aivi|visual|vision|camera|image|imagery|photo|ai)\b|spot\s*cam|ptz/i],
    ]) {
      if (pattern.test(text)) return type;
    }
    return "";
  }

  function parseActionSequence(value) {
    const formatted = String(value || "").trim();
    if (!/^\d{1,8}$/.test(formatted)) {
      throw new Error("invalid_action_first_number");
    }
    return {
      formatted,
      startSequence: Number(formatted),
      sequenceWidth: formatted.length,
    };
  }

  function normalizeActionNamingOptions(options = {}) {
    const hierarchy = {
      enterprise: String(options.enterprise || "").trim().toUpperCase(),
      site: String(options.site || "").trim().toUpperCase(),
      area: String(options.area || "").trim().toUpperCase(),
      workCenter: String(options.workCenter || "").trim().toUpperCase(),
      equipment: String(options.equipment || "").trim().toUpperCase(),
    };
    for (const key of ["enterprise", "site", "area"]) {
      if (!hierarchy[key]) throw new Error("missing_required_name_segment");
    }
    for (const value of Object.values(hierarchy)) {
      if (value && !/^[A-Z0-9._]{1,32}$/.test(value)) {
        throw new Error("invalid_action_name_segment");
      }
    }
    const startSequence = Number(options.startSequence);
    const sequenceWidth = Number(options.sequenceWidth);
    if (!Number.isInteger(sequenceWidth) || sequenceWidth < 1 || sequenceWidth > 8) {
      throw new Error("invalid_action_sequence_width");
    }
    const maxSequence = 10 ** sequenceWidth - 1;
    if (
      !Number.isInteger(startSequence) ||
      startSequence < 0 ||
      startSequence > maxSequence
    ) {
      throw new Error("invalid_action_sequence_start");
    }
    return { hierarchy, startSequence, sequenceWidth };
  }

  function buildActionName(hierarchy, sequence, type) {
    const name = [
      hierarchy.enterprise,
      hierarchy.site,
      hierarchy.area,
      hierarchy.workCenter,
      hierarchy.equipment,
      sequence,
      type,
    ].filter(Boolean).join("-");
    if (!name || name.length > 512 || !/^[A-Z0-9._-]+$/.test(name)) {
      throw new Error("invalid_generated_action_name");
    }
    return name;
  }

  function appendMapSelectedAction(selections, currentActionId, actions = []) {
    const selected = Array.isArray(selections)
      ? selections
          .map((item) => ({
            id: String(item?.id || ""),
            type: String(item?.type || "").toUpperCase(),
          }))
          .filter((item) => item.id)
      : [];
    const id = String(currentActionId || "");
    const action = actions.find((item) => String(item?.id || "") === id);
    if (
      !id ||
      selected.some((item) => item.id === id) ||
      !action
    ) return selected;
    return [...selected, { id, type: suggestInspectionType(action) }];
  }

  function actionNameOverlayLabels(actions) {
    const labels = [];
    for (const action of Array.isArray(actions) ? actions : []) {
      const id = String(action?.id || "");
      const name = String(action?.name || "").trim();
      const sourcePosition = action?.position;
      const position = Number.isFinite(sourcePosition?.x) && Number.isFinite(sourcePosition?.y)
        ? {
            x: sourcePosition.x,
            y: sourcePosition.y,
            z: Number.isFinite(sourcePosition.z) ? sourcePosition.z : 0,
          }
        : null;
      if (!id || !name || !position) continue;
      labels.push({
        id,
        name,
        position,
      });
    }
    return labels;
  }

  function planSelectedActionNames(snapshot, selections, options = {}) {
    const { hierarchy, startSequence, sequenceWidth } =
      normalizeActionNamingOptions(options);
    const selectedActions = Array.isArray(selections)
      ? selections.map((item) => ({
          id: String(item?.id || ""),
          type: String(item?.type || "").toUpperCase(),
        })).filter((item) => item.id)
      : [];
    if (!selectedActions.length) throw new Error("no_selected_actions");
    if (new Set(selectedActions.map((item) => item.id)).size !== selectedActions.length) {
      throw new Error("duplicate_action_id");
    }
    const selectedActionIds = selectedActions.map((item) => item.id);

    const actions = Array.isArray(snapshot?.actions) ? snapshot.actions : [];
    const actionsById = new Map(
      actions.map((action) => [String(action?.id || ""), action]),
    );
    if (selectedActionIds.some((id) => !actionsById.has(id))) {
      throw new Error("selected_action_not_found");
    }

    const updates = [];
    const unchanged = [];
    const items = [];
    const unsupported = [];
    const desiredNameOwners = new Map();
    const conflicts = [];
    let nextSequence = startSequence;
    const maxSequence = 10 ** sequenceWidth - 1;

    for (const selection of selectedActions) {
      const { id, type } = selection;
      const action = actionsById.get(id);
      const observedName = String(action?.name || "").trim();
      const waypointIds = [...new Set(action?.waypointIds || [])].filter(Boolean);
      if (nextSequence > maxSequence) throw new Error("action_sequence_range_overflow");
      const sequence = String(nextSequence).padStart(sequenceWidth, "0");
      nextSequence += 1;
      if (!ACTION_NAME_SUFFIX_SET.has(type) || waypointIds.length !== 1) {
        unsupported.push({
          id,
          waypointId: waypointIds.length === 1 ? waypointIds[0] : "",
          observedName,
          sequence,
          reason: waypointIds.length !== 1
            ? "action_waypoint_unavailable"
            : "inspection_type_required",
        });
        continue;
      }
      const waypointId = waypointIds[0];
      const desiredName = buildActionName(hierarchy, sequence, type);
      const previousOwner = desiredNameOwners.get(desiredName);
      if (previousOwner && previousOwner !== id) {
        conflicts.push({
          id,
          waypointId,
          desiredName,
          reason: "duplicate_planned_action_name",
        });
        continue;
      }
      desiredNameOwners.set(desiredName, id);
      const item = { id, waypointId, observedName, desiredName, type, sequence };
      items.push(item);
      if (observedName === desiredName) unchanged.push(item);
      else updates.push(item);
    }

    const plannedIds = new Set([...updates, ...unchanged].map((item) => item.id));
    for (const action of actions) {
      const id = String(action?.id || "");
      const name = String(action?.name || "").trim();
      const plannedOwner = desiredNameOwners.get(name);
      if (plannedOwner && !plannedIds.has(id)) {
        conflicts.push({
          id: plannedOwner,
          conflictingId: id,
          desiredName: name,
          reason: "existing_action_name_collision",
        });
      }
    }

    return {
      schema: "orbit_action_name_plan_v2",
      hierarchy,
      startSequence,
      sequenceWidth,
      nextSequence,
      selections: selectedActions,
      selectedActionIds,
      updates,
      unchanged,
      items,
      unsupported,
      conflicts,
      canApply: Boolean(
        updates.length &&
        !unsupported.length &&
        !conflicts.length
      ),
    };
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
    ACTION_NAME_SUFFIXES,
    actionNameOverlayLabels,
    appendMapSelectedAction,
    BUILTIN_PRESETS,
    SETTING_FIELDS,
    explicitInspectionType,
    makePreset,
    parseConnectQueue,
    parseActionSequence,
    parsePresetLibrary,
    planSelectedActionNames,
    presetLibrary,
    suggestInspectionType,
    sanitizeSettings,
  });
})();
