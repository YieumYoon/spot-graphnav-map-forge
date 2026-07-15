"use strict";

const $ = (selector) => document.querySelector(selector);

const elements = {
  canvas: $("#map-canvas"),
  loading: $("#loading-state"),
  tooltip: $("#map-tooltip"),
  toast: $("#toast"),
  mapName: $("#map-name"),
  mapSummary: $("#map-summary"),
  zoneName: $("#zone-name"),
  haloHops: $("#halo-hops"),
  cloneHaloActions: $("#clone-halo-actions"),
  excludeUnanchored: $("#exclude-unanchored-waypoints"),
  excludeDependencyFree: $("#exclude-dependency-free-components"),
  showUnanchored: $("#show-unanchored"),
  save: $("#save-plan"),
  saveHint: $("#save-hint"),
  selectionState: $("#selection-state"),
  cursorPosition: $("#cursor-position"),
  zoomLevel: $("#zoom-level"),
  draw: $("#tool-draw"),
  pan: $("#tool-pan"),
  undo: $("#undo-point"),
  clear: $("#clear-polygon"),
  fit: $("#fit-map"),
  theme: $("#theme-toggle"),
  stats: {
    core: $("#stat-core"),
    halo: $("#stat-halo"),
    edges: $("#stat-edges"),
    actions: $("#stat-actions"),
    manual: $("#stat-manual"),
    fiducial: $("#stat-fiducial"),
    loop: $("#stat-loop"),
    cleanupUnanchored: $("#cleanup-unanchored"),
    cleanupRemnants: $("#cleanup-remnants"),
    cleanupComponents: $("#cleanup-components"),
  },
};

const state = {
  data: null,
  waypointById: new Map(),
  actionsByWaypoint: new Map(),
  adjacency: new Map(),
  selectionDependencyIds: new Set(),
  polygon: [],
  core: new Set(),
  halo: new Set(),
  mode: "draw",
  spacePan: false,
  dragging: false,
  dragMoved: false,
  pointerStart: null,
  viewStart: null,
  scale: 1,
  fitScale: 1,
  offsetX: 0,
  offsetY: 0,
  width: 0,
  height: 0,
  dpr: 1,
  renderPending: false,
  overwritePending: false,
  toastTimer: null,
};

const context = elements.canvas.getContext("2d", { alpha: false });

function css(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function worldToScreen(point) {
  return [point.x * state.scale + state.offsetX, -point.y * state.scale + state.offsetY];
}

function screenToWorld(x, y) {
  return [(x - state.offsetX) / state.scale, -(y - state.offsetY) / state.scale];
}

function requestRender() {
  if (state.renderPending) return;
  state.renderPending = true;
  requestAnimationFrame(() => {
    state.renderPending = false;
    render();
  });
}

function resizeCanvas() {
  const rect = elements.canvas.getBoundingClientRect();
  state.width = Math.max(1, rect.width);
  state.height = Math.max(1, rect.height);
  state.dpr = Math.min(window.devicePixelRatio || 1, 2);
  elements.canvas.width = Math.round(state.width * state.dpr);
  elements.canvas.height = Math.round(state.height * state.dpr);
  requestRender();
}

function visibleWaypoint(waypoint) {
  return elements.showUnanchored.checked || waypoint.source !== "waypoint_tform_ko_unanchored";
}

function fitMap() {
  if (!state.data || !state.width || !state.height) return;
  const points = state.data.waypoints.filter(visibleWaypoint);
  if (!points.length) return;
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const point of points) {
    minX = Math.min(minX, point.x);
    minY = Math.min(minY, point.y);
    maxX = Math.max(maxX, point.x);
    maxY = Math.max(maxY, point.y);
  }
  const margin = Math.min(72, Math.max(28, state.width * 0.06));
  const availableWidth = Math.max(1, state.width - margin * 2);
  const availableHeight = Math.max(1, state.height - margin * 2);
  state.scale = Math.min(
    availableWidth / Math.max(1, maxX - minX),
    availableHeight / Math.max(1, maxY - minY),
  );
  state.fitScale = state.scale;
  state.offsetX = state.width / 2 - ((minX + maxX) / 2) * state.scale;
  state.offsetY = state.height / 2 + ((minY + maxY) / 2) * state.scale;
  updateZoomLabel();
  requestRender();
}

function niceGridStep(targetWorldSize) {
  const exponent = Math.floor(Math.log10(Math.max(targetWorldSize, 0.0001)));
  const fraction = targetWorldSize / 10 ** exponent;
  const niceFraction = fraction < 1.5 ? 1 : fraction < 3.5 ? 2 : fraction < 7.5 ? 5 : 10;
  return niceFraction * 10 ** exponent;
}

function drawGrid() {
  const step = niceGridStep(72 / state.scale);
  const [left, bottom] = screenToWorld(0, state.height);
  const [right, top] = screenToWorld(state.width, 0);
  context.strokeStyle = css("--grid");
  context.lineWidth = 1;
  context.beginPath();
  for (let x = Math.floor(left / step) * step; x <= right; x += step) {
    const [screenX] = worldToScreen({ x, y: 0 });
    context.moveTo(Math.round(screenX) + 0.5, 0);
    context.lineTo(Math.round(screenX) + 0.5, state.height);
  }
  for (let y = Math.floor(bottom / step) * step; y <= top; y += step) {
    const [, screenY] = worldToScreen({ x: 0, y });
    context.moveTo(0, Math.round(screenY) + 0.5);
    context.lineTo(state.width, Math.round(screenY) + 0.5);
  }
  context.stroke();
}

function edgeStyle(source, selected) {
  if (source === "EDGE_SOURCE_USER_REQUEST") {
    return { color: css("--primary"), width: selected ? 2.2 : 1.35, dash: [] };
  }
  if (source === "EDGE_SOURCE_FIDUCIAL_LOOP_CLOSURE") {
    return { color: css("--violet"), width: selected ? 1.8 : 1, dash: [6, 4] };
  }
  if (source === "EDGE_SOURCE_SMALL_LOOP_CLOSURE") {
    return { color: css("--cyan"), width: selected ? 1.8 : 1, dash: [3, 3] };
  }
  if (source === "EDGE_SOURCE_LOCALIZATION") {
    return { color: css("--amber"), width: selected ? 1.7 : 0.85, dash: [2, 3] };
  }
  return { color: css("--faint"), width: selected ? 1.5 : 0.65, dash: [] };
}

function drawEdges() {
  const groups = new Map();
  for (const edge of state.data.edges) {
    const from = state.waypointById.get(edge.from);
    const to = state.waypointById.get(edge.to);
    if (!from || !to || !visibleWaypoint(from) || !visibleWaypoint(to)) continue;
    const selected =
      (state.core.has(edge.from) || state.halo.has(edge.from)) &&
      (state.core.has(edge.to) || state.halo.has(edge.to));
    const key = `${edge.source}:${selected ? "selected" : "base"}`;
    if (!groups.has(key)) groups.set(key, { source: edge.source, selected, edges: [] });
    groups.get(key).edges.push([from, to]);
  }
  const ordered = [...groups.values()].sort((a, b) => Number(a.selected) - Number(b.selected));
  for (const group of ordered) {
    const style = edgeStyle(group.source, group.selected);
    context.globalAlpha = group.selected ? 0.95 : 0.35;
    context.strokeStyle = style.color;
    context.lineWidth = style.width;
    context.setLineDash(style.dash);
    context.beginPath();
    for (const [from, to] of group.edges) {
      const [x1, y1] = worldToScreen(from);
      const [x2, y2] = worldToScreen(to);
      context.moveTo(x1, y1);
      context.lineTo(x2, y2);
    }
    context.stroke();
  }
  context.globalAlpha = 1;
  context.setLineDash([]);
}

function drawWaypoints() {
  for (const waypoint of state.data.waypoints) {
    if (!visibleWaypoint(waypoint)) continue;
    const [x, y] = worldToScreen(waypoint);
    if (x < -8 || x > state.width + 8 || y < -8 || y > state.height + 8) continue;
    const isCore = state.core.has(waypoint.id);
    const isHalo = state.halo.has(waypoint.id);
    if (isCore) {
      context.fillStyle = css("--primary");
      context.beginPath();
      context.arc(x, y, 3.1, 0, Math.PI * 2);
      context.fill();
    } else if (isHalo) {
      context.strokeStyle = css("--cyan");
      context.lineWidth = 1.7;
      context.beginPath();
      context.arc(x, y, 3.3, 0, Math.PI * 2);
      context.stroke();
    } else if (waypoint.actions > 0) {
      context.fillStyle = css("--amber");
      context.fillRect(x - 2.3, y - 2.3, 4.6, 4.6);
    } else if (waypoint.source === "waypoint_tform_ko_unanchored") {
      context.strokeStyle = css("--danger");
      context.globalAlpha = 0.65;
      context.lineWidth = 1;
      context.beginPath();
      context.moveTo(x - 2, y - 2);
      context.lineTo(x + 2, y + 2);
      context.moveTo(x + 2, y - 2);
      context.lineTo(x - 2, y + 2);
      context.stroke();
      context.globalAlpha = 1;
    } else {
      context.fillStyle = css("--muted");
      context.globalAlpha = 0.72;
      context.beginPath();
      context.arc(x, y, 1.45, 0, Math.PI * 2);
      context.fill();
      context.globalAlpha = 1;
    }
  }
}

function drawPolygon() {
  if (!state.polygon.length) return;
  context.lineJoin = "round";
  context.strokeStyle = css("--primary");
  context.lineWidth = 2;
  context.beginPath();
  state.polygon.forEach((point, index) => {
    const [x, y] = worldToScreen({ x: point[0], y: point[1] });
    if (index === 0) context.moveTo(x, y);
    else context.lineTo(x, y);
  });
  if (state.polygon.length >= 3) {
    context.closePath();
    context.globalAlpha = 0.12;
    context.fillStyle = css("--primary");
    context.fill();
    context.globalAlpha = 1;
  }
  context.stroke();

  for (let index = 0; index < state.polygon.length; index += 1) {
    const [x, y] = worldToScreen({ x: state.polygon[index][0], y: state.polygon[index][1] });
    context.fillStyle = index === 0 ? css("--text") : css("--primary");
    context.fillRect(x - 3.2, y - 3.2, 6.4, 6.4);
    context.strokeStyle = css("--canvas");
    context.lineWidth = 1;
    context.strokeRect(x - 3.2, y - 3.2, 6.4, 6.4);
  }
}

function render() {
  context.setTransform(state.dpr, 0, 0, state.dpr, 0, 0);
  context.fillStyle = css("--canvas");
  context.fillRect(0, 0, state.width, state.height);
  drawGrid();
  if (!state.data) return;
  drawEdges();
  drawWaypoints();
  drawPolygon();
}

function pointInPolygon(point, polygon) {
  if (polygon.length < 3) return false;
  const [x, y] = point;
  let inside = false;
  let previous = polygon[polygon.length - 1];
  for (const current of polygon) {
    const [x1, y1] = previous;
    const [x2, y2] = current;
    const crosses = (y1 > y) !== (y2 > y);
    if (crosses && x < ((x2 - x1) * (y - y1)) / (y2 - y1) + x1) inside = !inside;
    previous = current;
  }
  return inside;
}

function computeSelection() {
  state.core.clear();
  state.halo.clear();
  if (!state.data || state.polygon.length < 3) {
    updateStats([], 0, { unanchored: 0, remnants: 0, components: 0 });
    requestRender();
    return;
  }
  const rawCore = new Set();
  for (const waypoint of state.data.waypoints) {
    if (pointInPolygon([waypoint.x, waypoint.y], state.polygon)) rawCore.add(waypoint.id);
  }
  const hops = Math.max(0, Math.min(10, Number(elements.haloHops.value) || 0));
  const baselineDistances = expandHalo(rawCore, hops);
  for (const id of rawCore) {
    const waypoint = state.waypointById.get(id);
    if (
      !elements.excludeUnanchored.checked ||
      waypoint.source !== "waypoint_tform_ko_unanchored"
    ) {
      state.core.add(id);
    }
  }
  const distances = expandHalo(state.core, hops);
  for (const [id, distance] of distances) {
    if (distance > 0) state.halo.add(id);
  }

  let selected = new Set([...state.core, ...state.halo]);
  const unanchoredExcluded = elements.excludeUnanchored.checked
    ? [...baselineDistances.keys()].filter(
        (id) =>
          !selected.has(id) &&
          state.waypointById.get(id)?.source === "waypoint_tform_ko_unanchored",
      ).length
    : 0;
  let remnantWaypoints = 0;
  if (elements.excludeDependencyFree.checked) {
    const components = selectedComponents(selected);
    const largestSize = components[0]?.size || 0;
    for (const component of components) {
      if (component.size === largestSize) continue;
      if ([...component].some((id) => state.selectionDependencyIds.has(id))) continue;
      remnantWaypoints += component.size;
      for (const id of component) {
        state.core.delete(id);
        state.halo.delete(id);
      }
    }
    selected = new Set([...state.core, ...state.halo]);
  }

  const components = selectedComponents(selected);
  const selectedEdges = state.data.edges.filter(
    (edge) => selected.has(edge.from) && selected.has(edge.to),
  );
  const actionIds = elements.cloneHaloActions.checked ? selected : state.core;
  let actionCount = 0;
  for (const id of actionIds) actionCount += state.waypointById.get(id)?.actions || 0;
  updateStats(selectedEdges, actionCount, {
    unanchored: unanchoredExcluded,
    remnants: remnantWaypoints,
    components: components.length,
  });
  requestRender();
}

function expandHalo(core, hops) {
  const distances = new Map([...core].map((id) => [id, 0]));
  const queue = [...core];
  for (let cursor = 0; cursor < queue.length; cursor += 1) {
    const id = queue[cursor];
    const distance = distances.get(id);
    if (distance >= hops) continue;
    for (const neighbor of state.adjacency.get(id) || []) {
      if (!distances.has(neighbor)) {
        distances.set(neighbor, distance + 1);
        queue.push(neighbor);
      }
    }
  }
  return distances;
}

function selectedComponents(selected) {
  const remaining = new Set(selected);
  const components = [];
  while (remaining.size) {
    const root = remaining.values().next().value;
    const component = new Set([root]);
    const queue = [root];
    remaining.delete(root);
    for (let cursor = 0; cursor < queue.length; cursor += 1) {
      for (const neighbor of state.adjacency.get(queue[cursor]) || []) {
        if (!remaining.has(neighbor)) continue;
        remaining.delete(neighbor);
        component.add(neighbor);
        queue.push(neighbor);
      }
    }
    components.push(component);
  }
  return components.sort((left, right) => right.size - left.size);
}

function updateStats(selectedEdges, actionCount, cleanup) {
  const sources = new Map();
  for (const edge of selectedEdges) sources.set(edge.source, (sources.get(edge.source) || 0) + 1);
  elements.stats.core.textContent = state.core.size.toLocaleString();
  elements.stats.halo.textContent = state.halo.size.toLocaleString();
  elements.stats.edges.textContent = selectedEdges.length.toLocaleString();
  elements.stats.actions.textContent = actionCount.toLocaleString();
  elements.stats.manual.textContent = (sources.get("EDGE_SOURCE_USER_REQUEST") || 0).toLocaleString();
  elements.stats.fiducial.textContent = (
    sources.get("EDGE_SOURCE_FIDUCIAL_LOOP_CLOSURE") || 0
  ).toLocaleString();
  elements.stats.loop.textContent = (
    sources.get("EDGE_SOURCE_SMALL_LOOP_CLOSURE") || 0
  ).toLocaleString();
  elements.stats.cleanupUnanchored.textContent = cleanup.unanchored.toLocaleString();
  elements.stats.cleanupRemnants.textContent = cleanup.remnants.toLocaleString();
  elements.stats.cleanupComponents.textContent = cleanup.components.toLocaleString();
  const ready = state.polygon.length >= 3 && state.core.size > 0;
  elements.selectionState.textContent = ready ? "READY" : "NO POLYGON";
  elements.selectionState.classList.toggle("ready", ready);
  updateSaveState();
}

function updateSaveState() {
  const hasName = elements.zoneName.value.trim().length > 0;
  const hasPolygon = state.polygon.length >= 3 && state.core.size > 0;
  elements.save.disabled = !(hasName && hasPolygon);
  if (!hasPolygon) elements.saveHint.textContent = "Add at least three vertices around one waypoint.";
  else if (!hasName) elements.saveHint.textContent = "Enter a zone name to save this plan.";
  else elements.saveHint.textContent = `${state.core.size} core waypoint IDs will be written offline.`;
}

function buildIndexes() {
  state.waypointById = new Map(state.data.waypoints.map((waypoint) => [waypoint.id, waypoint]));
  state.actionsByWaypoint = new Map();
  for (const action of state.data.actions) {
    if (!state.actionsByWaypoint.has(action.waypoint_id)) {
      state.actionsByWaypoint.set(action.waypoint_id, []);
    }
    state.actionsByWaypoint.get(action.waypoint_id).push(action);
  }
  state.adjacency = new Map();
  state.selectionDependencyIds = new Set(state.data.selection_dependency_waypoint_ids || []);
  for (const edge of state.data.edges) {
    if (!state.adjacency.has(edge.from)) state.adjacency.set(edge.from, new Set());
    if (!state.adjacency.has(edge.to)) state.adjacency.set(edge.to, new Set());
    state.adjacency.get(edge.from).add(edge.to);
    state.adjacency.get(edge.to).add(edge.from);
  }
}

function setMode(mode) {
  state.mode = mode;
  elements.draw.classList.toggle("active", mode === "draw");
  elements.pan.classList.toggle("active", mode === "pan");
  elements.draw.setAttribute("aria-pressed", String(mode === "draw"));
  elements.pan.setAttribute("aria-pressed", String(mode === "pan"));
  elements.canvas.classList.toggle("mode-draw", mode === "draw");
  elements.canvas.classList.toggle("mode-pan", mode === "pan");
}

function canvasPoint(event) {
  const rect = elements.canvas.getBoundingClientRect();
  return [event.clientX - rect.left, event.clientY - rect.top];
}

function handlePointerDown(event) {
  elements.canvas.focus({ preventScroll: true });
  const [x, y] = canvasPoint(event);
  const panning = state.mode === "pan" || state.spacePan || event.button === 1;
  if (panning) {
    state.dragging = true;
    state.dragMoved = false;
    state.pointerStart = [x, y];
    state.viewStart = [state.offsetX, state.offsetY];
    elements.canvas.classList.add("dragging");
    elements.canvas.setPointerCapture(event.pointerId);
  }
}

function handlePointerMove(event) {
  const [x, y] = canvasPoint(event);
  const [worldX, worldY] = screenToWorld(x, y);
  elements.cursorPosition.textContent = `x ${worldX.toFixed(2)}  y ${worldY.toFixed(2)}`;
  if (state.dragging) {
    const dx = x - state.pointerStart[0];
    const dy = y - state.pointerStart[1];
    state.dragMoved ||= Math.hypot(dx, dy) > 2;
    state.offsetX = state.viewStart[0] + dx;
    state.offsetY = state.viewStart[1] + dy;
    hideTooltip();
    requestRender();
    return;
  }
  updateTooltip(x, y);
}

function handlePointerUp(event) {
  if (!state.dragging) return;
  state.dragging = false;
  elements.canvas.classList.remove("dragging");
  if (elements.canvas.hasPointerCapture(event.pointerId)) {
    elements.canvas.releasePointerCapture(event.pointerId);
  }
}

function handleCanvasClick(event) {
  if (state.mode !== "draw" || state.spacePan || state.dragMoved) {
    state.dragMoved = false;
    return;
  }
  const [x, y] = canvasPoint(event);
  state.polygon.push(screenToWorld(x, y));
  state.overwritePending = false;
  resetSaveButton();
  computeSelection();
}

function handleDoubleClick(event) {
  if (state.mode !== "draw") return;
  event.preventDefault();
  if (state.polygon.length > 3) state.polygon.pop();
  setMode("pan");
  computeSelection();
  showToast("Polygon closed. Pan or save the plan.");
}

function handleWheel(event) {
  event.preventDefault();
  const [x, y] = canvasPoint(event);
  const before = screenToWorld(x, y);
  const factor = Math.exp(-event.deltaY * 0.0012);
  state.scale = Math.max(state.fitScale * 0.08, Math.min(state.fitScale * 40, state.scale * factor));
  state.offsetX = x - before[0] * state.scale;
  state.offsetY = y + before[1] * state.scale;
  updateZoomLabel();
  requestRender();
}

function updateZoomLabel() {
  const percent = state.fitScale ? Math.round((state.scale / state.fitScale) * 100) : 100;
  elements.zoomLevel.textContent = `${percent}%`;
}

function updateTooltip(x, y) {
  if (!state.data) return;
  let nearest = null;
  let nearestDistance = 10;
  for (const waypoint of state.data.waypoints) {
    if (!visibleWaypoint(waypoint)) continue;
    const [screenX, screenY] = worldToScreen(waypoint);
    const distance = Math.hypot(screenX - x, screenY - y);
    if (distance < nearestDistance) {
      nearest = waypoint;
      nearestDistance = distance;
    }
  }
  if (!nearest) {
    hideTooltip();
    return;
  }
  const actions = state.actionsByWaypoint.get(nearest.id) || [];
  const actionText = actions.length
    ? `<span class="tooltip-action">${actions.length} action${actions.length === 1 ? "" : "s"}: ${escapeHtml(actions.slice(0, 2).map((action) => action.name).join(", "))}</span>`
    : "No actions";
  elements.tooltip.innerHTML = `<strong>${escapeHtml(nearest.id)}</strong>${actionText}<br>Component ${nearest.component + 1} · ${escapeHtml(nearest.source)}`;
  elements.tooltip.style.left = `${Math.min(state.width - 310, x + 13)}px`;
  elements.tooltip.style.top = `${Math.max(10, y - 18)}px`;
  elements.tooltip.hidden = false;
}

function hideTooltip() {
  elements.tooltip.hidden = true;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"]/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
  })[character]);
}

function undoPoint() {
  state.polygon.pop();
  state.overwritePending = false;
  resetSaveButton();
  computeSelection();
}

function clearPolygon() {
  state.polygon = [];
  state.overwritePending = false;
  resetSaveButton();
  computeSelection();
}

async function savePlan() {
  if (elements.save.disabled) return;
  elements.save.disabled = true;
  elements.save.querySelector("span").textContent = "Saving…";
  const request = {
    zone_name: elements.zoneName.value.trim(),
    polygon: state.polygon,
    halo_hops: Number(elements.haloHops.value),
    clone_halo_actions: elements.cloneHaloActions.checked,
    exclude_unanchored_waypoints: elements.excludeUnanchored.checked,
    exclude_dependency_free_components: elements.excludeDependencyFree.checked,
    overwrite: state.overwritePending,
  };
  try {
    const response = await fetch("/api/plans", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    const result = await response.json();
    if (response.status === 409) {
      state.overwritePending = true;
      elements.save.classList.add("danger-state");
      elements.save.querySelector("span").textContent = "Overwrite existing plan";
      showToast("A plan with this name already exists. Click again to overwrite it.", true);
      return;
    }
    if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
    state.overwritePending = false;
    resetSaveButton();
    elements.saveHint.textContent = result.path;
    showToast(`Saved ${result.plan.counts.core_waypoints} core waypoints to ${result.path}`);
  } catch (error) {
    showToast(error.message || String(error), true);
  } finally {
    if (!state.overwritePending) resetSaveButton();
    updateSaveState();
  }
}

function resetSaveButton() {
  elements.save.classList.remove("danger-state");
  elements.save.querySelector("span").textContent = "Save zone plan";
}

function showToast(message, error = false) {
  clearTimeout(state.toastTimer);
  elements.toast.textContent = message;
  elements.toast.classList.toggle("error", error);
  elements.toast.hidden = false;
  state.toastTimer = setTimeout(() => {
    elements.toast.hidden = true;
  }, 5000);
}

function handleKeyDown(event) {
  const isFormField = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName);
  if (event.code === "Space" && !isFormField) {
    event.preventDefault();
    state.spacePan = true;
    elements.canvas.classList.add("mode-pan");
    return;
  }
  if (isFormField) return;
  if (event.key.toLowerCase() === "d") setMode("draw");
  if (event.key.toLowerCase() === "p") setMode("pan");
  if (event.key.toLowerCase() === "f") fitMap();
  if (event.key === "Escape") clearPolygon();
  if (event.key === "Backspace") {
    event.preventDefault();
    undoPoint();
  }
  if (event.key === "+" || event.key === "=") zoomAtCenter(1.2);
  if (event.key === "-") zoomAtCenter(1 / 1.2);
}

function handleKeyUp(event) {
  if (event.code === "Space") {
    state.spacePan = false;
    elements.canvas.classList.toggle("mode-pan", state.mode === "pan");
  }
}

function zoomAtCenter(factor) {
  const before = screenToWorld(state.width / 2, state.height / 2);
  state.scale = Math.max(state.fitScale * 0.08, Math.min(state.fitScale * 40, state.scale * factor));
  state.offsetX = state.width / 2 - before[0] * state.scale;
  state.offsetY = state.height / 2 + before[1] * state.scale;
  updateZoomLabel();
  requestRender();
}

function toggleTheme() {
  const root = document.documentElement;
  const theme = root.dataset.theme === "dark" ? "light" : "dark";
  root.dataset.theme = theme;
  localStorage.setItem("map-forge-theme", theme);
  requestRender();
}

function bindEvents() {
  new ResizeObserver(resizeCanvas).observe(elements.canvas);
  elements.draw.addEventListener("click", () => setMode("draw"));
  elements.pan.addEventListener("click", () => setMode("pan"));
  elements.undo.addEventListener("click", undoPoint);
  elements.clear.addEventListener("click", clearPolygon);
  elements.fit.addEventListener("click", fitMap);
  elements.theme.addEventListener("click", toggleTheme);
  elements.save.addEventListener("click", savePlan);
  elements.canvas.addEventListener("pointerdown", handlePointerDown);
  elements.canvas.addEventListener("pointermove", handlePointerMove);
  elements.canvas.addEventListener("pointerup", handlePointerUp);
  elements.canvas.addEventListener("pointercancel", handlePointerUp);
  elements.canvas.addEventListener("pointerleave", hideTooltip);
  elements.canvas.addEventListener("click", handleCanvasClick);
  elements.canvas.addEventListener("dblclick", handleDoubleClick);
  elements.canvas.addEventListener("wheel", handleWheel, { passive: false });
  elements.zoneName.addEventListener("input", () => {
    state.overwritePending = false;
    resetSaveButton();
    updateSaveState();
  });
  elements.haloHops.addEventListener("input", computeSelection);
  elements.cloneHaloActions.addEventListener("change", computeSelection);
  elements.excludeUnanchored.addEventListener("change", computeSelection);
  elements.excludeDependencyFree.addEventListener("change", computeSelection);
  elements.showUnanchored.addEventListener("change", () => {
    fitMap();
    computeSelection();
  });
  window.addEventListener("keydown", handleKeyDown);
  window.addEventListener("keyup", handleKeyUp);
  window.addEventListener("blur", () => {
    state.spacePan = false;
    state.dragging = false;
    elements.canvas.classList.remove("dragging");
  });
}

async function initialize() {
  const storedTheme = localStorage.getItem("map-forge-theme");
  if (storedTheme === "light" || storedTheme === "dark") {
    document.documentElement.dataset.theme = storedTheme;
  }
  bindEvents();
  setMode("draw");
  resizeCanvas();
  try {
    const response = await fetch("/api/workspace");
    if (!response.ok) throw new Error(`Workspace request failed: HTTP ${response.status}`);
    state.data = await response.json();
    buildIndexes();
    elements.mapName.textContent = `${state.data.site_map.name} · ${state.data.counts.waypoints.toLocaleString()} waypoints`;
    elements.mapSummary.textContent =
      `${state.data.counts.edges.toLocaleString()} edges · ` +
      `${(
        state.data.counts.actions
      ).toLocaleString()} actions · ` +
      `${state.data.counts.components.toLocaleString()} components · ` +
      `${state.data.counts.unanchored_waypoints.toLocaleString()} unanchored`;
    fitMap();
    computeSelection();
    elements.loading.classList.add("hidden");
    elements.loading.hidden = true;
  } catch (error) {
    elements.loading.innerHTML = `<strong>Could not load workspace</strong><span>${escapeHtml(error.message || String(error))}</span>`;
    showToast(error.message || String(error), true);
  }
}

initialize();
