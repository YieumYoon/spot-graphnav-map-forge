(() => {
  "use strict";

  globalThis.OrbitSiteMapEditorValidateWorkspace = Object.freeze({
    id: "validate",
    label: "Validate",
    selectors: Object.freeze([
      "run-validation",
      "validation-summary",
      "findings",
      "path-start",
      "path-end",
      "inspect-path",
      "path-result",
      "run-reachability",
      "reachability",
      "run-crosswalk",
      "crosswalks",
    ]),
    render() {
      return `
        <section class="osme-section osme-advanced-pane" data-workspace-tab="validate">
          <div class="osme-section-heading">
            <div><span>VALIDATE</span><strong>Live graph findings</strong></div>
            <button class="osme-button osme-run-validation" type="button">Run</button>
          </div>
          <div class="osme-validation-summary"></div>
          <div class="osme-findings"></div>
          <div class="osme-subsection">
            <strong>Path inspector</strong>
            <div class="osme-toolbar">
              <input class="osme-field osme-path-start" type="text"
                placeholder="start waypoint ID">
              <input class="osme-field osme-path-end" type="text"
                placeholder="end waypoint ID">
              <button class="osme-button osme-inspect-path" type="button">Inspect</button>
            </div>
            <div class="osme-path-result"></div>
          </div>
          <div class="osme-subsection">
            <strong>Reachability</strong>
            <button class="osme-button osme-run-reachability" type="button">
              From first selected waypoint
            </button>
            <div class="osme-reachability"></div>
          </div>
          <div class="osme-subsection">
            <strong>Crosswalk audit</strong>
            <button class="osme-button osme-run-crosswalk" type="button">
              Audit callbacks
            </button>
            <div class="osme-crosswalks"></div>
          </div>
        </section>`;
    },
  });
})();
