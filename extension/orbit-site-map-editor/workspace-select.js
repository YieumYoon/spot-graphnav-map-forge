(() => {
  "use strict";

  globalThis.OrbitSiteMapEditorSelectWorkspace = Object.freeze({
    selectors: Object.freeze([
      "selection-count",
      "selection-mode",
      "from-orbit",
      "invert",
      "clear-selection",
      "apply-selection",
      "selection-summary",
      "query-builder",
      "run-query",
      "query-to-selection",
      "query-summary",
      "neighbors",
      "hop-count",
      "n-hop",
      "component",
      "recording",
      "leaves",
      "bridges",
      "select-path-start",
      "select-path-end",
      "select-path",
      "viewport",
      "rectangle",
      "apply-rectangle",
      "polygon",
      "apply-polygon",
      "set-name",
      "save-set",
      "named-sets",
    ]),
    render() {
      return `
        <section class="osme-section osme-advanced-pane" data-workspace-tab="select">
          <div class="osme-section-heading">
            <div><span>SELECT</span><strong>Exact-ID work selection</strong></div>
            <span class="osme-selection-count"></span>
          </div>
          <div class="osme-toolbar">
            <select class="osme-selection-mode" aria-label="Selection algebra">
              <option value="replace">Replace</option>
              <option value="add">Add</option>
              <option value="subtract">Subtract</option>
              <option value="intersect">Intersect</option>
            </select>
            <button class="osme-button osme-from-orbit" type="button">
              Use Orbit selection
            </button>
            <button class="osme-button osme-invert" type="button">Invert</button>
            <button class="osme-button osme-clear-selection" type="button">Clear</button>
            <button class="osme-button osme-primary osme-apply-selection" type="button">
              Select in Orbit
            </button>
          </div>
          <div class="osme-selection-summary"></div>
          <div class="osme-subsection">
            <strong>Query builder</strong>
            <input class="osme-field osme-query-builder" type="text"
              placeholder="type:edge source:manual recording:&lt;id&gt; setting:stairs">
            <div class="osme-toolbar">
              <button class="osme-button osme-run-query" type="button">Run query</button>
              <button class="osme-button osme-query-to-selection" type="button">
                Apply results
              </button>
            </div>
            <div class="osme-query-summary"></div>
          </div>
          <div class="osme-subsection">
            <strong>Graph & recording</strong>
            <div class="osme-toolbar">
              <button class="osme-button osme-neighbors" type="button">1-hop neighbors</button>
              <input class="osme-field osme-hop-count" type="number"
                min="1" max="1000" step="1" value="2" aria-label="N-hop radius">
              <button class="osme-button osme-n-hop" type="button">N-hop</button>
              <button class="osme-button osme-component" type="button">Component</button>
              <button class="osme-button osme-recording" type="button">Same recording</button>
              <button class="osme-button osme-leaves" type="button">Leaves</button>
              <button class="osme-button osme-bridges" type="button">Bridge edges</button>
            </div>
            <div class="osme-toolbar">
              <input class="osme-field osme-select-path-start" type="text"
                placeholder="path start waypoint ID">
              <input class="osme-field osme-select-path-end" type="text"
                placeholder="path end waypoint ID">
              <button class="osme-button osme-select-path" type="button">Shortest path</button>
            </div>
          </div>
          <div class="osme-subsection">
            <strong>Spatial selection</strong>
            <div class="osme-toolbar">
              <button class="osme-button osme-viewport" type="button">Current viewport</button>
              <input class="osme-field osme-rectangle" type="text"
                placeholder="rectangle: x1,y1,x2,y2">
              <button class="osme-button osme-apply-rectangle" type="button">Rectangle</button>
            </div>
            <textarea class="osme-field osme-polygon" rows="2"
              placeholder="polygon/lasso: one x,y point per line"></textarea>
            <button class="osme-button osme-apply-polygon" type="button">
              Polygon / lasso
            </button>
          </div>
          <div class="osme-subsection">
            <strong>Named selection sets</strong>
            <div class="osme-toolbar">
              <input class="osme-field osme-set-name" type="text" placeholder="Set name">
              <button class="osme-button osme-save-set" type="button">Save set</button>
            </div>
            <div class="osme-named-sets"></div>
          </div>
        </section>`;
    },
  });
})();
