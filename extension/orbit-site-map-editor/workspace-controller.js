(() => {
  "use strict";

  function createRegistry({root, nav, host, onActivate = () => {}}) {
    if (!root || !nav || !host) throw new Error("Workspace registry requires root, nav, and host.");
    const controllers = new Map();
    let activeId = "";
    let disposed = false;

    function register(controller) {
      const id = String(controller?.id || "").trim();
      const label = String(controller?.label || "").trim();
      if (!id || !label) throw new Error("Workspace controllers require id and label.");
      if (disposed) throw new Error("Workspace registry is disposed.");
      if (controllers.has(id)) return controllers.get(id);

      const discoveredPanes = [...root.querySelectorAll(`[data-workspace-tab="${id}"]`)];
      const panes = controller.panes?.length
        ? [...controller.panes]
        : discoveredPanes.length
          ? discoveredPanes
          : controller.pane
            ? [controller.pane]
            : [];
      if (!panes.length) throw new Error(`Workspace pane is missing: ${id}`);
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.tab = id;
      button.textContent = label;
      nav.append(button);
      const entry = Object.freeze({
        ...controller,
        id,
        label,
        pane: panes[0],
        panes: Object.freeze(panes),
        button,
      });
      controllers.set(id, entry);
      for (const pane of panes) pane.hidden = id !== activeId;
      button.dataset.active = String(id === activeId);
      return entry;
    }

    function activate(id, options = {}) {
      if (disposed || !controllers.has(id)) return false;
      const previousId = activeId;
      activeId = id;
      for (const controller of controllers.values()) {
        const active = controller.id === id;
        controller.button.dataset.active = String(active);
        for (const pane of controller.panes) pane.hidden = !active;
      }
      if (options.render !== false) controllers.get(id).render?.(options);
      onActivate(id, previousId, options);
      return previousId !== id;
    }

    function renderActive(options = {}) {
      if (disposed) return;
      controllers.get(activeId)?.render?.(options);
    }

    function dispose() {
      if (disposed) return;
      disposed = true;
      for (const controller of controllers.values()) controller.dispose?.();
      controllers.clear();
    }

    return Object.freeze({
      activate,
      activeId: () => activeId,
      controllers: () => [...controllers.values()],
      dispose,
      register,
      renderActive,
    });
  }

  globalThis.OrbitSiteMapEditorWorkspaceController = Object.freeze({createRegistry});
})();
