(() => {
  "use strict";

  globalThis.OrbitSiteMapEditorActionNamesWorkspace = Object.freeze({
    selectors: Object.freeze([
      "action-name-builder",
      "action-name-enterprise",
      "action-name-site",
      "action-name-area",
      "action-name-work-center",
      "action-name-equipment",
      "action-name-first-number",
      "action-name-mode",
      "action-name-shortcut",
      "action-name-label-toggle",
      "action-name-label-status",
      "action-name-map-selection-status",
      "action-name-clear-selection",
      "action-name-selection-summary",
      "action-name-action-list",
      "review-action-names",
      "action-name-summary",
      "action-name-preview",
      "action-name-mutation-review",
      "action-name-mutation-title",
      "action-name-mutation-detail",
      "cancel-action-name-mutation",
      "confirm-action-name-mutation",
    ]),
    render() {
      return `
        <section class="osme-section osme-advanced-pane"
          data-workspace-tab="action-names">
          <div class="osme-section-heading">
            <div><span>ACTION NAMES</span><strong>Rename selected Actions</strong></div>
            <span class="osme-safety-chip">unsaved until Orbit Save</span>
          </div>
          <p class="osme-action-scope-note">
            Only selected Action names change; waypoint names stay unchanged.
          </p>
          <div class="osme-subsection">
            <strong>1. Select Actions on the map</strong>
            <div class="osme-action-name-mode" role="group"
              aria-label="Action selection mode">
              <button class="osme-button" type="button"
                data-action-name-add-mode="false" aria-pressed="true">
                Normal
              </button>
              <button class="osme-button" type="button"
                data-action-name-add-mode="true" aria-pressed="false">
                Add Actions
              </button>
            </div>
            <small class="osme-action-name-shortcut"></small>
            <label class="osme-action-name-label-control">
              <input class="osme-action-name-label-toggle" type="checkbox" checked>
              Show Action names on map
            </label>
            <small class="osme-action-name-label-status"></small>
            <div class="osme-action-name-map-selection-status"></div>
            <button class="osme-button osme-action-name-clear-selection" type="button">
              Clear selection
            </button>
            <div class="osme-action-name-selection-summary"></div>
            <div class="osme-action-name-action-list"></div>
            <small>Inspection types are suggested when possible. Change any incorrect value.</small>
          </div>
          <div class="osme-subsection osme-action-name-builder">
            <strong>2. Enter naming fields</strong>
            <div class="osme-action-name-options">
              <label>
                Enterprise
                <input class="osme-field osme-action-name-enterprise" type="text"
                  placeholder="ENTERPRISE_CODE" maxlength="32" spellcheck="false">
              </label>
              <label>
                Site
                <input class="osme-field osme-action-name-site" type="text"
                  placeholder="SITE_CODE" maxlength="32" spellcheck="false">
              </label>
              <label>
                Area
                <input class="osme-field osme-action-name-area" type="text"
                  placeholder="AREA_CODE" maxlength="32" spellcheck="false">
              </label>
              <label>
                Work center (optional)
                <input class="osme-field osme-action-name-work-center" type="text"
                  placeholder="WORK_CENTER_CODE" maxlength="32" spellcheck="false">
              </label>
              <label>
                Machine / equipment (optional)
                <input class="osme-field osme-action-name-equipment" type="text"
                  placeholder="EQUIPMENT_CODE" maxlength="32" spellcheck="false">
              </label>
              <label>
                Starting sequence
                <input class="osme-field osme-action-name-first-number" type="text"
                  value="0001" inputmode="numeric" pattern="[0-9]{1,8}" maxlength="8"
                  spellcheck="false">
              </label>
            </div>
            <small>Blank optional fields are skipped. Each selected Action gets the next number.</small>
          </div>
          <div class="osme-subsection">
            <strong>3. Review</strong>
            <div class="osme-action-name-summary"></div>
            <div class="osme-action-name-preview"></div>
            <button class="osme-button osme-primary osme-review-action-names" type="button">
              Review renames
            </button>
          </div>
          <div class="osme-mutation-review osme-action-name-mutation-review" hidden>
            <strong class="osme-action-name-mutation-title"></strong>
            <div class="osme-action-name-mutation-detail"></div>
            <div class="osme-toolbar">
              <button class="osme-button osme-cancel-action-name-mutation" type="button">
                Cancel
              </button>
              <button class="osme-button osme-primary osme-confirm-action-name-mutation"
                type="button">
                Apply renames (unsaved)
              </button>
            </div>
          </div>
        </section>`;
    },
  });
})();
