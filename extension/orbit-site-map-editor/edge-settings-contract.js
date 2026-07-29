(() => {
  "use strict";

  const FIELDS = Object.freeze([
    "stairs",
    "directionConstraint",
    "requireAlignment",
    "flatGround",
    "overrideMobilityParams",
    "mobilityParams",
    "cost",
    "disableAlternateRouteFinding",
    "pathFollowingMode",
    "maxCorridorDistance",
    "disableDirectedExploration",
    "areaCallbacks",
    "groundClutterMode",
    "audioVisualSettings",
  ]);
  const FIELD_SET = new Set(FIELDS);

  function isSupported(field) {
    return FIELD_SET.has(field);
  }

  globalThis.OrbitSiteMapEditorEdgeSettingsContract = Object.freeze({
    FIELDS,
    FIELD_SET,
    isSupported,
  });
})();
