(() => {
  "use strict";

  const SVG_NS = "http://www.w3.org/2000/svg";

  function svgElement(name, attributes = {}) {
    const element = document.createElementNS(SVG_NS, name);
    for (const [key, value] of Object.entries(attributes)) {
      element.setAttribute(key, String(value));
    }
    return element;
  }

  function stableStringHash(value) {
    let hash = 2166136261;
    for (const character of String(value || "")) {
      hash ^= character.codePointAt(0);
      hash = Math.imul(hash, 16777619);
    }
    return hash;
  }

  function boundedLabel(parts, maximum = 300) {
    const full = parts.join(" · ");
    if (full.length <= maximum) return {display: full, full};
    const included = [];
    for (const part of parts) {
      const candidate = [...included, part].join(" · ");
      if (candidate.length > maximum - 18) break;
      included.push(part);
    }
    const hidden = parts.length - included.length;
    const suffix = hidden > 0 ? ` · … (+${hidden})` : "…";
    const display = included.length
      ? `${included.join(" · ")}${suffix}`
      : `${full.slice(0, maximum - 1)}…`;
    return {display, full};
  }

  function setLabel(element, parts, maximum = 300) {
    const summary = boundedLabel(parts, maximum);
    element.textContent = summary.display;
    if (summary.display !== summary.full) {
      const title = svgElement("title");
      title.textContent = summary.full.length > 2000
        ? `${summary.full.slice(0, 1999)}…`
        : summary.full;
      element.append(title);
    }
    return summary.display;
  }

  function recordingColor(recordingId) {
    return `hsl(${Math.abs(stableStringHash(recordingId)) % 360} 72% 58%)`;
  }

  function labelDensity(steps, zoom) {
    return steps.find((step) => zoom < step.maxZoom) || steps.at(-1);
  }

  function createFrame(
    overlay,
    {rect, cameraX, cameraY, zoom, cameraWidthMeters, detailedVisible},
  ) {
    const pixelsPerMeter = rect.width / cameraWidthMeters * zoom;
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
    const clip = svgElement("clipPath", {id: clipId});
    clip.append(svgElement("rect", {
      x: rect.left,
      y: rect.top,
      width: rect.width,
      height: rect.height,
    }));
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
    const group = svgElement("g", {
      "clip-path": `url(#${clipId})`,
      visibility: detailedVisible ? "visible" : "hidden",
    });
    const areaLabelGroup = svgElement("g", {"clip-path": `url(#${clipId})`});
    const actionNameGroup = svgElement("g", {"clip-path": `url(#${clipId})`});
    overlay.replaceChildren(definitions, group, areaLabelGroup, actionNameGroup);
    return Object.freeze({actionNameGroup, areaLabelGroup, group, inside, project});
  }

  function createAnimationLoop({draw, shouldContinue, schedule}) {
    function animationLoop() {
      if (!shouldContinue()) return;
      draw();
      schedule(animationLoop);
    }
    return animationLoop;
  }

  globalThis.OrbitSiteMapEditorOverlayRenderer = Object.freeze({
    boundedLabel,
    createAnimationLoop,
    createFrame,
    labelDensity,
    recordingColor,
    setLabel,
    stableStringHash,
    svgElement,
  });
})();
