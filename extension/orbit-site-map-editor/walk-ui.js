(() => {
  "use strict";

  const runtime = globalThis.OrbitSiteMapEditorRuntime;
  const planner = globalThis.OrbitSiteMapEditorWalkPlanner;
  const extensionContext = globalThis.OrbitSiteMapEditorExtensionContext;
  if (!runtime || !planner || !extensionContext) return;
  if (runtime.isDisposed?.() || !extensionContext.isActive()) return;

  const root = runtime.elements.panel;
  const nav = root?.querySelector(".osme-tabs");
  const workspace = root?.querySelector(".osme-workspace");
  if (!root || !nav || !workspace) return;
  if (root.dataset.osmeWalkInstance === runtime.instanceId) return;
  root.dataset.osmeWalkInstance = runtime.instanceId;

  const state = {
    siteViewSnapshot: null,
    plan: null,
    planStale: false,
    planGraphSignature: "",
    loading: false,
    refreshRetryCount: 0,
    refreshRetryTimer: 0,
    graphWaypointCountAtSiteViewRefresh: 0,
    overlayRevision: 0,
    overlayCache: null,
    overlay: {
      coverageRoute: true,
      routeTargets: true,
      exclusions: true,
      siteViewGaps: true,
    },
  };
  const lifecycleController = new AbortController();
  const lifecycleSignal = lifecycleController.signal;
  let removeInvalidationListener = () => {};

  const tabButton = document.createElement("button");
  tabButton.type = "button";
  tabButton.dataset.tab = "walk";
  tabButton.textContent = "Walk";
  nav.append(tabButton);

  const pane = document.createElement("section");
  pane.className = "osme-section osme-advanced-pane osme-walk-pane";
  pane.dataset.workspaceTab = "walk";
  pane.hidden = true;
  pane.innerHTML = `
    <div class="osme-section-heading">
      <div><span>WALK</span><strong>Site View coverage route</strong></div>
      <span class="osme-safety-chip">read-only plan</span>
    </div>
    <p class="osme-empty">
      Plan a graph-valid route through the active component reachable from a selected
      start or Dock. Existing SiteWalks and SiteElements are neither read nor modified.
    </p>
    <div class="osme-toolbar">
      <button class="osme-button osme-walk-refresh" type="button">
        Refresh Site View
      </button>
    </div>
    <div class="osme-walk-capabilities"></div>
    <div class="osme-subsection">
      <strong>Operational waypoint coverage plan</strong>
      <label class="osme-walk-label">
        Scope
        <select class="osme-field osme-walk-scope">
          <option value="reachable">Reachable from start / Dock — active edges</option>
          <option value="largest">Largest active connected component</option>
          <option value="all">Audit all components — includes disconnected</option>
        </select>
      </label>
      <div class="osme-toolbar">
        <input class="osme-field osme-walk-start" type="text"
          placeholder="start waypoint ID (optional; Dock fallback)">
        <button class="osme-button osme-walk-use-selected" type="button">
          Use Orbit selection
        </button>
      </div>
      <label class="osme-walk-label">
        Excluded waypoints (optional; exact waypoint ID)
        <textarea class="osme-field osme-walk-exclusions" rows="4"
          placeholder="one exact waypoint ID per line"></textarea>
      </label>
      <div class="osme-toolbar">
        <button class="osme-button osme-walk-add-exclusions" type="button">
          Add Orbit selection to exclusions
        </button>
        <button class="osme-button osme-walk-clear-exclusions" type="button">
          Clear exclusions
        </button>
      </div>
      <p class="osme-empty osme-walk-exclusion-summary">
        0 waypoints explicitly excluded.
      </p>
      <div class="osme-walk-options">
        <label>
          <input class="osme-walk-return" type="checkbox">
          Return to each component start
        </label>
        <label>
          Max waypoints per NavigateRoute
          <input class="osme-field osme-walk-chunk" type="number"
            min="2" max="1000" step="1" value="150">
        </label>
        <label>
          Route-checkpoint compatibility
          <select class="osme-field osme-walk-checkpoint-mode">
            <option value="navigation_only">Navigation-only targets — default</option>
            <option value="compatibility_sleep">
              Short Sleep fallback at required checkpoints
            </option>
          </select>
        </label>
        <label>
          Fallback Sleep seconds
          <input class="osme-field osme-walk-sleep-duration" type="number"
            min="0" step="0.1" value="1" disabled>
        </label>
      </div>
      <label class="osme-walk-label">
        Intentional Sleep Actions (optional)
        <textarea class="osme-field osme-walk-sleeps" rows="3"
          placeholder="waypoint-id, seconds, optional name&#10;# one Sleep per line"></textarea>
      </label>
      <div class="osme-toolbar">
        <button class="osme-button osme-walk-add-sleep" type="button">
          Add Sleep at selected
        </button>
        <button class="osme-button osme-primary osme-walk-plan" type="button">
          Plan coverage
        </button>
      </div>
      <p class="osme-empty">
        Archived/disabled edges and active-disconnected waypoints are ignored by
        default. Excluded waypoints and all incident edges are removed before route
        planning. No Action is added merely because an intermediate waypoint is
        visited. Enable the Sleep fallback only after a target Orbit version rejects
        navigation-only checkpoints.
      </p>
    </div>
    <div class="osme-subsection">
      <strong>Map overlay</strong>
      <div class="osme-walk-overlay-options">
        <label><input type="checkbox" data-walk-overlay="coverageRoute" checked>
          Planned coverage route</label>
        <label><input type="checkbox" data-walk-overlay="routeTargets" checked>
          Numbered route targets</label>
        <label><input type="checkbox" data-walk-overlay="exclusions" checked>
          Explicit exclusions</label>
        <label><input type="checkbox" data-walk-overlay="siteViewGaps" checked>
          Site View eligible gaps</label>
      </div>
    </div>
    <div class="osme-subsection">
      <strong>Coverage result</strong>
      <div class="osme-walk-plan-summary"></div>
      <div class="osme-walk-components"></div>
      <div class="osme-walk-schedule"></div>
      <div class="osme-toolbar">
        <button class="osme-button osme-walk-copy" type="button" disabled>
          Copy plan JSON
        </button>
        <button class="osme-button osme-walk-export" type="button" disabled>
          Download plan JSON
        </button>
      </div>
    </div>
  `;
  workspace.append(pane);

  const element = (className) =>
    pane.querySelector(`.osme-${className.replaceAll("_", "-")}`);
  const el = {
    refresh: element("walk_refresh"),
    capabilities: element("walk_capabilities"),
    scope: element("walk_scope"),
    start: element("walk_start"),
    useSelected: element("walk_use_selected"),
    exclusions: element("walk_exclusions"),
    addExclusions: element("walk_add_exclusions"),
    clearExclusions: element("walk_clear_exclusions"),
    exclusionSummary: element("walk_exclusion_summary"),
    returnToStart: element("walk_return"),
    chunk: element("walk_chunk"),
    checkpointMode: element("walk_checkpoint_mode"),
    sleepDuration: element("walk_sleep_duration"),
    sleeps: element("walk_sleeps"),
    addSleep: element("walk_add_sleep"),
    plan: element("walk_plan"),
    planSummary: element("walk_plan_summary"),
    components: element("walk_components"),
    schedule: element("walk_schedule"),
    copy: element("walk_copy"),
    export: element("walk_export"),
  };

  function create(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== "") node.textContent = String(text);
    return node;
  }

  function graphSnapshot() {
    return runtime.state.snapshot || {
      map: { id: runtime.currentMapId(), name: "" },
      editIndex: null,
      selectedWaypointIds: [],
      waypoints: [],
      edges: [],
      docks: [],
    };
  }

  function graphSignature(snapshot = graphSnapshot()) {
    return [
      snapshot.map?.id || "",
      snapshot.editIndex ?? "",
      snapshot.waypoints?.length || 0,
      snapshot.edges?.length || 0,
    ].join("|");
  }

  function shortId(value, size = 7) {
    return runtime.model.shortId(value, size);
  }

  function formatNumber(value, digits = 0) {
    return Number.isFinite(value)
      ? value.toLocaleString(undefined, {
          maximumFractionDigits: digits,
          minimumFractionDigits: digits,
        })
      : "—";
  }

  function selectedWaypointId() {
    return graphSnapshot().selectedWaypointIds?.[0] || "";
  }

  function touchOverlay() {
    state.overlayRevision += 1;
    state.overlayCache = null;
    runtime.state.lastOverlayKey = "";
  }

  function renderRefreshState() {
    el.refresh.disabled = state.loading;
  }

  function renderCapabilities() {
    el.capabilities.replaceChildren();
    if (!state.siteViewSnapshot) {
      el.capabilities.append(create(
        "p",
        "osme-empty",
        state.loading
          ? "Reading Orbit's Site View settings…"
          : "Open the Walk tab or refresh Site View data.",
      ));
      return;
    }
    const capabilities = state.siteViewSnapshot.capabilities || {};
    const available = Object.entries(capabilities)
      .filter(([, adapter]) => adapter)
      .map(([kind]) => kind);
    el.capabilities.append(create(
      "p",
      "osme-empty",
      `${state.siteViewSnapshot.sitePanoWaypoints.length} Site View waypoint settings · ` +
      `${state.siteViewSnapshot.siteDocks.length} Docks · ` +
      `read-only adapters: ${available.join(", ") || "none"}`,
    ));
  }

  function focusButton(waypointId, label = "Focus") {
    const button = create("button", "osme-button osme-small", label);
    button.type = "button";
    button.dataset.walkFocus = waypointId;
    return button;
  }

  function parseExcludedWaypointIds(value = el.exclusions.value) {
    return [...new Set(
      String(value || "")
        .split(/\r?\n/)
        .map((line) => line.replace(/#.*/, "").trim())
        .filter(Boolean),
    )];
  }

  function setExcludedWaypointIds(waypointIds) {
    el.exclusions.value = [...new Set(waypointIds)]
      .sort()
      .join("\n");
    renderExclusionSummary();
    touchOverlay();
  }

  function renderExclusionSummary() {
    const count = parseExcludedWaypointIds().length;
    el.exclusionSummary.textContent =
      `${count.toLocaleString()} waypoint${count === 1 ? "" : "s"} ` +
      "explicitly excluded.";
  }

  function renderPlanSummary() {
    el.planSummary.replaceChildren();
    el.components.replaceChildren();
    el.schedule.replaceChildren();
    el.copy.disabled = !state.plan;
    el.export.disabled = !state.plan;
    const plan = state.plan;
    if (!plan) {
      el.planSummary.append(create(
        "p",
        "osme-empty",
        "No coverage plan yet. Planning is local and does not change Orbit.",
      ));
      return;
    }
    const valid = plan.validation?.valid;
    const status = create(
      "div",
      "osme-finding",
    );
    status.dataset.severity = valid && !state.planStale ? "info" : "warning";
    status.append(
      create(
        "strong",
        "",
        valid && !state.planStale
          ? "Graph-valid dry-run plan"
          : state.planStale
            ? "Plan is stale after a graph change"
            : "Plan validation failed",
      ),
      create(
        "p",
        "",
        `${plan.totals.requiredWaypointCount.toLocaleString()} required waypoints · ` +
        `${plan.totals.traversalCount.toLocaleString()} edge traversals · ` +
        `${plan.totals.repeatedVisitCount.toLocaleString()} repeated visits · ` +
        `${plan.executionSequence.entryCount.toLocaleString()} ordered targets ` +
        `(${plan.executionSequence.navigationOnlyCheckpointCount.toLocaleString()} ` +
        `navigation-only, ` +
        `${plan.executionSequence.compatibilitySleepCheckpointCount.toLocaleString()} ` +
        `fallback Sleeps) · ` +
        `${plan.totals.componentTransitions.toLocaleString()} component transitions`,
      ),
    );
    el.planSummary.append(status);
    el.planSummary.append(create(
      "p",
      "osme-empty",
      `${plan.compatibility.requiredNewSiteElementCount.toLocaleString()} ` +
      "new route-target/intentional-Sleep SiteElements proposed · " +
      "0 existing SiteWalks or SiteElements read or modified",
    ));
    el.planSummary.append(create(
      "p",
      "osme-empty",
      `Coverage anchor ${shortId(plan.coverageAnchor.waypointId)} ` +
      `(${plan.coverageAnchor.source.replaceAll("_", " ")}) · active edges only`,
    ));
    const siteView = plan.siteViewCoverage;
    if (siteView) {
      el.planSummary.append(create(
        "p",
        "osme-empty",
        `Site View route coverage ` +
        `${siteView.plannedCoveredEligibleWaypointCount.toLocaleString()}/` +
        `${siteView.eligibleWaypointCount.toLocaleString()} eligible waypoints · ` +
        `${siteView.explicitlyExcludedEligibleWaypointCount.toLocaleString()} ` +
        `explicitly excluded · ` +
        `${siteView.disconnectedEligibleWaypointCount.toLocaleString()} outside ` +
        "the planned active scope · mission-independent. " +
        "This proves route reachability, not image capture.",
      ));
    }
    if (plan.exclusions.waypointCount) {
      el.planSummary.append(create(
        "p",
        "osme-warning-text",
        `${plan.exclusions.waypointCount.toLocaleString()} explicit exclusions ` +
        `removed ${plan.exclusions.removedActiveEdgeCount.toLocaleString()} ` +
        "incident active edges before planning. Verify the red exclusion markers.",
      ));
    }
    if (plan.totals.componentTransitions > 0) {
      el.planSummary.append(create(
        "p",
        "osme-warning-text",
        `${plan.graphSummary.plannedComponentCount.toLocaleString()} selected ` +
        "components cannot be one continuous GraphNav route. Each component " +
        "needs a separate start; transitions require relocalization or a dock.",
      ));
    }
    if (plan.graphSummary.excludedDisconnectedWaypointCount) {
      el.planSummary.append(create(
        "p",
        "osme-empty",
        `${plan.graphSummary.excludedDisconnectedWaypointCount.toLocaleString()} ` +
        "waypoints in other active-disconnected or isolated components are excluded. " +
        "Use the audit scope only when those components must be inspected.",
      ));
    }
    if (plan.executionSequence.compatibilitySleepCheckpointCount) {
      el.planSummary.append(create(
        "p",
        "osme-warning-text",
        `${plan.executionSequence.compatibilitySleepCheckpointCount.toLocaleString()} ` +
        "short Sleeps are proposed only as route-checkpoint compatibility fallbacks. " +
        "Qualify them on the target Orbit version.",
      ));
    }
    const reviewEdgeCount = new Set(
      plan.components.flatMap((component) => component.reviewEdgeKeys || []),
    ).size;
    if (reviewEdgeCount) {
      el.planSummary.append(create(
        "p",
        "osme-warning-text",
        `${reviewEdgeCount.toLocaleString()} route edges carry stairs, direction, ` +
        "mobility, path, alternate-route, or Area callback settings. Topology " +
        "validation does not prove robot traversability; qualify the generated Walk.",
      ));
    }
    if (plan.validation?.errors?.length) {
      el.planSummary.append(create(
        "p",
        "osme-warning-text",
        plan.validation.errors.slice(0, 8).join(" · "),
      ));
    }

    el.components.append(create(
      "strong",
      "",
      `Component routes (${plan.components.length.toLocaleString()})`,
    ));
    for (const component of plan.components.slice(0, 100)) {
      const row = create("div", "osme-list-row");
      row.append(
        create(
          "strong",
          "",
          `#${component.componentIndex + 1} · ` +
          `${component.requiredWaypointIds.length.toLocaleString()} waypoints`,
        ),
        create(
          "span",
          component.requiresManualLocalization ? "osme-warning-text" : "",
          `${component.traversalCount.toLocaleString()} traversals · ` +
          `${component.checkpointCount.toLocaleString()} checkpoints` +
          (component.isolated ? " · isolated" : "") +
          (component.hasDock ? " · dock" : " · no known dock") +
          (component.reviewEdgeKeys?.length
            ? ` · ${component.reviewEdgeKeys.length} constrained edges`
            : ""),
        ),
        focusButton(component.startWaypointId, "Start"),
      );
      el.components.append(row);
    }
    if (plan.components.length > 100) {
      el.components.append(create(
        "p",
        "osme-empty",
        `Showing 100 of ${plan.components.length.toLocaleString()} component routes. ` +
        "The downloaded JSON contains all of them.",
      ));
    }

    el.schedule.append(create(
      "strong",
      "",
      `Ordered route targets (${plan.executionSequence.entryCount})`,
    ));
    el.schedule.append(create(
      "p",
      "osme-empty",
      "Follow #1, #2, … in this order. A target may represent a NavigateRoute " +
      "checkpoint, a component entry, or an intentional Sleep; intermediate " +
      "route waypoints need no Action.",
    ));
    const kindLabel = (entry) => {
      if (entry.kind === "intentional_sleep") return "Intentional Sleep";
      if (entry.action?.kind === "sleep") return "Compatibility Sleep";
      if (entry.kind === "component_entry") return "Component entry";
      return "NavigateRoute";
    };
    for (const item of plan.executionSequence.entries.slice(0, 500)) {
      const row = create("div", "osme-list-row osme-walk-schedule-row");
      row.append(
        create(
          "strong",
          "",
          `#${item.sequence} · ${kindLabel(item)}`,
        ),
        create(
          "span",
          "",
          `component ${item.componentIndex + 1} · ` +
          `${item.routeWaypointIds.length.toLocaleString()} route waypoints`,
        ),
        create("code", "", item.targetWaypointId),
        focusButton(item.targetWaypointId),
      );
      el.schedule.append(row);
    }
    if (plan.executionSequence.entries.length > 500) {
      el.schedule.append(create(
        "p",
        "osme-empty",
        `Showing 500 of ${plan.executionSequence.entryCount.toLocaleString()} ` +
        "ordered targets. The downloaded JSON contains all targets.",
      ));
    }
    if (plan.actionSchedule.unscheduled.length) {
      el.schedule.append(create(
        "p",
        "osme-warning-text",
        `${plan.actionSchedule.unscheduled.length} intentional Sleeps could not ` +
        `be placed: ${[
          ...new Set(plan.actionSchedule.unscheduled.map((item) => item.reason)),
        ].join(", ")}`,
      ));
    }
  }

  function render() {
    if (lifecycleSignal.aborted) return;
    renderRefreshState();
    renderCapabilities();
    renderExclusionSummary();
    renderPlanSummary();
    el.plan.disabled = state.loading || !(graphSnapshot().waypoints || []).length;
    el.checkpointMode.disabled = state.loading;
    el.sleepDuration.disabled =
      el.checkpointMode.value !== "compatibility_sleep";
  }

  async function refreshSiteViewSnapshot() {
    if (state.loading || lifecycleSignal.aborted) return;
    if (state.refreshRetryTimer) {
      window.clearTimeout(state.refreshRetryTimer);
      state.refreshRetryTimer = 0;
    }
    state.loading = true;
    let retryAfterLoad = false;
    render();
    try {
      const response = await runtime.requestBridge(
        "site_view_snapshot",
        {},
        12000,
      );
      if (lifecycleSignal.aborted) return;
      state.siteViewSnapshot = response.snapshot;
      state.graphWaypointCountAtSiteViewRefresh =
        graphSnapshot().waypoints?.length || 0;
      touchOverlay();
      retryAfterLoad =
        !state.siteViewSnapshot.sitePanoWaypoints?.length &&
        Boolean(graphSnapshot().waypoints?.length) &&
        state.refreshRetryCount < 4;
      if (retryAfterLoad) {
        state.refreshRetryCount += 1;
        runtime.setStatus(
          `Site View data is still loading; retrying ` +
          `(${state.refreshRetryCount}/4). No resource was changed.`,
          "warning",
        );
      } else {
        state.refreshRetryCount = 0;
        runtime.setStatus(
          `Read ${state.siteViewSnapshot.sitePanoWaypoints.length} Site View ` +
          "waypoint settings. No SiteWalk or SiteElement was read.",
          "ok",
        );
      }
    } catch (error) {
      state.refreshRetryCount = 0;
      runtime.setStatus(
        `${runtime.friendlyError(error.message)}. ` +
        "Site View inspection is read-only.",
        "error",
      );
    } finally {
      state.loading = false;
      render();
      if (retryAfterLoad && !lifecycleSignal.aborted) {
        state.refreshRetryTimer = window.setTimeout(() => {
          state.refreshRetryTimer = 0;
          refreshSiteViewSnapshot();
        }, 1200);
      }
    }
  }

  function parseSupplementalSleeps(value) {
    const actions = [];
    for (const [index, rawLine] of String(value || "").split(/\r?\n/).entries()) {
      const line = rawLine.trim();
      if (!line || line.startsWith("#")) continue;
      const [rawWaypointId, rawSeconds, ...rawName] = line.split(",");
      const waypointId = String(rawWaypointId || "").trim();
      const durationSeconds = Number(String(rawSeconds || "").trim());
      if (!waypointId || !Number.isFinite(durationSeconds) || durationSeconds < 0) {
        throw new Error(
          `Invalid Sleep line ${index + 1}; use waypoint-id, seconds, optional name.`,
        );
      }
      actions.push({
        waypointId,
        durationSeconds,
        name: rawName.join(",").trim() || `Sleep ${actions.length + 1}`,
      });
    }
    return actions;
  }

  function createCoveragePlan() {
    try {
      const snapshot = graphSnapshot();
      const maxRouteWaypoints = Number(el.chunk.value);
      const sleepDurationSeconds = Number(el.sleepDuration.value);
      const supplementalSleepActions = parseSupplementalSleeps(el.sleeps.value);
      const excludedWaypointIds = parseExcludedWaypointIds();
      state.plan = planner.planCoverage(snapshot, {
        scope: el.scope.value,
        startWaypointId: el.start.value.trim(),
        returnToStart: el.returnToStart.checked,
        maxRouteWaypoints,
        checkpointMode: el.checkpointMode.value,
        sleepDurationSeconds,
        dockWaypointIds: [
          ...(snapshot.docks || []).flatMap((dock) => dock.waypointIds || []),
          ...(state.siteViewSnapshot?.siteDocks || []).flatMap(
            (dock) => dock.waypointIds || [],
          ),
        ],
        excludedWaypointIds,
        sitePanoWaypoints: state.siteViewSnapshot?.sitePanoWaypoints || [],
        supplementalSleepActions,
      });
      state.planStale = false;
      state.planGraphSignature = graphSignature(snapshot);
      touchOverlay();
      const plan = state.plan;
      runtime.setStatus(
        `Planned ${plan.totals.requiredWaypointCount.toLocaleString()} waypoints ` +
        `with ${plan.executionSequence.entryCount.toLocaleString()} ordered targets. ` +
        "Orbit was not changed.",
        plan.validation.valid ? "ok" : "warning",
      );
      render();
    } catch (error) {
      runtime.setStatus(runtime.friendlyError(error.message), "error");
    }
  }

  function planJson() {
    return `${JSON.stringify(state.plan, null, 2)}\n`;
  }

  function downloadPlan() {
    if (!state.plan) return;
    const blob = new Blob([planJson()], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download =
      `orbit-coverage-plan-${graphSnapshot().map.id || "site-map"}.json`;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  function focusWaypoint(waypointId) {
    if (!waypointId) return;
    runtime.requestBridge("focus", { waypointIds: [waypointId] })
      .catch((error) =>
        runtime.setStatus(runtime.friendlyError(error.message), "error")
      );
  }

  function overlayState() {
    if (state.overlayCache) return state.overlayCache;
    state.overlayCache = {
      revision: state.overlayRevision,
      stale: state.planStale,
      routeTargetMarkers: state.overlay.routeTargets
        ? (state.plan?.executionSequence?.entries || []).map((item) => ({
            waypointId: item.targetWaypointId,
            sequence: item.sequence,
            kind: item.kind,
          }))
        : [],
      coverageComponents: state.overlay.coverageRoute
        ? state.plan?.components?.map((component) => ({
            componentIndex: component.componentIndex,
            waypointWalk: component.waypointWalk,
          })) || []
        : [],
      excludedWaypointIds: state.overlay.exclusions
        ? state.plan?.exclusions?.waypointIds || parseExcludedWaypointIds()
        : [],
      siteViewGapWaypointIds: state.overlay.siteViewGaps
        ? state.plan?.siteViewCoverage?.disconnectedEligibleWaypointIds ||
          (state.siteViewSnapshot?.sitePanoWaypoints || [])
            .filter((item) => item.allowCaptureVisual)
            .map((item) => item.waypointId)
        : [],
    };
    return state.overlayCache;
  }

  el.refresh.addEventListener("click", refreshSiteViewSnapshot, {
    signal: lifecycleSignal,
  });
  el.useSelected.addEventListener("click", () => {
    const waypointId = selectedWaypointId();
    if (!waypointId) {
      runtime.setStatus("Select a waypoint in Orbit first.", "warning");
      return;
    }
    el.start.value = waypointId;
    runtime.setStatus(`Coverage start set to ${shortId(waypointId)}.`, "ok");
  }, { signal: lifecycleSignal });
  el.addExclusions.addEventListener("click", () => {
    const selected = graphSnapshot().selectedWaypointIds || [];
    if (!selected.length) {
      runtime.setStatus("Select one or more waypoints in Orbit first.", "warning");
      return;
    }
    setExcludedWaypointIds([
      ...parseExcludedWaypointIds(),
      ...selected,
    ]);
    runtime.setStatus(
      `Added ${selected.length.toLocaleString()} selected waypoints to exclusions.`,
      "ok",
    );
  }, { signal: lifecycleSignal });
  el.clearExclusions.addEventListener("click", () => {
    setExcludedWaypointIds([]);
    runtime.setStatus("Cleared explicit waypoint exclusions.", "ok");
  }, { signal: lifecycleSignal });
  el.exclusions.addEventListener("input", () => {
    renderExclusionSummary();
    touchOverlay();
  }, { signal: lifecycleSignal });
  el.addSleep.addEventListener("click", () => {
    const waypointId = selectedWaypointId();
    if (!waypointId) {
      runtime.setStatus("Select a waypoint in Orbit first.", "warning");
      return;
    }
    const prefix = el.sleeps.value.trim() ? `${el.sleeps.value.trimEnd()}\n` : "";
    el.sleeps.value = `${prefix}${waypointId}, 1, Sleep`;
  }, { signal: lifecycleSignal });
  el.checkpointMode.addEventListener("change", () => {
    el.sleepDuration.disabled =
      el.checkpointMode.value !== "compatibility_sleep";
  }, { signal: lifecycleSignal });
  el.plan.addEventListener("click", createCoveragePlan, {
    signal: lifecycleSignal,
  });
  el.copy.addEventListener("click", () => {
    if (!state.plan) return;
    navigator.clipboard.writeText(planJson())
      .then(() => runtime.setStatus("Coverage plan JSON copied.", "ok"))
      .catch(() => runtime.setStatus("Clipboard access was unavailable.", "warning"));
  }, { signal: lifecycleSignal });
  el.export.addEventListener("click", downloadPlan, {
    signal: lifecycleSignal,
  });
  pane.addEventListener("click", (event) => {
    const button = event.target.closest("[data-walk-focus]");
    if (button) focusWaypoint(button.dataset.walkFocus);
  }, { signal: lifecycleSignal });
  pane.addEventListener("change", (event) => {
    const checkbox = event.target.closest("[data-walk-overlay]");
    if (!checkbox) return;
    state.overlay[checkbox.dataset.walkOverlay] = checkbox.checked;
    touchOverlay();
  }, { signal: lifecycleSignal });
  nav.addEventListener("click", (event) => {
    if (
      event.target.closest("[data-tab]")?.dataset.tab === "walk" &&
      !state.siteViewSnapshot &&
      !state.loading
    ) refreshSiteViewSnapshot();
  }, { signal: lifecycleSignal });
  window.addEventListener(runtime.instanceEvents.snapshot, (event) => {
    const snapshot = graphSnapshot();
    const liveMapId = String(event.detail?.mapId || snapshot.map?.id || "");
    if (
      state.siteViewSnapshot?.map?.id &&
      liveMapId &&
      state.siteViewSnapshot.map.id !== liveMapId
    ) {
      state.siteViewSnapshot = null;
      state.plan = null;
      state.planStale = false;
      state.planGraphSignature = "";
      state.refreshRetryCount = 0;
      state.graphWaypointCountAtSiteViewRefresh = 0;
      if (state.refreshRetryTimer) {
        window.clearTimeout(state.refreshRetryTimer);
        state.refreshRetryTimer = 0;
      }
      touchOverlay();
      render();
      return;
    }
    if (
      state.siteViewSnapshot &&
      !state.siteViewSnapshot.sitePanoWaypoints?.length &&
      (snapshot.waypoints?.length || 0) >
        state.graphWaypointCountAtSiteViewRefresh &&
      !state.loading &&
      !state.refreshRetryTimer
    ) {
      state.refreshRetryCount = 0;
      refreshSiteViewSnapshot();
    }
    if (
      state.plan &&
      state.planGraphSignature &&
      graphSignature(snapshot) !== state.planGraphSignature
    ) {
      state.planStale = true;
      state.plan.validation = planner.validateCoveragePlan(snapshot, state.plan);
      state.planGraphSignature = graphSignature(snapshot);
      touchOverlay();
      renderPlanSummary();
    }
  }, { signal: lifecycleSignal });

  function disposeWalk(event) {
    if (event?.detail?.instanceId === runtime.instanceId) return;
    if (state.refreshRetryTimer) window.clearTimeout(state.refreshRetryTimer);
    lifecycleController.abort();
    removeInvalidationListener();
  }
  window.addEventListener(runtime.disposeEvent, disposeWalk, {
    signal: lifecycleSignal,
  });
  removeInvalidationListener = extensionContext.onInvalidated(disposeWalk);

  globalThis.OrbitSiteMapEditorWalk = Object.freeze({ overlayState });
  render();
})();
