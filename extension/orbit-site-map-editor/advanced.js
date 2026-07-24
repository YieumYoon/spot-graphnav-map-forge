(() => {
  "use strict";

  const runtime = globalThis.OrbitSiteMapEditorRuntime;
  const select = globalThis.OrbitSiteMapEditorSelection;
  const validate = globalThis.OrbitSiteMapEditorValidation;
  const workflow = globalThis.OrbitSiteMapEditorWorkflow;
  const extensionContext = globalThis.OrbitSiteMapEditorExtensionContext;
  if (!runtime || !select || !validate || !workflow || !extensionContext) return;
  if (
    !runtime.instanceId ||
    !runtime.disposeEvent ||
    !runtime.instanceEvents?.addSelection ||
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
  workspace.innerHTML = `
    <section class="osme-section osme-advanced-pane" data-workspace-tab="select">
      <div class="osme-section-heading">
        <div><span>SELECT</span><strong>Exact-ID work selection</strong></div>
        <span class="osme-selection-count"></span>
      </div>
      <div class="osme-toolbar">
        <select class="osme-selection-mode" aria-label="Selection algebra">
          <option value="replace">Replace</option>
          <option value="add">Add</option>
          <option value="subtract">Subtract</option>
          <option value="intersect">Intersect</option>
        </select>
        <button class="osme-button osme-from-orbit" type="button">Use Orbit selection</button>
        <button class="osme-button osme-invert" type="button">Invert</button>
        <button class="osme-button osme-clear-selection" type="button">Clear</button>
        <button class="osme-button osme-primary osme-apply-selection" type="button">Select in Orbit</button>
      </div>
      <div class="osme-selection-summary"></div>
      <div class="osme-subsection">
        <strong>Query builder</strong>
        <input class="osme-field osme-query-builder" type="text"
          placeholder="type:edge source:manual recording:&lt;id&gt; setting:stairs">
        <div class="osme-toolbar">
          <button class="osme-button osme-run-query" type="button">Run query</button>
          <button class="osme-button osme-query-to-selection" type="button">Apply results</button>
        </div>
        <div class="osme-query-summary"></div>
      </div>
      <div class="osme-subsection">
        <strong>Graph & recording</strong>
        <div class="osme-toolbar">
          <button class="osme-button osme-neighbors" type="button">1-hop neighbors</button>
          <input class="osme-field osme-hop-count" type="number"
            min="1" max="1000" step="1" value="2" aria-label="N-hop radius">
          <button class="osme-button osme-n-hop" type="button">N-hop</button>
          <button class="osme-button osme-component" type="button">Component</button>
          <button class="osme-button osme-recording" type="button">Same recording</button>
          <button class="osme-button osme-leaves" type="button">Leaves</button>
          <button class="osme-button osme-bridges" type="button">Bridge edges</button>
        </div>
        <div class="osme-toolbar">
          <input class="osme-field osme-select-path-start" type="text"
            placeholder="path start waypoint ID">
          <input class="osme-field osme-select-path-end" type="text"
            placeholder="path end waypoint ID">
          <button class="osme-button osme-select-path" type="button">Shortest path</button>
        </div>
      </div>
      <div class="osme-subsection">
        <strong>Spatial selection</strong>
        <div class="osme-toolbar">
          <button class="osme-button osme-viewport" type="button">Current viewport</button>
          <input class="osme-field osme-rectangle" type="text"
            placeholder="rectangle: x1,y1,x2,y2">
          <button class="osme-button osme-apply-rectangle" type="button">Rectangle</button>
        </div>
        <textarea class="osme-field osme-polygon" rows="2"
          placeholder="polygon/lasso: one x,y point per line"></textarea>
        <button class="osme-button osme-apply-polygon" type="button">Polygon / lasso</button>
      </div>
      <div class="osme-subsection">
        <strong>Named selection sets</strong>
        <div class="osme-toolbar">
          <input class="osme-field osme-set-name" type="text" placeholder="Set name">
          <button class="osme-button osme-save-set" type="button">Save set</button>
        </div>
        <div class="osme-named-sets"></div>
      </div>
    </section>
    <section class="osme-section osme-advanced-pane" data-workspace-tab="edit">
      <div class="osme-section-heading">
        <div><span>EDIT</span><strong>Archive & edge settings</strong></div>
        <span class="osme-safety-chip">one native draft</span>
      </div>
      <div class="osme-uncertainty-recovery"></div>
      <div class="osme-toolbar">
        <button class="osme-button osme-preview-archive" type="button">Archive selected edges</button>
        <button class="osme-button osme-copy-settings" type="button">Copy settings</button>
        <button class="osme-button osme-preview-paste" type="button">Paste settings</button>
        <select class="osme-preset-list" aria-label="Edge setting preset"></select>
        <button class="osme-button osme-use-preset" type="button">Use preset</button>
      </div>
      <div class="osme-settings-clipboard"></div>
      <div class="osme-settings-matrix"></div>
      <div class="osme-subsection">
        <strong>Preset library</strong>
        <div class="osme-toolbar">
          <input class="osme-field osme-preset-name" type="text" placeholder="Preset name">
          <button class="osme-button osme-save-preset" type="button">Save copied settings</button>
          <button class="osme-button osme-show-presets" type="button">Show JSON</button>
          <button class="osme-button osme-import-presets" type="button">Import JSON</button>
        </div>
        <textarea class="osme-field osme-preset-json" rows="4"
          placeholder="Shareable preset library JSON; no Site Map data"></textarea>
      </div>
      <div class="osme-mutation-review" hidden>
        <strong class="osme-mutation-title"></strong>
        <div class="osme-mutation-detail"></div>
        <div class="osme-toolbar">
          <button class="osme-button osme-cancel-mutation" type="button">Cancel</button>
          <button class="osme-button osme-primary osme-confirm-mutation" type="button">
            Create unsaved draft
          </button>
        </div>
      </div>
      <div class="osme-subsection">
        <strong>Connect queue</strong>
        <textarea class="osme-field osme-queue-source" rows="3"
          placeholder="one exact pair per line: waypoint-id-a, waypoint-id-b"></textarea>
        <button class="osme-button osme-parse-queue" type="button">Parse queue</button>
        <div class="osme-connect-queue"></div>
      </div>
    </section>
    <section class="osme-section osme-advanced-pane" data-workspace-tab="validate">
      <div class="osme-section-heading">
        <div><span>VALIDATE</span><strong>Live graph findings</strong></div>
        <button class="osme-button osme-run-validation" type="button">Run</button>
      </div>
      <div class="osme-validation-summary"></div>
      <div class="osme-findings"></div>
      <div class="osme-subsection">
        <strong>Path inspector</strong>
        <div class="osme-toolbar">
          <input class="osme-field osme-path-start" type="text" placeholder="start waypoint ID">
          <input class="osme-field osme-path-end" type="text" placeholder="end waypoint ID">
          <button class="osme-button osme-inspect-path" type="button">Inspect</button>
        </div>
        <div class="osme-path-result"></div>
      </div>
      <div class="osme-subsection">
        <strong>Reachability</strong>
        <button class="osme-button osme-run-reachability" type="button">
          From first selected waypoint
        </button>
        <div class="osme-reachability"></div>
      </div>
      <div class="osme-subsection">
        <strong>Crosswalk audit</strong>
        <button class="osme-button osme-run-crosswalk" type="button">Audit callbacks</button>
        <div class="osme-crosswalks"></div>
      </div>
    </section>`;
  root.querySelector(".osme-footer").before(workspace);

  const el = {};
  for (const className of [
    "selection-count", "selection-mode", "from-orbit", "invert", "clear-selection",
    "apply-selection", "selection-summary", "query-builder", "run-query",
    "query-to-selection", "query-summary", "neighbors", "hop-count", "n-hop",
    "component", "recording", "leaves", "bridges", "select-path-start",
    "select-path-end", "select-path", "viewport", "rectangle", "apply-rectangle", "polygon",
    "apply-polygon", "set-name", "save-set", "named-sets", "preview-archive",
    "copy-settings", "preview-paste", "preset-list", "use-preset",
    "settings-clipboard", "settings-matrix", "preset-name", "save-preset",
    "show-presets", "import-presets", "preset-json", "mutation-review", "mutation-title",
    "mutation-detail", "cancel-mutation", "confirm-mutation", "uncertainty-recovery",
    "queue-source", "parse-queue", "connect-queue", "run-validation",
    "validation-summary", "findings", "path-start", "path-end", "inspect-path",
    "path-result", "run-reachability", "reachability", "run-crosswalk",
    "crosswalks",
  ]) {
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
    state.tab = tab;
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

  function setPending(pending) {
    state.pending = pending;
    renderMutation();
  }

  function renderMutation() {
    const mutationLocked = Boolean(runtime.state.mutationUncertain);
    el.confirm_mutation.disabled = mutationLocked;
    el.mutation_review.hidden = !state.pending;
    el.mutation_detail.replaceChildren();
    if (!state.pending) return;
    el.mutation_title.textContent = state.pending.title;
    el.mutation_detail.append(
      create("p", "", state.pending.detail),
      create("code", "", `Site Map ${snapshot().map.id}`),
      create("small", "", `Observed draft index ${snapshot().editIndex ?? "—"}`),
    );
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
        "Orbit will create one unsaved batch Archive draft. Review the highlighted selection first.",
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
        "Orbit will create one unsaved native settings draft.",
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
      detail: `${from} ↔ ${to}. Orbit validation runs before one unsaved draft is created.`,
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
        "A previous native edit is still unverified. Inspect or restore Orbit, then clear the lock in Edit before another edit.",
        "error",
      );
      renderAdvanced();
      return;
    }
    if (
      pending.observedEditIndex !== snapshot().editIndex ||
      snapshot().map.id !== runtime.currentMapId()
    ) {
      message("Live Site Map or draft index changed; review the operation again.", "error");
      setPending(null);
      return;
    }
    el.confirm_mutation.disabled = true;
    try {
      let response;
      if (pending.type === "archive") {
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
        `Orbit created one unsaved ${pending.type} Undo step ` +
        `(draft index +${response.draftIndexDelta ?? "?"}). ` +
        "Review it, then use Orbit Save or one Undo.",
        "ok",
      );
      state.pending = null;
      await runtime.refreshSnapshot({ quiet: true, allowBusy: true });
    } catch (error) {
      if (error.mutationMayExist) {
        if (pending.queueIndex >= 0 && state.connectQueue[pending.queueIndex]) {
          state.connectQueue[pending.queueIndex].status = "unverified draft";
        }
        state.pending = null;
        await runtime.refreshSnapshot({ quiet: true, allowBusy: true });
        message(
          `${runtime.friendlyError(error.message)}. An unverified native draft may exist; ` +
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
      create("strong", "", "Native edit result is unverified"),
      create(
        "p",
        "",
        `${uncertain.command || "edit"} · Draft index ` +
        `${context.beforeEditIndex ?? "?"}→${context.afterEditIndex ?? "?"} · ` +
        `Undo depth ${context.beforeUndoDepth ?? "?"}→${context.afterUndoDepth ?? "?"} · ` +
        `${context.targetKeys?.length || 0} target(s)`,
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
    renderSelection();
    renderQuery();
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
    if (button) setTab(button.dataset.tab, { userInitiated: true });
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
            ? `${runtime.friendlyError(error.message)}. An unverified native draft may exist; ` +
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
    overlayState: () => ({
      revision: state.overlayRevision,
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
    }),
  });

  function resetWorkspaceState() {
    state.tab = "explore";
    state.selection = select.normalize();
    state.selectionMode = "replace";
    state.namedSets = [];
    state.findings = [];
    state.queryResults = [];
    state.pending = null;
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
    const validTabs = ["explore", "select", "edit", "validate", "walk"];
    const preserveSelectedTab = validTabs.includes(tabSelectedWhileLoading);
    state.tab = preserveSelectedTab
      ? tabSelectedWhileLoading
      : validTabs.includes(stored.tab)
        ? stored.tab
        : "explore";
    state.selection = select.normalize(stored.selection);
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
