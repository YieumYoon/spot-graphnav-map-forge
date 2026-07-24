(() => {
  "use strict";

  let invalidated = false;
  const invalidationListeners = new Set();

  function invalidate() {
    if (invalidated) return;
    invalidated = true;
    for (const listener of invalidationListeners) {
      try {
        listener();
      } catch {
        // Invalidation cleanup must never create a second extension error.
      }
    }
    invalidationListeners.clear();
  }

  function onInvalidated(listener) {
    if (typeof listener !== "function") return () => {};
    if (invalidated) {
      try {
        listener();
      } catch {
        // The caller owns cleanup errors; the context adapter remains fail-closed.
      }
      return () => {};
    }
    invalidationListeners.add(listener);
    return () => invalidationListeners.delete(listener);
  }

  function isActive() {
    if (invalidated) return false;
    try {
      const runtime = globalThis.chrome?.runtime;
      if (!runtime?.id) {
        invalidate();
        return false;
      }
      if (typeof runtime.getManifest === "function") runtime.getManifest();
      return true;
    } catch {
      invalidate();
      return false;
    }
  }

  function localStorageArea() {
    try {
      if (!isActive()) return null;
      return globalThis.chrome?.storage?.local || null;
    } catch {
      invalidate();
      return null;
    }
  }

  function storageGet(keys) {
    const local = localStorageArea();
    if (!local) return Promise.resolve({});
    return new Promise((resolve) => {
      let settled = false;
      const finish = (value = {}) => {
        if (settled) return;
        settled = true;
        resolve(value || {});
      };
      try {
        const pending = local.get(keys, (value) => {
          try {
            if (chrome.runtime?.lastError) {
              invalidate();
              finish();
              return;
            }
          } catch {
            invalidate();
            finish();
            return;
          }
          finish(value);
        });
        if (pending && typeof pending.then === "function") {
          pending.then(finish).catch(() => {
            invalidate();
            finish();
          });
        }
      } catch {
        invalidate();
        finish();
      }
    });
  }

  function storageSet(value) {
    const local = localStorageArea();
    if (!local) return false;
    try {
      const pending = local.set(value, () => {
        try {
          if (chrome.runtime?.lastError) invalidate();
        } catch {
          invalidate();
          // Reloading an unpacked extension invalidates the previous page's content-script
          // context. The extension keeps its current workspace in memory until Orbit reloads.
        }
      });
      if (pending && typeof pending.catch === "function") {
        pending.catch(() => invalidate());
      }
      return true;
    } catch {
      invalidate();
      return false;
    }
  }

  function getUrl(path) {
    if (!isActive()) return "";
    try {
      return chrome.runtime.getURL(path);
    } catch {
      invalidate();
      return "";
    }
  }

  globalThis.OrbitSiteMapEditorExtensionContext = Object.freeze({
    getUrl,
    invalidate,
    isActive,
    isInvalidated: () => invalidated,
    onInvalidated,
    storageGet,
    storageSet,
  });
})();
