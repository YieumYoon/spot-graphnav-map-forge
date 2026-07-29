(() => {
  "use strict";

  const runtime = globalThis.OrbitSiteMapEditorRuntime;
  const areaSettings = globalThis.OrbitSiteMapEditorAreaSettings;
  const extensionContext = globalThis.OrbitSiteMapEditorExtensionContext;
  if (!runtime || !areaSettings || !extensionContext) return;
  if (runtime.isDisposed?.() || !extensionContext.isActive()) return;

  const root = runtime.elements.panel;
  const workspace = root?.querySelector(".osme-workspace");
  const workspaceRegistry = globalThis.OrbitSiteMapEditorWorkspaces;
  if (!root || !workspace || !workspaceRegistry) return;
  if (root.dataset.osmeAreasInstance === runtime.instanceId) return;
  root.dataset.osmeAreasInstance = runtime.instanceId;

  const state = {
    selectedIds: new Set(),
    pending: null,
    overlayRevision: 0,
  };
  const lifecycleController = new AbortController();
  const lifecycleSignal = lifecycleController.signal;
  let removeInvalidationListener = () => {};

  const pane = document.createElement("section");
  pane.className = "osme-section osme-advanced-pane osme-areas-pane";
  pane.dataset.workspaceTab = "areas";
  pane.hidden = true;
  pane.innerHTML = `
    <div class="osme-section-heading">
      <div><span>AREA SETTINGS</span><strong>Inspect & batch edit</strong></div>
      <span class="osme-safety-chip">one unsaved change</span>
    </div>
    <p class="osme-action-scope-note">
      Area callback settings live on connected Edges. Labels show the effective
      callback settings; a batch is applied as one native unsaved Orbit draft.
    </p>
    <div class="osme-subsection">
      <strong>1. View and choose Areas</strong>
      <small>
        Configure Area map labels in Explore → Detailed overlay → Areas.
      </small>
      <div class="osme-toolbar">
        <input class="osme-field osme-area-filter" type="search"
          aria-label="Filter Areas"
          placeholder="Filter Area name, ID, or setting">
        <button class="osme-button osme-area-select-visible" type="button">
          Check filtered
        </button>
        <button class="osme-button osme-area-clear" type="button">Clear</button>
      </div>
      <div class="osme-area-summary"></div>
      <div class="osme-area-list"></div>
    </div>
    <div class="osme-subsection">
      <strong>2. Batch scope and change</strong>
      <div class="osme-area-options">
        <label>
          Target
          <select class="osme-field osme-area-scope">
            <option value="selected">Checked Areas only</option>
            <option value="all">All editable Areas</option>
          </select>
        </label>
        <label>
          Settings
          <select class="osme-field osme-area-setting-target">
            <option value="edge">Associated Edge settings (stairs, cost…)</option>
            <option value="callback">Area callback (crosswalk…)</option>
          </select>
        </label>
        <label>
          Change mode
          <select class="osme-field osme-area-mode">
            <option value="merge">Merge listed fields (partial update)</option>
            <option value="replace">Replace complete selected settings</option>
          </select>
        </label>
      </div>
      <label class="osme-area-patch-label">
        Settings JSON
        <textarea class="osme-field osme-area-patch" rows="8"
          spellcheck="false"
          placeholder='{"stairs":true}'></textarea>
      </label>
      <small>
        Merge mode keeps omitted fields and null removes one field. Edge replacement
        preserves Area callbacks; callback replacement changes only the selected callback.
      </small>
      <button class="osme-button osme-primary osme-area-preview" type="button">
        Review batch change
      </button>
    </div>
    <div class="osme-mutation-review osme-area-mutation-review" hidden>
      <strong class="osme-area-mutation-title"></strong>
      <div class="osme-area-mutation-detail"></div>
      <div class="osme-toolbar">
        <button class="osme-button osme-area-cancel" type="button">Cancel</button>
        <button class="osme-button osme-primary osme-area-confirm" type="button">
          Apply unsaved change
        </button>
      </div>
    </div>
  `;
  workspace.append(pane);

  const element = (name) => pane.querySelector(`.osme-${name}`);
  const el = {
    filter: element("area-filter"),
    selectVisible: element("area-select-visible"),
    clear: element("area-clear"),
    summary: element("area-summary"),
    list: element("area-list"),
    scope: element("area-scope"),
    settingTarget: element("area-setting-target"),
    mode: element("area-mode"),
    patch: element("area-patch"),
    preview: element("area-preview"),
    review: element("area-mutation-review"),
    reviewTitle: element("area-mutation-title"),
    reviewDetail: element("area-mutation-detail"),
    cancel: element("area-cancel"),
    confirm: element("area-confirm"),
  };

  function create(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== "") node.textContent = String(text);
    return node;
  }

  function snapshot() {
    return runtime.state.snapshot || {
      map: { id: runtime.currentMapId(), name: "" },
      editIndex: null,
      waypoints: [],
      edges: [],
      areas: [],
    };
  }

  function records() {
    return runtime.areaRecords?.() || areaSettings.records(snapshot());
  }

  function filteredRecords(all = records()) {
    const query = el.filter.value.trim().toLocaleLowerCase();
    return all.filter((area) =>
      !query || [area.name, area.id, area.summary]
        .join(" ")
        .toLocaleLowerCase()
        .includes(query)
    );
  }

  function touchOverlay() {
    state.overlayRevision += 1;
    runtime.state.lastOverlayKey = "";
  }

  function settingsJson(area) {
    const value = JSON.stringify({
      areaType: area.type || "",
      callbacks: area.callbackSettings.slice(0, 6),
      edgeSettings: area.edgeSettings.slice(0, 6),
    }, null, 2);
    return value.length > 6000 ? `${value.slice(0, 5999)}…` : value;
  }

  function renderList() {
    const all = records();
    const visible = filteredRecords(all);
    const editable = all.filter((area) => area.editable);
    const callbackEditable = all.filter((area) => area.callbackEditable);
    const currentEditable = el.settingTarget.value === "callback"
      ? callbackEditable
      : editable;
    const selectedEditable = currentEditable.filter((area) =>
      state.selectedIds.has(area.id)
    );
    el.summary.replaceChildren(create(
      "p",
      "osme-empty",
        `${all.length.toLocaleString()} Areas · ${editable.length.toLocaleString()} with Edges · ` +
        `${callbackEditable.length.toLocaleString()} with callbacks · ` +
        `${selectedEditable.length.toLocaleString()} checked`,
    ));
    el.list.replaceChildren();
    for (const area of visible.slice(0, 500)) {
      const label = create("label", "osme-area-row");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.dataset.areaId = area.id;
      checkbox.checked = state.selectedIds.has(area.id);
      checkbox.disabled = el.settingTarget.value === "callback"
        ? !area.callbackEditable
        : !area.editable;
      const detail = create("span");
      const settingsDetails = create("details", "osme-area-details");
      settingsDetails.append(
        create("summary", "", "Current settings JSON"),
        create("pre", "", settingsJson(area)),
      );
      detail.append(
        create("strong", "", area.name || runtime.model.shortId(area.id, 12)),
        create(
          "small",
          "",
          area.editable
            ? `${area.edgeCount} associated Edge${area.edgeCount === 1 ? "" : "s"} · ` +
              `${area.callbackVariantCount} callback + ` +
              `${area.edgeVariantCount} Edge setting variant(s)`
            : "No associated editable Edge",
        ),
        create("code", "", area.summary),
        settingsDetails,
      );
      label.append(checkbox, detail);
      el.list.append(label);
    }
    if (visible.length > 500) {
      el.list.append(create(
        "p",
        "osme-empty",
        `Showing 500 of ${visible.length.toLocaleString()} matching Areas. Narrow the filter.`,
      ));
    }
    el.preview.disabled = !currentEditable.length;
  }

  function targetAreaIds() {
    const editable = records().filter((area) =>
      el.settingTarget.value === "callback" ? area.callbackEditable : area.editable
    );
    return el.scope.value === "all"
      ? editable.map((area) => area.id)
      : editable.filter((area) => state.selectedIds.has(area.id)).map((area) => area.id);
  }

  function setPending(pending) {
    state.pending = pending;
    renderReview();
  }

  function renderReview() {
    el.review.hidden = !state.pending;
    el.reviewDetail.replaceChildren();
    el.confirm.disabled = Boolean(runtime.state.mutationUncertain);
    if (!state.pending) return;
    const plan = state.pending.plan;
    el.reviewTitle.textContent =
      `${plan.mode === "merge" ? "Partially update" : "Replace settings for"} ` +
      `${plan.areaIds.length} Area${plan.areaIds.length === 1 ? "" : "s"}?`;
    el.reviewDetail.append(
      create(
        "p",
        "",
        `${plan.edgeUpdates.length.toLocaleString()} exact Edges will change in one ` +
        `unsaved Orbit draft. ${plan.unchangedEdgeCount.toLocaleString()} matched ` +
        "callbacks already have the requested values.",
      ),
      create("code", "", `Site Map ${state.pending.mapId}`),
      create(
        "code",
        "",
        `${plan.target === "edge" ? "Edge settings" : "Area callback"} · ` +
        `${plan.mode} ${JSON.stringify(plan.patch)}`,
      ),
      create("small", "", `Observed edit revision ${state.pending.editIndex ?? "—"}`),
    );
  }

  function preview() {
    try {
      const patch = areaSettings.parsePatch(el.patch.value);
      const plan = areaSettings.updatePlan(
        snapshot(),
        targetAreaIds(),
        patch,
        el.mode.value,
        el.settingTarget.value,
      );
      if (!plan.edgeUpdates.length) {
        runtime.setStatus("Every targeted Area already has the requested settings.", "ok");
        setPending(null);
        return;
      }
      setPending({
        mapId: snapshot().map.id,
        editIndex: snapshot().editIndex,
        plan,
      });
      runtime.setStatus(
        `Review ${plan.areaIds.length} Areas across ${plan.edgeUpdates.length} exact Edges. ` +
        "Orbit has not changed.",
        "warning",
      );
    } catch (error) {
      setPending(null);
      runtime.setStatus(error.message, "error");
    }
  }

  async function confirm() {
    const pending = state.pending;
    if (!pending) return;
    if (runtime.state.mutationUncertain) {
      runtime.setStatus(
        "A previous edit is unverified. Inspect or restore Orbit and clear the Edit-tab lock first.",
        "error",
      );
      renderReview();
      return;
    }
    if (
      pending.mapId !== snapshot().map.id ||
      pending.mapId !== runtime.currentMapId() ||
      pending.editIndex !== snapshot().editIndex
    ) {
      runtime.setStatus(
        "The Site Map or unsaved edit revision changed; review the Area batch again.",
        "error",
      );
      setPending(null);
      return;
    }
    el.confirm.disabled = true;
    try {
      await runtime.requestBridge("update_edge_settings", {
        settingsUpdates: pending.plan.edgeUpdates.map((update) => ({
          waypointIds: [update.edge.from, update.edge.to],
          storedFrom: update.edge.from,
          storedTo: update.edge.to,
          observedSourceValue: update.edge.sourceValue,
          observedSettings: update.observedSettings,
          desiredSettings: update.desiredSettings,
        })),
      }, 18000);
      setPending(null);
      await runtime.refreshSnapshot({ quiet: true, allowBusy: true });
      touchOverlay();
      renderList();
      runtime.setStatus(
        "Area settings were applied as one unsaved Orbit change. Review the labels, then Save or Undo in Orbit.",
        "ok",
      );
    } catch (error) {
      if (error.mutationMayExist) {
        setPending(null);
        await runtime.refreshSnapshot({ quiet: true, allowBusy: true });
        runtime.setStatus(
          `${runtime.friendlyError(error.message)}. Orbit may contain an unverified ` +
          `unsaved change; ${runtime.unverifiedMutationGuidance(error)}`,
          "error",
        );
      } else {
        runtime.setStatus(runtime.friendlyError(error.message), "error");
      }
      renderReview();
    }
  }

  el.filter.addEventListener("input", renderList, { signal: lifecycleSignal });
  el.selectVisible.addEventListener("click", () => {
    for (const area of filteredRecords()) {
      if (
        el.settingTarget.value === "callback"
          ? area.callbackEditable
          : area.editable
      ) state.selectedIds.add(area.id);
    }
    touchOverlay();
    renderList();
  }, { signal: lifecycleSignal });
  el.clear.addEventListener("click", () => {
    state.selectedIds.clear();
    setPending(null);
    touchOverlay();
    renderList();
  }, { signal: lifecycleSignal });
  el.list.addEventListener("change", (event) => {
    const checkbox = event.target.closest("input[data-area-id]");
    if (!checkbox) return;
    if (checkbox.checked) state.selectedIds.add(checkbox.dataset.areaId);
    else state.selectedIds.delete(checkbox.dataset.areaId);
    setPending(null);
    touchOverlay();
    renderList();
  }, { signal: lifecycleSignal });
  el.scope.addEventListener("change", () => setPending(null), {
    signal: lifecycleSignal,
  });
  el.settingTarget.addEventListener("change", () => {
    el.patch.placeholder = el.settingTarget.value === "edge"
      ? '{"stairs":true}'
      : '{"description":"North crossing"}';
    setPending(null);
    renderList();
  }, { signal: lifecycleSignal });
  el.mode.addEventListener("change", () => setPending(null), {
    signal: lifecycleSignal,
  });
  el.patch.addEventListener("input", () => setPending(null), {
    signal: lifecycleSignal,
  });
  el.preview.addEventListener("click", preview, { signal: lifecycleSignal });
  el.cancel.addEventListener("click", () => setPending(null), {
    signal: lifecycleSignal,
  });
  el.confirm.addEventListener("click", confirm, { signal: lifecycleSignal });
  window.addEventListener(runtime.instanceEvents.snapshot, () => {
    const liveIds = new Set(records().map((area) => area.id));
    state.selectedIds = new Set(
      [...state.selectedIds].filter((id) => liveIds.has(id)),
    );
    if (
      state.pending &&
      (state.pending.mapId !== snapshot().map.id ||
        state.pending.editIndex !== snapshot().editIndex)
    ) setPending(null);
    touchOverlay();
    renderList();
  }, { signal: lifecycleSignal });
  window.addEventListener(runtime.instanceEvents.mutationUncertain, renderReview, {
    signal: lifecycleSignal,
  });

  function disposeAreas(event) {
    if (event?.detail?.instanceId === runtime.instanceId) return;
    lifecycleController.abort();
    removeInvalidationListener();
  }
  window.addEventListener(runtime.disposeEvent, disposeAreas, {
    signal: lifecycleSignal,
  });
  removeInvalidationListener = extensionContext.onInvalidated(disposeAreas);

  workspaceRegistry.register({
    id: "areas",
    label: "Areas",
    pane,
    render: () => {
      touchOverlay();
      renderList();
    },
  });

  globalThis.OrbitSiteMapEditorAreas = Object.freeze({
    overlayState: () => ({
      revision: state.overlayRevision,
      selectedIds: [...state.selectedIds],
    }),
  });

  renderList();
})();
