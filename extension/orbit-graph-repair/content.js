(() => {
  "use strict";

  const ROOT_ID = "orbit-graph-repair-root";
  const STORAGE_KEY = "orbitGraphRepairGuideStateV1";
  const BASELINE_STORAGE_KEY = "orbitGraphBaselineInventoryV1";
  const BRIDGE_CHANNEL = "orbit-graph-repair-v1";
  const SVG_NS = "http://www.w3.org/2000/svg";
  const CAMERA_WIDTH_METERS = 10;
  const WAYPOINT_ADVISORY_LIMIT = 3000;

  if (document.getElementById(ROOT_ID)) return;

  const state = {
    guide: null,
    selectedIndex: null,
    done: new Set(),
    filter: "all",
    panelOpen: true,
    status: "Load a B0 baseline or import an optional prebuilt guide.",
    statusKind: "neutral",
    lastProjectionKey: "",
    requestSequence: 0,
    pendingRequests: new Map(),
    orbitPositions: new Map(),
    bridgeReady: false,
    inspector: null,
    inspectorError: "",
    inspectorInFlight: false,
    baseline: null,
    baselineComparing: false,
    deleteOverlay: null,
    showAllDeleteEdges: false,
    connectingIndex: null,
    archivingIndex: null,
    bulkArchiving: false,
    updatingSettingsIndex: null,
    bulkUpdatingSettings: false,
  };

  const root = document.createElement("div");
  root.id = ROOT_ID;
  root.innerHTML = `
    <svg class="ogr-overlay" aria-hidden="true"></svg>
    <button class="ogr-launch" type="button" aria-label="Open graph repair guide" hidden>
      <span>Site Map Assistant</span><strong class="ogr-launch-count">0</strong>
    </button>
    <aside class="ogr-panel" aria-label="Orbit Site Map Assistant">
      <header class="ogr-header">
        <div>
          <span class="ogr-kicker">ORBIT SITE MAP</span>
          <h2>Site Map Assistant <span class="ogr-count">0</span></h2>
        </div>
        <button class="ogr-icon-button ogr-close" type="button" aria-label="Collapse graph repair guide">×</button>
      </header>
      <section class="ogr-inspector" aria-label="Selected Orbit entity inspector">
        <div class="ogr-inspector-header">
          <div>
            <span class="ogr-section-kicker">LIVE INSPECTOR</span>
            <strong>Current selection</strong>
          </div>
          <span class="ogr-inspector-state">Loading…</span>
        </div>
        <div class="ogr-health"></div>
        <div class="ogr-inspector-content">
          <p class="ogr-inspector-empty">Select a waypoint or edge in Orbit.</p>
        </div>
      </section>
      <div class="ogr-section-title">LIVE B0 COMPARISON</div>
      <div class="ogr-import-row ogr-baseline-row">
        <label class="ogr-button ogr-primary">
          Load B0 baseline
          <input class="ogr-baseline-file" type="file" accept=".json,application/json" hidden>
        </label>
        <button class="ogr-button ogr-refresh-baseline" type="button" disabled>Refresh</button>
        <button class="ogr-button ogr-clear-baseline" type="button" disabled>Remove B0</button>
      </div>
      <div class="ogr-baseline-summary"></div>
      <div class="ogr-visualization-actions" hidden>
        <button class="ogr-button ogr-delete-visualization" type="button" aria-pressed="false">
          Show edges pending Archive
        </button>
        <span class="ogr-visualization-note">
          Read-only B0 tombstone overlay using live Orbit anchors.
        </span>
      </div>
      <div class="ogr-section-title">REPAIR PAIRS</div>
      <div class="ogr-import-row">
        <label class="ogr-button ogr-primary">
          Import prebuilt guide
          <input class="ogr-file" type="file" accept=".json,application/json" hidden>
        </label>
        <button class="ogr-button ogr-clear" type="button" disabled>Remove guide</button>
      </div>
      <p class="ogr-status" role="status"></p>
      <div class="ogr-controls" hidden>
        <label>
          <span>Show</span>
          <select class="ogr-filter">
            <option value="all">All required actions</option>
            <option value="connect">Connect in Orbit</option>
            <option value="delete">Archive in Orbit</option>
            <option value="update">Restore edge settings</option>
            <option value="cut">Site Map boundary edges</option>
            <option value="pending">Not completed</option>
          </select>
        </label>
        <div class="ogr-stepper">
          <button class="ogr-button ogr-prev" type="button">Previous</button>
          <button class="ogr-button ogr-next" type="button">Next</button>
        </div>
      </div>
      <div class="ogr-bulk-actions" hidden>
        <button class="ogr-button ogr-archive-draft ogr-bulk-archive" type="button">
          Archive all pending edges
        </button>
        <span>Uses one native Orbit multi-selection and one Undo step.</span>
      </div>
      <div class="ogr-bulk-actions ogr-settings-actions" hidden>
        <button class="ogr-button ogr-settings-draft ogr-bulk-crosswalk-settings" type="button">
          Restore pending crosswalk settings
        </button>
        <button class="ogr-button ogr-settings-draft ogr-bulk-edge-settings" type="button">
          Restore all pending edge settings
        </button>
        <span>Each button creates one native Orbit Undo step. Save is never automatic.</span>
      </div>
      <div class="ogr-summary"></div>
      <div class="ogr-list"></div>
      <footer class="ogr-footer">
        Connect, Archive, and Restore settings create unsaved drafts through Orbit's own editor. This assistant never presses Save.
      </footer>
    </aside>`;
  document.documentElement.append(root);

  const elements = {
    overlay: root.querySelector(".ogr-overlay"),
    launch: root.querySelector(".ogr-launch"),
    launchCount: root.querySelector(".ogr-launch-count"),
    panel: root.querySelector(".ogr-panel"),
    close: root.querySelector(".ogr-close"),
    count: root.querySelector(".ogr-count"),
    inspectorState: root.querySelector(".ogr-inspector-state"),
    health: root.querySelector(".ogr-health"),
    inspectorContent: root.querySelector(".ogr-inspector-content"),
    baselineFile: root.querySelector(".ogr-baseline-file"),
    refreshBaseline: root.querySelector(".ogr-refresh-baseline"),
    clearBaseline: root.querySelector(".ogr-clear-baseline"),
    baselineSummary: root.querySelector(".ogr-baseline-summary"),
    visualizationActions: root.querySelector(".ogr-visualization-actions"),
    deleteVisualization: root.querySelector(".ogr-delete-visualization"),
    visualizationNote: root.querySelector(".ogr-visualization-note"),
    file: root.querySelector(".ogr-file"),
    clear: root.querySelector(".ogr-clear"),
    status: root.querySelector(".ogr-status"),
    controls: root.querySelector(".ogr-controls"),
    filter: root.querySelector(".ogr-filter"),
    previous: root.querySelector(".ogr-prev"),
    next: root.querySelector(".ogr-next"),
    bulkActions: root.querySelector(".ogr-bulk-actions"),
    bulkArchive: root.querySelector(".ogr-bulk-archive"),
    settingsActions: root.querySelector(".ogr-settings-actions"),
    bulkCrosswalkSettings: root.querySelector(".ogr-bulk-crosswalk-settings"),
    bulkEdgeSettings: root.querySelector(".ogr-bulk-edge-settings"),
    summary: root.querySelector(".ogr-summary"),
    list: root.querySelector(".ogr-list"),
  };

  function storageGet() {
    if (!globalThis.chrome?.storage?.local) return Promise.resolve({});
    return new Promise((resolve, reject) => {
      chrome.storage.local.get(
        [STORAGE_KEY, BASELINE_STORAGE_KEY],
        (value) => {
          const error = chrome.runtime?.lastError;
          if (error) reject(new Error(`Could not read local extension data: ${error.message}`));
          else resolve(value || {});
        },
      );
    });
  }

  function storageSet(value) {
    if (!globalThis.chrome?.storage?.local) return Promise.resolve();
    return new Promise((resolve, reject) => {
      chrome.storage.local.set({ [STORAGE_KEY]: value }, () => {
        const error = chrome.runtime?.lastError;
        if (error) reject(new Error(`Could not store the repair guide: ${error.message}`));
        else resolve();
      });
    });
  }

  function storageRemove() {
    if (!globalThis.chrome?.storage?.local) return Promise.resolve();
    return new Promise((resolve, reject) => {
      chrome.storage.local.remove([STORAGE_KEY], () => {
        const error = chrome.runtime?.lastError;
        if (error) reject(new Error(`Could not remove the repair guide: ${error.message}`));
        else resolve();
      });
    });
  }

  function baselineStorageSet(value) {
    if (!globalThis.chrome?.storage?.local) return Promise.resolve();
    return new Promise((resolve, reject) => {
      chrome.storage.local.set({ [BASELINE_STORAGE_KEY]: value }, () => {
        const error = chrome.runtime?.lastError;
        if (error) reject(new Error(`Could not store the B0 baseline: ${error.message}`));
        else resolve();
      });
    });
  }

  function baselineStorageRemove() {
    if (!globalThis.chrome?.storage?.local) return Promise.resolve();
    return new Promise((resolve, reject) => {
      chrome.storage.local.remove([BASELINE_STORAGE_KEY], () => {
        const error = chrome.runtime?.lastError;
        if (error) reject(new Error(`Could not remove the B0 baseline: ${error.message}`));
        else resolve();
      });
    });
  }

  function currentMapId() {
    const match = location.pathname.match(/\/control_room\/maps\/([^/]+)\/edit/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function finiteNumber(value) {
    return typeof value === "number" && Number.isFinite(value);
  }

  function baselineTools() {
    if (!globalThis.OrbitGraphBaseline) {
      throw new Error("The B0 comparison module did not load.");
    }
    return globalThis.OrbitGraphBaseline;
  }

  function validateGuide(value) {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw new Error("The guide must be a JSON object.");
    }
    if (value.kind !== "orbit_graph_reconciliation_guide") {
      throw new Error("This is not a graph reconciliation guide.");
    }
    if (!value.after_site_map || typeof value.after_site_map.id !== "string") {
      throw new Error("The guide has no post-move Site Map ID.");
    }
    if (!Array.isArray(value.actions)) {
      throw new Error("The guide has no action list.");
    }
    const indexes = new Set();
    for (const action of value.actions) {
      if (
        !action ||
        !Number.isInteger(action.index) ||
        indexes.has(action.index) ||
        !["connect", "delete", "update"].includes(action.operation) ||
        typeof action.from !== "string" ||
        typeof action.to !== "string" ||
        (
          action.coordinate_scope !== "orbit_live" &&
          (
            !finiteNumber(action.from_x) ||
            !finiteNumber(action.from_y) ||
            !finiteNumber(action.to_x) ||
            !finiteNumber(action.to_y)
          )
        )
      ) {
        throw new Error("The guide contains an invalid action.");
      }
      if (
        action.operation === "update" &&
        (
          !action.desired_settings ||
          typeof action.desired_settings !== "object" ||
          Array.isArray(action.desired_settings) ||
          !action.observed_settings ||
          typeof action.observed_settings !== "object" ||
          Array.isArray(action.observed_settings)
        )
      ) {
        throw new Error("The guide contains an invalid edge-settings action.");
      }
      indexes.add(action.index);
    }
    if (value.intentional_cuts !== undefined && !Array.isArray(value.intentional_cuts)) {
      throw new Error("The guide has an invalid boundary-cut list.");
    }
    for (const cut of value.intentional_cuts || []) {
      if (
        !cut ||
        typeof cut.from !== "string" ||
        typeof cut.to !== "string" ||
        cut.from === cut.to
      ) {
        throw new Error("The guide contains an invalid boundary cut.");
      }
    }
    return value;
  }

  function reasonLabel(reason) {
    return {
      missing_manual_edge: "manually created edge missing",
      missing_expected_edge: "expected edge missing",
      resurrected_deleted_edge: "archived edge returned",
      unexpected_edge: "edge should be archived",
      edge_settings_mismatch: "edge settings differ",
    }[reason] || String(reason || "graph difference");
  }

  function operationLabel(operation) {
    return {
      connect: "connect",
      delete: "archive",
      update: "edge settings",
    }[operation] || operation;
  }

  function selectedAction() {
    return state.guide?.actions.find((action) => action.index === state.selectedIndex) || null;
  }

  function filteredActions() {
    const actions = state.guide?.actions || [];
    if (state.filter === "cut") return [];
    if (state.filter === "all") return actions;
    if (state.filter === "pending") {
      return actions.filter((action) => !state.done.has(action.index));
    }
    return actions.filter((action) => action.operation === state.filter);
  }

  function filteredCuts() {
    return state.filter === "cut" ? state.guide?.intentional_cuts || [] : [];
  }

  function pendingArchiveActions() {
    return (state.guide?.actions || []).filter(
      (action) =>
        action.operation === "delete" &&
        action.coordinate_scope !== "local_frame" &&
        !state.done.has(action.index),
    );
  }

  function pendingSettingsActions(crosswalkOnly = false) {
    return (state.guide?.actions || []).filter(
      (action) =>
        action.operation === "update" &&
        action.coordinate_scope !== "local_frame" &&
        action.stored_direction_matches !== false &&
        (!crosswalkOnly || action.crosswalk) &&
        !state.done.has(action.index),
    );
  }

  function pendingDeleteOverviewEdges() {
    if (mapMatchesGuide()) {
      return (state.guide?.actions || []).filter(
        (action) =>
          action.operation === "delete" &&
          action.coordinate_scope !== "local_frame" &&
          finiteNumber(action.from_x) &&
          finiteNumber(action.from_y) &&
          finiteNumber(action.to_x) &&
          finiteNumber(action.to_y),
      );
    }
    return [];
  }

  function deleteOverviewEdges() {
    const pendingDeletes = pendingDeleteOverviewEdges();
    if (pendingDeletes.length) return pendingDeletes;
    if (
      state.deleteOverlay?.map?.id === currentMapId() &&
      Array.isArray(state.deleteOverlay.edges)
    ) {
      return state.deleteOverlay.edges;
    }
    return [];
  }

  function setStatus(message, kind = "neutral") {
    state.status = message;
    state.statusKind = kind;
    elements.status.textContent = message;
    elements.status.dataset.kind = kind;
  }

  function mapMatchesGuide() {
    return Boolean(state.guide && currentMapId() === state.guide.after_site_map.id);
  }

  function persist() {
    if (!state.guide) return storageRemove();
    return storageSet({
      guide: state.guide,
      selectedIndex: state.selectedIndex,
      done: [...state.done].sort((a, b) => a - b),
      showAllDeleteEdges: state.showAllDeleteEdges,
    });
  }

  function persistInBackground() {
    persist().catch((error) => setStatus(error.message || String(error), "error"));
  }

  function setGuide(guide, saved = {}) {
    state.guide = validateGuide(guide);
    state.done = new Set(
      Array.isArray(saved.done)
        ? saved.done.filter((value) => Number.isInteger(value))
        : [],
    );
    const savedAction = state.guide.actions.find(
      (action) => action.index === saved.selectedIndex,
    );
    state.selectedIndex = savedAction?.index ?? state.guide.actions[0]?.index ?? null;
    state.filter = "all";
    if (typeof saved.showAllDeleteEdges === "boolean") {
      state.showAllDeleteEdges = saved.showAllDeleteEdges;
    }
    state.orbitPositions.clear();
    elements.filter.value = "all";
    if (mapMatchesGuide()) {
      setStatus(
        state.guide.fully_reconciled ?? state.guide.graph_reconciled
          ? "This Site Map already matches the baseline graph and available public edge settings."
          : `Guide matches ${state.guide.after_site_map.name || state.guide.after_site_map.id}.`,
        "ok",
      );
    } else {
      setStatus(
        `Site Map mismatch: open ${state.guide.after_site_map.name || state.guide.after_site_map.id} before using this guide.`,
        "error",
      );
    }
    render();
    if (state.bridgeReady && state.selectedIndex !== null && mapMatchesGuide()) {
      resolveInOrbit(selectedAction(), false);
    }
  }

  function makeBadge(text, kind = "") {
    const badge = document.createElement("span");
    badge.className = `ogr-badge ${kind ? `ogr-${kind}` : ""}`;
    badge.textContent = text;
    return badge;
  }

  function formattedCount(value) {
    return Number(value || 0).toLocaleString();
  }

  function formattedPosition(position) {
    if (![position?.x, position?.y, position?.z].every(Number.isFinite)) return "—";
    return `${position.x.toFixed(3)}, ${position.y.toFixed(3)}, ${position.z.toFixed(3)} m`;
  }

  function formattedSecondsTimestamp(value) {
    const seconds = Number(value?.seconds);
    if (!Number.isFinite(seconds)) return "—";
    return new Date(seconds * 1000).toLocaleString();
  }

  function formattedNanosecondsTimestamp(value) {
    if (typeof value !== "string" || !/^\d+$/.test(value)) return "—";
    try {
      return new Date(Number(BigInt(value) / 1000000n)).toLocaleString();
    } catch {
      return "—";
    }
  }

  function sourceSummary(value) {
    return Object.entries(value || {})
      .sort((left, right) => right[1] - left[1])
      .map(([source, count]) => `${source}: ${count}`)
      .join(" · ") || "none";
  }

  function inspectorDetail(label, value, mono = false) {
    const row = document.createElement("div");
    row.className = "ogr-inspector-detail";
    const term = document.createElement("span");
    term.textContent = label;
    const description = document.createElement(mono ? "code" : "span");
    description.textContent = value || "—";
    description.title = value || "";
    row.append(term, description);
    return row;
  }

  function inspectorCopyButton(label, text) {
    const button = document.createElement("button");
    button.className = "ogr-button";
    button.type = "button";
    button.textContent = label;
    button.addEventListener("click", () => copyText(text, `${label} copied.`));
    return button;
  }

  function waypointInspectorCard(waypoint) {
    const card = document.createElement("article");
    card.className = "ogr-inspector-card";
    const top = document.createElement("div");
    top.className = "ogr-action-top";
    top.append(
      makeBadge("waypoint", "connect"),
      makeBadge(`${waypoint.degree || 0} edges`),
    );
    const title = document.createElement("strong");
    title.textContent = waypoint.name || "Unnamed waypoint";
    const id = document.createElement("code");
    id.textContent = waypoint.id;
    const details = document.createElement("div");
    details.className = "ogr-inspector-details";
    const recording = waypoint.recording;
    const neighbors = waypoint.neighbors || [];
    details.append(
      inspectorDetail(
        "Recording",
        recording
          ? `${recording.name || "unnamed"} · ${formattedCount(recording.waypointCount)} WP`
          : "unresolved",
      ),
      inspectorDetail("Recording ID", recording?.id || "—", true),
      inspectorDetail(
        "Robot",
        recording?.robotNickname || recording?.robotSerial || "—",
      ),
      inspectorDetail("Created", formattedSecondsTimestamp(waypoint.creationTime)),
      inspectorDetail("Map XYZ", formattedPosition(waypoint.mapPosition), true),
      inspectorDetail("Edge sources", sourceSummary(waypoint.edgeSources)),
      inspectorDetail(
        "Neighbors",
        neighbors
          .map(
            (neighbor) =>
              `${neighbor.name ? `${neighbor.name} · ` : ""}${neighbor.id} [${neighbor.source}]`,
          )
          .join("\n") || "none",
        true,
      ),
      inspectorDetail("Snapshot", waypoint.snapshotId || "—", true),
    );
    const buttons = document.createElement("div");
    buttons.className = "ogr-action-buttons";
    buttons.append(
      inspectorCopyButton("Copy waypoint ID", waypoint.id),
      recording?.id
        ? inspectorCopyButton("Copy recording ID", recording.id)
        : document.createDocumentFragment(),
      neighbors.length
        ? inspectorCopyButton(
            "Copy neighbor IDs",
            neighbors.map((neighbor) => neighbor.id).join("\n"),
          )
        : document.createDocumentFragment(),
    );
    card.append(top, title, id, details, buttons);
    return card;
  }

  function edgeInspectorCard(edge) {
    const card = document.createElement("article");
    card.className = "ogr-inspector-card";
    const top = document.createElement("div");
    top.className = "ogr-action-top";
    top.append(
      makeBadge("edge", edge.manual ? "connect" : ""),
      makeBadge(edge.manual ? "manually created" : edge.source, edge.manual ? "connect" : ""),
    );
    if (edge.crossRecording) top.append(makeBadge("cross-recording", "warning"));
    if (edge.disabled) top.append(makeBadge("disabled", "warning"));
    if (edge.archived) top.append(makeBadge("archived", "delete"));
    const title = document.createElement("strong");
    title.textContent = `${edge.fromName || edge.from} ↔ ${edge.toName || edge.to}`;
    const ids = document.createElement("code");
    ids.textContent = `${edge.from}\n${edge.to}`;
    const settings = edge.settings || {};
    const velocity = settings.mobilityParams?.velLimit?.maxVel;
    const crosswalks = edge.crosswalks || [];
    const areaCallbacks = edge.areaCallbacks || [];
    const details = document.createElement("div");
    details.className = "ogr-inspector-details";
    details.append(
      inspectorDetail(
        "Recordings",
        `${edge.fromRecording?.name || "unresolved"} ↔ ${edge.toRecording?.name || "unresolved"}`,
      ),
      inspectorDetail(
        "Recording IDs",
        `${edge.fromRecording?.id || "—"} ↔ ${edge.toRecording?.id || "—"}`,
        true,
      ),
      inspectorDetail(
        "Length",
        Number.isFinite(edge.length) ? `${edge.length.toFixed(3)} m` : "—",
      ),
      inspectorDetail(
        "Crosswalk",
        crosswalks
          .map((callback) => callback.description || callback.id)
          .join("\n") || "none",
        true,
      ),
      inspectorDetail(
        "Area callbacks",
        areaCallbacks
          .map(
            (callback) =>
              `${callback.serviceName || "unknown"} · ${callback.description || callback.id}`,
          )
          .join("\n") || "none",
        true,
      ),
      inspectorDetail(
        "Velocity max",
        Number.isFinite(velocity?.linear?.x)
          ? `x ${velocity.linear.x.toFixed(3)} · y ${Number(velocity.linear.y || 0).toFixed(3)} ` +
            `· yaw ${Number(velocity.angular || 0).toFixed(3)}`
          : "—",
      ),
      inspectorDetail(
        "Mobility",
        [
          settings.mobilityParams?.locomotionHint !== undefined
            ? `gait ${settings.mobilityParams.locomotionHint}`
            : "",
          settings.mobilityParams?.stairsMode !== undefined
            ? `stairs ${settings.mobilityParams.stairsMode}`
            : "",
          settings.mobilityParams?.hazardDetectionMode !== undefined
            ? `hazard ${settings.mobilityParams.hazardDetectionMode}`
            : "",
        ].filter(Boolean).join(" · ") || "—",
      ),
      inspectorDetail(
        "Path / ground",
        [
          settings.directionConstraint !== undefined
            ? `direction ${settings.directionConstraint}`
            : "",
          settings.pathFollowingMode !== undefined
            ? `path ${settings.pathFollowingMode}`
            : "",
          settings.groundClutterMode !== undefined
            ? `clutter ${settings.groundClutterMode}`
            : "",
        ].filter(Boolean).join(" · ") || "—",
      ),
      inspectorDetail(
        "Route / alert",
        [
          settings.disableAlternateRouteFinding !== undefined
            ? settings.disableAlternateRouteFinding
              ? "alternate route disabled"
              : "alternate route enabled"
            : "",
          settings.disableDirectedExploration !== undefined
            ? settings.disableDirectedExploration
              ? "directed exploration disabled"
              : "directed exploration enabled"
            : "",
          settings.audioVisualSettings?.behaviorName
            ? `behavior ${settings.audioVisualSettings.behaviorName}`
            : "",
        ].filter(Boolean).join(" · "),
      ),
      inspectorDetail(
        "Setting fields",
        Object.keys(settings).sort().join(", ") || "none",
        true,
      ),
      inspectorDetail("Edge ID", edge.id || "—", true),
      inspectorDetail("Snapshot", edge.snapshotId || "—", true),
    );
    const buttons = document.createElement("div");
    buttons.className = "ogr-action-buttons";
    buttons.append(
      inspectorCopyButton("Copy endpoint IDs", `${edge.from}\n${edge.to}`),
      inspectorCopyButton("Copy edge ID", edge.id),
    );
    card.append(top, title, ids, details, buttons);
    return card;
  }

  function renderInspector() {
    elements.health.replaceChildren();
    elements.inspectorContent.replaceChildren();
    const inspector = state.inspector;
    if (!inspector) {
      elements.inspectorState.textContent = state.inspectorError ? "Unavailable" : "Loading…";
      const empty = document.createElement("p");
      empty.className = "ogr-inspector-empty";
      empty.textContent = state.inspectorError || "Connecting to the loaded Orbit map…";
      elements.inspectorContent.append(empty);
      return;
    }

    const map = inspector.map;
    elements.health.append(
      makeBadge(`${formattedCount(map.waypointCount)} WP`),
      makeBadge(`${formattedCount(map.edgeCount)} edges`),
      makeBadge(`${formattedCount(map.recordingCount)} recordings`),
      makeBadge(`${formattedCount(map.sourceCounts?.manual)} manually created`, "connect"),
      makeBadge(
        `${formattedCount(map.crossRecordingManualEdges)} cross-recording manually created`,
        map.crossRecordingManualEdges ? "warning" : "",
      ),
    );
    if (map.waypointCount > WAYPOINT_ADVISORY_LIMIT) {
      elements.health.append(
        makeBadge(
          `${formattedCount(map.waypointCount - WAYPOINT_ADVISORY_LIMIT)} over ${formattedCount(WAYPOINT_ADVISORY_LIMIT)} advisory`,
          "warning",
        ),
      );
    }

    const waypointCount = inspector.waypointSelectionCount || 0;
    const edgeCount = inspector.edgeSelectionCount || 0;
    if (waypointCount) {
      elements.inspectorState.textContent = `${formattedCount(waypointCount)} waypoint${waypointCount === 1 ? "" : "s"}`;
    } else if (edgeCount) {
      elements.inspectorState.textContent = `${formattedCount(edgeCount)} edge${edgeCount === 1 ? "" : "s"}`;
    } else {
      elements.inspectorState.textContent = "No selection";
    }

    if (!waypointCount && !edgeCount) {
      const empty = document.createElement("p");
      empty.className = "ogr-inspector-empty";
      empty.textContent = "Select a waypoint or edge in Orbit to inspect exact IDs and recording context.";
      elements.inspectorContent.append(empty);
      return;
    }
    for (const waypoint of inspector.waypoints || []) {
      elements.inspectorContent.append(waypointInspectorCard(waypoint));
    }
    for (const edge of inspector.edges || []) {
      elements.inspectorContent.append(edgeInspectorCard(edge));
    }
    if (waypointCount > (inspector.waypoints || []).length || edgeCount > (inspector.edges || []).length) {
      const capped = document.createElement("p");
      capped.className = "ogr-inspector-cap";
      capped.textContent = "Showing the first 20 selected entities to keep Orbit responsive.";
      elements.inspectorContent.append(capped);
    }
  }

  function actionCard(action) {
    const card = document.createElement("article");
    card.className = "ogr-action";
    card.dataset.operation = action.operation;
    card.dataset.selected = String(action.index === state.selectedIndex);
    card.dataset.done = String(state.done.has(action.index));

    const top = document.createElement("div");
    top.className = "ogr-action-top";
    top.append(
      makeBadge(`#${String(action.index).padStart(3, "0")}`),
      makeBadge(operationLabel(action.operation), action.operation),
      makeBadge(reasonLabel(action.reason)),
    );
    if (action.coordinate_scope === "local_frame") {
      top.append(makeBadge("local frame", "warning"));
    }
    if (action.crosswalk) top.append(makeBadge("crosswalk", "update"));
    for (const category of action.settings_categories || []) {
      if (category !== "crosswalk") top.append(makeBadge(category, "update"));
    }
    if (action.operation === "update" && action.stored_direction_matches === false) {
      top.append(makeBadge("direction review required", "warning"));
    }
    if (state.done.has(action.index)) top.append(makeBadge("done", "done"));

    const title = document.createElement("strong");
    title.textContent = `${action.from_name || action.from} ↔ ${action.to_name || action.to}`;
    const sessions = document.createElement("span");
    sessions.className = "ogr-sessions";
    sessions.textContent = `${action.from_session || "—"} ↔ ${action.to_session || "—"}`;
    const ids = document.createElement("code");
    ids.textContent = `${action.from} ↔ ${action.to}`;

    const buttons = document.createElement("div");
    buttons.className = "ogr-action-buttons";
    if (action.operation === "connect") {
      const connect = document.createElement("button");
      connect.className = "ogr-button ogr-connect-draft";
      connect.type = "button";
      connect.textContent = state.connectingIndex === action.index
        ? "Connecting…"
        : state.done.has(action.index)
        ? "Connected"
        : "Connect in Orbit";
      connect.disabled =
        !mapMatchesGuide() ||
        action.coordinate_scope === "local_frame" ||
        state.connectingIndex !== null ||
        state.archivingIndex !== null ||
        state.updatingSettingsIndex !== null ||
        state.bulkArchiving ||
        state.bulkUpdatingSettings ||
        state.done.has(action.index);
      connect.addEventListener("click", () => connectInOrbit(action));
      buttons.append(connect);
    }
    if (action.operation === "delete") {
      const archive = document.createElement("button");
      archive.className = "ogr-button ogr-archive-draft";
      archive.type = "button";
      archive.textContent = state.archivingIndex === action.index
        ? "Archiving…"
        : state.done.has(action.index)
        ? "Archived"
        : "Archive in Orbit";
      archive.disabled =
        !mapMatchesGuide() ||
        action.coordinate_scope === "local_frame" ||
        state.connectingIndex !== null ||
        state.archivingIndex !== null ||
        state.updatingSettingsIndex !== null ||
        state.bulkArchiving ||
        state.bulkUpdatingSettings ||
        state.done.has(action.index);
      archive.addEventListener("click", () => archiveInOrbit(action));
      buttons.append(archive);
    }
    if (action.operation === "update") {
      const update = document.createElement("button");
      update.className = "ogr-button ogr-settings-draft";
      update.type = "button";
      update.textContent = state.updatingSettingsIndex === action.index
        ? "Restoring…"
        : state.done.has(action.index)
        ? "Settings restored"
        : "Restore settings in Orbit";
      update.disabled =
        !mapMatchesGuide() ||
        action.coordinate_scope === "local_frame" ||
        action.stored_direction_matches === false ||
        state.connectingIndex !== null ||
        state.archivingIndex !== null ||
        state.updatingSettingsIndex !== null ||
        state.bulkArchiving ||
        state.bulkUpdatingSettings ||
        state.done.has(action.index);
      update.addEventListener("click", () => updateSettingsInOrbit([action]));
      buttons.append(update);
    }
    const focus = document.createElement("button");
    focus.className = "ogr-button ogr-focus";
    focus.type = "button";
    focus.textContent = "Focus in Orbit";
    focus.disabled = !mapMatchesGuide() || action.coordinate_scope === "local_frame";
    focus.addEventListener("click", () => resolveInOrbit(action, true));
    const copy = document.createElement("button");
    copy.className = "ogr-button";
    copy.type = "button";
    copy.textContent = "Copy IDs";
    copy.addEventListener("click", () => copyIds(action));
    const done = document.createElement("button");
    done.className = "ogr-button";
    done.type = "button";
    done.textContent = state.done.has(action.index) ? "Undo done" : "Mark done";
    done.addEventListener("click", () => toggleDone(action));
    buttons.append(focus, copy, done);

    card.append(top, title, sessions, ids, buttons);
    card.addEventListener("click", (event) => {
      if (event.target.closest("button")) return;
      state.selectedIndex = action.index;
      persistInBackground();
      render();
      resolveInOrbit(action, false);
    });
    return card;
  }

  function cutCard(cut, index) {
    const card = document.createElement("article");
    card.className = "ogr-action ogr-cut-card";
    card.dataset.operation = "cut";
    const top = document.createElement("div");
    top.className = "ogr-action-top";
    top.append(
      makeBadge(`#${String(index + 1).padStart(3, "0")}`),
      makeBadge("boundary cut", "warning"),
    );
    if (cut.manual) top.append(makeBadge("manually created in B0", "connect"));
    if (cut.edge_source) top.append(makeBadge(cut.edge_source));
    const title = document.createElement("strong");
    title.textContent = `${cut.from} ↔ ${cut.to}`;
    const explanation = document.createElement("span");
    explanation.className = "ogr-sessions";
    explanation.textContent =
      "Only one endpoint is in this Site Map. This edge cannot exist after the partition.";
    const ids = document.createElement("code");
    ids.textContent = `${cut.from}\n${cut.to}`;
    const buttons = document.createElement("div");
    buttons.className = "ogr-action-buttons";
    buttons.append(
      inspectorCopyButton("Copy IDs", `${cut.from}\n${cut.to}`),
      inspectorCopyButton("Copy missing endpoint", cut.missing_endpoint || ""),
    );
    card.append(top, title, explanation, ids, buttons);
    return card;
  }

  function renderBaselineState() {
    elements.refreshBaseline.disabled = !state.baseline || !state.bridgeReady || state.baselineComparing;
    elements.clearBaseline.disabled = !state.baseline || state.baselineComparing;
    if (!state.baseline) {
      elements.baselineSummary.textContent =
        "Load the immutable graph-baseline.json made from B0; B1 is not required.";
      return;
    }
    const counts = state.baseline.counts || {};
    const liveCounts = state.guide?.comparison_source === "live_orbit_vs_b0_baseline"
      ? state.guide.counts
      : null;
    const source = state.baseline.site_map.name || state.baseline.site_map.id;
    elements.baselineSummary.textContent = liveCounts
      ? `B0 ${source}: ${formattedCount(counts.waypoints)} WP · ` +
        `current: ${formattedCount(liveCounts.current_waypoints)} WP / ` +
        `${formattedCount(liveCounts.current_recordings)} recordings · ` +
        `${formattedCount(liveCounts.desired_internal_edges)} expected edges · ` +
        `${formattedCount(liveCounts.update_edges)} settings diff / ` +
        `${formattedCount(liveCounts.crosswalk_update_edges)} crosswalk · ` +
        `${formattedCount(liveCounts.ignored_extra_waypoints)} extra WP ignored`
      : `B0 ${source}: ${formattedCount(counts.waypoints)} WP · ` +
        `${formattedCount(counts.effective_edges)} effective edges · ` +
        `${formattedCount(counts.site_edge_tombstones)} tombstones · ` +
        `${formattedCount(counts.crosswalk_edges)} crosswalk edges`;
  }

  function render() {
    const actions = state.guide?.actions || [];
    const filtered = filteredActions();
    const cuts = filteredCuts();
    const connectCount = actions.filter((action) => action.operation === "connect").length;
    const deleteCount = actions.filter((action) => action.operation === "delete").length;
    const updateCount = actions.filter((action) => action.operation === "update").length;
    const crosswalkUpdateCount = actions.filter(
      (action) => action.operation === "update" && action.crosswalk,
    ).length;
    const pendingArchives = pendingArchiveActions();
    const pendingSettings = pendingSettingsActions();
    const pendingCrosswalkSettings = pendingSettingsActions(true);
    const pendingDeleteOverview = pendingDeleteOverviewEdges();
    const showingPendingDeleteOverview = pendingDeleteOverview.length > 0;
    const deleteOverviewCount = deleteOverviewEdges().length;
    const internalDeleteCount = showingPendingDeleteOverview
      ? deleteOverviewCount
      : state.deleteOverlay?.map?.id === currentMapId()
      ? Number(state.deleteOverlay.counts?.internal_edges || 0)
      : deleteOverviewCount;
    const cutCount = Number(state.guide?.counts?.intentional_cut_edges || 0);
    elements.count.textContent = String(actions.length);
    elements.launchCount.textContent = String(actions.length);
    elements.clear.disabled = !state.guide;
    elements.controls.hidden = !state.guide;
    elements.previous.disabled = state.filter === "cut";
    elements.next.disabled = state.filter === "cut";
    elements.visualizationActions.hidden = internalDeleteCount === 0;
    const deleteOverviewLabel = showingPendingDeleteOverview
      ? "edges pending Archive"
      : "B0 archived edges";
    elements.deleteVisualization.textContent = state.showAllDeleteEdges
      ? `Hide ${deleteOverviewLabel} (${internalDeleteCount})`
      : `Show ${deleteOverviewLabel} (${internalDeleteCount})`;
    elements.deleteVisualization.disabled = deleteOverviewCount === 0;
    elements.deleteVisualization.setAttribute(
      "aria-pressed",
      String(state.showAllDeleteEdges),
    );
    const missingDeletePositions = Number(
      state.deleteOverlay?.counts?.missing_position_edges || 0,
    );
    elements.visualizationNote.textContent = showingPendingDeleteOverview
      ? "Read-only Archive overlay using live Orbit anchors."
      : missingDeletePositions
      ? `${deleteOverviewCount} of ${internalDeleteCount} B0 archived edges drawn; ` +
        `${missingDeletePositions} skipped because Orbit has no anchor position.`
      : "Read-only B0 tombstone overlay using live Orbit anchors.";
    elements.bulkActions.hidden = !state.guide || deleteCount === 0;
    elements.bulkArchive.textContent = state.bulkArchiving
      ? `Archiving ${pendingArchives.length} edges…`
      : `Archive all pending edges (${pendingArchives.length})`;
    elements.bulkArchive.disabled =
      !mapMatchesGuide() ||
      pendingArchives.length === 0 ||
      state.connectingIndex !== null ||
      state.archivingIndex !== null ||
      state.updatingSettingsIndex !== null ||
      state.bulkArchiving ||
      state.bulkUpdatingSettings;
    elements.settingsActions.hidden = !state.guide || updateCount === 0;
    elements.bulkCrosswalkSettings.textContent = state.bulkUpdatingSettings
      ? "Restoring settings…"
      : `Restore pending crosswalk settings (${pendingCrosswalkSettings.length})`;
    elements.bulkEdgeSettings.textContent = state.bulkUpdatingSettings
      ? "Restoring settings…"
      : `Restore all pending edge settings (${pendingSettings.length})`;
    elements.bulkCrosswalkSettings.disabled =
      !mapMatchesGuide() ||
      pendingCrosswalkSettings.length === 0 ||
      state.connectingIndex !== null ||
      state.archivingIndex !== null ||
      state.updatingSettingsIndex !== null ||
      state.bulkArchiving ||
      state.bulkUpdatingSettings;
    elements.bulkEdgeSettings.disabled =
      !mapMatchesGuide() ||
      pendingSettings.length === 0 ||
      state.connectingIndex !== null ||
      state.archivingIndex !== null ||
      state.updatingSettingsIndex !== null ||
      state.bulkArchiving ||
      state.bulkUpdatingSettings;
    elements.summary.textContent = state.guide
      ? `${connectCount} connect · ${deleteCount} archive · ${updateCount} edge settings ` +
        `(${crosswalkUpdateCount} crosswalk) · ${cutCount} boundary · ${state.done.size} done`
      : "";
    elements.list.replaceChildren();
    if (state.guide && !filtered.length && !cuts.length) {
      const empty = document.createElement("p");
      empty.className = "ogr-empty";
      empty.textContent = state.filter === "cut"
        ? cutCount
          ? `This prebuilt guide reports ${cutCount} Site Map boundary edge(s) without details.`
          : "No B0 edge crosses this Site Map boundary."
        : state.guide.fully_reconciled ?? state.guide.graph_reconciled
        ? "No graph or public edge-settings repair is required."
        : "No actions match this filter.";
      elements.list.append(empty);
    } else {
      for (const action of filtered) elements.list.append(actionCard(action));
      for (const [index, cut] of cuts.entries()) {
        elements.list.append(cutCard(cut, index));
      }
    }
    elements.status.textContent = state.status;
    elements.status.dataset.kind = state.statusKind;
    renderBaselineState();
    drawOverlay();
  }

  function requestBridge(command, action) {
    if (!state.bridgeReady) {
      return Promise.reject(new Error("Orbit waypoint focus is still loading."));
    }
    if (!action || !mapMatchesGuide()) {
      return Promise.reject(new Error("Open the guide's exact Site Map first."));
    }
    const requestId = `${Date.now()}-${state.requestSequence += 1}`;
    return new Promise((resolve, reject) => {
      const timeout = window.setTimeout(() => {
        state.pendingRequests.delete(requestId);
        reject(new Error(
          command === "connect"
            ? "Orbit edge validation did not respond."
            : command === "archive"
            ? "Orbit edge archive did not respond."
            : "Orbit waypoint focus did not respond.",
        ));
      }, command === "connect" ? 18000 : 2500);
      state.pendingRequests.set(requestId, { resolve, reject, timeout });
      window.postMessage(
        {
          channel: BRIDGE_CHANNEL,
          type: "orbit-graph-repair-request",
          requestId,
          command,
          mapId: state.guide.after_site_map.id,
          waypointIds: [action.from, action.to],
        },
        location.origin,
      );
    });
  }

  function requestArchiveBatch(actions) {
    if (!state.bridgeReady) {
      return Promise.reject(new Error("Orbit edge archive is still loading."));
    }
    if (!actions.length || !mapMatchesGuide()) {
      return Promise.reject(new Error("Open the guide's exact Site Map first."));
    }
    const requestId = `${Date.now()}-${state.requestSequence += 1}`;
    return new Promise((resolve, reject) => {
      const timeout = window.setTimeout(() => {
        state.pendingRequests.delete(requestId);
        reject(new Error("Orbit batch edge archive did not respond."));
      }, 12000);
      state.pendingRequests.set(requestId, { resolve, reject, timeout });
      window.postMessage(
        {
          channel: BRIDGE_CHANNEL,
          type: "orbit-graph-repair-request",
          requestId,
          command: "archive_many",
          mapId: state.guide.after_site_map.id,
          waypointPairs: actions.map((action) => [action.from, action.to]),
        },
        location.origin,
      );
    });
  }

  function requestSettingsBatch(actions) {
    if (!state.bridgeReady) {
      return Promise.reject(new Error("Orbit edge-settings adapter is still loading."));
    }
    if (!actions.length || !mapMatchesGuide()) {
      return Promise.reject(new Error("Open the guide's exact Site Map first."));
    }
    const requestId = `${Date.now()}-${state.requestSequence += 1}`;
    return new Promise((resolve, reject) => {
      const timeout = window.setTimeout(() => {
        state.pendingRequests.delete(requestId);
        reject(new Error("Orbit edge-settings update did not respond."));
      }, 12000);
      state.pendingRequests.set(requestId, { resolve, reject, timeout });
      window.postMessage(
        {
          channel: BRIDGE_CHANNEL,
          type: "orbit-graph-repair-request",
          requestId,
          command: "update_settings_many",
          mapId: state.guide.after_site_map.id,
          settingsUpdates: actions.map((action) => ({
            waypointIds: [action.from, action.to],
            storedFrom: action.from,
            storedTo: action.to,
            observedSourceValue: action.observed_source_value,
            observedSettings: action.observed_settings,
            desiredSettings: action.desired_settings,
          })),
        },
        location.origin,
      );
    });
  }

  function requestInspector() {
    if (!state.bridgeReady) {
      return Promise.reject(new Error("Orbit inspector is still loading."));
    }
    const mapId = currentMapId();
    if (!mapId) return Promise.reject(new Error("Open an Orbit Site Map editor."));
    const requestId = `${Date.now()}-${state.requestSequence += 1}`;
    return new Promise((resolve, reject) => {
      const timeout = window.setTimeout(() => {
        state.pendingRequests.delete(requestId);
        reject(new Error("Orbit inspector did not respond."));
      }, 2500);
      state.pendingRequests.set(requestId, { resolve, reject, timeout });
      window.postMessage(
        {
          channel: BRIDGE_CHANNEL,
          type: "orbit-graph-repair-request",
          requestId,
          command: "inspect",
          mapId,
        },
        location.origin,
      );
    });
  }

  function requestGraphSnapshot() {
    if (!state.bridgeReady) {
      return Promise.reject(new Error("Orbit graph access is still loading."));
    }
    const mapId = currentMapId();
    if (!mapId) return Promise.reject(new Error("Open an Orbit Site Map editor."));
    const requestId = `${Date.now()}-${state.requestSequence += 1}`;
    return new Promise((resolve, reject) => {
      const timeout = window.setTimeout(() => {
        state.pendingRequests.delete(requestId);
        reject(new Error("Orbit graph snapshot did not respond."));
      }, 12000);
      state.pendingRequests.set(requestId, { resolve, reject, timeout });
      window.postMessage(
        {
          channel: BRIDGE_CHANNEL,
          type: "orbit-graph-repair-request",
          requestId,
          command: "snapshot",
          mapId,
        },
        location.origin,
      );
    });
  }

  async function compareBaselineToCurrentMap() {
    if (!state.baseline || state.baselineComparing) return;
    state.baselineComparing = true;
    state.deleteOverlay = null;
    setStatus("Reading the current Orbit graph and comparing exact waypoint IDs…");
    renderBaselineState();
    try {
      const response = await requestGraphSnapshot();
      const guide = baselineTools().buildGuide(state.baseline, response.snapshot);
      state.deleteOverlay = baselineTools().buildDeletedEdgeOverlay(
        state.baseline,
        response.snapshot,
      );
      setGuide(guide);
      await persist();
      const counts = guide.counts;
      const fullyReconciled = guide.fully_reconciled ?? guide.graph_reconciled;
      const ignoredScope =
        Number(counts.ignored_extra_waypoints || 0) ||
        Number(counts.ignored_extra_edges || 0)
          ? ` ${counts.ignored_extra_waypoints} extra waypoint(s) and ` +
            `${counts.ignored_extra_edges} incident edge(s) were ignored.`
          : "";
      setStatus(
        fullyReconciled
          ? `Current graph and available public edge settings match B0. ` +
            `${counts.intentional_cut_edges} boundary cut(s) are informational only.` +
            ignoredScope
          : `Live comparison ready: ${counts.connect_edges} connect, ` +
            `${counts.delete_edges} archive, ${counts.update_edges} edge settings ` +
            `(${counts.crosswalk_update_edges} crosswalk), ` +
            `${counts.intentional_cut_edges} Site Map boundary.` +
            ignoredScope,
        fullyReconciled ? "ok" : "neutral",
      );
    } catch (error) {
      state.deleteOverlay = null;
      state.showAllDeleteEdges = false;
      if (state.guide?.comparison_source === "live_orbit_vs_b0_baseline") {
        state.guide = null;
        state.selectedIndex = null;
        state.done.clear();
        state.orbitPositions.clear();
        await storageRemove();
      }
      setStatus(`${error.message || String(error)} No edit guidance was generated.`, "error");
    } finally {
      state.baselineComparing = false;
      render();
    }
  }

  async function refreshInspector() {
    if (!state.bridgeReady || state.inspectorInFlight || document.hidden) return;
    state.inspectorInFlight = true;
    try {
      const response = await requestInspector();
      state.inspector = response.inspector;
      state.inspectorError = "";
    } catch (error) {
      state.inspector = null;
      state.inspectorError = `${error.message || String(error)} Exact-ID inspection is unavailable.`;
    } finally {
      state.inspectorInFlight = false;
      renderInspector();
    }
  }

  async function resolveInOrbit(action, focus) {
    if (!action || action.coordinate_scope === "local_frame") return;
    state.selectedIndex = action.index;
    persistInBackground();
    try {
      const response = await requestBridge(focus ? "focus" : "resolve", action);
      state.orbitPositions.set(action.index, response.positions);
      setStatus(
        focus
          ? "Orbit centered the exact waypoint pair."
          : "Resolved exact waypoint positions from the current Orbit map.",
        "ok",
      );
      render();
    } catch (error) {
      setStatus(
        `${error.message || String(error)} Copy IDs remains available.`,
        "error",
      );
    }
  }

  async function connectInOrbit(action) {
    if (
      !action ||
      action.operation !== "connect" ||
      action.coordinate_scope === "local_frame" ||
      state.connectingIndex !== null ||
      state.updatingSettingsIndex !== null ||
      state.bulkArchiving ||
      state.bulkUpdatingSettings
    ) return;
    state.selectedIndex = action.index;
    state.connectingIndex = action.index;
    setStatus("Orbit is validating the exact waypoint pair…");
    render();
    try {
      const response = await requestBridge("connect", action);
      if (!response.added) throw new Error("Orbit did not create an edge draft.");
      state.done.add(action.index);
      await persist();
      setStatus(
        `Orbit created unsaved edge draft #${response.editIndex ?? "—"}. Review it, then use Orbit Save when ready.`,
        "ok",
      );
    } catch (error) {
      setStatus(
        `${error.message || String(error)} No edge draft was added.`,
        "error",
      );
    } finally {
      state.connectingIndex = null;
      render();
      refreshInspector();
    }
  }

  async function archiveInOrbit(action) {
    if (
      !action ||
      action.operation !== "delete" ||
      action.coordinate_scope === "local_frame" ||
      state.connectingIndex !== null ||
      state.archivingIndex !== null ||
      state.updatingSettingsIndex !== null ||
      state.bulkArchiving ||
      state.bulkUpdatingSettings
    ) return;
    const confirmed = window.confirm(
      `Archive this edge in Orbit's unsaved editor?\n\n` +
      `${action.from_name || action.from} ↔ ${action.to_name || action.to}\n\n` +
      "Orbit warns that archiving edges may alter recording orientation relative to the drawing. " +
      "Pin additional waypoints first when layout preservation matters. Save is not automatic.",
    );
    if (!confirmed) {
      setStatus("Archive cancelled. Orbit graph data was not changed.");
      return;
    }
    state.selectedIndex = action.index;
    state.archivingIndex = action.index;
    setStatus("Orbit is selecting and archiving the exact edge draft…");
    render();
    try {
      const response = await requestBridge("archive", action);
      if (!response.archived) throw new Error("Orbit did not create an archive draft.");
      state.done.add(action.index);
      await persist();
      setStatus(
        `Orbit created unsaved archive draft #${response.editIndex ?? "—"}. Review it, then use Orbit Save when ready.`,
        "ok",
      );
    } catch (error) {
      setStatus(
        `${error.message || String(error)} No archive draft was added.`,
        "error",
      );
    } finally {
      state.archivingIndex = null;
      render();
      refreshInspector();
    }
  }

  async function archiveAllPendingInOrbit() {
    const actions = pendingArchiveActions();
    if (
      !actions.length ||
      state.connectingIndex !== null ||
      state.archivingIndex !== null ||
      state.updatingSettingsIndex !== null ||
      state.bulkArchiving ||
      state.bulkUpdatingSettings
    ) return;
    const confirmed = window.confirm(
      `Archive ${actions.length} pending edges in one Orbit unsaved edit?\n\n` +
      "The assistant will validate every exact endpoint pair before changing the editor, " +
      "then use Orbit's native multi-selection and Archive action once.\n\n" +
      "Orbit warns that archiving edges may alter recording orientation relative to the drawing. " +
      "Pin additional waypoints first when layout preservation matters. Save is not automatic.",
    );
    if (!confirmed) {
      setStatus("Batch archive cancelled. Orbit graph data was not changed.");
      return;
    }
    state.bulkArchiving = true;
    setStatus(`Orbit is validating and selecting ${actions.length} exact edges…`);
    render();
    try {
      const response = await requestArchiveBatch(actions);
      if (!response.archived || response.archivedCount !== actions.length) {
        throw new Error("Orbit did not verify the complete archive batch.");
      }
      for (const action of actions) state.done.add(action.index);
      await persist();
      setStatus(
        `Orbit created one unsaved archive draft #${response.editIndex ?? "—"} containing ` +
        `${actions.length} edges. Review it or use one Orbit Undo, then Save when ready.`,
        "ok",
      );
    } catch (error) {
      setStatus(
        `${error.message || String(error)} Review Orbit's unsaved changes; the complete batch was not verified.`,
        "error",
      );
    } finally {
      state.bulkArchiving = false;
      render();
      refreshInspector();
    }
  }

  async function updateSettingsInOrbit(actions, bulk = false) {
    if (
      !actions.length ||
      actions.some(
        (action) =>
          action.operation !== "update" ||
          action.coordinate_scope === "local_frame" ||
          action.stored_direction_matches === false,
      ) ||
      state.connectingIndex !== null ||
      state.archivingIndex !== null ||
      state.updatingSettingsIndex !== null ||
      state.bulkArchiving ||
      state.bulkUpdatingSettings
    ) return;
    const crosswalkCount = actions.filter((action) => action.crosswalk).length;
    const confirmed = window.confirm(
      `Restore B0 public settings on ${actions.length} edge${actions.length === 1 ? "" : "s"} ` +
      `in one Orbit unsaved edit?\n\n` +
      `${crosswalkCount} edge${crosswalkCount === 1 ? "" : "s"} include crosswalk callbacks. ` +
      "The assistant will reject stale settings, changed edge sources, or reversed stored " +
      "directions before dispatching Orbit's native updateSiteEdges action.\n\n" +
      "This creates one Orbit Undo step. Save is not automatic.",
    );
    if (!confirmed) {
      setStatus("Edge-settings restore cancelled. Orbit graph data was not changed.");
      return;
    }
    if (bulk) state.bulkUpdatingSettings = true;
    else state.updatingSettingsIndex = actions[0].index;
    setStatus(`Orbit is validating ${actions.length} exact edge setting profile(s)…`);
    render();
    try {
      const response = await requestSettingsBatch(actions);
      if (!response.updated || response.updatedCount !== actions.length) {
        throw new Error("Orbit did not verify the complete edge-settings batch.");
      }
      for (const action of actions) state.done.add(action.index);
      await persist();
      setStatus(
        `Orbit created one unsaved edge-settings draft #${response.editIndex ?? "—"} ` +
        `containing ${actions.length} edge${actions.length === 1 ? "" : "s"} ` +
        `(${crosswalkCount} crosswalk). Review it or use one Orbit Undo, then Save when ready.`,
        "ok",
      );
    } catch (error) {
      setStatus(
        `${error.message || String(error)} No verified edge-settings batch was created.`,
        "error",
      );
    } finally {
      state.updatingSettingsIndex = null;
      state.bulkUpdatingSettings = false;
      render();
      refreshInspector();
    }
  }

  async function copyText(text, successMessage) {
    try {
      await navigator.clipboard.writeText(text);
      setStatus(successMessage, "ok");
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.append(textarea);
      textarea.select();
      document.execCommand("copy");
      textarea.remove();
      setStatus(successMessage, "ok");
    }
  }

  async function copyIds(action) {
    return copyText(
      `${action.from}\n${action.to}`,
      "Copied the two exact waypoint IDs.",
    );
  }

  function toggleDone(action) {
    if (state.done.has(action.index)) {
      state.done.delete(action.index);
      setStatus("Marked this pair pending. Orbit graph data was not changed.");
    } else {
      state.done.add(action.index);
      setStatus("Marked this pair done locally. Orbit graph data was not changed.", "ok");
    }
    persistInBackground();
    render();
  }

  function step(direction) {
    const actions = filteredActions();
    if (!actions.length) return;
    const current = actions.findIndex((action) => action.index === state.selectedIndex);
    const next = current < 0
      ? 0
      : (current + direction + actions.length) % actions.length;
    state.selectedIndex = actions[next].index;
    persistInBackground();
    render();
    elements.list
      .querySelector('[data-selected="true"]')
      ?.scrollIntoView({ block: "nearest" });
  }

  function svgElement(name, attributes = {}) {
    const element = document.createElementNS(SVG_NS, name);
    for (const [key, value] of Object.entries(attributes)) {
      element.setAttribute(key, String(value));
    }
    return element;
  }

  function drawOverlay() {
    elements.overlay.replaceChildren();
    const canvas = document.querySelector("canvas");
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const params = new URL(location.href).searchParams;
    const cameraXValue = params.get("x");
    const cameraYValue = params.get("y");
    const zoomValue = params.get("zoom");
    if (cameraXValue === null || cameraYValue === null || zoomValue === null) return;
    const cameraX = Number(cameraXValue);
    const cameraY = Number(cameraYValue);
    const zoom = Number(zoomValue);
    if (![cameraX, cameraY, zoom].every(Number.isFinite) || zoom <= 0) return;
    const pixelsPerMeter = rect.width / CAMERA_WIDTH_METERS * zoom;
    const project = (x, y) => ({
      x: rect.left + rect.width / 2 + (x - cameraX) * pixelsPerMeter,
      y: rect.top + rect.height / 2 - (y - cameraY) * pixelsPerMeter,
    });

    if (state.showAllDeleteEdges) {
      const segments = [];
      for (const edge of deleteOverviewEdges()) {
        if (
          !finiteNumber(edge.from_x) ||
          !finiteNumber(edge.from_y) ||
          !finiteNumber(edge.to_x) ||
          !finiteNumber(edge.to_y)
        ) continue;
        const from = project(edge.from_x, edge.from_y);
        const to = project(edge.to_x, edge.to_y);
        segments.push(
          `M${from.x.toFixed(2)} ${from.y.toFixed(2)} ` +
          `L${to.x.toFixed(2)} ${to.y.toFixed(2)}`,
        );
      }
      if (segments.length) {
        const pathData = segments.join(" ");
        const clipId = "ogr-map-canvas-clip";
        const definitions = svgElement("defs");
        const clip = svgElement("clipPath", { id: clipId });
        clip.append(svgElement("rect", {
          x: rect.left,
          y: rect.top,
          width: rect.width,
          height: rect.height,
        }));
        definitions.append(clip);
        elements.overlay.append(definitions);
        const group = svgElement("g", {
          class: "ogr-delete-overview",
          "clip-path": `url(#${clipId})`,
        });
        group.append(
          svgElement("path", {
            d: pathData,
            fill: "none",
            stroke: "#07131f",
            "stroke-width": 6,
            "stroke-linecap": "round",
            opacity: 0.72,
          }),
          svgElement("path", {
            d: pathData,
            fill: "none",
            stroke: "#fb7185",
            "stroke-width": 2.5,
            "stroke-linecap": "round",
            opacity: 0.82,
          }),
        );
        elements.overlay.append(group);
      }
    }

    const action = selectedAction();
    if (!action || !mapMatchesGuide() || action.coordinate_scope === "local_frame") return;
    const orbitPositions = state.orbitPositions.get(action.index);
    const fromPosition = orbitPositions?.[action.from] || (
      finiteNumber(action.from_x) && finiteNumber(action.from_y)
        ? { x: action.from_x, y: action.from_y }
        : null
    );
    const toPosition = orbitPositions?.[action.to] || (
      finiteNumber(action.to_x) && finiteNumber(action.to_y)
        ? { x: action.to_x, y: action.to_y }
        : null
    );
    if (!fromPosition || !toPosition) return;
    const from = project(fromPosition.x, fromPosition.y);
    const to = project(toPosition.x, toPosition.y);
    const color = action.operation === "connect"
      ? "#2dd4bf"
      : action.operation === "update"
      ? "#fbbf24"
      : "#fb7185";
    const group = svgElement("g", { class: `ogr-mark ogr-mark-${action.operation}` });
    const halo = svgElement("line", {
      x1: from.x, y1: from.y, x2: to.x, y2: to.y,
      stroke: "#07131f", "stroke-width": 12, "stroke-linecap": "round",
    });
    const line = svgElement("line", {
      x1: from.x, y1: from.y, x2: to.x, y2: to.y,
      stroke: color, "stroke-width": 4, "stroke-linecap": "round",
      "stroke-dasharray": action.operation === "connect" ? "11 7" : "none",
    });
    group.append(halo, line);
    for (const [point, label] of [[from, "A"], [to, "B"]]) {
      group.append(svgElement("circle", {
        cx: point.x, cy: point.y, r: 13, fill: "#07131f", stroke: color, "stroke-width": 4,
      }));
      const text = svgElement("text", {
        x: point.x, y: point.y + 4, fill: "#f8fafc", "font-size": 11,
        "font-family": "ui-monospace, SFMono-Regular, Menlo, monospace",
        "font-weight": 700, "text-anchor": "middle",
      });
      text.textContent = label;
      group.append(text);
    }
    const label = svgElement("text", {
      x: (from.x + to.x) / 2,
      y: (from.y + to.y) / 2 - 14,
      fill: color,
      "font-size": 12,
      "font-family": "ui-monospace, SFMono-Regular, Menlo, monospace",
      "font-weight": 700,
      "text-anchor": "middle",
      stroke: "#07131f",
      "stroke-width": 5,
      "paint-order": "stroke",
    });
    label.textContent = action.operation.toUpperCase();
    group.append(label);
    elements.overlay.append(group);
  }

  function projectionLoop() {
    const canvas = document.querySelector("canvas");
    const rect = canvas?.getBoundingClientRect();
    const overviewKey = state.deleteOverlay
      ? `${state.deleteOverlay.map?.id || ""}:${state.deleteOverlay.edges?.length || 0}`
      : `guide:${deleteOverviewEdges().length}`;
    const key = rect
      ? `${location.href}|${rect.left}|${rect.top}|${rect.width}|${rect.height}|` +
        `${state.selectedIndex}|${state.showAllDeleteEdges}|${overviewKey}`
      : `${location.href}|no-canvas|${state.selectedIndex}|` +
        `${state.showAllDeleteEdges}|${overviewKey}`;
    if (key !== state.lastProjectionKey) {
      state.lastProjectionKey = key;
      drawOverlay();
    }
    requestAnimationFrame(projectionLoop);
  }

  async function removeGuide(message = "Removed the locally stored guide.") {
    state.guide = null;
    state.selectedIndex = null;
    state.done.clear();
    state.orbitPositions.clear();
    await storageRemove();
    setStatus(message);
    render();
  }

  elements.baselineFile.addEventListener("change", async () => {
    const file = elements.baselineFile.files?.[0];
    if (!file) return;
    try {
      const baseline = baselineTools().normalizeBaseline(JSON.parse(await file.text()));
      state.baseline = baseline;
      state.deleteOverlay = null;
      state.showAllDeleteEdges = false;
      await baselineStorageSet({ baseline });
      setStatus(
        `Loaded immutable B0 baseline for ${baseline.site_map.name || baseline.site_map.id}.`,
        "ok",
      );
      render();
      if (state.bridgeReady) await compareBaselineToCurrentMap();
    } catch (error) {
      setStatus(error.message || String(error), "error");
    } finally {
      elements.baselineFile.value = "";
    }
  });
  elements.refreshBaseline.addEventListener("click", compareBaselineToCurrentMap);
  elements.deleteVisualization.addEventListener("click", () => {
    if (!deleteOverviewEdges().length) return;
    state.showAllDeleteEdges = !state.showAllDeleteEdges;
    state.lastProjectionKey = "";
    persistInBackground();
    render();
  });
  elements.clearBaseline.addEventListener("click", async () => {
    state.baseline = null;
    state.deleteOverlay = null;
    state.showAllDeleteEdges = false;
    await baselineStorageRemove();
    if (state.guide?.comparison_source === "live_orbit_vs_b0_baseline") {
      await removeGuide("Removed the locally stored B0 baseline and live comparison.");
      return;
    }
    setStatus("Removed the locally stored B0 baseline.");
    render();
  });

  elements.file.addEventListener("change", async () => {
    const file = elements.file.files?.[0];
    if (!file) return;
    try {
      const guide = validateGuide(JSON.parse(await file.text()));
      setGuide(guide);
      await persist();
    } catch (error) {
      setStatus(error.message || String(error), "error");
    } finally {
      elements.file.value = "";
    }
  });
  elements.clear.addEventListener("click", () => removeGuide());
  elements.filter.addEventListener("change", () => {
    state.filter = elements.filter.value;
    render();
  });
  elements.previous.addEventListener("click", () => step(-1));
  elements.next.addEventListener("click", () => step(1));
  elements.bulkArchive.addEventListener("click", archiveAllPendingInOrbit);
  elements.bulkCrosswalkSettings.addEventListener("click", () =>
    updateSettingsInOrbit(pendingSettingsActions(true), true)
  );
  elements.bulkEdgeSettings.addEventListener("click", () =>
    updateSettingsInOrbit(pendingSettingsActions(), true)
  );
  elements.close.addEventListener("click", () => {
    state.panelOpen = false;
    elements.panel.hidden = true;
    elements.launch.hidden = false;
  });
  elements.launch.addEventListener("click", () => {
    state.panelOpen = true;
    elements.panel.hidden = false;
    elements.launch.hidden = true;
  });
  window.addEventListener("popstate", drawOverlay);
  window.addEventListener("resize", drawOverlay);
  window.addEventListener("message", (event) => {
    if (
      event.source !== window ||
      event.origin !== location.origin ||
      event.data?.channel !== BRIDGE_CHANNEL
    ) return;
    if (event.data.type === "orbit-graph-repair-ready") {
      state.bridgeReady = true;
      refreshInspector();
      if (state.baseline) compareBaselineToCurrentMap();
      if (selectedAction() && mapMatchesGuide()) resolveInOrbit(selectedAction(), false);
      return;
    }
    if (event.data.type !== "orbit-graph-repair-response") return;
    const pending = state.pendingRequests.get(event.data.requestId);
    if (!pending) return;
    window.clearTimeout(pending.timeout);
    state.pendingRequests.delete(event.data.requestId);
    if (event.data.ok) pending.resolve(event.data);
    else pending.reject(new Error({
      map_or_waypoint_mismatch: "The guide does not match this Orbit map.",
      orbit_store_unavailable: "This Orbit version does not expose the expected focus adapter.",
      orbit_map_not_loaded: "Orbit has not finished loading this Site Map.",
      waypoint_anchor_unavailable: "Orbit could not resolve both waypoint anchors.",
      orbit_inspector_unavailable: "This Orbit version does not expose the expected inspector state.",
      orbit_snapshot_unavailable: "This Orbit version does not expose the expected graph snapshot state.",
      orbit_map_changed: "The open Orbit map changed during edge validation.",
      orbit_selection_changed: "The selected waypoint pair changed during edge validation.",
      edge_already_exists: "This waypoint pair already has an active edge.",
      edge_validation_failed: "Orbit rejected this edge candidate.",
      edge_validation_warning: "Orbit reported an edge warning; use the native Orbit controls to review it.",
      edge_validation_timeout: "Orbit did not finish validating this edge candidate.",
      edge_draft_not_created: "Orbit did not add the validated edge to its edit history.",
      edge_not_found: "Orbit no longer has an active edge for this waypoint pair.",
      edge_already_archived: "This edge already has an unsaved archive draft.",
      edge_archive_not_created: "Orbit did not add the archive tombstone to its edit history.",
      invalid_archive_batch: "The pending Archive list is not a valid batch.",
      duplicate_edge_pair: "The pending Archive list contains a duplicate waypoint pair.",
      edge_archive_batch_not_created: "Orbit did not create every archive tombstone in one edit.",
      invalid_settings_batch: "The pending edge-settings list is not a valid update batch.",
      unsupported_edge_setting: "The B0 profile contains an unsupported edge setting.",
      edge_direction_mismatch:
        "The edge's stored direction differs from B0; automatic settings replay stopped.",
      edge_source_changed:
        "The edge source changed since the B0 comparison; refresh before restoring settings.",
      edge_settings_changed:
        "The edge settings changed since the B0 comparison; refresh before restoring settings.",
      edge_settings_draft_not_created:
        "Orbit did not add every settings update to one native edit-history step.",
    }[event.data.error] || "Orbit editor action failed."));
  });

  if (globalThis.chrome?.runtime?.getURL) {
    const bridge = document.createElement("script");
    bridge.src = chrome.runtime.getURL("page-bridge.js");
    bridge.addEventListener("load", () => bridge.remove());
    bridge.addEventListener("error", () => {
      bridge.remove();
      setStatus("Could not load the Orbit focus adapter. Copy IDs remains available.", "error");
    });
    (document.head || document.documentElement).append(bridge);
  }

  Promise.resolve()
    .then(async () => {
      const developmentGuide = globalThis.__ORBIT_GRAPH_REPAIR_DEV_GUIDE__;
      const developmentBaseline = globalThis.__ORBIT_GRAPH_BASELINE_DEV_BASELINE__;
      if (developmentBaseline) {
        state.baseline = baselineTools().normalizeBaseline(developmentBaseline);
        if (developmentGuide) setGuide(developmentGuide);
        else render();
        if (state.bridgeReady) await compareBaselineToCurrentMap();
        return;
      }
      if (developmentGuide) {
        setGuide(developmentGuide);
        return;
      }
      const stored = await storageGet();
      const savedBaseline = stored[BASELINE_STORAGE_KEY]?.baseline;
      if (savedBaseline) {
        state.baseline = baselineTools().normalizeBaseline(savedBaseline);
      }
      const saved = stored[STORAGE_KEY];
      if (saved?.guide) setGuide(saved.guide, saved);
      else render();
      if (state.baseline && state.bridgeReady) await compareBaselineToCurrentMap();
    })
    .catch((error) => setStatus(error.message || String(error), "error"));
  renderInspector();
  window.setInterval(refreshInspector, 750);
  requestAnimationFrame(projectionLoop);
})();
