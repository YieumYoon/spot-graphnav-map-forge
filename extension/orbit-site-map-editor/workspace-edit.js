(() => {
  "use strict";

  globalThis.OrbitSiteMapEditorEditWorkspace = Object.freeze({
    selectors: Object.freeze([
      "preview-archive",
      "copy-settings",
      "preview-paste",
      "preset-list",
      "use-preset",
      "settings-clipboard",
      "settings-matrix",
      "preset-name",
      "save-preset",
      "show-presets",
      "import-presets",
      "preset-json",
      "mutation-review",
      "mutation-title",
      "mutation-detail",
      "cancel-mutation",
      "confirm-mutation",
      "uncertainty-recovery",
      "queue-source",
      "parse-queue",
      "connect-queue",
    ]),
    render() {
      return `
        <section class="osme-section osme-advanced-pane" data-workspace-tab="edit">
          <div class="osme-section-heading">
            <div><span>EDIT</span><strong>Archive & edge settings</strong></div>
            <span class="osme-safety-chip">one native draft</span>
          </div>
          <div class="osme-uncertainty-recovery"></div>
          <div class="osme-toolbar">
            <button class="osme-button osme-preview-archive" type="button">
              Archive selected edges
            </button>
            <button class="osme-button osme-copy-settings" type="button">Copy settings</button>
            <button class="osme-button osme-preview-paste" type="button">Paste settings</button>
            <select class="osme-preset-list" aria-label="Edge setting preset"></select>
            <button class="osme-button osme-use-preset" type="button">Use preset</button>
          </div>
          <div class="osme-settings-clipboard"></div>
          <div class="osme-settings-matrix"></div>
          <div class="osme-subsection">
            <strong>Preset library</strong>
            <div class="osme-toolbar">
              <input class="osme-field osme-preset-name" type="text" placeholder="Preset name">
              <button class="osme-button osme-save-preset" type="button">
                Save copied settings
              </button>
              <button class="osme-button osme-show-presets" type="button">Show JSON</button>
              <button class="osme-button osme-import-presets" type="button">Import JSON</button>
            </div>
            <textarea class="osme-field osme-preset-json" rows="4"
              placeholder="Shareable preset library JSON; no Site Map data"></textarea>
          </div>
          <div class="osme-mutation-review" hidden>
            <strong class="osme-mutation-title"></strong>
            <div class="osme-mutation-detail"></div>
            <div class="osme-toolbar">
              <button class="osme-button osme-cancel-mutation" type="button">Cancel</button>
              <button class="osme-button osme-primary osme-confirm-mutation" type="button">
                Create unsaved draft
              </button>
            </div>
          </div>
          <div class="osme-subsection">
            <strong>Connect queue</strong>
            <textarea class="osme-field osme-queue-source" rows="3"
              placeholder="one exact pair per line: waypoint-id-a, waypoint-id-b"></textarea>
            <button class="osme-button osme-parse-queue" type="button">Parse queue</button>
            <div class="osme-connect-queue"></div>
          </div>
        </section>`;
    },
  });
})();
