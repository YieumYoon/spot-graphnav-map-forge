(() => {
  "use strict";

  const ROOT_ID = "orbit-site-map-editor-root";
  const STORAGE_KEY = "orbitSiteMapEditorPreferencesV1";
  const BRIDGE_CHANNEL = "orbit-site-map-editor-v1";
  const REQUEST_TYPE = "orbit-site-map-editor-request";
  const RESPONSE_TYPE = "orbit-site-map-editor-response";
  const READY_TYPE = "orbit-site-map-editor-ready";
  const DISPOSE_EVENT = "orbit-site-map-editor-dispose-v1";
  const SVG_NS = "http://www.w3.org/2000/svg";
  const CAMERA_WIDTH_METERS = 10;
  const SNAPSHOT_INTERVAL_MS = 1800;
  const MAX_NATIVE_VALIDATIONS = 12;
  const MAX_OVERLAY_WAYPOINTS = 350;
  const MAX_OVERLAY_EDGES = 750;
  const MAX_WALK_OVERLAY_SEGMENTS = 3000;
  const MAX_WALK_OVERLAY_MARKERS = 500;
  const MUTATION_COMMANDS = new Set([
    "connect",
    "archive_edges",
    "update_edge_settings",
  ]);
  const extensionContext = globalThis.OrbitSiteMapEditorExtensionContext;
  const model = globalThis.OrbitSiteMapEditorModel;
  const queryEngine = globalThis.OrbitSiteMapEditorQuery;

  if (!extensionContext || !model || !queryEngine) return;
  const instanceId =
    globalThis.crypto?.randomUUID?.() ||
    `osme-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const instanceEvents = Object.freeze({
    addSelection: `osme:add-selection:${instanceId}`,
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
    snapshotInFlight: false,
    hasSuccessfulSnapshot: false,
    bridgeReady: false,
    requestSequence: 0,
    pendingRequests: new Map(),
    status: "Waiting for Orbit's live Site Map…",
    statusKind: "neutral",
    panelOpen: true,
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
    overlay: {
      detailed: true,
      names: true,
      ids: false,
      recordings: false,
      degree: true,
      robot: false,
      timestamps: false,
      edges: true,
      edgeDetails: false,
      selection: true,
      findings: true,
      components: false,
    },
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
          <h2>Editor Assistant <span class="osme-version">0.5.0</span></h2>
        </div>
        <button class="osme-icon-button osme-close" type="button" aria-label="Collapse">×</button>
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
          <span class="osme-safety-chip">native draft</span>
        </div>
        <div class="osme-connect-controls">
          <label>Radius
            <input class="osme-radius" type="number" min="0.5" max="100" step="0.5" value="12">
            <span>m</span>
          </label>
          <button class="osme-button osme-validate-visible" type="button">
            Validate visible
          </button>
        </div>
        <div class="osme-connect-summary"></div>
        <div class="osme-connect-confirmation" hidden>
          <span class="osme-kind">review connect pair</span>
          <strong>Create one unsaved native Orbit draft?</strong>
          <div class="osme-connect-confirmation-details"></div>
          <div class="osme-connect-confirmation-actions">
            <button class="osme-button osme-cancel-connect" type="button">Cancel</button>
            <button class="osme-button osme-primary osme-confirm-connect" type="button">
              Create unsaved draft
            </button>
          </div>
        </div>
        <div class="osme-candidates"></div>
      </section>
      <section class="osme-section">
        <div class="osme-section-heading">
          <div><span>VIEW</span><strong>Detailed overlay</strong></div>
        </div>
        <div class="osme-overlay-controls">
          <label><input type="checkbox" data-overlay="detailed" checked> Enabled</label>
          <label><input type="checkbox" data-overlay="names" checked> Names</label>
          <label><input type="checkbox" data-overlay="ids"> IDs</label>
          <label><input type="checkbox" data-overlay="recordings"> Recordings</label>
          <label><input type="checkbox" data-overlay="degree" checked> Degree</label>
          <label><input type="checkbox" data-overlay="robot"> Robot</label>
          <label><input type="checkbox" data-overlay="timestamps"> Timestamp</label>
          <label><input type="checkbox" data-overlay="edges" checked> Edges</label>
          <label><input type="checkbox" data-overlay="edgeDetails"> Edge details</label>
          <label><input type="checkbox" data-overlay="selection" checked> Work selection</label>
          <label><input type="checkbox" data-overlay="findings" checked> Findings</label>
          <label><input type="checkbox" data-overlay="components"> Components</label>
        </div>
      </section>
      <footer class="osme-footer">
        Validation is selection-only. Connect creates one unsaved native Orbit draft and never presses Save.
      </footer>
    </aside>`;
  document.documentElement.append(root);

  const elements = {
    overlay: root.querySelector(".osme-overlay"),
    launch: root.querySelector(".osme-launch"),
    panel: root.querySelector(".osme-panel"),
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
  let removeInvalidationListener = () => {};

  function mutationTargetKeys(command, payload = {}) {
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
    return {
      command,
      beforeEditIndex: state.snapshot?.editIndex ?? null,
      afterEditIndex: null,
      beforeUndoDepth: state.snapshot?.history?.undoDepth ?? null,
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
      [snapshot.editIndex ?? "—", "draft index"],
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
        "span",
        "osme-validation",
        validation.status === "valid"
          ? "validated"
          : validation.status === "rejected"
            ? friendlyError(validation.reason)
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
    elements.status.textContent = state.status;
    elements.status.dataset.kind = state.statusKind;
    renderSummary();
    renderSearch();
    renderInspector();
    ensureValidationContext();
    renderConnect();
    state.lastOverlayKey = "";
  }

  async function refreshSnapshot({ quiet = false, allowBusy = false } = {}) {
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
      state.snapshot = response.snapshot;
      const firstSuccessfulSnapshot = !state.hasSuccessfulSnapshot;
      state.hasSuccessfulSnapshot = true;
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
        detail: { mapId: state.snapshot.map.id, editIndex: state.snapshot.editIndex },
      }));
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
      });
      return response.valid;
    } catch (error) {
      state.validation.set(candidateId, {
        status: "rejected",
        reason: error.message,
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
          ? `${friendlyError(error.message)}. An unverified native draft may exist; ` +
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
        `Orbit created one unsaved Connect Undo step ` +
        `(draft index +${response.draftIndexDelta ?? "?"}). ` +
        "Review it, then Save or Undo in Orbit.",
        "ok",
      );
      await refreshSnapshot({ quiet: true, allowBusy: true });
    } catch (error) {
      if (error.mutationMayExist) {
        await refreshSnapshot({ quiet: true, allowBusy: true });
        setStatus(
          `${friendlyError(error.message)}. An unverified native draft may exist; ` +
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

  function svgElement(name, attributes = {}) {
    const element = document.createElementNS(SVG_NS, name);
    for (const [key, value] of Object.entries(attributes)) {
      element.setAttribute(key, String(value));
    }
    return element;
  }

  function recordingColor(recordingId) {
    let hash = 2166136261;
    for (const character of String(recordingId || "")) {
      hash ^= character.codePointAt(0);
      hash = Math.imul(hash, 16777619);
    }
    return `hsl(${Math.abs(hash) % 360} 72% 58%)`;
  }

  function drawOverlay() {
    if (!state.overlay.detailed || !state.snapshot) {
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
    const advancedOverlay =
      globalThis.OrbitSiteMapEditorAdvanced?.overlayState?.() || {};
    const walkOverlay =
      globalThis.OrbitSiteMapEditorWalk?.overlayState?.() || {};
    const advancedOverlayKey = String(advancedOverlay.revision || 0);
    const walkOverlayKey = String(walkOverlay.revision || 0);
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
    ].join("|");
    if (overlayKey === state.lastOverlayKey) return;
    state.lastOverlayKey = overlayKey;
    elements.overlay.replaceChildren();

    const pixelsPerMeter = rect.width / CAMERA_WIDTH_METERS * zoom;
    const project = (position) => ({
      x: rect.left + rect.width / 2 + (position.x - cameraX) * pixelsPerMeter,
      y: rect.top + rect.height / 2 - (position.y - cameraY) * pixelsPerMeter,
    });
    const inside = (point, margin = 20) =>
      point.x >= rect.left - margin &&
      point.x <= rect.right + margin &&
      point.y >= rect.top - margin &&
      point.y <= rect.bottom + margin;
    const clipId = "osme-map-clip";
    const definitions = svgElement("defs");
    const clip = svgElement("clipPath", { id: clipId });
    clip.append(
      svgElement("rect", {
        x: rect.left,
        y: rect.top,
        width: rect.width,
        height: rect.height,
      }),
    );
    const edgeArrow = svgElement("marker", {
      id: "osme-edge-arrow",
      markerWidth: 7,
      markerHeight: 7,
      refX: 6,
      refY: 3.5,
      orient: "auto",
      markerUnits: "strokeWidth",
    });
    edgeArrow.append(svgElement("path", {
      d: "M 0 0 L 0 7 L 7 3.5 z",
      fill: "context-stroke",
    }));
    definitions.append(clip, edgeArrow);
    elements.overlay.append(definitions);
    const group = svgElement("g", { "clip-path": `url(#${clipId})` });
    elements.overlay.append(group);
    const liveGraph = graph();
    const workWaypointIds = new Set(
      state.overlay.selection ? advancedOverlay.selection?.waypointIds || [] : [],
    );
    const workEdgeIds = new Set(
      state.overlay.selection ? advancedOverlay.selection?.edgeIds || [] : [],
    );
    const findingWaypointIds = new Set(
      state.overlay.findings ? advancedOverlay.findingWaypointIds || [] : [],
    );
    const findingEdgeIds = new Set(
      state.overlay.findings ? advancedOverlay.findingEdgeIds || [] : [],
    );
    const componentByWaypoint = state.overlay.components
      ? globalThis.OrbitSiteMapEditorValidation?.topology?.(state.snapshot)
          ?.componentByWaypoint || new Map()
      : new Map();

    if (state.overlay.edges) {
      let drawnEdges = 0;
      for (const edge of state.snapshot.edges) {
        if (drawnEdges >= MAX_OVERLAY_EDGES) break;
        const fromPosition = liveGraph.waypointById.get(edge.from)?.position;
        const toPosition = liveGraph.waypointById.get(edge.to)?.position;
        if (!model.finitePosition(fromPosition) || !model.finitePosition(toPosition)) {
          continue;
        }
        const from = project(fromPosition);
        const to = project(toPosition);
        if (!inside(from, 80) && !inside(to, 80)) continue;
        const settings = model.importantSettings(edge.settings);
        const id = edge.id || model.edgeKey(edge.from, edge.to);
        const color =
          workEdgeIds.has(id) || workEdgeIds.has(model.edgeKey(edge.from, edge.to))
            ? "#fbbf24"
            : findingEdgeIds.has(id) ||
                findingEdgeIds.has(model.edgeKey(edge.from, edge.to))
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
            workEdgeIds.has(id) || findingEdgeIds.has(id)
              ? 3
              : edge.manual ? 2.4 : 1.4,
          opacity: edge.manual ? 0.82 : 0.46,
        };
        if (state.overlay.edgeDetails) {
          lineAttributes["marker-end"] = "url(#osme-edge-arrow)";
        }
        group.append(svgElement("line", lineAttributes));
        if (state.overlay.edgeDetails && zoom >= 1.2 && drawnEdges < 150) {
          const text = svgElement("text", {
            x: (from.x + to.x) / 2,
            y: (from.y + to.y) / 2 - 4,
            class: "osme-map-label osme-edge-label",
          });
          text.textContent =
            edge.source + (settings.length ? ` · ${settings.join(", ")}` : "");
          group.append(text);
        }
        drawnEdges += 1;
      }
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

    let drawnWaypoints = 0;
    for (const waypoint of state.snapshot.waypoints) {
      if (
        drawnWaypoints >= MAX_OVERLAY_WAYPOINTS ||
        !model.finitePosition(waypoint.position)
      ) continue;
      const point = project(waypoint.position);
      if (!inside(point)) continue;
      const candidate = candidateById.get(waypoint.id);
      const validation = candidateStatus(waypoint.id);
      const selected = state.snapshot.selectedWaypointIds.includes(waypoint.id);
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
      if (zoom >= 0.72 || selected || candidate) {
        const parts = [];
        if (state.overlay.names && waypoint.name) parts.push(waypoint.name);
        if (state.overlay.ids) parts.push(model.shortId(waypoint.id, 6));
        if (state.overlay.recordings) {
          parts.push(waypoint.recordingName || model.shortId(waypoint.recordingId, 5));
        }
        if (state.overlay.degree) parts.push(`d${waypoint.degree ?? 0}`);
        if (state.overlay.robot) {
          parts.push(waypoint.robotNickname || waypoint.robotSerial || "robot —");
        }
        if (state.overlay.timestamps) {
          const timestamp = typeof waypoint.creationTime === "string"
            ? waypoint.creationTime
            : JSON.stringify(waypoint.creationTime || "");
          if (timestamp) parts.push(timestamp);
        }
        if (parts.length) {
          const label = svgElement("text", {
            x: point.x + 8,
            y: point.y - 7,
            class: "osme-map-label",
          });
          label.textContent = parts.join(" · ");
          group.append(label);
        }
      }
      drawnWaypoints += 1;
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

  function animationLoop() {
    if (state.disposed || !root.isConnected) return;
    drawOverlay();
    overlayAnimationId = window.requestAnimationFrame(animationLoop);
  }

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
  elements.refresh.addEventListener("click", () => refreshSnapshot());
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
    const key = event.target?.dataset?.overlay;
    if (!key || !Object.prototype.hasOwnProperty.call(state.overlay, key)) return;
    state.overlay[key] = Boolean(event.target.checked);
    state.lastOverlayKey = "";
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
            : friendlyError(candidateStatus(candidateId).reason),
          valid ? "ok" : "warning",
        );
        render();
      }).catch((error) => {
        setStatus(
          error.mutationMayExist
            ? `${friendlyError(error.message)}. An unverified native draft may exist; ` +
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
      state.overlay = { ...state.overlay, ...stored.overlay };
    }
    for (const input of elements.overlayControls.querySelectorAll("[data-overlay]")) {
      input.checked = Boolean(state.overlay[input.dataset.overlay]);
    }
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
    }, SNAPSHOT_INTERVAL_MS);
    overlayAnimationId = window.requestAnimationFrame(animationLoop);
  }

  globalThis.OrbitSiteMapEditorRuntime = Object.freeze({
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
  });

  initialize();
})();
