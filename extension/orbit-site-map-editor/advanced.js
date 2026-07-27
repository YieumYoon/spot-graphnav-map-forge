(() => {
  "use strict";

  const runtime = globalThis.OrbitSiteMapEditorRuntime;
  const select = globalThis.OrbitSiteMapEditorSelection;
  const validate = globalThis.OrbitSiteMapEditorValidation;
  const workflow = globalThis.OrbitSiteMapEditorWorkflow;
  const extensionContext = globalThis.OrbitSiteMapEditorExtensionContext;
  const workspacePanes = [
    globalThis.OrbitSiteMapEditorSelectWorkspace,
    globalThis.OrbitSiteMapEditorActionNamesWorkspace,
    globalThis.OrbitSiteMapEditorEditWorkspace,
    globalThis.OrbitSiteMapEditorValidateWorkspace,
  ];
  if (
    !runtime ||
    !select ||
    !validate ||
    !workflow ||
    !extensionContext ||
    workspacePanes.some((pane) => !pane?.render || !Array.isArray(pane.selectors))
  ) return;
  if (
    !runtime.instanceId ||
    !runtime.disposeEvent ||
    !runtime.instanceEvents?.addSelection ||
    !runtime.instanceEvents?.actionSelection ||
    !runtime.instanceEvents?.snapshot
  ) return;
  if (runtime.isDisposed?.() || !extensionContext.isActive()) return;

  const STORAGE_PREFIX = "orbitSiteMapEditorWorkspaceV1:";
  const state = {
    tab: "explore",
    selection: select.normalize(),
    selectionMode: "replace",
    namedSets: [],
    findings: [],
    queryResults: [],
    pending: null,
    actionNamePlan: null,
    actionNamePlanError: "",
    actionNameSelections: [],
    actionNameAddMode: false,
    actionNameLabelsVisible: true,
    actionNameOverlayLabels: [],
    copiedSettings: null,
    copiedSettingsName: "",
    presets: [...workflow.BUILTIN_PRESETS],
    connectQueue: [],
    path: null,
    reachability: [],
    crosswalks: [],
    overlayRevision: 0,
    workspaceMapId: "",
  };
  let workspaceLoadGeneration = 0;
  let workspaceLoadingMapId = "";
  let tabSelectionRevision = 0;
  const actionNameRowsById = new Map();

  const root = runtime.elements.panel;
  if (!root || root.dataset.osmeAdvancedInstance === runtime.instanceId) return;
  root.dataset.osmeAdvancedInstance = runtime.instanceId;
  const lifecycleController = new AbortController();
  const lifecycleSignal = lifecycleController.signal;
  let removeInvalidationListener = () => {};
  function disposeAdvanced(event) {
    if (event?.detail?.instanceId === runtime.instanceId) return;
    lifecycleController.abort();
    removeInvalidationListener();
  }
  window.addEventListener(runtime.disposeEvent, disposeAdvanced, {
    signal: lifecycleSignal,
  });
  removeInvalidationListener = extensionContext.onInvalidated(disposeAdvanced);
  const originalSections = [...root.querySelectorAll(":scope > .osme-section")];
  const nav = document.createElement("nav");
  nav.className = "osme-tabs";
  nav.setAttribute("aria-label", "Editor workflows");
  for (const [id, label] of [
    ["explore", "Explore"],
    ["select", "Select"],
    ["action-names", "Action Names"],
    ["edit", "Edit"],
    ["validate", "Validate"],
  ]) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.tab = id;
    button.textContent = label;
    nav.append(button);
  }
  runtime.elements.summary.after(nav);

  originalSections[0]?.setAttribute("data-workspace-tab", "explore");
  originalSections[1]?.setAttribute("data-workspace-tab", "explore");
  originalSections[2]?.setAttribute("data-workspace-tab", "edit");
  originalSections[3]?.setAttribute("data-workspace-tab", "explore");

  const workspace = document.createElement("div");
  workspace.className = "osme-workspace";
  workspace.innerHTML = workspacePanes.map((pane) => pane.render()).join("");
  root.querySelector(".osme-footer").before(workspace);

  const el = {};
  for (const className of workspacePanes.flatMap((pane) => pane.selectors)) {
    el[className.replaceAll("-", "_")] = workspace.querySelector(`.osme-${className}`);
  }

  function create(tag, className = "", value = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== "") node.textContent = String(value);
    return node;
  }

  function snapshot() {
    return runtime.state.snapshot || {
      map: { id: runtime.currentMapId(), name: "" },
      waypoints: [],
      edges: [],
      areas: [],
      docks: [],
      fiducials: [],
      actions: [],
      selectedWaypointIds: [],
      selectedEdgeIds: [],
    };
  }

  function currentMapKey(mapId = state.workspaceMapId || runtime.currentMapId()) {
    return `${STORAGE_PREFIX}${mapId}`;
  }

  function storageGet(key) {
    return extensionContext.storageGet([key]);
  }

  function storageSet(value) {
    return extensionContext.storageSet(value);
  }

  function persist() {
    if (
      lifecycleSignal.aborted ||
      runtime.isDisposed?.() ||
      !state.workspaceMapId ||
      snapshot().map.id && snapshot().map.id !== state.workspaceMapId
    ) return false;
    const key = currentMapKey(state.workspaceMapId);
    return storageSet({
      [key]: {
        tab: state.tab,
        actionNameLabelsVisible: state.actionNameLabelsVisible,
        selection: state.selection,
        namedSets: state.namedSets,
        presets: state.presets.filter(
          (preset) => !workflow.BUILTIN_PRESETS.some((builtin) => builtin.id === preset.id),
        ),
        connectQueue: state.connectQueue,
      },
    });
  }

  function message(value, kind = "neutral") {
    runtime.setStatus(value, kind);
  }

  function edgeBySelectionId(id) {
    return (snapshot().edges || []).find(
      (edge) => edge.id === id || runtime.model.edgeKey(edge.from, edge.to) === id,
    );
  }

  function selectedEdges() {
    return state.selection.edgeIds.map(edgeBySelectionId).filter(Boolean);
  }

  function actionById(id) {
    return (snapshot().actions || []).find((action) => action.id === id);
  }

  function applyIncoming(incoming) {
    state.selection = select.combine(state.selection, incoming, state.selectionMode);
    persist();
    renderAdvanced();
  }

  function nativeSelect(focus = false) {
    return runtime.requestBridge("select_entities", {
      waypointIds: state.selection.waypointIds,
      edgeIds: state.selection.edgeIds,
      focus,
    }).then((response) => {
      message(
        `Selected ${response.waypointCount ?? 0} waypoints and ` +
        `${response.edgeCount ?? 0} edges in Orbit.`,
        "ok",
      );
      return runtime.refreshSnapshot({ quiet: true, allowBusy: true });
    }).catch((error) => message(runtime.friendlyError(error.message), "error"));
  }

  function selectedRecordingId() {
    const ids = new Set(
      snapshot().waypoints
        .filter((waypoint) => state.selection.waypointIds.includes(waypoint.id))
        .map((waypoint) => waypoint.recordingId)
        .filter(Boolean),
    );
    return ids.size === 1 ? [...ids][0] : "";
  }

  function viewportBounds() {
    const canvas = document.querySelector("canvas");
    const params = new URL(location.href).searchParams;
    const x = Number(params.get("x"));
    const y = Number(params.get("y"));
    const zoom = Number(params.get("zoom"));
    if (!canvas || ![x, y, zoom].every(Number.isFinite) || zoom <= 0) return null;
    const rect = canvas.getBoundingClientRect();
    const width = 10 / zoom;
    const height = width * (rect.height / rect.width);
    return { x1: x - width / 2, x2: x + width / 2, y1: y - height / 2, y2: y + height / 2 };
  }

  function parseRectangle(value) {
    const values = String(value || "").split(/[\s,]+/).map(Number);
    if (values.length !== 4 || !values.every(Number.isFinite)) {
      throw new Error("Rectangle requires x1,y1,x2,y2.");
    }
    return { x1: values[0], y1: values[1], x2: values[2], y2: values[3] };
  }

  function parsePolygon(value) {
    const points = String(value || "").trim().split(/\r?\n/).filter(Boolean).map((line) => {
      const values = line.trim().split(/[\s,]+/).map(Number);
      if (values.length !== 2 || !values.every(Number.isFinite)) {
        throw new Error("Each polygon point must be x,y.");
      }
      return { x: values[0], y: values[1] };
    });
    if (points.length < 3) throw new Error("Polygon requires at least three points.");
    return points;
  }

  function setTab(tab, { userInitiated = false } = {}) {
    const changed = state.tab !== tab;
    if (state.tab === "action-names" && tab !== "action-names") {
      state.actionNameAddMode = false;
    }
    state.tab = tab;
    if (changed) state.overlayRevision += 1;
    if (userInitiated) tabSelectionRevision += 1;
    for (const button of nav.querySelectorAll("[data-tab]")) {
      button.dataset.active = String(button.dataset.tab === tab);
    }
    for (const pane of root.querySelectorAll("[data-workspace-tab]")) {
      pane.hidden = pane.dataset.workspaceTab !== tab;
    }
    if (changed) persist();
  }

  function renderSelection() {
    el.selection_count.textContent =
      `${state.selection.waypointIds.length} W · ${state.selection.edgeIds.length} E`;
    el.selection_mode.value = state.selectionMode;
    el.selection_summary.replaceChildren();
    const ids = [
      ...state.selection.waypointIds.map((id) => `W ${runtime.model.shortId(id, 7)}`),
      ...state.selection.edgeIds.map((id) => `E ${runtime.model.shortId(id, 7)}`),
    ];
    el.selection_summary.append(
      create(
        "p",
        "osme-empty",
        ids.length ? ids.slice(0, 24).join(" · ") : "No work selection.",
      ),
    );
    if (ids.length > 24) {
      el.selection_summary.append(create("small", "", `+${ids.length - 24} more exact IDs`));
    }
    el.named_sets.replaceChildren();
    for (const [index, named] of state.namedSets.entries()) {
      const row = create("div", "osme-list-row");
      row.append(
        create("strong", "", named.name),
        create(
          "small",
          "",
          `${named.selection.waypointIds.length} W · ${named.selection.edgeIds.length} E`,
        ),
      );
      const use = create("button", "osme-button osme-small", "Apply");
      use.dataset.index = String(index);
      use.dataset.action = "use-set";
      const remove = create("button", "osme-button osme-small", "Delete");
      remove.dataset.index = String(index);
      remove.dataset.action = "delete-set";
      row.append(use, remove);
      el.named_sets.append(row);
    }
  }

  function renderQuery() {
    el.query_summary.replaceChildren(
      create(
        "p",
        "osme-empty",
        state.queryResults.length
          ? `${state.queryResults.length} matching live objects; use ${state.selectionMode}.`
          : "Predicates: type, id, name, recording, source, degree, status, setting.",
      ),
    );
  }

  function renderPresets() {
    const selected = el.preset_list.value;
    el.preset_list.replaceChildren();
    for (const preset of state.presets) {
      const option = create("option", "", preset.name);
      option.value = preset.id;
      el.preset_list.append(option);
    }
    if (state.presets.some((preset) => preset.id === selected)) {
      el.preset_list.value = selected;
    }
    el.settings_clipboard.replaceChildren(
      create(
        "p",
        "osme-empty",
        state.copiedSettings
          ? `${state.copiedSettingsName}: ${Object.keys(state.copiedSettings).join(", ") || "default"}`
          : "Copy one selected edge or choose a preset.",
      ),
    );
    const matrix = validate.settingsMatrix(selectedEdges());
    el.settings_matrix.replaceChildren();
    if (matrix.length) {
      const table = create("table", "osme-results-table");
      const body = create("tbody");
      for (const row of matrix) {
        const tr = create("tr");
        tr.append(
          create("td", "", row.field),
          create("td", row.mixed ? "osme-warning-text" : "", row.mixed ? "mixed" : "same"),
          create("td", "", row.values.map((value) => `${value.count}× ${JSON.stringify(value.value)}`).join(" · ")),
        );
        body.append(tr);
      }
      table.append(body);
      el.settings_matrix.append(table);
    }
  }

  function actionNamingOptions() {
    const sequence = workflow.parseActionSequence(el.action_name_first_number.value);
    return {
      enterprise: el.action_name_enterprise.value,
      site: el.action_name_site.value,
      area: el.action_name_area.value,
      workCenter: el.action_name_work_center.value,
      equipment: el.action_name_equipment.value,
      startSequence: sequence.startSequence,
      sequenceWidth: sequence.sequenceWidth,
    };
  }

  function isActionAddModeShortcut(event) {
    return Boolean(
      event.code === "KeyA" &&
      !event.ctrlKey &&
      !event.altKey &&
      !event.shiftKey &&
      !event.metaKey &&
      !event.repeat &&
      !event.isComposing &&
      !event.defaultPrevented
    );
  }

  function isTextEntryTarget(target) {
    return Boolean(target?.closest?.(
      "input, textarea, select, [contenteditable]:not([contenteditable='false'])",
    ));
  }

  function toggleActionAddMode() {
    state.actionNameAddMode = !state.actionNameAddMode;
    renderActionNamePicker();
    message(state.actionNameAddMode ? "Add Actions mode enabled." : "Normal mode enabled.");
  }

  function updateActionNamePlan() {
    state.actionNamePlan = null;
    state.actionNamePlanError = "";
    if (!state.actionNameSelections.length) return;
    try {
      state.actionNamePlan = workflow.planSelectedActionNames(
        snapshot(),
        state.actionNameSelections,
        actionNamingOptions(),
      );
    } catch (error) {
      state.actionNamePlanError = runtime.friendlyError(error.message);
    }
  }

  function createActionNameRow(id) {
    const row = create("div", "osme-action-choice");
    row.dataset.actionNameRowId = id;
    const indexLabel = create("strong");
    const name = create("span");
    const type = create("select", "osme-field osme-action-name-type");
    type.dataset.actionNameTypeId = id;
    const choose = create("option", "", "Choose type");
    choose.value = "";
    type.append(choose);
    for (const value of workflow.ACTION_NAME_SUFFIXES) {
      const option = create("option", "", value);
      option.value = value;
      type.append(option);
    }
    const remove = create("button", "osme-icon-button", "×");
    remove.type = "button";
    remove.dataset.actionNameRemoveId = id;
    row.append(indexLabel, name, type, remove);
    return { row, indexLabel, name, type, remove };
  }

  function renderActionNamePicker() {
    const liveSnapshot = snapshot();
    const actions = liveSnapshot.actions || [];
    const selections = state.actionNameSelections.map((selection) => ({
      ...selection,
      action: actionById(selection.id),
    }));
    const current = actionById(liveSnapshot.currentActionId);
    state.actionNameOverlayLabels = workflow.actionNameOverlayLabels(actions);
    el.action_name_shortcut.textContent = "Shortcut: A";
    el.action_name_label_toggle.checked = state.actionNameLabelsVisible;
    el.action_name_label_status.textContent = state.actionNameLabelsVisible
      ? `${state.actionNameOverlayLabels.length} of ${actions.length} Actions have map positions.`
      : "Action name projection is off.";
    for (const button of el.action_name_mode.querySelectorAll(
      "[data-action-name-add-mode]",
    )) {
      const active = String(state.actionNameAddMode) === button.dataset.actionNameAddMode;
      button.dataset.active = String(active);
      button.setAttribute("aria-pressed", String(active));
    }
    el.action_name_map_selection_status.replaceChildren(
      create(
        "small",
        "",
        state.actionNameAddMode
          ? "Add Actions mode — map clicks append Actions in sequence order."
          : "Normal mode — map clicks do not change this list.",
      ),
      ...(current
        ? [create("small", "", `Current Action: ${current.name || runtime.model.shortId(current.id)}`)]
        : []),
    );
    el.action_name_selection_summary.replaceChildren(
      create(
        "p",
        state.actionNameSelections.length ? "osme-ok-text" : "osme-empty",
        `${state.actionNameSelections.length} selected`,
      ),
    );
    const selectedIds = new Set();
    let cursor = el.action_name_action_list.firstElementChild;
    for (const [index, selection] of selections.entries()) {
      selectedIds.add(selection.id);
      let entry = actionNameRowsById.get(selection.id);
      if (!entry) {
        entry = createActionNameRow(selection.id);
        actionNameRowsById.set(selection.id, entry);
      }
      entry.indexLabel.textContent = `#${index + 1}`;
      entry.name.textContent = selection.action?.name || "Unavailable Action";
      entry.type.setAttribute("aria-label", `Inspection type for Action ${index + 1}`);
      entry.remove.setAttribute("aria-label", `Remove Action ${index + 1}`);
      if (document.activeElement !== entry.type && entry.type.value !== selection.type) {
        entry.type.value = selection.type;
      }
      if (entry.row !== cursor) {
        el.action_name_action_list.insertBefore(entry.row, cursor);
      }
      cursor = entry.row.nextElementSibling;
    }
    for (const [id, entry] of actionNameRowsById) {
      if (selectedIds.has(id)) continue;
      entry.row.remove();
      actionNameRowsById.delete(id);
    }
    if (!selections.length) {
      let empty = el.action_name_action_list.querySelector(":scope > .osme-empty");
      if (!empty) {
        empty = create("p", "osme-empty", "No Actions selected.");
        el.action_name_action_list.append(empty);
      }
    } else {
      el.action_name_action_list.querySelector(":scope > .osme-empty")?.remove();
    }
  }

  function captureMapActionSelection(actionId = snapshot().currentActionId) {
    if (!state.actionNameAddMode || state.tab !== "action-names") return false;
    const next = workflow.appendMapSelectedAction(
      state.actionNameSelections,
      actionId,
      snapshot().actions,
    );
    if (next.length === state.actionNameSelections.length) return false;
    state.actionNameSelections = next;
    state.overlayRevision += 1;
    setPending(null);
    updateActionNamePlan();
    return true;
  }

  function renderActionNamePlan() {
    const plan = state.actionNamePlan;
    el.action_name_summary.replaceChildren();
    el.action_name_preview.replaceChildren();
    el.review_action_names.disabled = true;
    if (state.actionNamePlanError) {
      el.action_name_summary.append(
        create("p", "osme-warning-text", state.actionNamePlanError),
      );
      return;
    }
    if (!plan) {
      el.action_name_summary.append(
        create("p", "osme-empty", "Select Actions to build the preview."),
      );
      return;
    }
    const issues = plan.unsupported.length + plan.conflicts.length;
    el.action_name_summary.append(
      create(
        "p",
        issues ? "osme-warning-text" : "osme-ok-text",
        `${plan.selectedActionIds.length} selected · ${plan.updates.length} to rename · ` +
          `${plan.unchanged.length} unchanged · ${issues} issue${issues === 1 ? "" : "s"}`,
      ),
    );
    for (const item of plan.items.slice(0, 200)) {
      const row = create("div", "osme-list-row osme-action-name-row");
      const names = create("div");
      names.append(
        create("small", "", item.observedName || "(unnamed)"),
        create("code", "", item.desiredName),
      );
      row.append(create("strong", "", item.sequence), names);
      el.action_name_preview.append(row);
    }
    if (plan.items.length > 200) {
      el.action_name_preview.append(
        create("small", "", `+${plan.items.length - 200} more`),
      );
    }
    for (const item of plan.unsupported.slice(0, 30)) {
      el.action_name_preview.append(
        create(
          "div",
          "osme-list-row osme-warning-text",
          item.reason === "inspection_type_required"
            ? `Choose an inspection type: ${item.observedName || "Unnamed Action"}`
            : `Action waypoint unavailable: ${item.observedName || "Unnamed Action"}`,
        ),
      );
    }
    if (plan.conflicts.length) {
      el.action_name_preview.append(
        create(
          "div",
          "osme-list-row osme-error",
          `${plan.conflicts.length} name collision${plan.conflicts.length === 1 ? "" : "s"}.`,
        ),
      );
    }
    el.review_action_names.disabled = !plan.canApply;
  }

  function setPending(pending) {
    state.pending = pending;
    renderMutation();
  }

  function renderMutation() {
    const mutationLocked = Boolean(runtime.state.mutationUncertain);
    el.confirm_mutation.disabled = mutationLocked;
    el.confirm_action_name_mutation.disabled = mutationLocked;
    const actionMutation = state.pending?.type === "rename_actions";
    el.mutation_review.hidden = !state.pending || actionMutation;
    el.action_name_mutation_review.hidden = !actionMutation;
    el.mutation_detail.replaceChildren();
    el.action_name_mutation_detail.replaceChildren();
    if (!state.pending) return;
    const title = actionMutation
      ? el.action_name_mutation_title
      : el.mutation_title;
    const detail = actionMutation
      ? el.action_name_mutation_detail
      : el.mutation_detail;
    title.textContent = state.pending.title;
    detail.append(
      create("p", "", state.pending.detail),
      create("code", "", `Site Map ${snapshot().map.id}`),
      ...(state.pending.type === "rename_actions"
        ? []
        : [create("small", "", `Observed edit revision ${snapshot().editIndex ?? "—"}`)]),
    );
  }

  function reviewActionNames() {
    updateActionNamePlan();
    const plan = state.actionNamePlan;
    renderActionNamePlan();
    if (!plan?.canApply) {
      message(state.actionNamePlanError || "Fix the listed issues first.", "warning");
      return;
    }
    setPending({
      type: "rename_actions",
      title: `Rename ${plan.updates.length} selected Action${plan.updates.length === 1 ? "" : "s"}?`,
      detail: "Orbit will keep the renames unsaved so they can be reviewed or undone.",
      actionNameUpdates: plan.updates,
      actionNameSelections: plan.selections,
      observedActionEditIndex: snapshot().actionEditIndex,
    });
  }

  function previewArchive(edges = selectedEdges()) {
    if (!edges.length) {
      message("Select at least one active edge.", "warning");
      return;
    }
    setPending({
      type: "archive",
      title: `Archive ${edges.length} exact edge${edges.length === 1 ? "" : "s"}?`,
      detail:
        "Orbit will create one unsaved Archive change. Review the highlighted selection first.",
      edges,
      observedEditIndex: snapshot().editIndex,
    });
  }

  function previewSettings(edges = selectedEdges(), settings = state.copiedSettings) {
    if (!edges.length || !settings) {
      message("Select target edges and copy settings or choose a preset.", "warning");
      return;
    }
    const desiredByEdge = edges.map((edge) => ({
      edge,
      settings: { ...(edge.settings || {}), ...settings },
    }));
    setPending({
      type: "update_settings",
      title: `Update settings on ${edges.length} exact edge${edges.length === 1 ? "" : "s"}?`,
      detail:
        `Fields: ${Object.keys(settings).join(", ") || "default"}. ` +
        "Orbit will create one unsaved settings change.",
      desiredByEdge,
      observedEditIndex: snapshot().editIndex,
    });
  }

  function previewConnect(pair, queueIndex = -1) {
    const [from, to] = pair;
    const graph = runtime.graph();
    if (!graph.waypointById.has(from) || !graph.waypointById.has(to)) {
      message("Connect queue contains a waypoint outside this Site Map.", "error");
      return;
    }
    if (graph.edgeByKey.has(runtime.model.edgeKey(from, to))) {
      message("This endpoint pair is already connected.", "warning");
      return;
    }
    setPending({
      type: "connect",
      title: "Connect this exact waypoint pair?",
      detail: `${from} ↔ ${to}. Orbit validates the pair before creating an unsaved change.`,
      pair,
      queueIndex,
      observedEditIndex: snapshot().editIndex,
    });
  }

  async function executePending() {
    const pending = state.pending;
    if (!pending) return;
    if (runtime.state.mutationUncertain) {
      message(
        "A previous edit is still unverified. Inspect or restore Orbit, then clear the lock in Edit before another edit.",
        "error",
      );
      renderAdvanced();
      return;
    }
    const actionSelectionChanged = pending.type === "rename_actions" &&
      JSON.stringify(pending.actionNameSelections) !==
        JSON.stringify(state.actionNameSelections);
    const draftChanged = pending.type === "rename_actions"
      ? pending.observedActionEditIndex !== snapshot().actionEditIndex
      : pending.observedEditIndex !== snapshot().editIndex;
    if (draftChanged || actionSelectionChanged || snapshot().map.id !== runtime.currentMapId()) {
      message("The Site Map or unsaved edit state changed; review the operation again.", "error");
      setPending(null);
      return;
    }
    el.confirm_mutation.disabled = true;
    el.confirm_action_name_mutation.disabled = true;
    try {
      let response;
      if (pending.type === "rename_actions") {
        response = await runtime.requestBridge("rename_actions", {
          actionNameUpdates: pending.actionNameUpdates,
        }, 18000);
      } else if (pending.type === "archive") {
        response = await runtime.requestBridge("archive_edges", {
          waypointPairs: pending.edges.map((edge) => [edge.from, edge.to]),
        }, 18000);
      } else if (pending.type === "update_settings") {
        response = await runtime.requestBridge("update_edge_settings", {
          settingsUpdates: pending.desiredByEdge.map(({ edge, settings }) => ({
            waypointIds: [edge.from, edge.to],
            storedFrom: edge.from,
            storedTo: edge.to,
            observedSourceValue: edge.sourceValue,
            observedSettings: edge.settings || {},
            desiredSettings: settings,
          })),
        }, 18000);
      } else {
        response = await runtime.requestBridge("connect", {
          waypointIds: pending.pair,
        }, 18000);
        if (pending.queueIndex >= 0 && state.connectQueue[pending.queueIndex]) {
          state.connectQueue[pending.queueIndex].status = "drafted";
        }
      }
      message(
        pending.type === "rename_actions"
          ? "Renames applied as one unsaved Orbit change. Review them, then Save or Undo in Orbit."
          : `Orbit created one unsaved ${pending.type} change. ` +
            "Review it, then use Orbit Save or one Undo.",
        "ok",
      );
      state.pending = null;
      if (pending.type === "rename_actions") {
        state.actionNameSelections = [];
        state.actionNamePlan = null;
        state.actionNamePlanError = "";
        state.actionNameAddMode = false;
      }
      await runtime.refreshSnapshot({ quiet: true, allowBusy: true });
    } catch (error) {
      if (error.mutationMayExist) {
        if (pending.queueIndex >= 0 && state.connectQueue[pending.queueIndex]) {
          state.connectQueue[pending.queueIndex].status = "unverified draft";
        }
        state.pending = null;
        await runtime.refreshSnapshot({ quiet: true, allowBusy: true });
        message(
          `${runtime.friendlyError(error.message)}. Orbit may contain an unverified unsaved change; ` +
          runtime.unverifiedMutationGuidance(error),
          "error",
        );
      } else {
        message(`${runtime.friendlyError(error.message)}. No mutation was verified.`, "error");
      }
    } finally {
      el.confirm_mutation.disabled = false;
      renderAdvanced();
    }
  }

  function renderQueue() {
    el.connect_queue.replaceChildren();
    for (const [index, item] of state.connectQueue.entries()) {
      const row = create("div", "osme-list-row");
      row.append(
        create("code", "", `${runtime.model.shortId(item.waypointIds[0], 7)} ↔ ${runtime.model.shortId(item.waypointIds[1], 7)}`),
        create("small", "", item.status),
      );
      for (const [action, label] of [
        ["focus", "Focus"],
        ["validate", "Validate"],
        ["draft", "Review"],
      ]) {
        const button = create("button", "osme-button osme-small", label);
        button.dataset.action = action;
        button.dataset.index = String(index);
        row.append(button);
      }
      el.connect_queue.append(row);
    }
  }

  function renderFindings() {
    const counts = { error: 0, warning: 0, info: 0 };
    for (const item of state.findings) counts[item.severity] += 1;
    el.validation_summary.replaceChildren(
      create(
        "p",
        "osme-empty",
        `${counts.error} errors · ${counts.warning} warnings · ${counts.info} info`,
      ),
    );
    el.findings.replaceChildren();
    for (const [index, item] of state.findings.slice(0, 300).entries()) {
      const card = create("article", "osme-finding");
      card.dataset.severity = item.severity;
      card.append(
        create("span", "osme-kind", item.severity),
        create("strong", "", item.title),
        create("p", "", item.explanation),
        create(
          "small",
          "",
          `${item.waypointIds.length} waypoints · ${item.edgeIds.length} edges`,
        ),
      );
      const actions = create("div", "osme-toolbar");
      for (const [action, label] of [
        ["focus", "Focus"],
        ["add", "Add selection"],
        ["copy", "Copy IDs"],
        ["explain", "Explain"],
      ]) {
        const button = create("button", "osme-button osme-small", label);
        button.dataset.action = action;
        button.dataset.index = String(index);
        actions.append(button);
      }
      card.append(actions);
      el.findings.append(card);
    }
  }

  function renderPath() {
    el.path_result.replaceChildren();
    if (!state.path) return;
    el.path_result.append(
      create(
        "p",
        state.path.reachable ? "osme-ok-text" : "osme-error",
        state.path.reachable
          ? `${state.path.edgeCount} edges · ${runtime.model.formatDistance(state.path.totalLength)}`
          : "No active path.",
      ),
    );
    for (const row of state.path.settings || []) {
      el.path_result.append(
        create("small", row.mixed ? "osme-warning-text" : "", `${row.field}: ${row.mixed ? "mixed" : "consistent"}`),
      );
    }
  }

  function renderReachability() {
    el.reachability.replaceChildren();
    for (const item of state.reachability) {
      const row = create("div", "osme-list-row");
      row.append(
        create("span", item.reachable ? "osme-ok-text" : "osme-error", item.reachable ? "reachable" : "unreachable"),
        create("strong", "", item.name || runtime.model.shortId(item.id)),
        create("code", "", item.id),
      );
      el.reachability.append(row);
    }
  }

  function renderCrosswalks() {
    el.crosswalks.replaceChildren();
    for (const item of state.crosswalks) {
      const row = create("div", "osme-list-row");
      row.append(
        create("strong", "", item.areaName || runtime.model.shortId(item.areaId)),
        create("code", "", item.edgeId),
        create("small", item.areaPresent ? "" : "osme-error", item.areaPresent ? item.description || "callback" : "missing Area"),
      );
      el.crosswalks.append(row);
    }
    if (!state.crosswalks.length) {
      el.crosswalks.append(create("p", "osme-empty", "No spot-crosswalk callbacks found."));
    }
  }

  function renderUncertaintyRecovery() {
    el.uncertainty_recovery.replaceChildren();
    const uncertain = runtime.state.mutationUncertain;
    if (!uncertain) return;
    const context = uncertain.mutationContext || {};
    const warning = create("div", "osme-card osme-error");
    warning.append(
      create("strong", "", "Edit result is unverified"),
      create(
        "p",
        "",
        `${uncertain.command || "edit"} · Draft index ` +
        `${context.beforeEditIndex ?? "?"}→${context.afterEditIndex ?? "?"} · ` +
        `Undo depth ${context.beforeUndoDepth ?? "?"}→${context.afterUndoDepth ?? "?"} · ` +
        `${context.targetKeys?.length || 0} targets`,
      ),
      create(
        "small",
        "",
        "Do not Save. Inspect the exact target and Orbit history. Undo only if this change is the newest Undo step; otherwise reload Orbit or restore the backup.",
      ),
    );
    const acknowledge = create(
      "button",
      "osme-button osme-acknowledge-uncertain",
      "Clear lock after inspection / restore",
    );
    acknowledge.type = "button";
    warning.append(acknowledge);
    el.uncertainty_recovery.append(warning);
  }

  function renderAdvanced() {
    state.overlayRevision += 1;
    updateActionNamePlan();
    renderSelection();
    renderQuery();
    renderActionNamePicker();
    renderActionNamePlan();
    renderPresets();
    renderMutation();
    renderQueue();
    renderFindings();
    renderPath();
    renderReachability();
    renderCrosswalks();
    renderUncertaintyRecovery();
    setTab(state.tab);
  }

  nav.addEventListener("click", (event) => {
    const button = event.target.closest("[data-tab]");
    if (!button) return;
    const tab = button.dataset.tab;
    setTab(tab, { userInitiated: true });
    if (tab === "action-names") renderActionNamePicker();
  });
  el.selection_mode.addEventListener("change", () => {
    state.selectionMode = el.selection_mode.value;
    renderSelection();
  });
  el.from_orbit.addEventListener("click", () => applyIncoming({
    waypointIds: snapshot().selectedWaypointIds,
    edgeIds: snapshot().selectedEdgeIds,
  }));
  el.invert.addEventListener("click", () => {
    state.selection = select.invert(snapshot(), state.selection);
    persist();
    renderAdvanced();
  });
  el.clear_selection.addEventListener("click", () => {
    state.selection = select.normalize();
    persist();
    renderAdvanced();
  });
  el.apply_selection.addEventListener("click", () => nativeSelect(true));
  el.run_query.addEventListener("click", () => {
    state.queryResults = runtime.queryEngine.querySnapshot(
      snapshot(),
      el.query_builder.value,
      { limit: 5000 },
    );
    renderQuery();
  });
  el.query_to_selection.addEventListener("click", () =>
    applyIncoming(select.fromRecords(state.queryResults))
  );
  el.neighbors.addEventListener("click", () =>
    applyIncoming(select.nHop(snapshot(), state.selection.waypointIds, 1))
  );
  el.n_hop.addEventListener("click", () => {
    const hops = Math.max(1, Math.min(1000, Math.floor(Number(el.hop_count.value) || 1)));
    el.hop_count.value = String(hops);
    applyIncoming(select.nHop(snapshot(), state.selection.waypointIds, hops));
  });
  el.select_path.addEventListener("click", () => {
    const startId = el.select_path_start.value.trim();
    const endId = el.select_path_end.value.trim();
    const path = select.shortestPath(snapshot(), startId, endId);
    if (!path.waypointIds.length) {
      message("No active path connects those exact waypoint IDs.", "warning");
      return;
    }
    applyIncoming(path);
  });
  el.component.addEventListener("click", () => {
    const id = state.selection.waypointIds[0];
    if (id) applyIncoming(select.component(snapshot(), id));
  });
  el.recording.addEventListener("click", () => {
    const id = selectedRecordingId();
    if (id) applyIncoming(select.recording(snapshot(), id));
    else message("Select waypoints from exactly one recording session.", "warning");
  });
  el.leaves.addEventListener("click", () => {
    const result = validate.topology(snapshot());
    applyIncoming({ waypointIds: result.leaves, edgeIds: [] });
  });
  el.bridges.addEventListener("click", () => {
    const graph = runtime.graph();
    const result = validate.topology(snapshot());
    applyIncoming({
      waypointIds: [...result.bridges].flatMap((key) => key.split("|")),
      edgeIds: [...result.bridges]
        .map((key) => graph.edgeByKey.get(key))
        .filter(Boolean)
        .map((edge) => edge.id),
    });
  });
  el.viewport.addEventListener("click", () => {
    const bounds = viewportBounds();
    if (bounds) applyIncoming(select.rectangle(snapshot(), bounds));
    else message("Orbit camera coordinates are not available.", "warning");
  });
  el.apply_rectangle.addEventListener("click", () => {
    try {
      applyIncoming(select.rectangle(snapshot(), parseRectangle(el.rectangle.value)));
    } catch (error) {
      message(error.message, "error");
    }
  });
  el.apply_polygon.addEventListener("click", () => {
    try {
      applyIncoming(select.polygon(snapshot(), parsePolygon(el.polygon.value)));
    } catch (error) {
      message(error.message, "error");
    }
  });
  el.save_set.addEventListener("click", () => {
    try {
      const named = select.serializeNamedSet(
        el.set_name.value,
        snapshot().map.id,
        state.selection,
      );
      const existing = state.namedSets.findIndex((item) => item.name === named.name);
      if (existing >= 0) state.namedSets[existing] = named;
      else state.namedSets.push(named);
      el.set_name.value = "";
      persist();
      renderAdvanced();
    } catch (error) {
      message(error.message, "error");
    }
  });
  el.named_sets.addEventListener("click", (event) => {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    const index = Number(button.dataset.index);
    if (button.dataset.action === "delete-set") state.namedSets.splice(index, 1);
    else applyIncoming(state.namedSets[index]?.selection || {});
    persist();
    renderAdvanced();
  });
  el.preview_archive.addEventListener("click", () => previewArchive());
  el.action_name_mode.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action-name-add-mode]");
    if (!button) return;
    const requestedMode = button.dataset.actionNameAddMode === "true";
    if (state.actionNameAddMode !== requestedMode) toggleActionAddMode();
  });
  el.action_name_builder.addEventListener("input", () => {
    setPending(null);
    updateActionNamePlan();
    renderActionNamePlan();
  });
  el.action_name_label_toggle.addEventListener("change", () => {
    state.actionNameLabelsVisible = el.action_name_label_toggle.checked;
    state.overlayRevision += 1;
    persist();
    renderActionNamePicker();
  });
  el.action_name_action_list.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action-name-remove-id]");
    if (!button) return;
    const id = button.dataset.actionNameRemoveId;
    state.actionNameSelections = state.actionNameSelections
      .filter((selection) => selection.id !== id);
    state.overlayRevision += 1;
    setPending(null);
    updateActionNamePlan();
    renderActionNamePicker();
    renderActionNamePlan();
  });
  el.action_name_action_list.addEventListener("change", (event) => {
    const selectElement = event.target.closest("select[data-action-name-type-id]");
    if (!selectElement) return;
    const selection = state.actionNameSelections.find(
      (item) => item.id === selectElement.dataset.actionNameTypeId,
    );
    if (!selection) return;
    selection.type = selectElement.value;
    setPending(null);
    updateActionNamePlan();
    renderActionNamePlan();
  });
  el.action_name_clear_selection.addEventListener("click", () => {
    state.actionNameSelections = [];
    state.overlayRevision += 1;
    state.actionNamePlan = null;
    state.actionNamePlanError = "";
    setPending(null);
    renderActionNamePicker();
    renderActionNamePlan();
  });
  el.review_action_names.addEventListener("click", reviewActionNames);
  el.copy_settings.addEventListener("click", () => {
    const edges = selectedEdges();
    if (edges.length !== 1) {
      message("Select exactly one edge to copy its settings.", "warning");
      return;
    }
    state.copiedSettings = JSON.parse(JSON.stringify(edges[0].settings || {}));
    state.copiedSettingsName = `Copied from ${runtime.model.shortId(edges[0].id)}`;
    renderPresets();
  });
  el.preview_paste.addEventListener("click", () => previewSettings());
  el.use_preset.addEventListener("click", () => {
    const preset = state.presets.find((item) => item.id === el.preset_list.value);
    if (!preset) return;
    state.copiedSettings = JSON.parse(JSON.stringify(preset.settings));
    state.copiedSettingsName = `Preset “${preset.name}”`;
    renderPresets();
  });
  el.save_preset.addEventListener("click", () => {
    if (!state.copiedSettings) {
      message("Copy edge settings or choose a preset first.", "warning");
      return;
    }
    try {
      const preset = workflow.makePreset({
        name: el.preset_name.value,
        settings: state.copiedSettings,
      });
      state.presets.push(preset);
      el.preset_name.value = "";
      persist();
      renderPresets();
    } catch (error) {
      message(error.message, "error");
    }
  });
  el.show_presets.addEventListener("click", () => {
    el.preset_json.value = JSON.stringify(workflow.presetLibrary(state.presets), null, 2);
  });
  el.import_presets.addEventListener("click", () => {
    try {
      const library = workflow.parsePresetLibrary(el.preset_json.value);
      const byId = new Map(state.presets.map((preset) => [preset.id, preset]));
      for (const preset of library.presets) byId.set(preset.id, preset);
      state.presets = [...byId.values()];
      persist();
      renderPresets();
      message(`Imported ${library.presets.length} edge-setting presets.`, "ok");
    } catch (error) {
      message(error.message, "error");
    }
  });
  el.cancel_mutation.addEventListener("click", () => setPending(null));
  el.confirm_mutation.addEventListener("click", executePending);
  el.cancel_action_name_mutation.addEventListener("click", () => setPending(null));
  el.confirm_action_name_mutation.addEventListener("click", executePending);
  el.parse_queue.addEventListener("click", () => {
    try {
      state.connectQueue = workflow.parseConnectQueue(el.queue_source.value);
      persist();
      renderQueue();
    } catch (error) {
      message(error.message, "error");
    }
  });
  el.connect_queue.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    const index = Number(button.dataset.index);
    const item = state.connectQueue[index];
    if (!item) return;
    if (button.dataset.action === "focus") {
      runtime.requestBridge("focus", { waypointIds: item.waypointIds })
        .catch((error) => message(runtime.friendlyError(error.message), "error"));
    } else if (button.dataset.action === "validate") {
      try {
        const response = await runtime.requestBridge(
          "validate_connect",
          { waypointIds: item.waypointIds },
          18000,
        );
        item.status = response.valid ? "validated" : `rejected: ${response.reason}`;
        message(
          response.valid ? "Orbit validated the queue pair; no draft was created." : item.status,
          response.valid ? "ok" : "warning",
        );
        persist();
        renderQueue();
      } catch (error) {
        item.status = error.mutationMayExist
          ? "unverified validation"
          : `rejected: ${error.message}`;
        message(
          error.mutationMayExist
            ? `${runtime.friendlyError(error.message)}. Orbit may contain an unverified unsaved change; ` +
              runtime.unverifiedMutationGuidance(error)
            : runtime.friendlyError(error.message),
          "error",
        );
        renderQueue();
      }
    } else if (button.dataset.action === "draft") {
      previewConnect(item.waypointIds, index);
    }
  });
  el.run_validation.addEventListener("click", () => {
    state.findings = validate.validateGraph(snapshot());
    renderFindings();
  });
  el.findings.addEventListener("click", (event) => {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    const item = state.findings[Number(button.dataset.index)];
    if (!item) return;
    if (button.dataset.action === "focus" && item.waypointIds.length) {
      runtime.requestBridge("focus", { waypointIds: item.waypointIds.slice(0, 5000) })
        .catch((error) => message(runtime.friendlyError(error.message), "error"));
    } else if (button.dataset.action === "add") {
      applyIncoming({ waypointIds: item.waypointIds, edgeIds: item.edgeIds });
    } else if (button.dataset.action === "copy") {
      navigator.clipboard.writeText([...item.waypointIds, ...item.edgeIds].join("\n"))
        .then(() => message("Exact finding IDs copied.", "ok"))
        .catch(() => message("Clipboard access was unavailable.", "warning"));
    } else {
      message(item.explanation, item.severity === "error" ? "error" : "warning");
    }
  });
  el.inspect_path.addEventListener("click", () => {
    state.path = validate.pathInspector(
      snapshot(),
      el.path_start.value.trim(),
      el.path_end.value.trim(),
    );
    renderPath();
  });
  el.run_reachability.addEventListener("click", () => {
    const start = state.selection.waypointIds[0];
    if (!start) {
      message("Select a start waypoint first.", "warning");
      return;
    }
    const targets = [
      ...(snapshot().docks || []).map((item) => ({ ...item, kind: "dock" })),
      ...(snapshot().actions || []).map((item) => ({ ...item, kind: "action" })),
      ...(snapshot().areas || []).map((item) => ({ ...item, kind: "area" })),
    ];
    state.reachability = validate.reachability(snapshot(), [start], targets);
    renderReachability();
  });
  el.run_crosswalk.addEventListener("click", () => {
    state.crosswalks = validate.crosswalkAudit(snapshot());
    renderCrosswalks();
  });
  el.uncertainty_recovery.addEventListener("click", (event) => {
    if (!event.target.closest(".osme-acknowledge-uncertain")) return;
    runtime.acknowledgeMutationUncertainty();
    message(
      "Unverified-edit lock cleared after operator acknowledgement. Re-check the live draft baseline before editing.",
      "warning",
    );
    renderAdvanced();
  });

  window.addEventListener(runtime.instanceEvents.addSelection, (event) => {
    applyIncoming({
      waypointIds: event.detail?.waypointIds || [],
      edgeIds: event.detail?.edgeIds || [],
    });
  }, { signal: lifecycleSignal });
  window.addEventListener(runtime.instanceEvents.mutationUncertain, () => {
    renderAdvanced();
  }, { signal: lifecycleSignal });
  window.addEventListener(runtime.instanceEvents.actionSelection, (event) => {
    if (!event.detail?.actionId || !captureMapActionSelection(event.detail.actionId)) return;
    renderActionNamePicker();
    renderActionNamePlan();
  }, { signal: lifecycleSignal });
  window.addEventListener("keydown", (event) => {
    if (
      state.tab !== "action-names" ||
      !runtime.state.panelOpen ||
      isTextEntryTarget(event.target) ||
      !isActionAddModeShortcut(event)
    ) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    toggleActionAddMode();
  }, { capture: true, signal: lifecycleSignal });
  window.addEventListener(runtime.instanceEvents.snapshot, (event) => {
    const liveMapId = String(event.detail?.mapId || snapshot().map.id || "");
    if (liveMapId && liveMapId !== state.workspaceMapId) {
      loadWorkspace(liveMapId);
      return;
    }
    state.findings = validate.validateGraph(snapshot());
    renderAdvanced();
  }, { signal: lifecycleSignal });

  globalThis.OrbitSiteMapEditorAdvanced = Object.freeze({
    overlayState: () => {
      const actionNameLabelsVisible = Boolean(
        state.tab === "action-names" &&
        runtime.state.panelOpen &&
        state.actionNameLabelsVisible
      );
      return {
        revision: state.overlayRevision,
        actionNameLabels: actionNameLabelsVisible ? state.actionNameOverlayLabels : [],
        actionNameLabelsVisible,
        selection: state.selection,
        findingWaypointIds: [...new Set(
          state.findings
            .filter((item) => item.severity !== "info")
            .flatMap((item) => item.waypointIds),
        )],
        findingEdgeIds: [...new Set(
          state.findings
            .filter((item) => item.severity !== "info")
            .flatMap((item) => item.edgeIds),
        )],
      };
    },
  });

  function resetWorkspaceState() {
    state.tab = "explore";
    state.selection = select.normalize();
    state.selectionMode = "replace";
    state.namedSets = [];
    state.findings = [];
    state.queryResults = [];
    state.pending = null;
    state.actionNamePlan = null;
    state.actionNamePlanError = "";
    state.actionNameSelections = [];
    state.actionNameAddMode = false;
    state.actionNameLabelsVisible = true;
    state.actionNameOverlayLabels = [];
    state.copiedSettings = null;
    state.copiedSettingsName = "";
    state.presets = [...workflow.BUILTIN_PRESETS];
    state.connectQueue = [];
    state.path = null;
    state.reachability = [];
    state.crosswalks = [];
    el.query_builder.value = "";
    el.queue_source.value = "";
    el.path_start.value = "";
    el.path_end.value = "";
    el.select_path_start.value = "";
    el.select_path_end.value = "";
  }

  async function loadWorkspace(mapId) {
    const normalizedMapId = String(mapId || "");
    if (!normalizedMapId || workspaceLoadingMapId === normalizedMapId) return;
    workspaceLoadingMapId = normalizedMapId;
    const generation = workspaceLoadGeneration += 1;
    const startingTabSelectionRevision = tabSelectionRevision;
    const key = currentMapKey(normalizedMapId);
    const stored = (await storageGet(key))[key] || {};
    if (
      lifecycleSignal.aborted ||
      runtime.isDisposed?.() ||
      !extensionContext.isActive() ||
      generation !== workspaceLoadGeneration
    ) {
      if (workspaceLoadingMapId === normalizedMapId) workspaceLoadingMapId = "";
      return;
    }
    const tabSelectedWhileLoading =
      tabSelectionRevision !== startingTabSelectionRevision
        ? state.tab
        : "";
    resetWorkspaceState();
    state.workspaceMapId = normalizedMapId;
    const validTabs = [
      "explore",
      "select",
      "action-names",
      "edit",
      "validate",
      "walk",
    ];
    const preserveSelectedTab = validTabs.includes(tabSelectedWhileLoading);
    state.tab = preserveSelectedTab
      ? tabSelectedWhileLoading
      : validTabs.includes(stored.tab)
        ? stored.tab
        : "explore";
    state.selection = select.normalize(stored.selection);
    state.actionNameLabelsVisible = stored.actionNameLabelsVisible !== false;
    state.namedSets = Array.isArray(stored.namedSets)
      ? stored.namedSets
          .map((item) => {
            try {
              return select.validateNamedSet(item, normalizedMapId);
            } catch {
              return null;
            }
          })
          .filter(Boolean)
      : [];
    state.presets = [
      ...workflow.BUILTIN_PRESETS,
      ...(Array.isArray(stored.presets) ? stored.presets : []),
    ];
    state.connectQueue = Array.isArray(stored.connectQueue) ? stored.connectQueue : [];
    state.findings = validate.validateGraph(snapshot());
    const current = snapshot().selectedWaypointIds || [];
    if (current.length >= 2) {
      el.path_start.value = current[0];
      el.path_end.value = current[1];
      el.select_path_start.value = current[0];
      el.select_path_end.value = current[1];
    }
    workspaceLoadingMapId = "";
    renderAdvanced();
    if (preserveSelectedTab) persist();
  }

  loadWorkspace(snapshot().map.id || runtime.currentMapId());
})();
