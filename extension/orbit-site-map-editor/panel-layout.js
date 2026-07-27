(() => {
  "use strict";

  const DEFAULT_LAYOUT = "rail-right";
  const LAYOUTS = Object.freeze(["rail-left", "float", "rail-right"]);
  const LAYOUT_SET = new Set(LAYOUTS);
  const HOST_ATTRIBUTE = "data-osme-editor-rail";

  function normalize(value) {
    return LAYOUT_SET.has(value) ? value : DEFAULT_LAYOUT;
  }

  function apply(host, layout, panelOpen) {
    if (!host?.setAttribute || !host?.removeAttribute) return "";
    const normalized = normalize(layout);
    const side = panelOpen && normalized.startsWith("rail-")
      ? normalized.slice("rail-".length)
      : "";
    if (side) host.setAttribute(HOST_ATTRIBUTE, side);
    else host.removeAttribute(HOST_ATTRIBUTE);
    return side;
  }

  function clear(host) {
    host?.removeAttribute?.(HOST_ATTRIBUTE);
  }

  globalThis.OrbitSiteMapEditorPanelLayout = Object.freeze({
    DEFAULT_LAYOUT,
    HOST_ATTRIBUTE,
    LAYOUTS,
    apply,
    clear,
    normalize,
  });
})();
