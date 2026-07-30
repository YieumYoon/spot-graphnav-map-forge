(() => {
  "use strict";

  const ROOT_ID = "orbit-site-map-editor-root";
  const STORAGE_KEY = "orbitSiteMapEditorPreferencesV1";
  const BRIDGE_CHANNEL = "orbit-site-map-editor-v1";
  const REQUEST_TYPE = "orbit-site-map-editor-request";
  const RESPONSE_TYPE = "orbit-site-map-editor-response";
  const READY_TYPE = "orbit-site-map-editor-ready";
  const ACTION_SELECTION_TYPE = "orbit-site-map-editor-action-selection";
  const DISPOSE_EVENT = "orbit-site-map-editor-dispose-v1";
  const CAMERA_WIDTH_METERS = 10;
  const SNAPSHOT_POLL_INTERVAL_MS = 1800;
  const MAX_NATIVE_VALIDATIONS = 12;
  const MAX_OVERLAY_WAYPOINTS = 350;
  const MAX_OVERLAY_EDGES = 750;
  const MAX_OVERLAY_EDGE_LABELS = 150;
  const MAX_OVERLAY_AREAS = 350;
  const MAX_OVERLAY_AREA_SCAN = 5000;
  const MAX_WALK_OVERLAY_SEGMENTS = 3000;
  const MAX_WALK_OVERLAY_MARKERS = 500;
  const ACTION_NAME_LABEL_DENSITY_STEPS = [
    { maxZoom: 0.7, cellWidth: 200, cellHeight: 36 },
    { maxZoom: 0.85, cellWidth: 150, cellHeight: 30 },
    { maxZoom: 1, cellWidth: 110, cellHeight: 26 },
    { maxZoom: 1.2, cellWidth: 72, cellHeight: 22 },
    { maxZoom: Infinity, cellWidth: 0, cellHeight: 0 },
  ];
  const WAYPOINT_LABEL_DENSITY_STEPS = [
    { maxZoom: 0.45, cellWidth: 190, cellHeight: 34 },
    { maxZoom: 0.6, cellWidth: 140, cellHeight: 30 },
    { maxZoom: 0.72, cellWidth: 100, cellHeight: 26 },
    { maxZoom: Infinity, cellWidth: 0, cellHeight: 0 },
  ];
  const EDGE_LABEL_DENSITY_STEPS = [
    { maxZoom: 0.55, cellWidth: 240, cellHeight: 40 },
    { maxZoom: 0.75, cellWidth: 180, cellHeight: 34 },
    { maxZoom: 1, cellWidth: 130, cellHeight: 28 },
    { maxZoom: 1.2, cellWidth: 90, cellHeight: 24 },
    { maxZoom: Infinity, cellWidth: 0, cellHeight: 0 },
  ];
  const AREA_LABEL_DENSITY_STEPS = [
    { maxZoom: 0.8, cellWidth: 240, cellHeight: 44 },
    { maxZoom: 1.25, cellWidth: 190, cellHeight: 38 },
    { maxZoom: 1.5, cellWidth: 140, cellHeight: 30 },
    { maxZoom: Infinity, cellWidth: 0, cellHeight: 0 },
  ];
  const MUTATION_COMMANDS = new Set([
    "connect",
    "archive_edges",
    "update_edge_settings",
    "rename_actions",
  ]);
  const extensionContext = globalThis.OrbitSiteMapEditorExtensionContext;
  const panelLayout = globalThis.OrbitSiteMapEditorPanelLayout;
  const model = globalThis.OrbitSiteMapEditorModel;
  const queryEngine = globalThis.OrbitSiteMapEditorQuery;
  const areaSettings = globalThis.OrbitSiteMapEditorAreaSettings;
  const overlaySettings = globalThis.OrbitSiteMapEditorOverlaySettings;
  const overlayRenderer = globalThis.OrbitSiteMapEditorOverlayRenderer;

  if (
    !extensionContext ||
    !panelLayout ||
    !model ||
    !queryEngine ||
    !areaSettings ||
    !overlaySettings ||
    !overlayRenderer
  ) return;
  const {
    labelDensity,
    recordingColor,
    setLabel: setOverlayLabel,
    stableStringHash,
    svgElement,
  } = overlayRenderer;
  const instanceId =
    globalThis.crypto?.randomUUID?.() ||
    `osme-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const instanceEvents = Object.freeze({
    addSelection: `osme:add-selection:${instanceId}`,
    actionSelection: `osme:action-selection:${instanceId}`,
    snapshot: `osme:snapshot:${instanceId}`,
    mutationUncertain: `osme:mutation-uncertain:${instanceId}`,
  });
  const previousRoot = document.getElementById(ROOT_ID);
  if (previousRoot) {
    window.dispatchEvent(new CustomEvent(DISPOSE_EVENT, { detail: { instanceId } }));
    previousRoot.remove();
  }

  const state = {
    snapshot: null,
    snapshotFingerprint: "",
    snapshotRevision: 0,
    snapshotInFlight: false,
    hasSuccessfulSnapshot: false,
    bridgeReady: false,
    requestSequence: 0,
    pendingRequests: new Map(),
    status: "Waiting for Orbit's live Site Map…",
    statusKind: "neutral",
    panelOpen: true,
    panelLayout: panelLayout.DEFAULT_LAYOUT,
    query: "",
    searchKind: "all",
    searchSortBy: "rank",
    searchDescending: false,
    radiusMeters: model.DEFAULT_RADIUS_METERS,
    candidateLimit: model.DEFAULT_CANDIDATE_LIMIT,
    validation: new Map(),
    validationContext: "",
    validatingId: "",
    validatingBatch: false,
    connectingId: "",
    pendingConnectId: "",
    mutationUncertain: null,
    overlay: overlaySettings.defaults(),
    lastOverlayKey: "",
    disposed: false,
  };

  const root = document.createElement("div");
  root.id = ROOT_ID;
  root.innerHTML = `
    <svg class="osme-overlay" aria-hidden="true"></svg>
    <button class="osme-launch" type="button" hidden>Site Map Editor</button>
    <aside class="osme-panel" aria-label="Orbit Site Map Editor">
      <header class="osme-header">
        <div>
          <span class="osme-kicker">ORBIT SITE MAP</span>
          <h2>Editor Assistant <span class="osme-version"></span></h2>
        </div>
        <div class="osme-header-actions">
          <div class="osme-layout-controls" role="group" aria-label="Panel layout">
            <button type="button" data-panel-layout="rail-left" title="Separate left rail">
              Left
            </button>
            <button type="button" data-panel-layout="float" title="Float over Orbit">
              Float
            </button>
            <button type="button" data-panel-layout="rail-right" title="Separate right rail">
              Right
            </button>
          </div>
          <button class="osme-icon-button osme-close" type="button" aria-label="Collapse">×</button>
        </div>
      </header>
      <div class="osme-status" role="status"></div>
      <section class="osme-summary" aria-label="Live Site Map summary"></section>
      <section class="osme-section">
        <div class="osme-section-heading">
          <div><span>EXPLORE</span><strong>Live Site Map</strong></div>
          <button class="osme-button osme-refresh" type="button">Refresh</button>
        </div>
        <div class="osme-search-row">
          <input class="osme-search" type="search"
            placeholder="Search IDs, names, or use type:edge source:manual"
            aria-label="Search live Site Map objects">
          <select class="osme-search-kind" aria-label="Object type">
            <option value="all">All</option>
            <option value="waypoint">Waypoints</option>
            <option value="edge">Edges</option>
            <option value="recording">Recordings</option>
            <option value="area">Areas</option>
            <option value="dock">Docks</option>
            <option value="fiducial">Fiducials</option>
            <option value="action">Actions</option>
          </select>
          <select class="osme-search-sort" aria-label="Sort search results">
            <option value="rank">Best match</option>
            <option value="kind">Type</option>
            <option value="name">Name</option>
            <option value="id">Exact ID</option>
            <option value="recordingName">Recording</option>
            <option value="degree">Degree</option>
            <option value="source">Edge source</option>
            <option value="status">Status</option>
          </select>
          <button class="osme-button osme-small osme-search-direction"
            type="button" aria-label="Toggle sort direction">↑</button>
        </div>
        <div class="osme-search-results"></div>
      </section>
      <section class="osme-section">
        <div class="osme-section-heading">
          <div><span>INSPECT</span><strong>Current Orbit selection</strong></div>
        </div>
        <div class="osme-inspector"></div>
      </section>
      <section class="osme-section osme-connect-section">
        <div class="osme-section-heading">
          <div><span>EDIT</span><strong>Connect mode</strong></div>
          <span class="osme-safety-chip">unsaved change</span>
        </div>
        <div class="osme-connect-controls">
          <label>Radius
            <input class="osme-radius" type="number" min="0.5" max="100" step="0.5" value="2">
            <span>m</span>
          </label>
          <button class="osme-button osme-validate-visible" type="button">
            Validate visible
          </button>
        </div>
        <div class="osme-connect-summary"></div>
        <div class="osme-connect-confirmation" hidden>
          <span class="osme-kind">review connect pair</span>
          <strong>Create one unsaved Orbit change?</strong>
          <div class="osme-connect-confirmation-details"></div>
          <div class="osme-connect-confirmation-actions">
            <button class="osme-button osme-cancel-connect" type="button">Cancel</button>
            <button class="osme-button osme-primary osme-confirm-connect" type="button">
              Apply unsaved change
            </button>
          </div>
        </div>
        <div class="osme-candidates"></div>
      </section>
      <section class="osme-section">
        <div class="osme-section-heading">
          <div><span>VIEW</span><strong>Detailed overlay</strong></div>
        </div>
        <div class="osme-overlay-controls"></div>
      </section>
      <footer class="osme-footer">
        Validation is selection-only. Connect creates one unsaved native Orbit draft and never presses Save.
      </footer>
    </aside>`;
  root.querySelector(".osme-version").textContent =
    extensionContext.getVersionLabel?.() || "development";
  document.documentElement.append(root);

  const elements = {
    overlay: root.querySelector(".osme-overlay"),
    launch: root.querySelector(".osme-launch"),
    panel: root.querySelector(".osme-panel"),
    layoutControls: root.querySelector(".osme-layout-controls"),
    close: root.querySelector(".osme-close"),
    status: root.querySelector(".osme-status"),
    summary: root.querySelector(".osme-summary"),
    refresh: root.querySelector(".osme-refresh"),
    search: root.querySelector(".osme-search"),
    searchKind: root.querySelector(".osme-search-kind"),
    searchSort: root.querySelector(".osme-search-sort"),
    searchDirection: root.querySelector(".osme-search-direction"),
    searchResults: root.querySelector(".osme-search-results"),
    inspector: root.querySelector(".osme-inspector"),
    radius: root.querySelector(".osme-radius"),
    validateVisible: root.querySelector(".osme-validate-visible"),
    connectSummary: root.querySelector(".osme-connect-summary"),
    connectConfirmation: root.querySelector(".osme-connect-confirmation"),
    connectConfirmationDetails: root.querySelector(
      ".osme-connect-confirmation-details",
    ),
    cancelConnect: root.querySelector(".osme-cancel-connect"),
    confirmConnect: root.querySelector(".osme-confirm-connect"),
    candidates: root.querySelector(".osme-candidates"),
    overlayControls: root.querySelector(".osme-overlay-controls"),
  };
  let snapshotIntervalId = null;
  let overlayAnimationId = null;
  let appliedPanelRail = "";
  let removeInvalidationListener = () => {};
  let cachedAreaSnapshot = null;
  let cachedAreaRecords = [];
  let cachedAreaCatalogSnapshot = null;
  let cachedAreaCatalog = [];

  buildOverlayControls();

  function notifyOrbitViewportChanged() {
    window.requestAnimationFrame(() => {
      window.dispatchEvent(new Event("resize"));
    });
  }

  function syncPanelLayout() {
    const nextRail = panelLayout.apply(
      document.documentElement,
      state.panelLayout,
      state.panelOpen,
    );
    if (nextRail === appliedPanelRail) return;
    appliedPanelRail = nextRail;
    notifyOrbitViewportChanged();
  }

  function mutationTargetKeys(command, payload = {}) {
    if (command === "rename_actions" && Array.isArray(payload.actionNameUpdates)) {
      return payload.actionNameUpdates
        .map((update) => String(update?.id || ""))
        .filter(Boolean);
    }
    if (command === "connect" && Array.isArray(payload.waypointIds)) {
      return payload.waypointIds.length === 2
        ? [model.edgeKey(payload.waypointIds[0], payload.waypointIds[1])]
        : [];
    }
    if (command === "archive_edges" && Array.isArray(payload.waypointPairs)) {
      return payload.waypointPairs
        .filter((pair) => Array.isArray(pair) && pair.length === 2)
        .map((pair) => model.edgeKey(pair[0], pair[1]));
    }
    if (
      command === "update_edge_settings" &&
      Array.isArray(payload.settingsUpdates)
    ) {
      return payload.settingsUpdates
        .map((update) => update?.waypointIds)
        .filter((pair) => Array.isArray(pair) && pair.length === 2)
        .map((pair) => model.edgeKey(pair[0], pair[1]));
    }
    return [];
  }

  function requestMutationContext(command, payload = {}) {
    const actionMutation = command === "rename_actions";
    return {
      command,
      beforeEditIndex: actionMutation
        ? state.snapshot?.actionEditIndex ?? null
        : state.snapshot?.editIndex ?? null,
      afterEditIndex: null,
      beforeUndoDepth: actionMutation
        ? state.snapshot?.actionHistory?.undoDepth ?? null
        : state.snapshot?.history?.undoDepth ?? null,
      afterUndoDepth: null,
      targetKeys: mutationTargetKeys(command, payload),
    };
  }

  function bridgeError(
    message,
    {
      command = "",
      mutationMayExist = false,
      mutationContext = {},
      mutationBlocked = false,
    } = {},
  ) {
    const error = new Error(message);
    error.command = command;
    error.mutationMayExist = Boolean(mutationMayExist);
    error.mutationContext = {
      command,
      beforeEditIndex: mutationContext.beforeEditIndex ?? null,
      afterEditIndex: mutationContext.afterEditIndex ?? null,
      beforeUndoDepth: mutationContext.beforeUndoDepth ?? null,
      afterUndoDepth: mutationContext.afterUndoDepth ?? null,
      targetKeys: Array.isArray(mutationContext.targetKeys)
        ? [...mutationContext.targetKeys]
        : [],
    };
    error.mutationBlocked = Boolean(mutationBlocked);
    return error;
  }

  function latchMutationUncertainty(command, error) {
    if (!error?.mutationMayExist || state.mutationUncertain) return;
    state.mutationUncertain = {
      command,
      timestamp: new Date().toISOString(),
      mutationContext: {
        command,
        beforeEditIndex: error.mutationContext?.beforeEditIndex ?? null,
        afterEditIndex: error.mutationContext?.afterEditIndex ?? null,
        beforeUndoDepth: error.mutationContext?.beforeUndoDepth ?? null,
        afterUndoDepth: error.mutationContext?.afterUndoDepth ?? null,
        targetKeys: Array.isArray(error.mutationContext?.targetKeys)
          ? [...error.mutationContext.targetKeys]
          : [],
      },
    };
    window.dispatchEvent(new CustomEvent(instanceEvents.mutationUncertain, {
      detail: state.mutationUncertain,
    }));
  }

  function acknowledgeMutationUncertainty() {
    const previous = state.mutationUncertain;
    state.mutationUncertain = null;
    render();
    return previous;
  }

  function unverifiedMutationGuidance(error) {
    const context = error?.mutationContext || {};
    const history =
      `Draft index ${context.beforeEditIndex ?? "?"}→${context.afterEditIndex ?? "?"}; ` +
      `Undo depth ${context.beforeUndoDepth ?? "?"}→${context.afterUndoDepth ?? "?"}. `;
    return (
      `${history}Do not Save. Inspect the exact target and Orbit history. ` +
      "Undo only if Orbit shows this change as the newest Undo step; " +
      "otherwise reload Orbit or restore the backup."
    );
  }

  function deactivate() {
    if (state.disposed) return;
    state.disposed = true;
    if (snapshotIntervalId !== null) window.clearInterval(snapshotIntervalId);
    if (overlayAnimationId !== null) window.cancelAnimationFrame(overlayAnimationId);
    snapshotIntervalId = null;
    overlayAnimationId = null;
    for (const pending of state.pendingRequests.values()) {
      const error = bridgeError("extension_context_invalidated", {
        command: pending.command,
        mutationMayExist: pending.isMutation,
        mutationContext: pending.mutationContext,
      });
      latchMutationUncertainty(pending.command, error);
      pending.reject(error);
    }
    state.pendingRequests.clear();
    elements.overlay.replaceChildren();
    const releasedRail = Boolean(appliedPanelRail);
    panelLayout.clear(document.documentElement);
    appliedPanelRail = "";
    if (releasedRail) notifyOrbitViewportChanged();
    root.dataset.inactive = "true";
    elements.panel.inert = true;
    setStatus(
      "Extension was reloaded. Reload this Orbit tab once to activate the new version.",
      "warning",
    );
  }

  function dispose() {
    deactivate();
    removeInvalidationListener();
    window.removeEventListener("message", handleWindowMessage);
    window.removeEventListener(DISPOSE_EVENT, handleExternalDispose);
    root.remove();
  }

  function handleExternalDispose(event) {
    if (event.detail?.instanceId !== instanceId) dispose();
  }

  function currentMapId() {
    const match = location.pathname.match(/\/control_room\/maps\/([^/]+)\/edit/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function setStatus(message, kind = "neutral") {
    state.status = message;
    state.statusKind = kind;
    elements.status.textContent = message;
    elements.status.dataset.kind = kind;
  }

  function storageGet() {
    return extensionContext.storageGet([STORAGE_KEY]);
  }

  function persist() {
    return extensionContext.storageSet({
      [STORAGE_KEY]: {
        panelOpen: state.panelOpen,
        panelLayout: state.panelLayout,
        radiusMeters: state.radiusMeters,
        overlay: state.overlay,
        searchSortBy: state.searchSortBy,
        searchDescending: state.searchDescending,
      },
    });
  }

  function requestBridge(command, payload = {}, timeoutMs = 7000) {
    const isMutation = MUTATION_COMMANDS.has(command);
    const blockedByUncertainty = isMutation || command === "validate_connect";
    if (blockedByUncertainty && state.mutationUncertain) {
      return Promise.reject(bridgeError("unverified_mutation_pending", {
        command,
        mutationMayExist: true,
        mutationContext: state.mutationUncertain.mutationContext,
        mutationBlocked: true,
      }));
    }
    if (state.disposed || !extensionContext.isActive()) {
      deactivate();
      return Promise.reject(bridgeError("extension_context_invalidated", {
        command,
        mutationMayExist: isMutation,
        mutationContext: requestMutationContext(command, payload),
      }));
    }
    return new Promise((resolve, reject) => {
      const requestId = `osme-${Date.now()}-${state.requestSequence += 1}`;
      const mutationContext = requestMutationContext(command, payload);
      const timer = window.setTimeout(() => {
        state.pendingRequests.delete(requestId);
        const error = bridgeError("Orbit adapter timed out.", {
          command,
          mutationMayExist: isMutation,
          mutationContext,
        });
        latchMutationUncertainty(command, error);
        reject(error);
      }, timeoutMs);
      state.pendingRequests.set(requestId, {
        command,
        isMutation,
        mutationContext,
        resolve: (value) => {
          window.clearTimeout(timer);
          resolve(value);
        },
        reject: (error) => {
          window.clearTimeout(timer);
          reject(error);
        },
      });
      window.postMessage(
        {
          channel: BRIDGE_CHANNEL,
          type: REQUEST_TYPE,
          requestId,
          sessionId: instanceId,
          command,
          mapId: currentMapId(),
          ...payload,
        },
        location.origin,
      );
    });
  }

  function create(tag, className = "", text = "") {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text) element.textContent = text;
    return element;
  }

  function buildOverlayControls() {
    elements.overlayControls.replaceChildren();
    for (const group of overlaySettings.CONTROL_GROUPS) {
      const details = create("details", "osme-overlay-group");
      details.dataset.overlayGroupPanel = group.id;
      details.open = group.id === "global" || group.id === "waypoint";
      const summary = create("summary");
      summary.append(
        create("strong", "", group.label),
        create("small", "osme-overlay-active-count"),
      );
      summary.querySelector("small").dataset.overlayCount = group.id;
      const body = create("div", "osme-overlay-group-body");
      const master = create("label", "osme-overlay-master");
      const masterInput = document.createElement("input");
      masterInput.type = "checkbox";
      masterInput.dataset.overlayGroup = group.id;
      masterInput.dataset.overlayEnabled = "true";
      master.append(masterInput, document.createTextNode(group.masterLabel));
      body.append(master);
      body.append(create(
        "small",
        "osme-overlay-guidance",
        group.guidance ||
          "Choose values to show. Select a few fields at a time for a readable map.",
      ));

      if (group.id !== "global") {
        const actions = create("div", "osme-overlay-value-actions");
        for (const [action, label] of [
          ["all", "Show all values"],
          ["clear", "Hide all values"],
        ]) {
          const button = create("button", "osme-button osme-small", label);
          button.type = "button";
          button.dataset.overlayFieldsAction = action;
          button.dataset.overlayGroup = group.id;
          actions.append(button);
        }
        body.append(actions);
      }

      for (const section of group.sections) {
        const fieldset = create("fieldset", "osme-overlay-fieldset");
        fieldset.append(create("legend", "", section.label));
        if (section.description) {
          fieldset.append(create(
            "small",
            "osme-overlay-section-guidance",
            section.description,
          ));
        }
        const grid = create("div", "osme-overlay-field-grid");
        for (const field of section.fields) {
          const label = create("label");
          const input = document.createElement("input");
          input.type = "checkbox";
          input.dataset.overlayGroup = group.id;
          input.dataset.overlayField = field.id;
          label.append(input, document.createTextNode(field.label));
          grid.append(label);
        }
        fieldset.append(grid);
        body.append(fieldset);
      }

      if (group.dynamicSectionLabel) {
        const dynamic = create("details", "osme-overlay-dynamic-section");
        const dynamicSummary = create("summary", "", group.dynamicSectionLabel);
        dynamicSummary.dataset.overlayDynamicSummary = group.id;
        dynamic.append(dynamicSummary);
        const filter = document.createElement("input");
        filter.type = "search";
        filter.className = "osme-field osme-overlay-callback-filter";
        filter.placeholder = "Filter callback parameters";
        filter.setAttribute("aria-label", "Filter Area callback parameters");
        filter.dataset.overlayCallbackFilter = group.id;
        if (group.dynamicSectionDescription) {
          dynamic.append(create(
            "small",
            "osme-overlay-section-guidance",
            group.dynamicSectionDescription,
          ));
        }
        const filterStatus = create("small", "osme-overlay-filter-status");
        filterStatus.dataset.overlayCallbackFilterStatus = group.id;
        filterStatus.setAttribute("aria-live", "polite");
        const fieldset = create("fieldset", "osme-overlay-fieldset");
        const grid = create("div", "osme-overlay-field-grid");
        grid.dataset.overlayDynamicFields = group.id;
        fieldset.append(grid);
        dynamic.append(filter, filterStatus, fieldset);
        body.append(dynamic);
      }
      details.append(summary, body);
      elements.overlayControls.append(details);
    }
    syncOverlayControls();
  }

  function areaRecordsForOverlay() {
    if (cachedAreaSnapshot === state.snapshot) return cachedAreaRecords;
    cachedAreaSnapshot = state.snapshot;
    cachedAreaRecords = state.snapshot ? areaSettings.records(state.snapshot) : [];
    cachedAreaCatalogSnapshot = null;
    return cachedAreaRecords;
  }

  function areaFieldCatalogForOverlay() {
    const records = areaRecordsForOverlay();
    if (cachedAreaCatalogSnapshot === state.snapshot) return cachedAreaCatalog;
    cachedAreaCatalogSnapshot = state.snapshot;
    cachedAreaCatalog = overlaySettings.areaCallbackFieldCatalog(
      records,
    );
    return cachedAreaCatalog;
  }

  function syncAreaCallbackControls() {
    const container = elements.overlayControls.querySelector(
      '[data-overlay-dynamic-fields="area"]',
    );
    if (!container) return [];
    const catalog = areaFieldCatalogForOverlay();
    const catalogKey = JSON.stringify({
      truncated: Boolean(catalog.truncated),
      paths: catalog.map((field) => field.path),
    });
    if (container.dataset.catalogKey !== catalogKey) {
      container.dataset.catalogKey = catalogKey;
      container.replaceChildren();
      if (!catalog.length) {
        container.append(create(
          "small",
          "osme-overlay-empty-fields",
          "No current callback parameters found in this map.",
        ));
      }
      for (const field of catalog) {
        const label = create("label");
        label.title = field.path;
        label.dataset.overlayCallbackField = "true";
        label.dataset.overlaySearch = `${field.label} ${field.path}`.toLocaleLowerCase();
        const input = document.createElement("input");
        input.type = "checkbox";
        input.dataset.overlayGroup = "area";
        input.dataset.overlayCallbackPath = field.path;
        input.setAttribute("aria-label", `${field.label}; callback path ${field.path}`);
        label.append(input, document.createTextNode(field.label));
        container.append(label);
      }
      if (catalog.truncated) {
        container.append(create(
          "small",
          "osme-overlay-empty-fields",
          `Showing the first ${catalog.length} callback parameters.`,
        ));
      }
    }
    filterAreaCallbackControls();
    return catalog;
  }

  function filterAreaCallbackControls() {
    const filter = elements.overlayControls.querySelector(
      '[data-overlay-callback-filter="area"]',
    );
    const query = filter?.value.trim().toLocaleLowerCase() || "";
    const labels = [...elements.overlayControls.querySelectorAll(
      '[data-overlay-callback-field="true"]',
    )];
    let visible = 0;
    let selected = 0;
    for (const label of labels) {
      label.hidden = Boolean(query && !label.dataset.overlaySearch.includes(query));
      if (!label.hidden) visible += 1;
      if (label.querySelector("input")?.checked) selected += 1;
    }
    const summary = elements.overlayControls.querySelector(
      '[data-overlay-dynamic-summary="area"]',
    );
    if (summary) {
      summary.textContent = `Callback parameters (${selected}/${labels.length} selected)`;
    }
    const status = elements.overlayControls.querySelector(
      '[data-overlay-callback-filter-status="area"]',
    );
    if (status) {
      status.textContent = query
        ? `${visible} of ${labels.length} callback parameters match; ${selected} selected.`
        : `${labels.length} callback parameters available; ${selected} selected.`;
    }
  }

  function syncOverlayControls() {
    const areaCatalog = syncAreaCallbackControls();
    for (const input of elements.overlayControls.querySelectorAll(
      "input[data-overlay-group]",
    )) {
      const group = input.dataset.overlayGroup;
      if (input.dataset.overlayEnabled) {
        input.checked = Boolean(state.overlay[group]?.enabled);
      } else if (input.dataset.overlayField) {
        input.checked = overlaySettings.fieldEnabled(
          state.overlay,
          group,
          input.dataset.overlayField,
        );
      } else if (input.dataset.overlayCallbackPath) {
        input.checked = overlaySettings.callbackFieldEnabled(
          state.overlay,
          input.dataset.overlayCallbackPath,
        );
      }
    }
    for (const group of overlaySettings.CONTROL_GROUPS) {
      const fixedCount = group.sections
        .flatMap((section) => section.fields)
        .filter((field) => overlaySettings.fieldEnabled(
          state.overlay,
          group.id,
          field.id,
        )).length;
      const dynamicCount = group.id === "area"
        ? areaCatalog.filter((field) => overlaySettings.callbackFieldEnabled(
            state.overlay,
            field.path,
          )).length
        : 0;
      const counter = elements.overlayControls.querySelector(
        `[data-overlay-count="${group.id}"]`,
      );
      if (counter) {
        const suppressed = group.id !== "global" && !state.overlay.global.enabled;
        const enabled = state.overlay[group.id]?.enabled ? "On" : "Off";
        const selectedCount = fixedCount + dynamicCount;
        const selected = `${selectedCount} field${selectedCount === 1 ? "" : "s"} selected`;
        counter.textContent = suppressed
          ? `${enabled} · hidden by Overall · ${selected}`
          : `${enabled} · ${selected}`;
        counter.closest("details")?.classList.toggle(
          "osme-overlay-suppressed",
          suppressed,
        );
      }
    }
    filterAreaCallbackControls();
  }

  function codeValue(value) {
    const code = create("code", "", String(value || "—"));
    code.title = String(value || "");
    return code;
  }

  function detailRow(label, value, code = false) {
    const row = create("div", "osme-detail-row");
    row.append(create("span", "", label), code ? codeValue(value) : create("span", "", value));
    return row;
  }

  function selectedBaseId() {
    const selected = state.snapshot?.selectedWaypointIds || [];
    return selected.length === 1 ? selected[0] : "";
  }

  function graph() {
    return model.buildGraph(state.snapshot || {});
  }

  function candidates() {
    return model.connectionCandidates(state.snapshot, selectedBaseId(), {
      radiusMeters: state.radiusMeters,
      limit: state.candidateLimit,
    });
  }

  function currentValidationContext() {
    return [
      state.snapshot?.map?.id || "",
      state.snapshot?.editIndex ?? "none",
      selectedBaseId(),
    ].join("|");
  }

  function ensureValidationContext() {
    const context = currentValidationContext();
    if (context !== state.validationContext) {
      state.validation.clear();
      state.pendingConnectId = "";
      state.validationContext = context;
    }
  }

  function friendlyError(error) {
    const code = String(error || "unknown_error");
    const messages = {
      edge_already_exists: "Already connected",
      edge_validation_failed: "Orbit rejected this pair",
      edge_validation_warning: "Orbit requires manual review",
      edge_validation_timeout: "Orbit validation timed out",
      map_or_waypoint_mismatch: "Site Map or waypoint changed",
      orbit_map_changed: "Site Map changed during validation",
      orbit_selection_changed: "Orbit selection changed",
      validation_changed_draft: "Validation unexpectedly changed the draft",
      edge_draft_not_created: "Orbit did not verify the Connect draft",
      edge_archive_batch_not_created: "Orbit did not verify the Archive draft",
      edge_settings_batch_not_created: "Orbit did not verify the settings draft",
      edge_annotation_readback_failed: "Orbit annotation read-back failed",
      action_name_batch_not_created: "Orbit did not verify the unsaved Action renames",
      action_name_readback_failed: "Orbit could not verify the renamed Actions",
      action_name_changed: "An Action name changed after preview",
      action_waypoint_changed: "An Action waypoint changed after preview",
      action_not_found: "A planned Action is no longer available",
      duplicate_action_name: "A planned Action name already exists",
      invalid_action_name_batch: "The Action-name batch is invalid",
      missing_required_name_segment: "Enter Enterprise, Site, and Area",
      invalid_action_name_segment:
        "Naming fields may use 1–32 letters, digits, dots, or underscores",
      invalid_action_sequence_start:
        "Starting sequence must be a non-negative integer that fits its width",
      invalid_action_sequence_width: "Sequence width must be from 1 to 8 digits",
      invalid_action_first_number:
        "Enter the starting sequence as 1–8 digits, including any leading zeros",
      action_sequence_range_overflow: "Action sequence exceeds the selected width",
      inspection_type_required: "Choose an inspection type for every selected Action",
      invalid_generated_action_name: "The naming fields produced an invalid Action name",
      orbit_action_form_unavailable: "Orbit Action draft state is unavailable",
      duplicate_action_id: "The selected Action batch contains a duplicate ID",
      no_selected_actions: "Select at least one Action in Action Names",
      selected_action_not_found: "A selected Action is no longer available",
      no_selected_waypoints: "Select at least one waypoint in Orbit",
      selected_waypoint_not_found: "A selected waypoint is no longer in this Site Map",
      native_mutation_in_progress: "Another native mutation is still in progress",
      native_operation_in_progress: "Another native validation is still in progress",
      native_mutation_exception: "Orbit raised an exception during the native edit",
      native_validation_exception: "Orbit raised an exception during validation",
      bridge_disposed: "The page adapter was replaced during the operation",
      unverified_mutation_pending: "A previous native edit is still unverified",
      duplicate_edge_selection: "Duplicate edge selection",
      edge_not_found: "The selected edge is no longer active",
      start_waypoint_not_found: "The coverage start waypoint is not in this Site Map",
      start_waypoint_has_no_active_edges:
        "The coverage start is isolated; choose a waypoint with an active edge",
      site_map_has_no_active_edges:
        "This Site Map has no active connected component to cover",
      site_map_has_no_waypoints: "This Site Map has no waypoints to cover",
      orbit_store_unavailable: "Orbit editor state is unavailable",
      orbit_snapshot_unavailable: "Live graph is unavailable",
    };
    return messages[code] || code.replaceAll("_", " ");
  }

  function validationFailureText(reason, details = []) {
    const summary = friendlyError(reason);
    const specifics = [...new Set(
      (Array.isArray(details) ? details : [])
        .map((detail) => String(detail || "").trim())
        .filter((detail) => detail && detail !== summary),
    )];
    return specifics.length ? `${summary}: ${specifics.join(" · ")}` : summary;
  }

  function renderSummary() {
    elements.summary.replaceChildren();
    const snapshot = state.snapshot;
    if (!snapshot) {
      elements.summary.append(create("p", "osme-empty", "No live snapshot."));
      return;
    }
    const title = create(
      "strong",
      "",
      snapshot.map.name || model.shortId(snapshot.map.id),
    );
    title.title = snapshot.map.id;
    const stats = create("div", "osme-stats");
    for (const [value, label] of [
      [snapshot.waypoints.length, "waypoints"],
      [snapshot.edges.length, "edges"],
      [snapshot.recordingCount, "recordings"],
      [snapshot.editIndex ?? "—", "edit revision"],
      [(snapshot.areas || []).length, "Areas"],
      [(snapshot.docks || []).length, "Docks"],
      [(snapshot.fiducials || []).length, "fiducials"],
      [(snapshot.actions || []).length, "Actions"],
    ]) {
      const item = create("span", "osme-stat");
      item.append(create("strong", "", String(value)), create("small", "", label));
      stats.append(item);
    }
    elements.summary.append(title, stats);
  }

  function resultWaypointIds(result) {
    return result.waypointIds || [];
  }

  function renderSearch() {
    elements.searchResults.replaceChildren();
    if (!state.query.trim()) {
      elements.searchResults.append(
        create("p", "osme-empty", "Search by exact ID, name, recording, robot, or edge source."),
      );
      return;
    }
    const results = queryEngine.querySnapshot(
      state.snapshot,
      state.query,
      {
        kind: state.searchKind,
        limit: 250,
        sortBy: state.searchSortBy,
        descending: state.searchDescending,
      },
    );
    if (!results.length) {
      elements.searchResults.append(create("p", "osme-empty", "No matching live objects."));
      return;
    }
    const table = create("table", "osme-results-table");
    const header = create("thead");
    const headerRow = create("tr");
    for (const label of ["Type", "Name / exact ID", "Context", "Actions"]) {
      headerRow.append(create("th", "", label));
    }
    header.append(headerRow);
    const body = create("tbody");
    for (const [index, result] of results.entries()) {
      const row = create("tr");
      row.append(create("td", "osme-kind", result.kind));
      const identity = create("td", "osme-result-identity");
      identity.append(
        create("strong", "", result.name || model.shortId(result.id)),
        codeValue(result.id),
      );
      const context = create("td", "", [
        result.recordingName || result.recordingId,
        result.source,
        Number.isFinite(result.degree) ? `degree ${result.degree}` : "",
        result.status,
      ].filter(Boolean).join(" · "));
      const actions = create("td", "osme-table-actions");
      const focus = create("button", "osme-button osme-small", "Focus");
      focus.type = "button";
      focus.dataset.action = result.kind === "waypoint"
        ? "select-result"
        : "focus-result";
      focus.dataset.index = String(index);
      focus.disabled = !resultWaypointIds(result).length;
      const add = create("button", "osme-button osme-small", "Add");
      add.type = "button";
      add.dataset.action = "add-result";
      add.dataset.index = String(index);
      actions.append(focus, add);
      row.append(identity, context, actions);
      body.append(row);
    }
    table.append(header, body);
    elements.searchResults.append(table);
    elements.searchResults.dataset.results = JSON.stringify(
      results.map((result) => ({
        kind: result.kind,
        id: result.id,
        waypointIds: resultWaypointIds(result),
        edgeIds: result.edgeIds || [],
      })),
    );
  }

  function renderInspector() {
    elements.inspector.replaceChildren();
    const snapshot = state.snapshot;
    if (!snapshot) {
      elements.inspector.append(create("p", "osme-empty", "Waiting for Orbit."));
      return;
    }
    const liveGraph = graph();
    const selectedWaypointIds = snapshot.selectedWaypointIds || [];
    const selectedEdgeIds = new Set(snapshot.selectedEdgeIds || []);
    const selectedEdges = (snapshot.edges || []).filter((edge) =>
      selectedEdgeIds.has(edge.id) ||
      selectedEdgeIds.has(model.edgeKey(edge.from, edge.to))
    );
    if (!selectedWaypointIds.length && !selectedEdges.length) {
      elements.inspector.append(
        create("p", "osme-empty", "Select a waypoint or edge in Orbit."),
      );
      return;
    }
    for (const id of selectedWaypointIds.slice(0, 20)) {
      const waypoint = liveGraph.waypointById.get(id);
      if (!waypoint) continue;
      const card = create("article", "osme-card");
      card.append(
        create("span", "osme-kind", "waypoint"),
        create("strong", "", waypoint.name || model.shortId(id)),
        detailRow("Waypoint ID", id, true),
        detailRow("Recording", waypoint.recordingName || waypoint.recordingId || "—"),
        detailRow("Recording ID", waypoint.recordingId || "—", true),
        detailRow("Degree", String(waypoint.degree ?? 0)),
        detailRow(
          "Edge sources",
          Object.entries(waypoint.edgeSources || {})
            .map(([source, count]) => `${source}: ${count}`)
            .join(", ") || "—",
        ),
        detailRow(
          "Position",
          model.finitePosition(waypoint.position)
            ? `${waypoint.position.x.toFixed(2)}, ${waypoint.position.y.toFixed(2)}, ` +
              `${Number(waypoint.position.z || 0).toFixed(2)}`
            : "No anchor",
        ),
        detailRow(
          "Robot",
          waypoint.robotNickname || waypoint.robotSerial || "—",
        ),
        detailRow(
          "Created",
          typeof waypoint.creationTime === "string"
            ? waypoint.creationTime
            : JSON.stringify(waypoint.creationTime || "—"),
        ),
      );
      elements.inspector.append(card);
    }
    for (const edge of selectedEdges.slice(0, 20)) {
      const from = liveGraph.waypointById.get(edge.from);
      const to = liveGraph.waypointById.get(edge.to);
      const card = create("article", "osme-card");
      const settings = model.importantSettings(edge.settings);
      card.append(
        create("span", "osme-kind", "edge"),
        create(
          "strong",
          "",
          `${from?.name || model.shortId(edge.from)} ↔ ` +
          `${to?.name || model.shortId(edge.to)}`,
        ),
        detailRow("Edge ID", edge.id, true),
        detailRow("From", edge.from, true),
        detailRow("To", edge.to, true),
        detailRow("Source", edge.source || "unknown"),
        detailRow("Length", model.formatDistance(edge.length)),
        detailRow("Settings", settings.join(", ") || "default"),
        detailRow("Cross-recording", edge.crossRecording ? "yes" : "no"),
      );
      elements.inspector.append(card);
    }
    if (selectedWaypointIds.length > 20 || selectedEdges.length > 20) {
      elements.inspector.append(
        create("p", "osme-empty", "Inspector is capped at 20 selected objects."),
      );
    }
  }

  function candidateStatus(id) {
    return state.validation.get(id) || { status: "unvalidated", reason: "" };
  }

  function renderConnect() {
    elements.connectSummary.replaceChildren();
    elements.connectConfirmation.hidden = true;
    elements.connectConfirmationDetails.replaceChildren();
    elements.candidates.replaceChildren();
    const baseId = selectedBaseId();
    const liveGraph = graph();
    const base = liveGraph.waypointById.get(baseId);
    const mutationLocked = Boolean(state.mutationUncertain);
    elements.validateVisible.disabled = Boolean(
      !base ||
      state.validatingBatch ||
      state.validatingId ||
      state.connectingId ||
      mutationLocked,
    );
    elements.radius.disabled = state.validatingBatch || Boolean(state.validatingId);
    if (!base) {
      elements.connectSummary.append(
        create(
          "p",
          "osme-empty",
          "Select exactly one anchored waypoint in Orbit or from Search.",
        ),
      );
      return;
    }
    const available = candidates();
    const summary = create("div", "osme-base");
    summary.append(
      create("span", "osme-kind", "base"),
      create("strong", "", base.name || model.shortId(base.id)),
      codeValue(base.id),
      create(
        "small",
        "",
        `${base.recordingName || model.shortId(base.recordingId)} · ` +
        `degree ${base.degree ?? 0} · ${available.length} candidates`,
      ),
    );
    elements.connectSummary.append(summary);
    const pendingCandidate = available.find(
      (candidate) => candidate.id === state.pendingConnectId,
    );
    if (
      pendingCandidate &&
      candidateStatus(pendingCandidate.id).status === "valid"
    ) {
      const from = create("div", "osme-confirm-endpoint");
      from.append(
        create("strong", "", base.name || model.shortId(base.id)),
        codeValue(base.id),
      );
      const to = create("div", "osme-confirm-endpoint");
      to.append(
        create(
          "strong",
          "",
          pendingCandidate.name || model.shortId(pendingCandidate.id),
        ),
        codeValue(pendingCandidate.id),
      );
      elements.connectConfirmationDetails.append(
        detailRow(
          "Site Map",
          state.snapshot?.map?.name || currentMapId(),
        ),
        from,
        create("div", "osme-confirm-arrow", "↕"),
        to,
        detailRow("Distance", model.formatDistance(pendingCandidate.distance)),
      );
      elements.connectConfirmation.hidden = false;
      elements.cancelConnect.disabled = Boolean(state.connectingId);
      elements.confirmConnect.disabled = Boolean(
        state.connectingId || mutationLocked,
      );
    }
    if (!model.finitePosition(base.position)) {
      elements.candidates.append(
        create("p", "osme-empty osme-error", "Selected waypoint has no live anchor."),
      );
      return;
    }
    if (!available.length) {
      elements.candidates.append(
        create("p", "osme-empty", "No unconnected anchored waypoints inside this radius."),
      );
      return;
    }

    for (const candidate of available) {
      const validation = candidateStatus(candidate.id);
      const card = create("article", "osme-candidate");
      card.dataset.status = validation.status;
      const copy = create("div", "osme-candidate-copy");
      copy.append(
        create(
          "strong",
          "",
          candidate.name || model.shortId(candidate.id),
        ),
        codeValue(candidate.id),
        create(
          "small",
          "",
          `${model.formatDistance(candidate.distance)} · degree ${candidate.degree} · ` +
          `${candidate.recordingName || model.shortId(candidate.recordingId)}` +
          `${candidate.sameRecording ? "" : " · cross-recording"}`,
        ),
      );
      const status = create(
        "div",
        "osme-validation",
        validation.status === "valid"
          ? "validated"
          : validation.status === "rejected"
            ? validationFailureText(validation.reason, validation.details)
            : state.validatingId === candidate.id
              ? "validating…"
              : "not validated",
      );
      const actions = create("div", "osme-candidate-actions");
      const focus = create("button", "osme-button osme-small", "Focus");
      focus.type = "button";
      focus.dataset.action = "focus-candidate";
      focus.dataset.id = candidate.id;
      const validate = create("button", "osme-button osme-small", "Validate");
      validate.type = "button";
      validate.dataset.action = "validate-candidate";
      validate.dataset.id = candidate.id;
      validate.disabled = Boolean(
        state.validatingBatch ||
        state.validatingId ||
        state.connectingId ||
        mutationLocked,
      );
      const connect = create("button", "osme-button osme-primary osme-small", "Connect");
      connect.type = "button";
      connect.dataset.action = "connect-candidate";
      connect.dataset.id = candidate.id;
      connect.disabled =
        validation.status !== "valid" ||
        Boolean(
          state.validatingBatch ||
          state.validatingId ||
          state.connectingId ||
          mutationLocked,
        );
      if (state.connectingId === candidate.id) connect.textContent = "Creating…";
      actions.append(focus, validate, connect);
      card.append(copy, status, actions);
      elements.candidates.append(card);
    }
  }

  function render() {
    root.dataset.open = String(state.panelOpen);
    root.dataset.panelLayout = state.panelLayout;
    syncPanelLayout();
    elements.panel.hidden = !state.panelOpen;
    elements.launch.hidden = state.panelOpen;
    elements.search.value = state.query;
    elements.searchKind.value = state.searchKind;
    elements.searchSort.value = state.searchSortBy;
    elements.searchDirection.textContent = state.searchDescending ? "↓" : "↑";
    elements.searchDirection.title = state.searchDescending
      ? "Descending; click for ascending"
      : "Ascending; click for descending";
    elements.radius.value = String(state.radiusMeters);
    for (const button of elements.layoutControls.querySelectorAll("[data-panel-layout]")) {
      button.dataset.active = String(button.dataset.panelLayout === state.panelLayout);
      button.setAttribute("aria-pressed", button.dataset.active);
    }
    elements.status.textContent = state.status;
    elements.status.dataset.kind = state.statusKind;
    renderSummary();
    renderSearch();
    renderInspector();
    ensureValidationContext();
    renderConnect();
    syncOverlayControls();
    state.lastOverlayKey = "";
  }

  function snapshotFingerprint(snapshot) {
    return JSON.stringify([
      snapshot?.map?.id || "",
      snapshot?.editIndex ?? null,
      snapshot?.undoDepth ?? null,
      (snapshot?.waypoints || []).length,
      (snapshot?.edges || []).length,
      (snapshot?.areas || []).length,
      (snapshot?.actions || []).length,
      snapshot?.selectedWaypointIds || [],
      snapshot?.selectedEdgeIds || [],
      snapshot?.currentActionId || "",
    ]);
  }

  async function refreshSnapshot({ quiet = false, allowBusy = false, force = false } = {}) {
    if (state.disposed) return null;
    if (
      state.snapshotInFlight ||
      !currentMapId() ||
      (
        !allowBusy &&
        (state.validatingBatch || state.validatingId || state.connectingId)
      )
    ) return;
    state.snapshotInFlight = true;
    try {
      const response = await requestBridge("snapshot", {}, 10000);
      if (
        !allowBusy &&
        (state.validatingBatch || state.validatingId || state.connectingId)
      ) return;
      const nextFingerprint = snapshotFingerprint(response.snapshot);
      const snapshotChanged = nextFingerprint !== state.snapshotFingerprint;
      state.snapshot = response.snapshot;
      state.snapshotFingerprint = nextFingerprint;
      if (snapshotChanged) state.snapshotRevision += 1;
      const firstSuccessfulSnapshot = !state.hasSuccessfulSnapshot;
      state.hasSuccessfulSnapshot = true;
      if (!snapshotChanged && !force) return state.snapshot;
      ensureValidationContext();
      const showingLiveRefreshStatus =
        state.statusKind === "ok" &&
        state.status.startsWith("Live graph refreshed:");
      if (!quiet || firstSuccessfulSnapshot || showingLiveRefreshStatus) {
        setStatus(
          `Live graph refreshed: ${state.snapshot.waypoints.length} waypoints, ` +
          `${state.snapshot.edges.length} edges.`,
          "ok",
        );
      }
      render();
      window.dispatchEvent(new CustomEvent(instanceEvents.snapshot, {
        detail: {
          mapId: state.snapshot.map.id,
          editIndex: state.snapshot.editIndex,
          revision: state.snapshotRevision,
          changed: snapshotChanged,
        },
      }));
      return state.snapshot;
    } catch (error) {
      if (!quiet) setStatus(friendlyError(error.message), "error");
    } finally {
      state.snapshotInFlight = false;
    }
  }

  async function selectOrFocus(result, select) {
    const waypointIds = resultWaypointIds(result);
    if (!waypointIds.length) return;
    try {
      await requestBridge(select ? "select_waypoint" : "focus", { waypointIds });
      setStatus(
        select ? "Waypoint selected in Orbit." : `Focused ${waypointIds.length} waypoint(s).`,
        "ok",
      );
      await refreshSnapshot({ quiet: true, allowBusy: true });
    } catch (error) {
      setStatus(friendlyError(error.message), "error");
    }
  }

  async function validateCandidate(candidateId, { renderProgress = true } = {}) {
    const baseId = selectedBaseId();
    if (!baseId || !candidateId) return false;
    const frozenContext = currentValidationContext();
    state.validatingId = candidateId;
    if (renderProgress) renderConnect();
    try {
      const response = await requestBridge(
        "validate_connect",
        { waypointIds: [baseId, candidateId] },
        18000,
      );
      if (frozenContext !== currentValidationContext()) {
        throw new Error("orbit_map_changed");
      }
      state.validation.set(candidateId, {
        status: response.valid ? "valid" : "rejected",
        reason: response.reason || "",
        details: Array.isArray(response.details) ? response.details : [],
      });
      return response.valid;
    } catch (error) {
      state.validation.set(candidateId, {
        status: "rejected",
        reason: error.message,
        details: [],
      });
      if (error.mutationMayExist) throw error;
      return false;
    } finally {
      state.validatingId = "";
      if (renderProgress) renderConnect();
      state.lastOverlayKey = "";
    }
  }

  async function validateVisible() {
    const visible = candidates().slice(0, MAX_NATIVE_VALIDATIONS);
    if (!visible.length || state.validatingBatch) return;
    const frozenContext = currentValidationContext();
    state.validatingBatch = true;
    setStatus(
      `Validating up to ${visible.length} nearby candidates. Orbit selection will be restored.`,
    );
    render();
    let validCount = 0;
    try {
      for (const [index, candidate] of visible.entries()) {
        if (frozenContext !== currentValidationContext()) {
          throw new Error("orbit_map_changed");
        }
        setStatus(
          `Validating candidate ${index + 1}/${visible.length}: ` +
          `${candidate.name || model.shortId(candidate.id)}`,
        );
        if (await validateCandidate(candidate.id, { renderProgress: false })) {
          validCount += 1;
        }
        renderConnect();
      }
      setStatus(
        `Validation complete: ${validCount} connectable, ` +
        `${visible.length - validCount} rejected. No draft was created.`,
        "ok",
      );
    } catch (error) {
      setStatus(
        error.mutationMayExist
          ? `${friendlyError(error.message)}. Orbit may contain an unverified unsaved change; ` +
            unverifiedMutationGuidance(error)
          : friendlyError(error.message),
        "error",
      );
    } finally {
      state.validatingBatch = false;
      render();
    }
  }

  async function connectCandidate(candidateId) {
    const baseId = selectedBaseId();
    const candidate = candidates().find((item) => item.id === candidateId);
    const validation = candidateStatus(candidateId);
    if (
      !baseId ||
      !candidate ||
      validation.status !== "valid" ||
      state.pendingConnectId !== candidateId
    ) return;
    const frozenMapId = state.snapshot?.map?.id;
    const frozenContext = currentValidationContext();
    state.pendingConnectId = "";
    state.connectingId = candidateId;
    renderConnect();
    try {
      if (
        frozenMapId !== currentMapId() ||
        frozenContext !== currentValidationContext()
      ) throw new Error("orbit_map_changed");
      const response = await requestBridge(
        "connect",
        { waypointIds: [baseId, candidateId] },
        18000,
      );
      if (!response.added) throw new Error("edge_draft_not_created");
      setStatus(
        "Orbit created one unsaved Connect change. Review it, then Save or Undo in Orbit.",
        "ok",
      );
      await refreshSnapshot({ quiet: true, allowBusy: true });
    } catch (error) {
      if (error.mutationMayExist) {
        await refreshSnapshot({ quiet: true, allowBusy: true });
        setStatus(
          `${friendlyError(error.message)}. Orbit may contain an unverified unsaved change; ` +
          unverifiedMutationGuidance(error),
          "error",
        );
      } else {
        setStatus(`${friendlyError(error.message)}. No mutation was verified.`, "error");
      }
    } finally {
      state.connectingId = "";
      render();
    }
  }

  function reviewConnectCandidate(candidateId) {
    const candidate = candidates().find((item) => item.id === candidateId);
    if (!candidate || candidateStatus(candidateId).status !== "valid") return;
    state.pendingConnectId = candidateId;
    setStatus(
      "Review the exact Site Map and waypoint pair, then create or cancel the unsaved draft.",
    );
    renderConnect();
  }

  function actionNameLabelDensity(zoom) {
    return labelDensity(ACTION_NAME_LABEL_DENSITY_STEPS, zoom);
  }

  function drawOverlay() {
    if (!state.snapshot) {
      elements.overlay.replaceChildren();
      return;
    }
    const advancedOverlay =
      globalThis.OrbitSiteMapEditorAdvanced?.overlayState?.() || {};
    const actionNameLabelsVisible = Boolean(advancedOverlay.actionNameLabelsVisible);
    const areaOverlay = globalThis.OrbitSiteMapEditorAreas?.overlayState?.() || {};
    const detailedVisible = Boolean(state.overlay.global.enabled);
    const areaLabelsVisible = Boolean(detailedVisible && state.overlay.area.enabled);
    if (!detailedVisible && !actionNameLabelsVisible) {
      elements.overlay.replaceChildren();
      return;
    }
    const canvas = document.querySelector("canvas");
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const params = new URL(location.href).searchParams;
    const cameraX = Number(params.get("x"));
    const cameraY = Number(params.get("y"));
    const zoom = Number(params.get("zoom"));
    if (![cameraX, cameraY, zoom].every(Number.isFinite) || zoom <= 0) return;
    const walkOverlay =
      globalThis.OrbitSiteMapEditorWalk?.overlayState?.() || {};
    const advancedOverlayKey = String(advancedOverlay.revision || 0);
    const walkOverlayKey = String(walkOverlay.revision || 0);
    const areaOverlayKey = String(areaOverlay.revision || 0);
    const overlayKey = [
      rect.left,
      rect.top,
      rect.width,
      rect.height,
      cameraX,
      cameraY,
      zoom,
      state.snapshot.editIndex,
      state.snapshot.selectedWaypointIds.join(","),
      state.validationContext,
      [...state.validation.entries()].map(([id, item]) => `${id}:${item.status}`).join(","),
      JSON.stringify(state.overlay),
      advancedOverlayKey,
      walkOverlayKey,
      areaOverlayKey,
      areaLabelsVisible,
    ].join("|");
    if (overlayKey === state.lastOverlayKey) return;
    state.lastOverlayKey = overlayKey;
    const {
      actionNameGroup,
      areaLabelGroup,
      group,
      inside,
      project,
    } = overlayRenderer.createFrame(elements.overlay, {
      rect,
      cameraX,
      cameraY,
      zoom,
      cameraWidthMeters: CAMERA_WIDTH_METERS,
      detailedVisible,
    });
    const liveGraph = graph();
    const workWaypointIds = new Set(
      state.overlay.global.fields.selection
        ? advancedOverlay.selection?.waypointIds || []
        : [],
    );
    const workEdgeIds = new Set(
      state.overlay.global.fields.selection
        ? advancedOverlay.selection?.edgeIds || []
        : [],
    );
    const findingWaypointIds = new Set(
      state.overlay.global.fields.findings
        ? advancedOverlay.findingWaypointIds || []
        : [],
    );
    const findingEdgeIds = new Set(
      state.overlay.global.fields.findings
        ? advancedOverlay.findingEdgeIds || []
        : [],
    );
    const componentByWaypoint = state.overlay.global.fields.components
      ? globalThis.OrbitSiteMapEditorValidation?.topology?.(state.snapshot)
          ?.componentByWaypoint || new Map()
      : new Map();
    const selectedEdgeIds = new Set(state.snapshot.selectedEdgeIds || []);
    const edgeFlags = (edge) => {
      const id = edge.id || model.edgeKey(edge.from, edge.to);
      const key = model.edgeKey(edge.from, edge.to);
      const selected = selectedEdgeIds.has(id) || selectedEdgeIds.has(key);
      const work = workEdgeIds.has(id) || workEdgeIds.has(key);
      const finding = findingEdgeIds.has(id) || findingEdgeIds.has(key);
      return { finding, id, priority: selected || work || finding, selected, work };
    };

    if (state.overlay.edge.enabled) {
      let drawnEdges = 0;
      const edgeLabelDensity = labelDensity(EDGE_LABEL_DENSITY_STEPS, zoom);
      const edgeLabelCandidatesByCell = new Map();
      const orderedEdges = [...state.snapshot.edges].sort((left, right) =>
        Number(edgeFlags(right).priority) - Number(edgeFlags(left).priority)
      );
      for (const edge of orderedEdges) {
        if (drawnEdges >= MAX_OVERLAY_EDGES) break;
        const fromPosition = liveGraph.waypointById.get(edge.from)?.position;
        const toPosition = liveGraph.waypointById.get(edge.to)?.position;
        if (!model.finitePosition(fromPosition) || !model.finitePosition(toPosition)) {
          continue;
        }
        const from = project(fromPosition);
        const to = project(toPosition);
        if (!inside(from, 80) && !inside(to, 80)) continue;
        const { finding, id, priority, work } = edgeFlags(edge);
        const color =
          work
            ? "#fbbf24"
            : finding
              ? "#fb7185"
              : edge.manual
                ? "#2dd4bf"
                : edge.crossRecording
                  ? "#c084fc"
                  : "#94a3b8";
        const lineAttributes = {
          x1: from.x,
          y1: from.y,
          x2: to.x,
          y2: to.y,
          stroke: color,
          "stroke-width":
            work || finding
              ? 3
              : edge.manual ? 2.4 : 1.4,
          opacity: edge.manual ? 0.82 : 0.46,
        };
        if (state.overlay.edge.fields.connectionDirection) {
          lineAttributes["marker-end"] = "url(#osme-edge-arrow)";
        }
        group.append(svgElement("line", lineAttributes));
        const labelParts = overlaySettings.edgeParts(edge, state.overlay);
        if (labelParts.length) {
          const point = {
            x: (from.x + to.x) / 2,
            y: (from.y + to.y) / 2 - 4,
          };
          const key = priority
            ? `priority:${id}`
            : edgeLabelDensity.cellWidth
              ? `cell:${Math.floor((point.x - rect.left) /
                  edgeLabelDensity.cellWidth)}:` +
                `${Math.floor((point.y - rect.top) /
                  edgeLabelDensity.cellHeight)}`
              : `edge:${id}`;
          const candidate = {
            id,
            labelParts,
            point,
            priority,
            rank: stableStringHash(id) >>> 0,
          };
          const previous = edgeLabelCandidatesByCell.get(key);
          if (!previous || candidate.rank < previous.rank) {
            edgeLabelCandidatesByCell.set(key, candidate);
          }
        }
        drawnEdges += 1;
      }
      const priorityLabels = [];
      const regularLabels = [];
      const edgeLabelCandidates = [...edgeLabelCandidatesByCell.values()].sort(
        (left, right) =>
          Number(right.priority) - Number(left.priority) ||
          left.point.y - right.point.y ||
          left.point.x - right.point.x,
      );
      for (const candidate of edgeLabelCandidates) {
        if (!candidate.priority && regularLabels.length >= MAX_OVERLAY_EDGE_LABELS) {
          continue;
        }
        const text = svgElement("text", {
          x: candidate.point.x,
          y: candidate.point.y,
          class: "osme-map-label osme-edge-label",
        });
        setOverlayLabel(text, candidate.labelParts);
        if (candidate.priority) priorityLabels.push(text);
        else regularLabels.push(text);
      }
      group.append(...regularLabels);
      group.append(...priorityLabels);
    }

    function drawWaypointRoute(
      waypointIds,
      {
        color,
        width,
        opacity,
        dash = "",
        stale = false,
      },
      segmentBudget,
    ) {
      let drawn = 0;
      for (
        let index = 0;
        index < waypointIds.length - 1 && drawn < segmentBudget;
        index += 1
      ) {
        const fromPosition = liveGraph.waypointById.get(
          waypointIds[index],
        )?.position;
        const toPosition = liveGraph.waypointById.get(
          waypointIds[index + 1],
        )?.position;
        if (
          !model.finitePosition(fromPosition) ||
          !model.finitePosition(toPosition)
        ) continue;
        const from = project(fromPosition);
        const to = project(toPosition);
        if (!inside(from, 80) && !inside(to, 80)) continue;
        const attributes = {
          x1: from.x,
          y1: from.y,
          x2: to.x,
          y2: to.y,
          stroke: stale ? "#fb7185" : color,
          "stroke-width": width,
          opacity,
        };
        if (dash || stale) {
          attributes["stroke-dasharray"] = stale ? "4 4" : dash;
        }
        if (index % 12 === 0) {
          attributes["marker-end"] = "url(#osme-edge-arrow)";
        }
        group.append(svgElement("line", attributes));
        drawn += 1;
      }
      return drawn;
    }

    let remainingWalkSegments = MAX_WALK_OVERLAY_SEGMENTS;
    for (const component of walkOverlay.coverageComponents || []) {
      if (remainingWalkSegments <= 0) break;
      const drawn = drawWaypointRoute(
        component.waypointWalk || [],
        {
          color: recordingColor(`walk-${component.componentIndex}`),
          width: 3,
          opacity: 0.86,
          stale: Boolean(walkOverlay.stale),
        },
        remainingWalkSegments,
      );
      remainingWalkSegments -= drawn;
    }

    let gapMarkers = 0;
    for (const waypointId of walkOverlay.siteViewGapWaypointIds || []) {
      if (gapMarkers >= MAX_WALK_OVERLAY_MARKERS) break;
      const position = liveGraph.waypointById.get(waypointId)?.position;
      if (!model.finitePosition(position)) continue;
      const point = project(position);
      if (!inside(point)) continue;
      group.append(svgElement("circle", {
        cx: point.x,
        cy: point.y,
        r: 7,
        fill: "none",
        stroke: "#f472b6",
        "stroke-width": 2,
        "stroke-dasharray": "2 2",
        opacity: 0.9,
      }));
      gapMarkers += 1;
    }

    const baseId = selectedBaseId();
    const candidateById = new Map(candidates().map((item) => [item.id, item]));
    const basePosition = liveGraph.waypointById.get(baseId)?.position;
    if (model.finitePosition(basePosition)) {
      const basePoint = project(basePosition);
      for (const candidate of candidateById.values()) {
        const point = project(candidate.position);
        if (!inside(point)) continue;
        const validation = candidateStatus(candidate.id);
        const color =
          validation.status === "valid"
            ? "#34d399"
            : validation.status === "rejected"
              ? "#fb7185"
              : "#94a3b8";
        group.append(
          svgElement("line", {
            x1: basePoint.x,
            y1: basePoint.y,
            x2: point.x,
            y2: point.y,
            stroke: color,
            "stroke-width": 1.5,
            "stroke-dasharray": validation.status === "valid" ? "none" : "5 4",
            opacity: 0.72,
          }),
        );
      }
    }

    if (state.overlay.waypoint.enabled) {
      let drawnWaypoints = 0;
      const selectedWaypointIds = new Set(state.snapshot.selectedWaypointIds || []);
      const waypointLabelDensity = labelDensity(WAYPOINT_LABEL_DENSITY_STEPS, zoom);
      const waypointLabelCandidatesByCell = new Map();
      const waypointPriority = (waypoint) =>
        selectedWaypointIds.has(waypoint.id) ||
        candidateById.has(waypoint.id) ||
        workWaypointIds.has(waypoint.id) ||
        findingWaypointIds.has(waypoint.id);
      const orderedWaypoints = [...state.snapshot.waypoints].sort((left, right) =>
        Number(waypointPriority(right)) - Number(waypointPriority(left))
      );
      for (const waypoint of orderedWaypoints) {
        if (
          drawnWaypoints >= MAX_OVERLAY_WAYPOINTS ||
          !model.finitePosition(waypoint.position)
        ) continue;
        const point = project(waypoint.position);
        if (!inside(point)) continue;
        const candidate = candidateById.get(waypoint.id);
        const validation = candidateStatus(waypoint.id);
        const selected = selectedWaypointIds.has(waypoint.id);
        const priority = waypointPriority(waypoint);
        const componentIndex = componentByWaypoint.get(waypoint.id);
        const color = selected
          ? "#fbbf24"
          : workWaypointIds.has(waypoint.id)
            ? "#38bdf8"
            : findingWaypointIds.has(waypoint.id)
              ? "#fb7185"
          : candidate
            ? validation.status === "valid"
              ? "#34d399"
              : validation.status === "rejected"
                ? "#fb7185"
                : "#cbd5e1"
            : Number.isInteger(componentIndex)
              ? recordingColor(`component-${componentIndex}`)
              : recordingColor(waypoint.recordingId);
        group.append(
          svgElement("circle", {
            cx: point.x,
            cy: point.y,
            r:
              selected ? 7
              : workWaypointIds.has(waypoint.id) || findingWaypointIds.has(waypoint.id)
                ? 5.5
                : candidate ? 5.5 : 3,
            fill: color,
            stroke: "#07111d",
            "stroke-width": selected || candidate ? 2 : 1,
            opacity: selected || candidate ? 1 : 0.76,
          }),
        );
        const parts = overlaySettings.waypointParts(waypoint, state.overlay);
        if (parts.length) {
          const labelPoint = { x: point.x + 8, y: point.y - 7 };
          const key = priority
            ? `priority:${waypoint.id}`
            : waypointLabelDensity.cellWidth
              ? `cell:${Math.floor((labelPoint.x - rect.left) /
                  waypointLabelDensity.cellWidth)}:` +
                `${Math.floor((labelPoint.y - rect.top) /
                  waypointLabelDensity.cellHeight)}`
              : `waypoint:${waypoint.id}`;
          const labelCandidate = {
            id: waypoint.id,
            parts,
            point: labelPoint,
            priority,
            rank: stableStringHash(waypoint.id) >>> 0,
          };
          const previous = waypointLabelCandidatesByCell.get(key);
          if (!previous || labelCandidate.rank < previous.rank) {
            waypointLabelCandidatesByCell.set(key, labelCandidate);
          }
        }
        drawnWaypoints += 1;
      }
      const waypointLabels = [...waypointLabelCandidatesByCell.values()].sort(
        (left, right) =>
          Number(left.priority) - Number(right.priority) ||
          left.point.y - right.point.y ||
          left.point.x - right.point.x,
      );
      for (const candidate of waypointLabels) {
        const label = svgElement("text", {
          x: candidate.point.x,
          y: candidate.point.y,
          class: "osme-map-label",
        });
        setOverlayLabel(label, candidate.parts);
        group.append(label);
      }
    }

    const actionLabelDensity = actionNameLabelDensity(zoom);
    const actionLabelCandidatesByCell = new Map();
    const actionNameLabels = actionNameLabelsVisible
      ? advancedOverlay.actionNameLabels || []
      : [];
    for (const item of actionNameLabels) {
      const position = item.position;
      if (!model.finitePosition(position)) continue;
      const point = project(position);
      if (!inside(point)) continue;
      let cellKey = `action:${item.id}`;
      if (actionLabelDensity.cellWidth) {
        const cellX = Math.floor((point.x - rect.left) / actionLabelDensity.cellWidth);
        const cellY = Math.floor((point.y - rect.top) / actionLabelDensity.cellHeight);
        cellKey = `${cellX}:${cellY}`;
      }
      const candidate = {
        item,
        point,
        rank: stableStringHash(item.id) >>> 0,
      };
      const existing = actionLabelCandidatesByCell.get(cellKey);
      if (!existing || candidate.rank < existing.rank) {
        actionLabelCandidatesByCell.set(cellKey, candidate);
      }
    }
    const actionLabelCandidates = [...actionLabelCandidatesByCell.values()].sort(
      (left, right) => left.point.y - right.point.y || left.point.x - right.point.x,
    );
    for (const { item, point } of actionLabelCandidates) {
      const displayName = item.name.length > 72
        ? `${item.name.slice(0, 71)}…`
        : item.name;
      const x = point.x + 11;
      const y = point.y + 13;
      const width = Math.min(440, Math.max(68, displayName.length * 5.8 + 12));
      actionNameGroup.append(
        svgElement("rect", {
          x: x - 4,
          y: y - 10,
          width,
          height: 14,
          rx: 3,
          class: "osme-action-name-label-bg",
        }),
      );
      const label = svgElement("text", {
        x,
        y,
        class: "osme-action-name-label",
      });
      label.textContent = displayName;
      actionNameGroup.append(label);
    }

    if (areaLabelsVisible) {
      const areaCandidatesByCell = new Map();
      const selectedAreaIds = new Set(areaOverlay.selectedIds || []);
      const areaLabelDensity = labelDensity(AREA_LABEL_DENSITY_STEPS, zoom);
      const { cellHeight, cellWidth } = areaLabelDensity;
      const areaRecords = [...areaRecordsForOverlay()].sort((left, right) =>
        Number(selectedAreaIds.has(right.id)) - Number(selectedAreaIds.has(left.id)) ||
        left.id.localeCompare(right.id)
      );
      const allowedCallbackPaths = new Map(
        areaFieldCatalogForOverlay().map((field) => [field.path, field]),
      );
      let scannedAreas = 0;
      for (const area of areaRecords) {
        const item = {
          ...area,
          selected: selectedAreaIds.has(area.id),
        };
        if (!model.finitePosition(item.position)) continue;
        const point = project(item.position);
        if (!inside(point, 80)) continue;
        if (scannedAreas >= MAX_OVERLAY_AREA_SCAN) break;
        scannedAreas += 1;
        const parts = overlaySettings.areaParts(
          item,
          state.overlay,
          allowedCallbackPaths,
        );
        if (!parts.length) continue;
        const key = item.selected
          ? `selected:${item.id}`
          : cellWidth
            ? `cell:${Math.floor((point.x - rect.left) / cellWidth)}:` +
              `${Math.floor((point.y - rect.top) / cellHeight)}`
            : `area:${item.id}`;
        const candidate = {
          item,
          parts,
          point,
          rank: item.selected ? -1 : stableStringHash(item.id) >>> 0,
        };
        const previous = areaCandidatesByCell.get(key);
        if (!previous || candidate.rank < previous.rank) {
          areaCandidatesByCell.set(key, candidate);
        }
      }
      const areaCandidates = [...areaCandidatesByCell.values()]
        .sort((left, right) =>
          Number(right.item.selected) - Number(left.item.selected) ||
          left.point.y - right.point.y ||
          left.point.x - right.point.x
        )
        .slice(0, MAX_OVERLAY_AREAS);
      for (const { item, parts, point } of areaCandidates) {
        const summary = overlayRenderer.boundedLabel(parts);
        const display = summary.display;
        if (!display) continue;
        const x = point.x + 9;
        const y = point.y - 9;
        areaLabelGroup.append(svgElement("circle", {
          cx: point.x,
          cy: point.y,
          r: item.selected ? 6 : 4,
          class: item.selected
            ? "osme-area-label-marker osme-area-label-marker-selected"
            : "osme-area-label-marker",
        }));
        const width = Math.min(620, Math.max(86, display.length * 5.6 + 14));
        areaLabelGroup.append(svgElement("rect", {
          x: x - 4,
          y: y - 10,
          width,
          height: 15,
          rx: 3,
          class: item.selected
            ? "osme-area-label-bg osme-area-label-bg-selected"
            : "osme-area-label-bg",
        }));
        const label = svgElement("text", {
          x,
          y,
          class: "osme-area-label",
        });
        setOverlayLabel(label, parts);
        areaLabelGroup.append(label);
      }
    }

    let exclusionMarkers = 0;
    for (const waypointId of walkOverlay.excludedWaypointIds || []) {
      if (exclusionMarkers >= MAX_WALK_OVERLAY_MARKERS) break;
      const position = liveGraph.waypointById.get(waypointId)?.position;
      if (!model.finitePosition(position)) continue;
      const point = project(position);
      if (!inside(point)) continue;
      group.append(svgElement("circle", {
        cx: point.x,
        cy: point.y,
        r: 9,
        fill: "#07111d",
        stroke: "#fb7185",
        "stroke-width": 2.5,
        opacity: 0.94,
      }));
      for (const [x1, y1, x2, y2] of [
        [point.x - 5, point.y - 5, point.x + 5, point.y + 5],
        [point.x + 5, point.y - 5, point.x - 5, point.y + 5],
      ]) {
        group.append(svgElement("line", {
          x1,
          y1,
          x2,
          y2,
          stroke: "#fb7185",
          "stroke-width": 2.5,
          "stroke-linecap": "round",
        }));
      }
      exclusionMarkers += 1;
    }

    const routeTargetsByWaypoint = new Map();
    for (const marker of walkOverlay.routeTargetMarkers || []) {
      if (!routeTargetsByWaypoint.has(marker.waypointId)) {
        routeTargetsByWaypoint.set(marker.waypointId, []);
      }
      routeTargetsByWaypoint.get(marker.waypointId).push(marker.sequence);
    }
    let routeTargetMarkers = 0;
    for (const [waypointId, sequences] of routeTargetsByWaypoint.entries()) {
      if (routeTargetMarkers >= MAX_WALK_OVERLAY_MARKERS) break;
      const position = liveGraph.waypointById.get(waypointId)?.position;
      if (!model.finitePosition(position)) continue;
      const point = project(position);
      if (!inside(point)) continue;
      group.append(svgElement("rect", {
        x: point.x - 5,
        y: point.y - 5,
        width: 10,
        height: 10,
        rx: 2,
        fill: "#f59e0b",
        stroke: "#07111d",
        "stroke-width": 1.5,
        opacity: 0.96,
        transform: `rotate(45 ${point.x} ${point.y})`,
      }));
      const label = svgElement("text", {
        x: point.x + 8,
        y: point.y + 3,
        class: "osme-map-label",
      });
      const sorted = sequences.sort((left, right) => left - right);
      label.textContent =
        sorted.length === 1
          ? `#${sorted[0]}`
          : `#${sorted[0]}…#${sorted.at(-1)}`;
      group.append(label);
      routeTargetMarkers += 1;
    }
  }

  const animationLoop = overlayRenderer.createAnimationLoop({
    draw: drawOverlay,
    shouldContinue: () => !state.disposed && root.isConnected,
    schedule: (callback) => {
      overlayAnimationId = window.requestAnimationFrame(callback);
    },
  });

  elements.close.addEventListener("click", () => {
    state.panelOpen = false;
    persist();
    render();
  });
  elements.launch.addEventListener("click", () => {
    state.panelOpen = true;
    persist();
    render();
  });
  elements.layoutControls.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-panel-layout]");
    if (!button) return;
    state.panelLayout = panelLayout.normalize(button.dataset.panelLayout);
    persist();
    render();
  });
  elements.refresh.addEventListener("click", () => refreshSnapshot({force: true}));
  elements.search.addEventListener("input", (event) => {
    state.query = event.target.value;
    renderSearch();
  });
  elements.searchKind.addEventListener("change", (event) => {
    state.searchKind = event.target.value;
    renderSearch();
  });
  elements.searchSort.addEventListener("change", (event) => {
    state.searchSortBy = event.target.value;
    persist();
    renderSearch();
  });
  elements.searchDirection.addEventListener("click", () => {
    state.searchDescending = !state.searchDescending;
    persist();
    render();
  });
  elements.radius.addEventListener("change", (event) => {
    const value = Number(event.target.value);
    state.radiusMeters = Number.isFinite(value)
      ? Math.min(100, Math.max(0.5, value))
      : model.DEFAULT_RADIUS_METERS;
    state.validation.clear();
    persist();
    render();
  });
  elements.validateVisible.addEventListener("click", validateVisible);
  elements.cancelConnect.addEventListener("click", () => {
    state.pendingConnectId = "";
    setStatus("Connect cancelled. Orbit graph data was not changed.");
    renderConnect();
  });
  elements.confirmConnect.addEventListener("click", () => {
    if (state.pendingConnectId) connectCandidate(state.pendingConnectId);
  });
  elements.overlayControls.addEventListener("change", (event) => {
    const input = event.target?.closest("input[data-overlay-group]");
    const group = input?.dataset.overlayGroup;
    if (
      !input ||
      !Object.prototype.hasOwnProperty.call(state.overlay, group) ||
      !state.overlay[group]
    ) return;
    if (input.dataset.overlayEnabled) {
      state.overlay[group].enabled = Boolean(input.checked);
    } else if (
      input.dataset.overlayField &&
      Object.prototype.hasOwnProperty.call(
        state.overlay[group].fields,
        input.dataset.overlayField,
      )
    ) {
      state.overlay[group].fields[input.dataset.overlayField] = Boolean(input.checked);
    } else if (group === "area" && input.dataset.overlayCallbackPath) {
      const path = input.dataset.overlayCallbackPath;
      if (!areaFieldCatalogForOverlay().some((field) => field.path === path)) return;
      if (!overlaySettings.setCallbackFieldPreference(
        state.overlay,
        path,
        Boolean(input.checked),
      )) return;
    } else return;
    state.lastOverlayKey = "";
    syncOverlayControls();
    persist();
  });
  elements.overlayControls.addEventListener("input", (event) => {
    if (event.target?.matches?.('[data-overlay-callback-filter="area"]')) {
      filterAreaCallbackControls();
    }
  });
  elements.overlayControls.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-overlay-fields-action]");
    if (!button) return;
    const group = button.dataset.overlayGroup;
    const descriptor = overlaySettings.CONTROL_GROUPS.find(
      (item) => item.id === group,
    );
    if (!descriptor || !state.overlay[group]) return;
    const enabled = button.dataset.overlayFieldsAction === "all";
    for (const field of descriptor.sections.flatMap((section) => section.fields)) {
      state.overlay[group].fields[field.id] = enabled;
    }
    if (group === "area") {
      state.overlay.area.callbackFieldDefault = enabled;
      state.overlay.area.callbackFields = {};
    }
    state.lastOverlayKey = "";
    syncOverlayControls();
    persist();
  });
  elements.searchResults.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const results = JSON.parse(elements.searchResults.dataset.results || "[]");
    const result = results[Number(button.dataset.index)];
    if (!result) return;
    if (button.dataset.action === "add-result") {
      window.dispatchEvent(new CustomEvent(instanceEvents.addSelection, { detail: result }));
    } else {
      selectOrFocus(result, button.dataset.action === "select-result");
    }
  });
  elements.candidates.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const candidateId = button.dataset.id;
    if (button.dataset.action === "focus-candidate") {
      requestBridge("focus", { waypointIds: [selectedBaseId(), candidateId] })
        .then(() => setStatus("Focused the candidate pair in Orbit.", "ok"))
        .catch((error) => setStatus(friendlyError(error.message), "error"));
    } else if (button.dataset.action === "validate-candidate") {
      validateCandidate(candidateId).then((valid) => {
        setStatus(
          valid
            ? "Orbit validated this pair. No draft was created."
            : validationFailureText(
              candidateStatus(candidateId).reason,
              candidateStatus(candidateId).details,
            ),
          valid ? "ok" : "warning",
        );
        render();
      }).catch((error) => {
        setStatus(
          error.mutationMayExist
            ? `${friendlyError(error.message)}. Orbit may contain an unverified unsaved change; ` +
              unverifiedMutationGuidance(error)
            : friendlyError(error.message),
          "error",
        );
        render();
      });
    } else if (button.dataset.action === "connect-candidate") {
      reviewConnectCandidate(candidateId);
    }
  });

  function handleWindowMessage(event) {
    if (
      event.source !== window ||
      event.origin !== location.origin ||
      event.data?.channel !== BRIDGE_CHANNEL ||
      event.data?.sessionId && event.data.sessionId !== instanceId
    ) return;
    if (event.data.type === READY_TYPE) {
      if (event.data.sessionId && event.data.sessionId !== instanceId) return;
      state.bridgeReady = true;
      refreshSnapshot();
      return;
    }
    if (event.data.type === ACTION_SELECTION_TYPE) {
      window.dispatchEvent(new CustomEvent(instanceEvents.actionSelection, {
        detail: { actionId: String(event.data.actionId || "") },
      }));
      return;
    }
    if (event.data.type !== RESPONSE_TYPE) return;
    const pending = state.pendingRequests.get(event.data.requestId);
    if (!pending) return;
    state.pendingRequests.delete(event.data.requestId);
    if (event.data.ok) pending.resolve(event.data);
    else {
      const error = new Error(event.data.error || "orbit_adapter_error");
      error.command = pending.command;
      error.mutationMayExist = Boolean(event.data.mutationMayExist);
      error.mutationContext = {
        command: pending.command,
        beforeEditIndex: event.data.beforeEditIndex ?? null,
        afterEditIndex: event.data.afterEditIndex ?? null,
        beforeUndoDepth: event.data.beforeUndoDepth ?? null,
        afterUndoDepth: event.data.afterUndoDepth ?? null,
        targetKeys: Array.isArray(event.data.targetKeys)
          ? [...event.data.targetKeys]
          : [...pending.mutationContext.targetKeys],
      };
      latchMutationUncertainty(pending.command, error);
      pending.reject(error);
    }
  }

  window.addEventListener("message", handleWindowMessage);
  window.addEventListener(DISPOSE_EVENT, handleExternalDispose);
  removeInvalidationListener = extensionContext.onInvalidated(deactivate);

  async function initialize() {
    const stored = (await storageGet())[STORAGE_KEY] || {};
    if (state.disposed || !extensionContext.isActive()) {
      deactivate();
      return;
    }
    state.panelOpen = stored.panelOpen !== false;
    state.panelLayout = panelLayout.normalize(stored.panelLayout);
    if (Number.isFinite(stored.radiusMeters)) {
      state.radiusMeters = Math.min(100, Math.max(0.5, stored.radiusMeters));
    }
    if (
      [
        "rank",
        "kind",
        "name",
        "id",
        "recordingName",
        "degree",
        "source",
        "status",
      ].includes(stored.searchSortBy)
    ) state.searchSortBy = stored.searchSortBy;
    state.searchDescending = Boolean(stored.searchDescending);
    if (stored.overlay && typeof stored.overlay === "object") {
      state.overlay = overlaySettings.normalizePreferences(stored.overlay);
    }
    syncOverlayControls();
    render();
    if (!extensionContext.isActive()) {
      setStatus(
        "Extension was reloaded. Reload this Orbit tab once to activate the new version.",
        "warning",
      );
      return;
    }
    const script = document.createElement("script");
    const bridgeUrl = extensionContext.getUrl("page-bridge.js");
    if (!bridgeUrl) {
      setStatus(
        "Extension was reloaded. Reload this Orbit tab once to activate the new version.",
        "warning",
      );
      return;
    }
    script.src = bridgeUrl;
    script.dataset.osmeSession = instanceId;
    script.addEventListener("load", () => script.remove());
    script.addEventListener("error", () => {
      setStatus("Could not load the Orbit page adapter.", "error");
      script.remove();
    });
    (document.head || document.documentElement).append(script);
    snapshotIntervalId = window.setInterval(() => {
      if (!extensionContext.isActive()) {
        deactivate();
        return;
      }
      refreshSnapshot({ quiet: true });
    }, SNAPSHOT_POLL_INTERVAL_MS);
    overlayAnimationId = window.requestAnimationFrame(animationLoop);
  }

  globalThis.OrbitSiteMapEditorRuntime = Object.freeze({
    areaRecords: areaRecordsForOverlay,
    currentMapId,
    dispose,
    disposeEvent: DISPOSE_EVENT,
    elements,
    friendlyError,
    graph,
    acknowledgeMutationUncertainty,
    instanceEvents,
    model,
    queryEngine,
    refreshSnapshot,
    requestBridge,
    instanceId,
    isDisposed: () => state.disposed,
    setStatus,
    state,
    unverifiedMutationGuidance,
    validationFailureText,
  });

  initialize();
})();
