import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

EXTENSION = Path("extension/orbit-site-map-editor")


def test_editor_extension_manifest_is_independent_and_minimal() -> None:
    manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["manifest_version"] == 3
    assert manifest["name"] == "Orbit Site Map Editor"
    if "version_name" in manifest:
        assert manifest["version_name"].startswith(f"{manifest['version']} dev ")
    assert manifest["permissions"] == ["storage"]
    assert "host_permissions" not in manifest
    assert "background" not in manifest
    assert len(manifest["content_scripts"]) == 1
    content_script = manifest["content_scripts"][0]
    assert content_script["matches"] == ["https://*/control_room/maps/*/edit*"]
    assert content_script["run_at"] == "document_idle"
    assert len(content_script["css"]) == len(set(content_script["css"]))
    assert len(content_script["js"]) == len(set(content_script["js"]))

    script_order = {name: index for index, name in enumerate(content_script["js"])}
    for dependency in ("extension-context.js", "model.js", "query.js"):
        assert script_order[dependency] < script_order["content.js"]
    assert script_order["panel-layout.js"] < script_order["content.js"]
    for consumer in (
        "workspace-select.js",
        "workspace-action-names.js",
        "workspace-edit.js",
        "workspace-validate.js",
        "advanced.js",
        "walk-ui.js",
    ):
        assert script_order["content.js"] < script_order[consumer]

    web_resources = [
        resource
        for group in manifest["web_accessible_resources"]
        for resource in group["resources"]
    ]
    assert len(web_resources) == len(set(web_resources))
    assert set(web_resources) == {"page-bridge.js"}
    assert set(content_script["js"]) | set(web_resources) == {
        path.name for path in EXTENSION.glob("*.js")
    }


def test_workspace_templates_own_complete_non_overlapping_selectors() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for JavaScript workspace tests")
    script = textwrap.dedent(
        """
        require("./extension/orbit-site-map-editor/workspace-select.js");
        require("./extension/orbit-site-map-editor/workspace-action-names.js");
        require("./extension/orbit-site-map-editor/workspace-edit.js");
        require("./extension/orbit-site-map-editor/workspace-validate.js");
        const panes = [
          OrbitSiteMapEditorSelectWorkspace,
          OrbitSiteMapEditorActionNamesWorkspace,
          OrbitSiteMapEditorEditWorkspace,
          OrbitSiteMapEditorValidateWorkspace,
        ];
        const selectors = panes.flatMap((pane) => pane.selectors);
        process.stdout.write(JSON.stringify({
          complete: panes.every((pane) => {
            const markup = pane.render();
            return pane.selectors.every((selector) =>
              markup.includes(`osme-${selector}`)
            );
          }),
          selectorCount: selectors.length,
          uniqueSelectorCount: new Set(selectors).size,
        }));
        """
    )

    completed = subprocess.run(
        [node, "-e", script],
        cwd=Path.cwd(),
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert result["complete"] is True
    assert result["selectorCount"] == result["uniqueSelectorCount"]

    action_markup = subprocess.run(
        [
            node,
            "-e",
            "require('./extension/orbit-site-map-editor/workspace-action-names.js');"
            "process.stdout.write(OrbitSiteMapEditorActionNamesWorkspace.render());",
        ],
        cwd=Path.cwd(),
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    edit_markup = subprocess.run(
        [
            node,
            "-e",
            "require('./extension/orbit-site-map-editor/workspace-edit.js');"
            "process.stdout.write(OrbitSiteMapEditorEditWorkspace.render());",
        ],
        cwd=Path.cwd(),
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert 'data-workspace-tab="action-names"' in action_markup
    assert 'class="osme-section osme-advanced-pane"' in action_markup
    assert "osme-action-name-map-selection-status" in action_markup
    assert "osme-action-name-mode" in action_markup
    assert "osme-action-name-shortcut" in action_markup
    assert "osme-action-name-label-toggle" in action_markup
    assert "Show Action names on map" in action_markup
    assert 'data-action-name-add-mode="false"' in action_markup
    assert 'data-action-name-add-mode="true"' in action_markup
    assert "osme-action-name-clear-selection" in action_markup
    assert "osme-action-name-action-list" in action_markup
    assert "osme-action-name-enterprise" in action_markup
    assert "osme-action-name-site" in action_markup
    assert "osme-action-name-area" in action_markup
    assert "osme-action-name-first-number" in action_markup
    for placeholder in (
        "ENTERPRISE_CODE",
        "SITE_CODE",
        "AREA_CODE",
        "WORK_CENTER_CODE",
        "EQUIPMENT_CODE",
    ):
        assert f'placeholder="{placeholder}"' in action_markup
    assert "osme-action-name-preview" in action_markup
    assert "osme-review-action-names" in action_markup
    assert "osme-confirm-action-name-mutation" in action_markup
    assert "osme-action-name-template" not in action_markup
    assert "osme-action-name-template" not in edit_markup
    advanced = (EXTENSION / "advanced.js").read_text(encoding="utf-8")
    assert 'action_name_builder.addEventListener("input"' in advanced
    assert "instanceEvents.actionSelection" in advanced
    assert "stored.actionNameSelections" not in advanced
    assert "captureCurrentActionOnNextSnapshot" not in advanced
    assert "actionNameRowsById" in advanced
    assert "action_name_action_list.replaceChildren" not in advanced
    assert "document.activeElement !== entry.type" in advanced
    assert "state.actionNameLabelsVisible = stored.actionNameLabelsVisible !== false" in advanced
    assert 'if (!state.actionNameAddMode || state.tab !== "action-names") return false;' in advanced
    assert 'event.code === "KeyA"' in advanced
    assert "!event.ctrlKey" in advanced
    assert "!event.altKey" in advanced
    assert "!event.shiftKey" in advanced
    assert "!event.metaKey" in advanced
    assert "isTextEntryTarget(event.target)" in advanced
    assert 'window.addEventListener("keydown"' in advanced
    content = (EXTENSION / "content.js").read_text(encoding="utf-8")
    assert "actionNameLabelsVisible" in content
    assert 'visibility: state.overlay.detailed ? "visible" : "hidden"' in content
    assert "ACTION_NAME_LABEL_DENSITY_STEPS" in content
    assert "maxZoom: 1.2, cellWidth: 72, cellHeight: 22" in content
    assert "maxZoom: Infinity, cellWidth: 0, cellHeight: 0" in content
    assert "actionNameLabelDensity(zoom)" in content
    assert "actionLabelCandidatesByCell" in content
    assert "const actionNameLabels = actionNameLabelsVisible" in content


def test_page_bridge_publishes_action_route_changes_and_restores_history() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for JavaScript bridge tests")
    script = textwrap.dedent(
        """
        const listeners = new Map();
        const posts = [];
        global.window = global;
        global.location = {
          origin: "https://orbit.example",
          pathname: "/control_room/maps/map/edit",
          search: "",
        };
        function updateLocation(url) {
          const next = new URL(url, `${location.origin}${location.pathname}${location.search}`);
          location.pathname = next.pathname;
          location.search = next.search;
        }
        const originalPushState = function(_state, _unused, url) {
          updateLocation(url);
        };
        global.history = {
          pushState: originalPushState,
          replaceState(_state, _unused, url) { updateLocation(url); },
        };
        global.document = {
          currentScript: {dataset: {osmeSession: "session-1"}},
          getElementById() { return null; },
        };
        window.addEventListener = (type, listener) => {
          const bucket = listeners.get(type) || [];
          bucket.push(listener);
          listeners.set(type, bucket);
        };
        window.removeEventListener = (type, listener) => {
          listeners.set(type, (listeners.get(type) || []).filter((item) => item !== listener));
        };
        window.postMessage = (payload) => posts.push(payload);
        require("./extension/orbit-site-map-editor/page-bridge.js");
        history.pushState({}, "", "?action=action-a");
        history.replaceState({}, "", "?action=action-b");
        setImmediate(() => {
          const actionPosts = posts.filter(
            (item) => item.type === "orbit-site-map-editor-action-selection"
          );
          global.__orbitSiteMapEditorBridgeV2.dispose();
          const restored = history.pushState === originalPushState;
          history.pushState({}, "", "?action=action-c");
          setImmediate(() => process.stdout.write(JSON.stringify({actionPosts, restored})));
        });
        """
    )
    completed = subprocess.run(
        [node, "--unhandled-rejections=strict", "-e", script],
        cwd=Path.cwd(),
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert result["restored"] is True
    assert [item["actionId"] for item in result["actionPosts"]] == [
        "action-a",
        "action-b",
    ]
    assert result["actionPosts"][0]["sessionId"] == "session-1"


def test_extension_context_fails_closed_after_unpacked_extension_reload() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for JavaScript extension tests")
    source = (EXTENSION / "extension-context.js").read_text(encoding="utf-8")

    def run_case(case: str) -> dict:
        completed = subprocess.run(
            [node, "--unhandled-rejections=strict", "-e", f"{source}\n{case}"],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    active = run_case(
        textwrap.dedent(
            """
            (async () => {
              let saved = null;
              globalThis.chrome = {
                runtime: {
                  id: "extension-id",
                  getManifest: () => ({
                    manifest_version: 3,
                    version: "0.5.0",
                    version_name: "0.5.0 dev test",
                  }),
                  getURL: (path) => `chrome-extension://extension-id/${path}`,
                  lastError: undefined,
                },
                storage: {local: {
                  get: (_keys, callback) => callback({saved: true}),
                  set: (value, callback) => {saved = value; callback();},
                }},
              };
              const api = OrbitSiteMapEditorExtensionContext;
              process.stdout.write(JSON.stringify({
                read: await api.storageGet(["saved"]),
                write: api.storageSet({value: 1}),
                url: api.getUrl("page-bridge.js"),
                version: api.getVersionLabel(),
                saved,
                invalidated: api.isInvalidated(),
              }));
            })();
            """
        )
    )
    runtime_invalid = run_case(
        textwrap.dedent(
            """
            (async () => {
              let storageCalled = false;
              globalThis.chrome = {
                runtime: {
                  get id() {throw new Error("Extension context invalidated.");},
                },
                storage: {local: {
                  get: () => {storageCalled = true;},
                  set: () => {storageCalled = true;},
                }},
              };
              const api = OrbitSiteMapEditorExtensionContext;
              let invalidations = 0;
              api.onInvalidated(() => {invalidations += 1;});
              process.stdout.write(JSON.stringify({
                read: await api.storageGet(["saved"]),
                write: api.storageSet({value: 2}),
                storageCalled,
                invalidations,
                invalidated: api.isInvalidated(),
              }));
            })();
            """
        )
    )
    storage_getter_invalid = run_case(
        textwrap.dedent(
            """
            (async () => {
              globalThis.chrome = {
                runtime: {
                  id: "stale-extension-id",
                  getManifest: () => ({manifest_version: 3}),
                },
                get storage() {throw new Error("Extension context invalidated.");},
              };
              const api = OrbitSiteMapEditorExtensionContext;
              process.stdout.write(JSON.stringify({
                read: await api.storageGet(["saved"]),
                write: api.storageSet({value: 3}),
                invalidated: api.isInvalidated(),
              }));
            })();
            """
        )
    )
    rejected_get = run_case(
        textwrap.dedent(
            """
            (async () => {
              globalThis.chrome = {
                runtime: {
                  id: "extension-id",
                  getManifest: () => ({manifest_version: 3}),
                  lastError: undefined,
                },
                storage: {local: {
                  get: () => Promise.reject(new Error("Extension context invalidated.")),
                }},
              };
              const api = OrbitSiteMapEditorExtensionContext;
              const read = await api.storageGet(["saved"]);
              await new Promise((resolve) => setImmediate(resolve));
              process.stdout.write(JSON.stringify({
                read,
                invalidated: api.isInvalidated(),
              }));
            })();
            """
        )
    )
    rejected_set = run_case(
        textwrap.dedent(
            """
            (async () => {
              globalThis.chrome = {
                runtime: {
                  id: "extension-id",
                  getManifest: () => ({manifest_version: 3}),
                  lastError: undefined,
                },
                storage: {local: {
                  set: () => Promise.reject(new Error("Extension context invalidated.")),
                }},
              };
              const api = OrbitSiteMapEditorExtensionContext;
              const writeStarted = api.storageSet({value: 4});
              await new Promise((resolve) => setImmediate(resolve));
              process.stdout.write(JSON.stringify({
                writeStarted,
                invalidated: api.isInvalidated(),
              }));
            })();
            """
        )
    )
    callback_error = run_case(
        textwrap.dedent(
            """
            (() => {
              globalThis.chrome = {
                runtime: {
                  id: "extension-id",
                  getManifest: () => ({manifest_version: 3}),
                  lastError: {message: "Extension context invalidated."},
                },
                storage: {local: {
                  set: (_value, callback) => callback(),
                }},
              };
              const api = OrbitSiteMapEditorExtensionContext;
              const writeStarted = api.storageSet({value: 5});
              process.stdout.write(JSON.stringify({
                writeStarted,
                invalidated: api.isInvalidated(),
              }));
            })();
            """
        )
    )

    assert active == {
        "read": {"saved": True},
        "write": True,
        "url": "chrome-extension://extension-id/page-bridge.js",
        "version": "0.5.0 dev test",
        "saved": {"value": 1},
        "invalidated": False,
    }
    assert runtime_invalid == {
        "read": {},
        "write": False,
        "storageCalled": False,
        "invalidations": 1,
        "invalidated": True,
    }
    assert storage_getter_invalid == {
        "read": {},
        "write": False,
        "invalidated": True,
    }
    assert rejected_get == {"read": {}, "invalidated": True}
    assert rejected_set == {"writeStarted": True, "invalidated": True}
    assert callback_error == {"writeStarted": True, "invalidated": True}


def run_model(script: str) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for JavaScript model tests")
    source = (EXTENSION / "model.js").read_text(encoding="utf-8")
    completed = subprocess.run(
        [node, "-e", f"{source}\n{script}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_panel_layout_reserves_and_releases_a_separate_orbit_rail() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for JavaScript panel-layout tests")
    script = textwrap.dedent(
        """
        require("./extension/orbit-site-map-editor/panel-layout.js");
        const layout = OrbitSiteMapEditorPanelLayout;
        const attributes = new Map();
        const host = {
          setAttribute(name, value) {attributes.set(name, value);},
          removeAttribute(name) {attributes.delete(name);},
        };
        const results = [];
        results.push(layout.apply(host, "rail-left", true));
        results.push(attributes.get(layout.HOST_ATTRIBUTE));
        results.push(layout.apply(host, "rail-right", true));
        results.push(attributes.get(layout.HOST_ATTRIBUTE));
        results.push(layout.apply(host, "float", true));
        results.push(attributes.has(layout.HOST_ATTRIBUTE));
        results.push(layout.apply(host, "rail-left", false));
        results.push(attributes.has(layout.HOST_ATTRIBUTE));
        results.push(layout.normalize("unknown"));
        process.stdout.write(JSON.stringify(results));
        """
    )
    completed = subprocess.run(
        [node, "-e", script],
        cwd=Path.cwd(),
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == [
        "left",
        "left",
        "right",
        "right",
        "",
        False,
        "",
        False,
        "rail-right",
    ]
    content = (EXTENSION / "content.js").read_text(encoding="utf-8")
    css = (EXTENSION / "panel.css").read_text(encoding="utf-8")
    assert 'data-panel-layout="rail-left"' in content
    assert 'data-panel-layout="float"' in content
    assert 'data-panel-layout="rail-right"' in content
    assert "panelLayout: state.panelLayout" in content
    assert "state.panelLayout = panelLayout.normalize(stored.panelLayout)" in content
    assert 'html[data-osme-editor-rail="left"] body #root' in css
    assert 'html[data-osme-editor-rail="right"] body #root' in css


def run_editor_modules(script: str) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for JavaScript model tests")
    sources = "\n".join(
        (EXTENSION / name).read_text(encoding="utf-8")
        for name in (
            "model.js",
            "query.js",
            "selection.js",
            "validation.js",
            "workflow.js",
            "walk-planner.js",
        )
    )
    completed = subprocess.run(
        [node, "-e", f"{sources}\n{script}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_universal_query_supports_predicates_and_all_catalog_kinds() -> None:
    result = run_editor_modules(
        textwrap.dedent(
            """
            const snapshot = {
              waypoints: [
                {id: "w1", name: "Start", recordingId: "r1", recordingName: "Run A"},
                {id: "w2", name: "End", recordingId: "r2", recordingName: "Run B"},
              ],
              edges: [{
                id: "e1", from: "w1", to: "w2", source: "manual",
                manual: true, crossRecording: true, settings: {stairs: true}
              }],
              areas: [{id: "area-1", name: "Crosswalk", waypointIds: ["w1"]}],
              docks: [{id: "dock-1", name: "Charger", waypointId: "w1"}],
              fiducials: [{id: "fid-1", name: "AprilTag 7"}],
              actions: [{id: "action-1", name: "Inspect", waypointId: "w2"}],
            };
            const query = OrbitSiteMapEditorQuery;
            process.stdout.write(JSON.stringify({
              edge: query.querySnapshot(
                snapshot, "type:edge source:manual cross-recording=true setting:stairs"
              ),
              sorted: query.querySnapshot(
                snapshot, "", {kind: "waypoint", sortBy: "name", descending: true}
              ).map((row) => row.id),
              kinds: [...new Set(query.universalRecords(snapshot).map((row) => row.kind))].sort(),
              parsed: query.parseQuery('type:waypoint degree>=0 "Run A"')
            }));
            """
        )
    )

    assert [row["id"] for row in result["edge"]] == ["e1"]
    assert result["sorted"] == ["w1", "w2"]
    assert result["kinds"] == [
        "action",
        "area",
        "dock",
        "edge",
        "fiducial",
        "recording",
        "waypoint",
    ]
    assert result["parsed"]["predicates"][1] == {
        "field": "degree",
        "operator": ">=",
        "value": "0",
    }
    assert result["parsed"]["freeText"] == ["Run A"]


def test_selection_algebra_graph_recording_path_and_spatial_queries() -> None:
    result = run_editor_modules(
        textwrap.dedent(
            """
            const snapshot = {
              waypoints: [
                {id: "a", recordingId: "r1", position: {x: 0, y: 0}},
                {id: "b", recordingId: "r1", position: {x: 1, y: 0}},
                {id: "c", recordingId: "r2", position: {x: 2, y: 0}},
                {id: "d", recordingId: "r2", position: {x: 20, y: 20}},
              ],
              edges: [
                {id: "ab", from: "a", to: "b"},
                {id: "bc", from: "b", to: "c"},
              ]
            };
            const select = OrbitSiteMapEditorSelection;
            process.stdout.write(JSON.stringify({
              add: select.combine(
                {waypointIds: ["a"], edgeIds: []},
                {waypointIds: ["b"], edgeIds: ["ab"]},
                "add"
              ),
              subtract: select.combine(
                {waypointIds: ["a", "b"], edgeIds: ["ab"]},
                {waypointIds: ["a"], edgeIds: []},
                "subtract"
              ),
              hops: select.nHop(snapshot, ["a"], 1),
              twoHops: select.nHop(snapshot, ["a"], 2),
              recording: select.recording(snapshot, "r2"),
              path: select.shortestPath(snapshot, "a", "c"),
              rectangle: select.rectangle(snapshot, {x1: -1, y1: -1, x2: 1.1, y2: 1}),
              component: select.component(snapshot, "a"),
              largeComponent: (() => {
                const large = {
                  waypoints: Array.from({length: 1505}, (_, index) => ({id: `w${index}`})),
                  edges: Array.from({length: 1504}, (_, index) => ({
                    id: `e${index}`, from: `w${index}`, to: `w${index + 1}`
                  }))
                };
                return select.component(large, "w0").waypointIds.length;
              })(),
            }));
            """
        )
    )

    assert result["add"] == {"waypointIds": ["a", "b"], "edgeIds": ["ab"]}
    assert result["subtract"] == {"waypointIds": ["b"], "edgeIds": ["ab"]}
    assert result["hops"] == {"waypointIds": ["a", "b"], "edgeIds": ["ab"]}
    assert result["twoHops"] == {
        "waypointIds": ["a", "b", "c"],
        "edgeIds": ["ab", "bc"],
    }
    assert result["recording"]["waypointIds"] == ["c", "d"]
    assert result["path"] == {
        "waypointIds": ["a", "b", "c"],
        "edgeIds": ["ab", "bc"],
    }
    assert result["rectangle"]["waypointIds"] == ["a", "b"]
    assert result["component"]["waypointIds"] == ["a", "b", "c"]
    assert result["largeComponent"] == 1505


def test_graph_validation_path_settings_crosswalk_reachability_and_preview() -> None:
    result = run_editor_modules(
        textwrap.dedent(
            """
            const snapshot = {
              waypoints: [
                {id: "a", name: "Same", recordingId: "r1"},
                {id: "b", name: "Same", recordingId: "r1"},
                {id: "c", name: "Leaf", recordingId: "r2"},
                {id: "isolated", name: "Alone", recordingId: "r3"},
              ],
              edges: [
                {
                  id: "ab", from: "a", to: "b", source: "odometry", length: 2,
                  settings: {
                    stairs: true,
                    areaCallbacks: {
                      "area-1": {serviceName: "spot-crosswalk", description: "south"}
                    }
                  }
                },
                {
                  id: "bc", from: "b", to: "c", source: "manual", manual: true,
                  crossRecording: true, length: 3,
                  settings: {areaCallbacks: {
                    "area-1": {serviceName: "spot-crosswalk", description: "north"}
                  }}
                }
              ],
              areas: [{id: "area-1", name: "Crosswalk", catalogPresent: true}],
              capabilities: {areas: "siteAreas"},
              docks: [{id: "dock", waypointId: "a"}],
              actions: [
                {id: "action", waypointId: "c"},
                {id: "action-isolated", waypointId: "isolated"}
              ],
              edgeStates: [{
                key: "c|isolated", from: "c", to: "isolated",
                ids: ["archived-c-isolated"], activeCount: 0, tombstoneCount: 1
              }],
              load: {expectedWaypointCount: 4}
            };
            const validation = OrbitSiteMapEditorValidation;
            const findings = validation.validateGraph(snapshot);
            process.stdout.write(JSON.stringify({
              findingTypes: [...new Set(findings.map((item) => item.type))].sort(),
              topology: validation.graphSummary(snapshot),
              path: validation.pathInspector(snapshot, "a", "c"),
              reachability: validation.reachability(
                snapshot, ["a"], [{kind: "action", id: "action", waypointId: "c"}]
              ),
              crosswalks: validation.crosswalkAudit(snapshot),
              staleArea: validation.validateGraph({
                ...snapshot,
                edges: [{
                  id: "missing-area-edge", from: "a", to: "b",
                  settings: {areaCallbacks: {
                    "missing-area": {serviceName: "spot-crosswalk"}
                  }}
                }],
                areas: [{
                  id: "missing-area", catalogPresent: false, inferredFromEdge: true
                }],
              }).filter((item) => item.type === "stale_area_callback"),
              unavailableAreaCatalog: validation.validateGraph({
                ...snapshot,
                edges: [{
                  id: "callback-only-edge", from: "a", to: "b",
                  settings: {areaCallbacks: {
                    "callback-only": {serviceName: "spot-crosswalk"}
                  }}
                }],
                areas: [{
                  id: "callback-only", catalogPresent: false, inferredFromEdge: true
                }],
                capabilities: {areas: "siteEdges.areaCallbacks"}
              }).filter((item) => item.type === "stale_area_callback")
            }));
            """
        )
    )

    assert {
        "articulation_waypoint",
        "bridge_edge",
        "cross_recording_manual",
        "archived_critical_connection",
        "dock_unreachable_action",
        "disconnected_component",
        "duplicate_waypoint_name",
        "isolated_waypoint",
        "leaf_waypoint",
    }.issubset(result["findingTypes"])
    assert result["topology"]["components"] == 2
    assert result["path"]["reachable"] is True
    assert result["path"]["totalLength"] == 5
    assert result["path"]["settings"][0]["mixed"] is True
    assert result["reachability"][0]["reachable"] is True
    assert len(result["crosswalks"]) == 2
    assert all(item["areaPresent"] for item in result["crosswalks"])
    assert all(item["inconsistentProfile"] for item in result["crosswalks"])
    assert len(result["staleArea"]) == 1
    assert result["staleArea"][0]["details"]["callbackIds"] == ["missing-area"]
    assert result["unavailableAreaCatalog"] == []


def test_connect_queue_presets_and_setting_guards() -> None:
    result = run_editor_modules(
        textwrap.dedent(
            """
            const workflow = OrbitSiteMapEditorWorkflow;
            let unsupported = "";
            try { workflow.sanitizeSettings({notASetting: true}); }
            catch (error) { unsupported = error.message; }
            process.stdout.write(JSON.stringify({
              queue: workflow.parseConnectQueue("a,b\\na b\\n# comment\\nb|c"),
              preset: workflow.makePreset({
                id: "safe", name: "Safe", settings: {cost: 5}
              }),
              library: workflow.parsePresetLibrary(JSON.stringify(
                workflow.presetLibrary([{id: "shared", name: "Shared", settings: {stairs: true}}])
              )),
              unsupported,
              builtins: workflow.BUILTIN_PRESETS.map((item) => item.id)
            }));
            """
        )
    )

    assert len(result["queue"]) == 2
    assert result["preset"]["settings"] == {"cost": 5}
    assert result["library"]["presets"][0]["id"] == "shared"
    assert result["unsupported"] == "unsupported_edge_setting"
    assert {"stairs", "avoid-alternate", "high-cost", "flat-ground"}.issubset(result["builtins"])


def test_action_name_plan_suggests_types_and_uses_optional_segments() -> None:
    result = run_editor_modules(
        textwrap.dedent(
            """
            const workflow = OrbitSiteMapEditorWorkflow;
            const snapshot = {
              waypoints: [{id: "w1"}, {id: "w2"}, {id: "w3"}],
              actions: [
                {id: "thermal", name: "Existing-0007-THRM", waypointIds: ["w2"]},
                {id: "leak", name: "Acoustic Leak Inspection - 8", waypointIds: ["w2"]},
                {id: "visual", name: "Spot Cam - PTZ - 9", waypointIds: ["w1"]},
              ],
            };
            const options = {
              enterprise: "3916",
              site: "site1",
              area: "area1",
              workCenter: "wc02",
              equipment: "eq134",
              startSequence: 42,
              sequenceWidth: 4,
            };
            const selections = [
              {id: "leak", type: "LEAK"},
              {id: "visual", type: "AIVI"},
              {id: "thermal", type: "THRM"},
            ];
            const mapSelections = [
              workflow.appendMapSelectedAction([], "leak", snapshot.actions),
              workflow.appendMapSelectedAction(
                [{id: "leak", type: "LEAK"}], "thermal", snapshot.actions
              ),
              workflow.appendMapSelectedAction(
                [{id: "leak", type: "LEAK"}], "leak", snapshot.actions
              ),
              workflow.appendMapSelectedAction(
                [{id: "leak", type: "LEAK"}], "missing", snapshot.actions
              ),
            ];
            const plan = workflow.planSelectedActionNames(
              snapshot, selections, options
            );
            const seed = workflow.parseActionSequence("0042");
            const optionalPlan = workflow.planSelectedActionNames(
              snapshot,
              [{id: "leak", type: "MECQ"}],
              {
                enterprise: "3916",
                site: "BGN1",
                area: "ADBM",
                workCenter: "",
                equipment: "",
                startSequence: 1,
                sequenceWidth: 4,
              },
            );
            const blockedSnapshot = {
              ...snapshot,
              actions: [
                ...snapshot.actions,
                {id: "unknown", name: "Operator note", waypointIds: ["w3"]},
              ],
            };
            const blocked = workflow.planSelectedActionNames(
              blockedSnapshot, [{id: "unknown", type: ""}], options
            );
            let missingRequired = "";
            try {
              workflow.planSelectedActionNames(snapshot, selections, {
                ...options, enterprise: "",
              });
            } catch (error) { missingRequired = error.message; }
            let overflow = "";
            try {
              workflow.planSelectedActionNames(snapshot, selections, {
                ...options,
                startSequence: 99,
                sequenceWidth: 2,
              });
            } catch (error) { overflow = error.message; }
            process.stdout.write(JSON.stringify({
              plan,
              seed,
              optionalPlan,
              mapSelections,
              blocked,
              missingRequired,
              overflow,
              explicitTypes: [
                workflow.explicitInspectionType("Existing-0007-THRM"),
                workflow.explicitInspectionType("Thermal Inspection"),
                workflow.explicitInspectionType("Existing-0008-AIVI (AI)"),
              ],
              suggestedTypes: [
                workflow.suggestInspectionType("Thermal Inspection - 1"),
                workflow.suggestInspectionType("Acoustic Mechanical Inspection - 2"),
                workflow.suggestInspectionType("Acoustic Leak Inspection - 3"),
                workflow.suggestInspectionType("Spot Cam - PTZ - 4"),
                workflow.suggestInspectionType({name: "Inspection", type: "infrared"}),
                workflow.suggestInspectionType("Operator note"),
              ],
              overlayLabels: workflow.actionNameOverlayLabels([
                  {
                    id: "leak", name: "Acoustic Leak Inspection - 8",
                    waypointIds: ["w2"], position: {x: 12, y: 4},
                  },
                  {
                    id: "thermal", name: "Existing-0007-THRM",
                    waypointIds: ["w2"], position: {x: 12, y: 7},
                  },
                  {
                    id: "waypoint-only", name: "No Action position",
                    waypointIds: ["w2"],
                  },
                ],
              ),
            }));
            """
        )
    )

    assert result["plan"]["canApply"] is True
    assert result["seed"] == {
        "formatted": "0042",
        "startSequence": 42,
        "sequenceWidth": 4,
    }
    assert result["plan"]["selectedActionIds"] == ["leak", "visual", "thermal"]
    assert result["optionalPlan"]["updates"][0]["desiredName"] == ("3916-BGN1-ADBM-0001-MECQ")
    assert result["mapSelections"] == [
        [{"id": "leak", "type": "LEAK"}],
        [{"id": "leak", "type": "LEAK"}, {"id": "thermal", "type": "THRM"}],
        [{"id": "leak", "type": "LEAK"}],
        [{"id": "leak", "type": "LEAK"}],
    ]
    assert [item["sequence"] for item in result["plan"]["updates"]] == [
        "0042",
        "0043",
        "0044",
    ]
    assert [item["desiredName"] for item in result["plan"]["updates"]] == [
        "3916-SITE1-AREA1-WC02-EQ134-0042-LEAK",
        "3916-SITE1-AREA1-WC02-EQ134-0043-AIVI",
        "3916-SITE1-AREA1-WC02-EQ134-0044-THRM",
    ]
    assert result["blocked"]["canApply"] is False
    assert result["blocked"]["unsupported"][0]["observedName"] == "Operator note"
    assert result["missingRequired"] == "missing_required_name_segment"
    assert result["overflow"] == "action_sequence_range_overflow"
    assert result["explicitTypes"] == ["THRM", "", "AIVI"]
    assert result["suggestedTypes"] == [
        "THRM",
        "MECQ",
        "LEAK",
        "AIVI",
        "THRM",
        "",
    ]
    assert result["overlayLabels"] == [
        {
            "id": "leak",
            "name": "Acoustic Leak Inspection - 8",
            "position": {"x": 12, "y": 4, "z": 0},
        },
        {
            "id": "thermal",
            "name": "Existing-0007-THRM",
            "position": {"x": 12, "y": 7, "z": 0},
        },
    ]


def test_connect_candidates_exclude_existing_and_rank_bounded_candidates() -> None:
    result = run_model(
        textwrap.dedent(
            """
            const snapshot = {
              waypoints: [
                {id: "base", name: "Base", recordingId: "r1", position: {x: 0, y: 0, z: 0}},
                {id: "neighbor", recordingId: "r1", position: {x: 1, y: 0, z: 0}},
                {id: "same", recordingId: "r1", position: {x: 2, y: 0, z: 0}},
                {id: "cross", recordingId: "r2", position: {x: 1.5, y: 0, z: 0}},
                {id: "far", recordingId: "r1", position: {x: 20, y: 0, z: 0}},
                {id: "no-anchor", recordingId: "r1", position: null}
              ],
              edges: [{from: "base", to: "neighbor"}]
            };
            const candidates = OrbitSiteMapEditorModel.connectionCandidates(
              snapshot, "base", {radiusMeters: 5, limit: 2}
            );
            process.stdout.write(JSON.stringify(candidates));
            """
        )
    )

    assert [item["id"] for item in result] == ["same", "cross"]
    assert result[0]["sameRecording"] is True
    assert result[1]["sameRecording"] is False
    assert all(item["id"] not in {"base", "neighbor", "far", "no-anchor"} for item in result)


def test_search_finds_exact_ids_names_recordings_and_edges() -> None:
    result = run_model(
        textwrap.dedent(
            """
            const snapshot = {
              waypoints: [
                {
                  id: "waypoint-alpha", name: "Loading Dock",
                  recordingId: "recording-17", recordingName: "North run",
                  robotNickname: "spot-a", position: {x: 0, y: 0}
                },
                {
                  id: "waypoint-beta", name: "Hallway",
                  recordingId: "recording-17", recordingName: "North run",
                  robotNickname: "spot-a", position: {x: 1, y: 0}
                }
              ],
              edges: [{
                id: "edge-alpha-beta", from: "waypoint-alpha", to: "waypoint-beta",
                source: "manual", length: 1
              }]
            };
            const model = OrbitSiteMapEditorModel;
            process.stdout.write(JSON.stringify({
              waypoint: model.searchSnapshot(snapshot, "waypoint-alpha", "all"),
              recording: model.searchSnapshot(snapshot, "North run", "recording"),
              edge: model.searchSnapshot(snapshot, "edge-alpha-beta", "edge")
            }));
            """
        )
    )

    assert result["waypoint"][0]["kind"] == "waypoint"
    assert result["waypoint"][0]["id"] == "waypoint-alpha"
    assert result["recording"][0]["kind"] == "recording"
    assert result["recording"][0]["id"] == "recording-17"
    assert result["edge"][0]["kind"] == "edge"
    assert result["edge"][0]["waypointIds"] == ["waypoint-alpha", "waypoint-beta"]


def test_editor_extension_has_no_direct_write_or_network_sink() -> None:
    combined = ""
    for path in sorted(EXTENSION.glob("*.js")):
        source = path.read_text(encoding="utf-8")
        combined += source
        for forbidden in (
            "fetch(",
            "XMLHttpRequest",
            "WebSocket",
            "/api/",
            "saveMapEdit",
            "saveMapEditComplete",
        ):
            assert forbidden not in source
    for removed_workflow in (
        'data-workspace-tab="history"',
        "workflow.parsePlan",
        "workflow.serializePlan",
        "state.journal",
        "state.planActions",
    ):
        assert removed_workflow not in combined


def test_editor_bridge_restores_validation_selection_and_adds_one_draft_step() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for JavaScript bridge tests")
    script = textwrap.dedent(
        """
        const mapId = "map-1";
        const key = (a, b) => a < b ? `${a}|${b}` : `${b}|${a}`;
        const waypoint = (id, name) => ({
          waypoint: {
            id, snapshotId: `snapshot-${id}`,
            annotations: {name, creationTime: "2026-01-01T00:00:00Z"},
            waypointTformKo: {position: {x: 0, y: 0, z: 0}},
          },
        });
        const state = {
          mapDisplay: {
            siteMapId: mapId,
            anchoring: {anchors: ["a", "b", "c"].map((id, index) => ({
              id, seedTformWaypoint: {position: {x: index, y: 0, z: 0}},
            }))},
          },
          siteMaps: {entities: {[mapId]: {
            waypointIds: ["a", "b", "c"], recordingSessionIds: ["r1"],
            metadata: {displayName: "Test map"},
          }}},
          siteWaypoints: {
            entities: {
              a: waypoint("a", "Alpha"),
              b: waypoint("b", "Beta"),
              c: waypoint("c", "Gamma"),
            },
            ids: ["a", "b", "c"],
          },
          siteEdges: {entities: {}, ids: []},
          recordingSessions: {entities: {r1: {
            name: "Run 1", waypointIds: ["a", "b", "c"],
            robotNickname: "spot-test", robotSerial: "serial-test",
          }}},
            mapEditor: {
              info: {
                activeTool: "waypoint_selection",
                selectedWaypointIds: ["a"], selectedEdgeIds: [],
                pendingEdgeCreation: {errors: [], warnings: [], validating: false},
              },
              form: {
                present: {index: 3}, past: [], future: [],
                data: {edges: {entities: {}, nonEntities: {}, ids: []}},
              },
            },
        };
        const dispatched = [];
        const store = {
          getState: () => state,
          dispatch(action) {
            dispatched.push({type: action.type, payload: action.payload});
            if (action.type === "mapEditorInfoSlice/setSelectedWaypoints") {
              const selected = [...action.payload];
              state.mapEditor.info.selectedWaypointIds = selected;
              if (selected.length === 2) {
                state.mapEditor.info.pendingEdgeCreation = {
                  errors: [], warnings: [], validating: true,
                };
                setTimeout(() => {
                  const [fromWaypoint, toWaypoint] = [...selected].sort();
                  state.mapEditor.info.pendingEdgeCreation = {
                    errors: [],
                    warnings: selected.includes("c") ? [{warning: true}] : [],
                    validating: false,
                    showModal: false,
                    createdEdgeCandidate: {
                      siteMapId: mapId, archived: false, disabled: false,
                      edge: {
                        id: {fromWaypoint, toWaypoint},
                        annotations: {edgeSource: 5},
                        fromTformTo: {position: {x: 1, y: 0, z: 0}},
                      },
                    },
                  };
                }, 5);
              }
            }
            if (action.type === "mapEditorFormSlice/addSiteEdge") {
              const {fromWaypoint, toWaypoint} = action.payload.edge.id;
              const edgeId = key(fromWaypoint, toWaypoint);
              state.mapEditor.form.past.push({
                index: state.mapEditor.form.present.index,
              });
              state.mapEditor.form.data.edges.entities[edgeId] = action.payload;
              state.mapEditor.form.data.edges.ids.push(edgeId);
              // Orbit may advance its internal edit index by several values
              // while still creating exactly one user-visible Undo step.
              state.mapEditor.form.present.index += 3;
            }
            return action;
          },
        };
        const root = {__reactContainer$test: {memoizedProps: {store}}};
        const messages = [];
        let onMessage;
        global.location = {
          origin: "https://orbit.test",
          pathname: `/control_room/maps/${mapId}/edit`,
          search: "?action=action-2",
        };
        global.document = {getElementById: (id) => id === "root" ? root : null};
        global.window = {
          addEventListener: (type, listener) => {if (type === "message") onMessage = listener;},
          postMessage: (message) => messages.push(message),
          setTimeout,
        };
        require("./extension/orbit-site-map-editor/page-bridge.js");

        async function request(requestId, command, waypointIds) {
          await onMessage({
            source: window,
            origin: location.origin,
            data: {
              channel: "orbit-site-map-editor-v1",
              type: "orbit-site-map-editor-request",
              requestId, command, mapId, waypointIds,
            },
          });
          return messages.find((message) => message.requestId === requestId);
        }

        (async () => {
          const snapshot = await request("snapshot", "snapshot");
          if (
            !snapshot?.ok ||
            snapshot.snapshot.waypoints.length !== 3 ||
            snapshot.snapshot.selectedWaypointIds.join(",") !== "a" ||
            snapshot.snapshot.currentActionId !== "action-2" ||
            snapshot.snapshot.editIndex !== 3
          ) throw new Error(`bad snapshot: ${JSON.stringify(snapshot)}`);

          const validation = await request("validation", "validate_connect", ["a", "b"]);
          if (!validation?.ok || !validation.valid) {
            throw new Error(`validation failed: ${JSON.stringify(validation)}`);
          }
          if (
            state.mapEditor.info.selectedWaypointIds.join(",") !== "a" ||
            state.mapEditor.form.present.index !== 3
          ) throw new Error("validation did not restore state");

          const warned = await request("warned", "validate_connect", ["a", "c"]);
          if (
            !warned?.ok ||
            warned.valid ||
            warned.reason !== "edge_validation_warning" ||
            state.mapEditor.info.selectedWaypointIds.join(",") !== "a" ||
            state.mapEditor.form.present.index !== 3
          ) throw new Error(`warning did not fail closed: ${JSON.stringify(warned)}`);

          const [connected, concurrent] = await Promise.all([
            request("connect", "connect", ["b", "a"]),
            request("connect-race", "connect", ["a", "b"]),
          ]);
          if (
            !connected?.ok ||
            !connected.added ||
            connected.edgeKey !== "a|b" ||
            connected.editIndex !== 6 ||
            connected.undoDepth !== 1 ||
            connected.draftIndexDelta !== 3
          ) throw new Error(`connect failed: ${JSON.stringify(connected)}`);
          if (
            concurrent?.ok ||
            concurrent?.error !== "native_mutation_in_progress"
          ) throw new Error(
            `concurrent mutation was not blocked: ${JSON.stringify(concurrent)}`
          );
          if (
            state.mapEditor.form.present.index !== 6 ||
            state.mapEditor.form.past.length !== 1
          ) {
            throw new Error("connect did not create exactly one history step");
          }

          const duplicate = await request("duplicate", "connect", ["a", "b"]);
          if (duplicate?.ok || duplicate?.error !== "edge_already_exists") {
            throw new Error(`duplicate was not blocked: ${JSON.stringify(duplicate)}`);
          }
          if (
            state.mapEditor.form.present.index !== 6 ||
            state.mapEditor.form.past.length !== 1
          ) {
            throw new Error("duplicate changed history");
          }
        })().catch((error) => {
          console.error(error);
          process.exitCode = 1;
        });
        """
    )
    subprocess.run(
        [node, "-e", script],
        cwd=Path.cwd(),
        check=True,
        text=True,
    )


def test_editor_bridge_selects_and_creates_one_archive_or_settings_step() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for JavaScript bridge tests")
    script = textwrap.dedent(
        """
        const mapId = "map-1";
        const key = (a, b) => a < b ? `${a}|${b}` : `${b}|${a}`;
        const edge = (fromWaypoint, toWaypoint, settings = {}) => ({
          siteMapId: mapId, archived: false, disabled: false,
          edge: {
            id: {fromWaypoint, toWaypoint},
            annotations: {edgeSource: 5, ...settings},
            fromTformTo: {position: {x: 1, y: 0, z: 0}},
          },
        });
        const waypoint = (id) => ({waypoint: {
          id, annotations: {name: id}, waypointTformKo: {position: {x: 0, y: 0, z: 0}}
        }});
        const ab = edge("a", "b", {
          stairs: false,
          areaCallbacks: {
            "area-2": {serviceName: "spot-crosswalk", description: "South crossing"}
          }
        });
        const bc = edge("b", "c", {
          cost: 2,
          futureSafetyField: {preserve: true},
        });
        let recordUndo = true;
        const state = {
          mapDisplay: {
            siteMapId: mapId,
            anchoring: {anchors: ["a", "b", "c"].map((id, x) => ({
              id, seedTformWaypoint: {
                position: {x, y: 0, z: 0},
                rotation: id === "c"
                  ? {x: 0, y: 0, z: Math.SQRT1_2, w: Math.SQRT1_2}
                  : {x: 0, y: 0, z: 0, w: 1},
              }
            }))}
          },
          siteMaps: {entities: {[mapId]: {
            waypointIds: ["a", "b", "c"], recordingSessionIds: ["r1"],
            metadata: {displayName: "Test"}
          }}},
          siteWaypoints: {
            ids: ["a", "b", "c"],
            entities: {a: waypoint("a"), b: waypoint("b"), c: waypoint("c")}
          },
          siteEdges: {
            ids: ["stored-edge-ab", "b|c"],
            entities: {"stored-edge-ab": ab, "b|c": bc},
          },
          recordingSessions: {entities: {r1: {
            name: "Run", waypointIds: ["a", "b", "c"]
          }}},
          siteAreas: {ids: ["area-1"], entities: {
            "area-1": {id: "area-1", siteMapId: mapId, name: "Crosswalk", waypointIds: ["b"]}
          }},
          siteDocks: {ids: ["dock-1"], entities: {
            "dock-1": {
              id: "dock-1", siteMapId: mapId, dockId: 7, dockedWaypointId: "a"
            }
          }},
          siteFiducials: {ids: ["fid-1"], entities: {
            "fid-1": {id: "fid-1", siteMapId: mapId, name: "Tag"}
          }},
          siteActions: {ids: ["action-1"], entities: {
            "action-1": {
              id: "action-1", siteMapId: mapId, name: "Inspect", waypointId: "c",
              waypointTformBodyOffset: {position: {x: 1, y: 0, z: 0}},
            }
          }},
          mapEditor: {
            info: {
              activeTool: "waypoint_selection",
              selectedWaypointIds: [], selectedEdgeIds: [],
              pendingEdgeCreation: {}
            },
            form: {
              present: {index: 0}, past: [], future: [],
              data: {edges: {ids: [], entities: {}, nonEntities: {}}}
            }
          }
        };
        const store = {
          getState: () => state,
          dispatch(action) {
            if (action.type === "mapEditorInfoSlice/activateTool") {
              state.mapEditor.info.activeTool = action.payload;
            } else if (action.type === "mapEditorInfoSlice/setSelectedWaypoints") {
              state.mapEditor.info.selectedWaypointIds = [...action.payload];
            } else if (action.type === "mapEditorInfoSlice/setSelectedEdges") {
              state.mapEditor.info.selectedEdgeIds = [...action.payload];
            } else if (action.type === "mapDisplay/updateNeedsZoomToWaypoints") {
              state.lastFocusPayload = [...action.payload];
            } else if (action.type === "mapEditorFormSlice/archiveSiteEdges") {
              if (recordUndo) {
                state.mapEditor.form.past.push({
                  index: state.mapEditor.form.present.index,
                });
              }
              for (const item of action.payload) {
                const id = key(item.edge.id.fromWaypoint, item.edge.id.toWaypoint);
                state.mapEditor.form.data.edges.nonEntities[id] = {...item, archived: true};
              }
              state.mapEditor.form.present.index += 1;
            } else if (action.type === "mapEditorFormSlice/updateSiteEdges") {
              if (recordUndo) {
                state.mapEditor.form.past.push({
                  index: state.mapEditor.form.present.index,
                });
              }
              for (const item of action.payload.updatedEdges) {
                const id = key(item.edge.id.fromWaypoint, item.edge.id.toWaypoint);
                state.mapEditor.form.data.edges.entities[id] = item;
                if (!state.mapEditor.form.data.edges.ids.includes(id)) {
                  state.mapEditor.form.data.edges.ids.push(id);
                }
              }
              state.mapEditor.form.present.index += 2;
            }
            return action;
          }
        };
        const root = {__reactContainer$test: {memoizedProps: {store}}};
        const messages = [];
        let onMessage;
        global.location = {
          origin: "https://orbit.test",
          pathname: `/control_room/maps/${mapId}/edit`,
        };
        global.document = {getElementById: (id) => id === "root" ? root : null};
        global.window = {
          addEventListener: (type, listener) => {if (type === "message") onMessage = listener;},
          postMessage: (message) => messages.push(message),
          setTimeout,
        };
        require("./extension/orbit-site-map-editor/page-bridge.js");

        async function request(requestId, command, payload = {}) {
          await onMessage({
            source: window,
            origin: location.origin,
            data: {
              channel: "orbit-site-map-editor-v1",
              type: "orbit-site-map-editor-request",
              requestId, command, mapId, ...payload,
            },
          });
          return messages.find((message) => message.requestId === requestId);
        }

        (async () => {
          const snapshot = await request("snapshot", "snapshot");
          const area1 = snapshot.snapshot.areas.find((area) => area.id === "area-1");
          const area2 = snapshot.snapshot.areas.find((area) => area.id === "area-2");
          if (
            !snapshot.ok ||
            snapshot.snapshot.areas.length !== 2 ||
            area1?.catalogPresent !== true ||
            area2?.catalogPresent !== false ||
            snapshot.snapshot.capabilities.areas !== "siteAreas" ||
            snapshot.snapshot.docks.length !== 1 ||
            snapshot.snapshot.docks[0].waypointIds.join(",") !== "a" ||
            snapshot.snapshot.fiducials.length !== 1 ||
            snapshot.snapshot.actions.length !== 1 ||
            Math.abs(snapshot.snapshot.actions[0].position?.x - 2) > 1e-9 ||
            Math.abs(snapshot.snapshot.actions[0].position?.y - 1) > 1e-9 ||
            !snapshot.snapshot.load.complete
          ) throw new Error(`catalog snapshot failed: ${JSON.stringify(snapshot)}`);

          const selectedWaypoints = await request("select-waypoints", "select_entities", {
            waypointIds: ["a", "b"], edgeIds: [], focus: true
          });
          if (
            !selectedWaypoints.ok ||
            selectedWaypoints.waypointCount !== 2 ||
            selectedWaypoints.edgeCount !== 0 ||
            state.mapEditor.info.selectedWaypointIds.join(",") !== "a,b" ||
            state.mapEditor.info.selectedEdgeIds.length !== 0 ||
            state.mapEditor.form.present.index !== 0
          ) throw new Error(
            `waypoint selection failed: ${JSON.stringify(selectedWaypoints)}`
          );

          const selected = await request("select-edge", "select_entities", {
            waypointIds: [], edgeIds: ["stored-edge-ab"], focus: true
          });
          if (
            !selected.ok ||
            selected.waypointCount !== 0 ||
            selected.edgeCount !== 1 ||
            state.mapEditor.info.selectedWaypointIds.length !== 0 ||
            state.mapEditor.info.selectedEdgeIds.join(",") !== "a|b" ||
            state.lastFocusPayload.join(",") !== "a,b" ||
            state.mapEditor.form.present.index !== 0
          ) throw new Error(`selection failed: ${JSON.stringify(selected)}`);

          const beforeUnknownAlias = JSON.stringify({
            waypointIds: state.mapEditor.info.selectedWaypointIds,
            edgeIds: state.mapEditor.info.selectedEdgeIds,
            focus: state.lastFocusPayload,
            editIndex: state.mapEditor.form.present.index,
            undoDepth: state.mapEditor.form.past.length,
          });
          const unknownAlias = await request(
            "select-unknown-edge",
            "select_entities",
            {waypointIds: [], edgeIds: ["unmapped-edge-alias"], focus: true}
          );
          const afterUnknownAlias = JSON.stringify({
            waypointIds: state.mapEditor.info.selectedWaypointIds,
            edgeIds: state.mapEditor.info.selectedEdgeIds,
            focus: state.lastFocusPayload,
            editIndex: state.mapEditor.form.present.index,
            undoDepth: state.mapEditor.form.past.length,
          });
          if (
            unknownAlias?.ok ||
            unknownAlias?.error !== "edge_not_found" ||
            beforeUnknownAlias !== afterUnknownAlias
          ) throw new Error(
            `unknown alias changed state: ${JSON.stringify(unknownAlias)}`
          );

          const selectedAfterEdge = await request(
            "select-after-edge",
            "select_entities",
            {waypointIds: ["c"], edgeIds: [], focus: false}
          );
          if (
            !selectedAfterEdge.ok ||
            state.mapEditor.info.selectedWaypointIds.join(",") !== "c" ||
            state.mapEditor.info.selectedEdgeIds.length !== 0
          ) throw new Error(
            `waypoint-after-edge failed: ${JSON.stringify(selectedAfterEdge)}`
          );

          const archived = await request("archive", "archive_edges", {
            waypointPairs: [["a", "b"]]
          });
          if (
            !archived.ok ||
            archived.archivedCount !== 1 ||
            archived.editIndex !== 1 ||
            archived.undoDepth !== 1 ||
            archived.draftIndexDelta !== 1 ||
            !state.mapEditor.form.data.edges.nonEntities["a|b"].archived
          ) throw new Error(`archive failed: ${JSON.stringify(archived)}`);

          const updated = await request("settings", "update_edge_settings", {
            settingsUpdates: [{
              waypointIds: ["b", "c"], storedFrom: "b", storedTo: "c",
              observedSourceValue: 5, observedSettings: {cost: 2},
              desiredSettings: {cost: 9, stairs: true}
            }]
          });
          const edited = state.mapEditor.form.data.edges.entities["b|c"];
          if (
            !updated.ok ||
            updated.updatedCount !== 1 ||
            updated.editIndex !== 3 ||
            updated.undoDepth !== 2 ||
            updated.draftIndexDelta !== 2 ||
            edited.edge.annotations.cost !== 9 ||
            edited.edge.annotations.stairs !== true ||
            edited.edge.annotations.futureSafetyField?.preserve !== true
          ) throw new Error(`settings failed: ${JSON.stringify(updated)}`);

          recordUndo = false;
          const noUndo = await request("settings-no-undo", "update_edge_settings", {
            settingsUpdates: [{
              waypointIds: ["b", "c"], storedFrom: "b", storedTo: "c",
              observedSourceValue: 5,
              observedSettings: {cost: 9, stairs: true},
              desiredSettings: {cost: 10, stairs: true}
            }]
          });
          if (
            noUndo.ok ||
            noUndo.error !== "edge_settings_batch_not_created" ||
            noUndo.mutationMayExist !== true ||
            noUndo.beforeEditIndex !== 3 ||
            noUndo.afterEditIndex !== 5 ||
            noUndo.beforeUndoDepth !== 2 ||
            noUndo.afterUndoDepth !== 2 ||
            state.mapEditor.form.data.edges.entities["b|c"].edge.annotations.cost !== 10
          ) throw new Error(`missing Undo was accepted: ${JSON.stringify(noUndo)}`);

          delete state.mapEditor.form.past;
          const noTelemetry = await request(
            "settings-no-telemetry",
            "update_edge_settings",
            {
              settingsUpdates: [{
                waypointIds: ["b", "c"], storedFrom: "b", storedTo: "c",
                observedSourceValue: 5,
                observedSettings: {cost: 10, stairs: true},
                desiredSettings: {cost: 11, stairs: true}
              }]
            }
          );
          if (
            noTelemetry.ok ||
            noTelemetry.error !== "edge_settings_batch_not_created" ||
            noTelemetry.mutationMayExist !== true ||
            noTelemetry.beforeEditIndex !== 5 ||
            noTelemetry.afterEditIndex !== 7 ||
            noTelemetry.beforeUndoDepth !== null ||
            noTelemetry.afterUndoDepth !== null
          ) throw new Error(
            `missing history telemetry was accepted: ${JSON.stringify(noTelemetry)}`
          );
        })().catch((error) => {
          console.error(error);
          process.exitCode = 1;
        });
        """
    )
    subprocess.run(
        [node, "-e", script],
        cwd=Path.cwd(),
        check=True,
        text=True,
    )


def test_edge_settings_rejects_future_annotation_loss_on_readback() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for JavaScript bridge tests")
    script = textwrap.dedent(
        """
        const mapId = "map-1";
        const original = {
          siteMapId: mapId, archived: false, disabled: false,
          edge: {
            id: {fromWaypoint: "a", toWaypoint: "b"},
            annotations: {
              edgeSource: 5,
              cost: 2,
              futureSafetyField: {preserve: true},
            },
          },
        };
        const state = {
          mapDisplay: {siteMapId: mapId, anchoring: {anchors: []}},
          siteMaps: {entities: {[mapId]: {
            waypointIds: ["a", "b"], recordingSessionIds: ["r1"],
          }}},
          siteWaypoints: {entities: {
            a: {waypoint: {annotations: {name: "a"}}},
            b: {waypoint: {annotations: {name: "b"}}},
          }},
          siteEdges: {ids: ["a|b"], entities: {"a|b": original}},
          recordingSessions: {entities: {
            r1: {name: "Run", waypointIds: ["a", "b"]},
          }},
          mapEditor: {
            info: {selectedWaypointIds: [], selectedEdgeIds: []},
            form: {
              present: {index: 0}, past: [], future: [],
              data: {edges: {ids: [], entities: {}, nonEntities: {}}},
            },
          },
        };
        const store = {
          getState: () => state,
          dispatch(action) {
            if (action.type === "mapEditorFormSlice/updateSiteEdges") {
              state.mapEditor.form.past.push({index: 0});
              state.mapEditor.form.present.index += 2;
              const stored = JSON.parse(
                JSON.stringify(action.payload.updatedEdges[0])
              );
              delete stored.edge.annotations.futureSafetyField;
              state.mapEditor.form.data.edges.entities["a|b"] = stored;
              state.mapEditor.form.data.edges.ids = ["a|b"];
            }
            return action;
          },
        };
        const root = {__reactContainer$test: {memoizedProps: {store}}};
        const messages = [];
        let onMessage;
        global.location = {
          origin: "https://orbit.test",
          pathname: `/control_room/maps/${mapId}/edit`,
        };
        global.document = {
          currentScript: {dataset: {osmeSession: "session-1"}},
          getElementById: (id) => id === "root" ? root : null,
        };
        global.window = {
          addEventListener: (type, listener) => {
            if (type === "message") onMessage = listener;
          },
          removeEventListener: () => {},
          postMessage: (message) => messages.push(message),
          setTimeout,
        };
        require("./extension/orbit-site-map-editor/page-bridge.js");
        (async () => {
          await onMessage({
            source: window,
            origin: location.origin,
            data: {
              channel: "orbit-site-map-editor-v1",
              type: "orbit-site-map-editor-request",
              sessionId: "session-1",
              requestId: "future-field-loss",
              command: "update_edge_settings",
              mapId,
              settingsUpdates: [{
                waypointIds: ["a", "b"],
                storedFrom: "a",
                storedTo: "b",
                observedSourceValue: 5,
                observedSettings: {cost: 2},
                desiredSettings: {cost: 9, stairs: true},
              }],
            },
          });
          const response = messages.find(
            (message) => message.requestId === "future-field-loss"
          );
          const edited =
            state.mapEditor.form.data.edges.entities["a|b"].edge.annotations;
          if (
            response?.ok ||
            response?.error !== "edge_annotation_readback_failed" ||
            response?.mutationMayExist !== true ||
            response?.beforeEditIndex !== 0 ||
            response?.afterEditIndex !== 2 ||
            response?.beforeUndoDepth !== 0 ||
            response?.afterUndoDepth !== 1 ||
            response?.targetKeys?.join(",") !== "a|b" ||
            edited.cost !== 9 ||
            edited.stairs !== true ||
            "futureSafetyField" in edited
          ) throw new Error(JSON.stringify({response, edited}));
        })().catch((error) => {
          console.error(error);
          process.exitCode = 1;
        });
        """
    )
    subprocess.run(
        [node, "-e", script],
        cwd=Path.cwd(),
        check=True,
        text=True,
    )


def test_page_bridge_reinjection_replaces_listener_and_deduplicates_mutations() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for JavaScript bridge tests")
    source = json.dumps((EXTENSION / "page-bridge.js").read_text(encoding="utf-8"))
    script = textwrap.dedent(
        f"""
        const vm = require("node:vm");
        const bridgeSource = {source};
        const mapId = "map-1";
        const edge = {{
          siteMapId: mapId, archived: false, disabled: false,
          edge: {{
            id: {{fromWaypoint: "a", toWaypoint: "b"}},
            annotations: {{edgeSource: 5}},
          }},
        }};
        const state = {{
          mapDisplay: {{siteMapId: mapId, anchoring: {{anchors: []}}}},
          siteMaps: {{entities: {{[mapId]: {{
            waypointIds: ["a", "b"], recordingSessionIds: ["r1"],
          }}}}}},
          siteWaypoints: {{entities: {{
            a: {{waypoint: {{annotations: {{name: "a"}}}}}},
            b: {{waypoint: {{annotations: {{name: "b"}}}}}},
          }}}},
          siteEdges: {{ids: ["a|b"], entities: {{"a|b": edge}}}},
          recordingSessions: {{entities: {{
            r1: {{name: "Run", waypointIds: ["a", "b"]}},
          }}}},
          mapEditor: {{
            info: {{selectedWaypointIds: [], selectedEdgeIds: []}},
            form: {{
              present: {{index: 0}}, past: [], future: [],
              data: {{edges: {{ids: [], entities: {{}}, nonEntities: {{}}}}}},
            }},
          }},
        }};
        const store = {{
          getState: () => state,
          dispatch(action) {{
            if (action.type === "mapEditorInfoSlice/setSelectedEdges") {{
              state.mapEditor.info.selectedEdgeIds = [...action.payload];
            }} else if (action.type === "mapEditorFormSlice/archiveSiteEdges") {{
              state.mapEditor.form.past.push({{
                index: state.mapEditor.form.present.index,
              }});
              state.mapEditor.form.data.edges.nonEntities["a|b"] = {{
                ...action.payload[0], archived: true,
              }};
              state.mapEditor.form.present.index += 1;
            }}
            return action;
          }},
        }};
        const listeners = new Set();
        const messages = [];
        const root = {{__reactContainer$test: {{memoizedProps: {{store}}}}}};
        global.location = {{
          origin: "https://orbit.test",
          pathname: `/control_room/maps/${{mapId}}/edit`,
        }};
        global.document = {{
          currentScript: {{dataset: {{osmeSession: "session-1"}}}},
          getElementById: (id) => id === "root" ? root : null,
        }};
        global.window = {{
          addEventListener: (type, listener) => {{
            if (type === "message") listeners.add(listener);
          }},
          removeEventListener: (type, listener) => {{
            if (type === "message") listeners.delete(listener);
          }},
          postMessage: (message) => messages.push(message),
          setTimeout,
        }};

        vm.runInThisContext(bridgeSource);
        document.currentScript = {{dataset: {{osmeSession: "session-2"}}}};
        vm.runInThisContext(bridgeSource);
        if (listeners.size !== 1) throw new Error(`listener count ${{listeners.size}}`);
        const listener = [...listeners][0];
        const request = {{
          source: window,
          origin: location.origin,
          data: {{
            channel: "orbit-site-map-editor-v1",
            type: "orbit-site-map-editor-request",
            sessionId: "session-2",
            requestId: "archive-once",
            command: "archive_edges",
            mapId,
            waypointPairs: [["a", "b"]],
          }},
        }};
        (async () => {{
          await listener(request);
          await listener(request);
          const responses = messages.filter((message) => message.requestId === "archive-once");
          if (
            state.mapEditor.form.present.index !== 1 ||
            responses.length !== 2 ||
            !responses[0].ok ||
            responses[1].error !== "duplicate_request" ||
            responses.some((message) => message.sessionId !== "session-2")
          ) throw new Error(JSON.stringify({{
            index: state.mapEditor.form.present.index,
            responses,
          }}));
        }})().catch((error) => {{
          console.error(error);
          process.exitCode = 1;
        }});
        """
    )
    subprocess.run(
        [node, "-e", script],
        cwd=Path.cwd(),
        check=True,
        text=True,
    )


def test_page_bridge_reinjection_aborts_pending_connect_before_dispatch() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for JavaScript bridge tests")
    source = json.dumps((EXTENSION / "page-bridge.js").read_text(encoding="utf-8"))
    script = f"const bridgeSource = {source};\n" + textwrap.dedent(
        """
        const vm = require("node:vm");
        const mapId = "map-1";
        const waypoint = (id) => ({waypoint: {
          id, annotations: {name: id},
          waypointTformKo: {position: {x: 0, y: 0, z: 0}},
        }});
        const state = {
          mapDisplay: {siteMapId: mapId, anchoring: {anchors: []}},
          siteMaps: {entities: {[mapId]: {
            waypointIds: ["a", "b"], recordingSessionIds: ["r1"],
          }}},
          siteWaypoints: {
            ids: ["a", "b"],
            entities: {a: waypoint("a"), b: waypoint("b")},
          },
          siteEdges: {ids: [], entities: {}},
          recordingSessions: {entities: {
            r1: {name: "Run", waypointIds: ["a", "b"]},
          }},
          mapEditor: {
            info: {
              selectedWaypointIds: [],
              selectedEdgeIds: [],
              pendingEdgeCreation: {
                errors: [], warnings: [], validating: false,
              },
            },
            form: {
              present: {index: 0}, past: [], future: [],
              data: {edges: {ids: [], entities: {}, nonEntities: {}}},
            },
          },
        };
        let addCount = 0;
        const store = {
          getState: () => state,
          dispatch(action) {
            if (action.type === "mapEditorInfoSlice/setSelectedWaypoints") {
              state.mapEditor.info.selectedWaypointIds = [...action.payload];
              if (action.payload.length === 2) {
                state.mapEditor.info.pendingEdgeCreation = {
                  errors: [], warnings: [], validating: true,
                };
              }
            } else if (action.type === "mapEditorFormSlice/addSiteEdge") {
              addCount += 1;
            }
            return action;
          },
        };
        const listeners = new Set();
        const messages = [];
        const timers = [];
        let completed = false;
        process.on("beforeExit", () => {
          if (!completed) {
            console.error("pending Connect test did not reach its assertions");
            process.exitCode = 1;
          }
        });
        const root = {__reactContainer$test: {memoizedProps: {store}}};
        global.location = {
          origin: "https://orbit.test",
          pathname: `/control_room/maps/${mapId}/edit`,
        };
        global.document = {
          currentScript: {dataset: {osmeSession: "session-1"}},
          getElementById: (id) => id === "root" ? root : null,
        };
        global.window = {
          addEventListener: (type, listener) => {
            if (type === "message") listeners.add(listener);
          },
          removeEventListener: (type, listener) => {
            if (type === "message") listeners.delete(listener);
          },
          postMessage: (message) => messages.push(message),
          setTimeout: (callback) => {
            timers.push(callback);
            return timers.length;
          },
        };

        vm.runInThisContext(bridgeSource);
        const oldListener = [...listeners][0];
        const oldRequest = oldListener({
          source: window,
          origin: location.origin,
          data: {
            channel: "orbit-site-map-editor-v1",
            type: "orbit-site-map-editor-request",
            sessionId: "session-1",
            requestId: "stale-connect",
            command: "connect",
            mapId,
            waypointIds: ["a", "b"],
          },
        });
        if (timers.length !== 1) {
          throw new Error(`expected one pending validation timer, got ${timers.length}`);
        }
        state.mapEditor.info.pendingEdgeCreation = {
          errors: [],
          warnings: [],
          validating: false,
          showModal: false,
          createdEdgeCandidate: {
            siteMapId: mapId,
            archived: false,
            disabled: false,
            edge: {
              id: {fromWaypoint: "a", toWaypoint: "b"},
              annotations: {edgeSource: 5},
            },
          },
        };

        document.currentScript = {dataset: {osmeSession: "session-2"}};
        vm.runInThisContext(bridgeSource);
        if (listeners.size !== 1) {
          throw new Error(`listener count ${listeners.size}`);
        }
        for (const callback of timers.splice(0)) callback();

        (async () => {
          await oldRequest;
          await Promise.resolve();
          const oldSuccess = messages.find(
            (message) => message.requestId === "stale-connect" && message.ok
          );
          if (addCount !== 0 || oldSuccess) {
            throw new Error(JSON.stringify({addCount, oldSuccess, messages}));
          }
          completed = true;
        })().catch((error) => {
          console.error(error);
          process.exitCode = 1;
        });
        """
    )
    subprocess.run(
        [node, "-e", script],
        cwd=Path.cwd(),
        check=True,
        text=True,
    )


def test_page_bridge_reports_ambiguous_failure_after_mutation_dispatch_throw() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for JavaScript bridge tests")
    source = json.dumps((EXTENSION / "page-bridge.js").read_text(encoding="utf-8"))

    for mode in ("dispatch_throw", "readback_throw"):
        script = (
            f"const bridgeSource = {source};\n"
            f"const failureMode = {json.dumps(mode)};\n"
            + textwrap.dedent(
                """
                const vm = require("node:vm");
                const mapId = "map-1";
                const edge = {
                  siteMapId: mapId, archived: false, disabled: false,
                  edge: {
                    id: {fromWaypoint: "a", toWaypoint: "b"},
                    annotations: {edgeSource: 5},
                  },
                };
                const state = {
                  mapDisplay: {siteMapId: mapId, anchoring: {anchors: []}},
                  siteMaps: {entities: {[mapId]: {
                    waypointIds: ["a", "b"], recordingSessionIds: ["r1"],
                  }}},
                  siteWaypoints: {entities: {
                    a: {waypoint: {annotations: {name: "a"}}},
                    b: {waypoint: {annotations: {name: "b"}}},
                  }},
                  siteEdges: {ids: ["a|b"], entities: {"a|b": edge}},
                  recordingSessions: {entities: {
                    r1: {name: "Run", waypointIds: ["a", "b"]},
                  }},
                  mapEditor: {
                    info: {selectedWaypointIds: [], selectedEdgeIds: []},
                    form: {
                      present: {index: 0}, past: [], future: [],
                      data: {edges: {ids: [], entities: {}, nonEntities: {}}},
                    },
                  },
                };
                let throwOnReadback = false;
                const store = {
                  getState() {
                    if (throwOnReadback) {
                      throwOnReadback = false;
                      throw new Error("readback failed");
                    }
                    return state;
                  },
                  dispatch(action) {
                    if (action.type === "mapEditorInfoSlice/setSelectedEdges") {
                      state.mapEditor.info.selectedEdgeIds = [...action.payload];
                    } else if (
                      action.type === "mapEditorFormSlice/archiveSiteEdges"
                    ) {
                      state.mapEditor.form.past.push({index: 0});
                      state.mapEditor.form.present.index = 1;
                      state.mapEditor.form.data.edges.nonEntities["a|b"] = {
                        ...action.payload[0], archived: true,
                      };
                      if (failureMode === "readback_throw") {
                        throwOnReadback = true;
                      } else {
                        throw new Error("dispatch failed after reducer write");
                      }
                    }
                    return action;
                  },
                };
                const listeners = new Set();
                const messages = [];
                const root = {__reactContainer$test: {memoizedProps: {store}}};
                global.location = {
                  origin: "https://orbit.test",
                  pathname: `/control_room/maps/${mapId}/edit`,
                };
                global.document = {
                  currentScript: {dataset: {osmeSession: "session-1"}},
                  getElementById: (id) => id === "root" ? root : null,
                };
                global.window = {
                  addEventListener: (type, listener) => {
                    if (type === "message") listeners.add(listener);
                  },
                  removeEventListener: (type, listener) => {
                    if (type === "message") listeners.delete(listener);
                  },
                  postMessage: (message) => messages.push(message),
                  setTimeout,
                };
                vm.runInThisContext(bridgeSource);
                const listener = [...listeners][0];
                (async () => {
                  await listener({
                    source: window,
                    origin: location.origin,
                    data: {
                      channel: "orbit-site-map-editor-v1",
                      type: "orbit-site-map-editor-request",
                      sessionId: "session-1",
                      requestId: "archive-throws",
                      command: "archive_edges",
                      mapId,
                      waypointPairs: [["a", "b"]],
                    },
                  });
                  const response = messages.find(
                    (message) => message.requestId === "archive-throws"
                  );
                  if (
                    response?.ok ||
                    response?.error !== "native_mutation_exception" ||
                    response?.mutationMayExist !== true ||
                    response?.targetKeys?.join(",") !== "a|b" ||
                    state.mapEditor.form.present.index !== 1 ||
                    !state.mapEditor.form.data.edges.nonEntities["a|b"]?.archived
                  ) throw new Error(JSON.stringify({response, state}));
                })().catch((error) => {
                  console.error(error);
                  process.exitCode = 1;
                });
                """
            )
        )
        subprocess.run(
            [node, "-e", script],
            cwd=Path.cwd(),
            check=True,
            text=True,
        )


def test_content_marks_mutation_timeout_and_invalidation_as_ambiguous() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for JavaScript content-script tests")

    harness = textwrap.dedent(
        """
        class FakeNode {
          constructor() {
            this.dataset = {};
            this.style = {};
            this.hidden = false;
            this.inert = false;
            this.value = "";
            this.checked = false;
            this.textContent = "";
            this.children = [];
            this.nodes = new Map();
            this.classList = {
              add() {}, remove() {}, toggle() {}, contains() {return false;},
            };
          }
          querySelector(selector) {
            if (!this.nodes.has(selector)) {
              this.nodes.set(selector, new FakeNode());
            }
            return this.nodes.get(selector);
          }
          querySelectorAll() {return [];}
          append(...nodes) {this.children.push(...nodes);}
          after() {}
          before() {}
          replaceChildren(...nodes) {this.children = [...nodes];}
          addEventListener() {}
          removeEventListener() {}
          setAttribute() {}
          remove() {}
          closest() {return null;}
          getBoundingClientRect() {
            return {left: 0, top: 0, width: 100, height: 100};
          }
        }
        const documentElement = new FakeNode();
        global.document = {
          documentElement,
          createElement: () => new FakeNode(),
          createElementNS: () => new FakeNode(),
          getElementById: () => null,
          querySelector: () => null,
        };
        const windowListeners = new Map();
        const postedMessages = [];
        global.location = {
          origin: "https://orbit.test",
          pathname: "/control_room/maps/map-1/edit",
          href: "https://orbit.test/control_room/maps/map-1/edit",
        };
        global.CustomEvent = class {
          constructor(type, init = {}) {
            this.type = type;
            this.detail = init.detail;
          }
        };
        global.window = {
          addEventListener(type, listener) {windowListeners.set(type, listener);},
          removeEventListener(type) {windowListeners.delete(type);},
          dispatchEvent() {},
          postMessage(message) {postedMessages.push(message);},
          setTimeout,
          clearTimeout,
          requestAnimationFrame: () => 1,
          cancelAnimationFrame() {},
          setInterval: () => 1,
          clearInterval() {},
          innerWidth: 1200,
          innerHeight: 800,
        };
        let active = true;
        let invalidationListener = () => {};
        global.OrbitSiteMapEditorExtensionContext = {
          isActive: () => active,
          storageGet: () => new Promise(() => {}),
          storageSet: () => true,
          getUrl: () => "",
          getVersionLabel: () => "0.5.0 test",
          onInvalidated(listener) {
            invalidationListener = listener;
            return () => {};
          },
        };
        require("./extension/orbit-site-map-editor/panel-layout.js");
        require("./extension/orbit-site-map-editor/model.js");
        require("./extension/orbit-site-map-editor/query.js");
        require("./extension/orbit-site-map-editor/content.js");
        const runtime = global.OrbitSiteMapEditorRuntime;
        const serial = (error) => ({
          message: error.message,
          mutationMayExist: Boolean(error.mutationMayExist),
          targetKeys: error.mutationContext?.targetKeys || [],
        });
        """
    )

    timeout_script = harness + textwrap.dedent(
        """
        (async () => {
          const mutation = await runtime.requestBridge(
            "archive_edges",
            {waypointPairs: [["a", "b"]]},
            1
          ).then(() => null, serial);
          const blocked = await runtime.requestBridge(
            "connect",
            {waypointIds: ["b", "c"]},
            1
          ).then(() => null, serial);
          const blockedValidation = await runtime.requestBridge(
            "validate_connect",
            {waypointIds: ["b", "c"]},
            1
          ).then(() => null, serial);
          const readOnly = await runtime.requestBridge(
            "snapshot",
            {},
            1
          ).then(() => null, serial);
          process.stdout.write(JSON.stringify({
            mutation, blocked, blockedValidation, readOnly
          }));
        })().catch((error) => {
          console.error(error);
          process.exitCode = 1;
        });
        """
    )
    timeout_result = subprocess.run(
        [node, "-e", timeout_script],
        cwd=Path.cwd(),
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(timeout_result.stdout) == {
        "mutation": {
            "message": "Orbit adapter timed out.",
            "mutationMayExist": True,
            "targetKeys": ["a|b"],
        },
        "blocked": {
            "message": "unverified_mutation_pending",
            "mutationMayExist": True,
            "targetKeys": ["a|b"],
        },
        "blockedValidation": {
            "message": "unverified_mutation_pending",
            "mutationMayExist": True,
            "targetKeys": ["a|b"],
        },
        "readOnly": {
            "message": "Orbit adapter timed out.",
            "mutationMayExist": False,
            "targetKeys": [],
        },
    }

    invalidation_script = harness + textwrap.dedent(
        """
        (async () => {
          const pending = runtime.requestBridge(
            "connect",
            {waypointIds: ["a", "b"]},
            10000
          ).then(() => null, serial);
          active = false;
          invalidationListener();
          const invalidated = await pending;
          process.stdout.write(JSON.stringify({invalidated}));
        })().catch((error) => {
          console.error(error);
          process.exitCode = 1;
        });
        """
    )
    invalidation_result = subprocess.run(
        [node, "-e", invalidation_script],
        cwd=Path.cwd(),
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(invalidation_result.stdout) == {
        "invalidated": {
            "message": "extension_context_invalidated",
            "mutationMayExist": True,
            "targetKeys": ["a|b"],
        }
    }

    validation_script = harness + textwrap.dedent(
        """
        (async () => {
          const pending = runtime.requestBridge(
            "validate_connect",
            {waypointIds: ["a", "b"]},
            10000
          ).then(() => null, serial);
          const request = postedMessages.at(-1);
          windowListeners.get("message")({
            source: window,
            origin: location.origin,
            data: {
              channel: "orbit-site-map-editor-v1",
              type: "orbit-site-map-editor-response",
              requestId: request.requestId,
              sessionId: request.sessionId,
              ok: false,
              error: "validation_changed_draft",
              mutationMayExist: true,
              beforeEditIndex: 4,
              afterEditIndex: 5,
              beforeUndoDepth: 0,
              afterUndoDepth: 1,
              targetKeys: ["a|b"],
            },
          });
          const ambiguous = await pending;
          const blocked = await runtime.requestBridge(
            "validate_connect",
            {waypointIds: ["b", "c"]},
            1
          ).then(() => null, serial);
          process.stdout.write(JSON.stringify({
            ambiguous,
            blocked,
            locked: Boolean(runtime.state.mutationUncertain),
          }));
        })().catch((error) => {
          console.error(error);
          process.exitCode = 1;
        });
        """
    )
    validation_result = subprocess.run(
        [node, "-e", validation_script],
        cwd=Path.cwd(),
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(validation_result.stdout) == {
        "ambiguous": {
            "message": "validation_changed_draft",
            "mutationMayExist": True,
            "targetKeys": ["a|b"],
        },
        "blocked": {
            "message": "unverified_mutation_pending",
            "mutationMayExist": True,
            "targetKeys": ["a|b"],
        },
        "locked": True,
    }


def test_walk_planner_covers_each_waypoint_with_graph_valid_revisits() -> None:
    result = run_editor_modules(
        textwrap.dedent(
            """
            const planner = OrbitSiteMapEditorWalkPlanner;
            const snapshot = {
              map: {id: "map-coverage", name: "Coverage"},
              editIndex: 7,
              waypoints: ["a", "b", "c", "d", "e", "f", "z"].map(
                (id, index) => ({id, position: {x: index, y: index % 2, z: 0}})
              ),
              edges: [
                ["ab", "a", "b"],
                ["bc", "b", "c"],
                ["bd", "b", "d"],
                ["de", "d", "e"],
                ["ef", "e", "f"],
                ["cf", "c", "f"],
              ].map(([id, from, to]) => ({id, from, to, length: 1})),
            };
            const open = planner.planCoverage(snapshot, {
              scope: "component",
              startWaypointId: "a",
              maxRouteWaypoints: 4,
              createdAt: "2026-07-24T00:00:00.000Z",
              supplementalSleepActions: [{
                waypointId: "d", durationSeconds: 2.5, name: "Pause at D",
              }],
            });
            const closed = planner.planCoverage(snapshot, {
              scope: "component",
              startWaypointId: "a",
              returnToStart: true,
              createdAt: "2026-07-24T00:00:00.000Z",
            });
            const all = planner.planCoverage(snapshot, {
              scope: "all",
              startWaypointId: "a",
              createdAt: "2026-07-24T00:00:00.000Z",
            });
            const changedSnapshot = {
              ...snapshot,
              edges: snapshot.edges.filter(
                (edge) => edge.id !== open.components[0].edgeWalk[0].id
              ),
            };
            const invalidAfterEdgeRemoval = planner.validateCoveragePlan(
              changedSnapshot,
              open,
            );
            const component = open.components[0];
            const activePairs = new Set(
              snapshot.edges.map((edge) => planner.edgeKey(edge.from, edge.to))
            );
            process.stdout.write(JSON.stringify({
              schemaVersion: open.schemaVersion,
              valid: open.validation.valid,
              required: component.requiredWaypointIds,
              visited: [...new Set(component.waypointWalk)].sort(),
              everyStepActive: component.waypointWalk.slice(0, -1).every(
                (from, index) => activePairs.has(
                  planner.edgeKey(from, component.waypointWalk[index + 1])
                )
              ),
              repeatCount: component.repeatedVisitCount,
              checkpointCount: component.checkpointCount,
              actionAtEveryWaypoint: open.checkpointPolicy.actionAtEveryWaypoint,
              scheduledKinds: open.actionSchedule.scheduled.map(
                (item) => item.actionKind
              ),
              missionIndependent: open.missionIndependent,
              executionValid: open.validation.valid,
              executionEntryCount: open.executionSequence.entryCount,
              navigationCheckpointCount:
                open.executionSequence.navigationCheckpointCount,
              intentionalSleepCount:
                open.executionSequence.intentionalSleepCount,
              orderedSequences: open.executionSequence.entries.map(
                (item) => item.sequence
              ),
              closedEnd: closed.components[0].endWaypointId,
              closedTraversalCount: closed.components[0].traversalCount,
              allComponentSizes: all.components.map(
                (item) => item.requiredWaypointIds.length
              ),
              isolated: all.components[1].isolated,
              invalidAfterEdgeRemoval: invalidAfterEdgeRemoval.valid,
            }));
            """
        )
    )

    assert result["schemaVersion"] == "orbit_site_view_coverage_plan_v2"
    assert result["valid"] is True
    assert result["required"] == ["a", "b", "c", "d", "e", "f"]
    assert result["visited"] == result["required"]
    assert result["everyStepActive"] is True
    assert result["repeatCount"] > 0
    assert result["checkpointCount"] < len(result["required"])
    assert result["actionAtEveryWaypoint"] is False
    assert result["scheduledKinds"] == ["sleep"]
    assert result["missionIndependent"] is True
    assert result["executionValid"] is True
    assert result["executionEntryCount"] < len(result["required"])
    assert result["navigationCheckpointCount"] < len(result["required"])
    assert result["intentionalSleepCount"] == 1
    assert result["orderedSequences"] == list(range(1, result["executionEntryCount"] + 1))
    assert result["closedEnd"] == "a"
    assert result["closedTraversalCount"] == 10
    assert result["allComponentSizes"] == [6, 1]
    assert result["isolated"] is True
    assert result["invalidAfterEdgeRemoval"] is False


def test_walk_planner_handles_more_than_the_observed_large_map_size() -> None:
    result = run_editor_modules(
        textwrap.dedent(
            """
            const planner = OrbitSiteMapEditorWalkPlanner;
            const waypointCount = 5000;
            const waypoints = Array.from({length: waypointCount}, (_, index) => ({
              id: `waypoint-${String(index).padStart(5, "0")}`,
              position: null,
            }));
            const edges = Array.from({length: waypointCount - 1}, (_, index) => {
              const child = index + 1;
              const parent = Math.floor((child - 1) / 3);
              return {
                id: `edge-${index}`,
                from: waypoints[parent].id,
                to: waypoints[child].id,
                length: 1,
              };
            });
            const plan = planner.planCoverage(
              {
                map: {id: "large-map", name: "Large map"},
                waypoints,
                edges,
              },
              {
                scope: "all",
                startWaypointId: waypoints[0].id,
                maxRouteWaypoints: 150,
                createdAt: "2026-07-24T00:00:00.000Z",
              },
            );
            const component = plan.components[0];
            process.stdout.write(JSON.stringify({
              valid: plan.validation.valid,
              required: plan.totals.requiredWaypointCount,
              visited: new Set(component.waypointWalk).size,
              repeated: component.repeatedVisitCount,
              executionEntries: plan.executionSequence.entryCount,
              maximumRouteSize: Math.max(
                ...plan.executionSequence.entries.map(
                  (entry) => entry.routeWaypointIds.length
                )
              ),
              componentCount: plan.graphSummary.mapComponentCount,
              actionAtEveryWaypoint:
                plan.executionSequence.actionAtEveryWaypoint,
            }));
            """
        )
    )

    assert result == {
        "valid": True,
        "required": 5000,
        "visited": 5000,
        "repeated": 4991,
        "executionEntries": 68,
        "maximumRouteSize": 150,
        "componentCount": 1,
        "actionAtEveryWaypoint": False,
    }


def test_walk_planner_defaults_to_dock_reachable_active_component_and_minimal_sleep() -> None:
    result = run_editor_modules(
        textwrap.dedent(
            """
            const planner = OrbitSiteMapEditorWalkPlanner;
            const snapshot = {
              map: {id: "operational-map", name: "Operational"},
              waypoints: ["a", "b", "c", "d", "e", "f", "g", "z"].map(
                (id) => ({id, position: null})
              ),
              edges: [
                {id: "ab", from: "a", to: "b"},
                {id: "bc", from: "b", to: "c"},
                {id: "de", from: "d", to: "e"},
                {id: "ef", from: "e", to: "f"},
                {id: "fg", from: "f", to: "g"},
                {id: "cz-archived", from: "c", to: "z", archived: true},
                {id: "az-disabled", from: "a", to: "z", disabled: true},
              ],
            };
            const sitePanoWaypoints = [
              {waypointId: "a", allowCaptureVisual: true},
              {waypointId: "b", allowCaptureVisual: false},
              {waypointId: "c", allowCaptureVisual: true},
              {waypointId: "d", allowCaptureVisual: true},
              {waypointId: "z", allowCaptureVisual: true},
              {waypointId: "ghost", allowCaptureVisual: true},
            ];
            const dockPlan = planner.planCoverage(snapshot, {
              dockWaypointIds: ["a"],
              maxRouteWaypoints: 2,
              sitePanoWaypoints,
              createdAt: "2026-07-24T00:00:00.000Z",
            });
            const explicitStart = planner.planCoverage(snapshot, {
              startWaypointId: "d",
              createdAt: "2026-07-24T00:00:00.000Z",
            });
            const fallback = planner.planCoverage(snapshot, {
              dockWaypointIds: ["a"],
              maxRouteWaypoints: 2,
              checkpointMode: "compatibility_sleep",
              sleepDurationSeconds: 0.5,
              createdAt: "2026-07-24T00:00:00.000Z",
            });
            const audit = planner.planCoverage(snapshot, {
              scope: "all",
              startWaypointId: "a",
              createdAt: "2026-07-24T00:00:00.000Z",
            });
            let isolatedStartError = "";
            try {
              planner.planCoverage(snapshot, {
                startWaypointId: "z",
                createdAt: "2026-07-24T00:00:00.000Z",
              });
            } catch (error) {
              isolatedStartError = error.message;
            }
            process.stdout.write(JSON.stringify({
              defaultScope: dockPlan.scope,
              defaultAnchor: dockPlan.coverageAnchor,
              dockRequired: dockPlan.components[0].requiredWaypointIds,
              dockActiveEdgeCount: dockPlan.graphSummary.mapEdgeCount,
              excluded: dockPlan.graphSummary.excludedDisconnectedWaypointCount,
              activeComponents:
                dockPlan.graphSummary.activeConnectedComponentCount,
              isolatedWaypoints: dockPlan.graphSummary.isolatedWaypointCount,
              defaultNavigationOnly:
                dockPlan.executionSequence.navigationOnlyCheckpointCount,
              defaultFallbackSleeps:
                dockPlan.executionSequence.compatibilitySleepCheckpointCount,
              siteViewBasis:
                dockPlan.siteViewCoverage.basis,
              siteViewEligible:
                dockPlan.siteViewCoverage.eligibleWaypointCount,
              siteViewCovered:
                dockPlan.siteViewCoverage.plannedCoveredEligibleWaypointIds,
              siteViewExcluded:
                dockPlan.siteViewCoverage.excludedEligibleWaypointIds,
              siteViewMissing:
                dockPlan.siteViewCoverage.missingMapWaypointIds,
              explicitRequired:
                explicitStart.components[0].requiredWaypointIds,
              explicitAnchor: explicitStart.coverageAnchor,
              fallbackMode: fallback.checkpointPolicy.mode,
              fallbackCount:
                fallback.executionSequence.compatibilitySleepCheckpointCount,
              fallbackDurations: fallback.executionSequence.entries
                .filter((entry) => entry.kind === "navigate_route_checkpoint")
                .map((entry) => entry.action?.durationSeconds),
              existingElements:
                fallback.compatibility.reusedExistingSiteElementCount,
              readsExistingMission:
                fallback.compatibility.existingSiteWalkRead,
              automaticFallbackCount:
                fallback.compatibility.automaticSleepFallbackCount,
              auditSizes: audit.components.map(
                (component) => component.requiredWaypointIds.length
              ),
              isolatedStartError,
            }));
            """
        )
    )

    assert result == {
        "defaultScope": "reachable",
        "defaultAnchor": {"waypointId": "a", "source": "dock"},
        "dockRequired": ["a", "b", "c"],
        "dockActiveEdgeCount": 5,
        "excluded": 5,
        "activeComponents": 2,
        "isolatedWaypoints": 1,
        "defaultNavigationOnly": 2,
        "defaultFallbackSleeps": 0,
        "siteViewBasis": "site_waypoint_pano_settings_and_planned_active_route",
        "siteViewEligible": 4,
        "siteViewCovered": ["a", "c"],
        "siteViewExcluded": ["d", "z"],
        "siteViewMissing": ["ghost"],
        "explicitRequired": ["d", "e", "f", "g"],
        "explicitAnchor": {"waypointId": "d", "source": "start_waypoint"},
        "fallbackMode": "compatibility_sleep",
        "fallbackCount": 2,
        "fallbackDurations": [0.5, 0.5],
        "existingElements": 0,
        "readsExistingMission": False,
        "automaticFallbackCount": 2,
        "auditSizes": [3, 4, 1],
        "isolatedStartError": "start_waypoint_has_no_active_edges",
    }


def test_walk_planner_excludes_exact_waypoints_before_graph_planning() -> None:
    result = run_editor_modules(
        textwrap.dedent(
            """
            const planner = OrbitSiteMapEditorWalkPlanner;
            const snapshot = {
              map: {id: "map-exclusions", name: "Exclusions"},
              waypoints: ["a", "b", "c", "d", "e"].map(
                (id) => ({id, position: null})
              ),
              edges: [
                {id: "ab", from: "a", to: "b"},
                {id: "bc", from: "b", to: "c"},
                {id: "cd", from: "c", to: "d"},
                {id: "be", from: "b", to: "e"},
              ],
            };
            const plan = planner.planCoverage(snapshot, {
              startWaypointId: "a",
              excludedWaypointIds: ["c", "c"],
              sitePanoWaypoints: ["a", "c", "d", "e"].map(
                (waypointId) => ({waypointId, allowCaptureVisual: true})
              ),
              maxRouteWaypoints: 2,
              createdAt: "2026-07-24T00:00:00.000Z",
            });
            const errorFor = (options) => {
              try {
                planner.planCoverage(snapshot, options);
                return "";
              } catch (error) {
                return error.message;
              }
            };
            process.stdout.write(JSON.stringify({
              valid: plan.validation.valid,
              required: plan.components[0].requiredWaypointIds,
              route: plan.components[0].waypointWalk,
              exclusions: plan.exclusions,
              graphSummary: plan.graphSummary,
              siteView: plan.siteViewCoverage,
              targetSequences: plan.executionSequence.entries.map(
                (entry) => entry.sequence
              ),
              unknownError: errorFor({excludedWaypointIds: ["missing"]}),
              startError: errorFor({
                startWaypointId: "c",
                excludedWaypointIds: ["c"],
              }),
              allError: errorFor({
                excludedWaypointIds: ["a", "b", "c", "d", "e"],
              }),
            }));
            """
        )
    )

    assert result["valid"] is True
    assert result["required"] == ["a", "b", "e"]
    assert "c" not in result["route"]
    assert "d" not in result["route"]
    assert result["exclusions"] == {
        "semantics": "remove_waypoints_and_incident_edges_before_route_planning",
        "waypointIds": ["c"],
        "waypointCount": 1,
        "removedActiveEdgeCount": 2,
    }
    assert result["graphSummary"]["mapWaypointCount"] == 5
    assert result["graphSummary"]["planningWaypointCount"] == 4
    assert result["graphSummary"]["explicitlyExcludedWaypointCount"] == 1
    assert result["graphSummary"]["excludedDisconnectedWaypointCount"] == 1
    assert result["graphSummary"]["totalExcludedWaypointCount"] == 2
    assert result["siteView"]["plannedCoveredEligibleWaypointIds"] == ["a", "e"]
    assert result["siteView"]["explicitlyExcludedEligibleWaypointIds"] == ["c"]
    assert result["siteView"]["disconnectedEligibleWaypointIds"] == ["d"]
    assert result["siteView"]["excludedEligibleWaypointIds"] == ["c", "d"]
    assert result["targetSequences"] == list(range(1, len(result["targetSequences"]) + 1))
    assert result["unknownError"] == "excluded_waypoint_not_found:missing"
    assert result["startError"] == "start_waypoint_excluded"
    assert result["allError"] == "all_waypoints_excluded"


def test_site_view_snapshot_ignores_missions_and_reads_pano_without_dispatch() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for JavaScript bridge tests")
    script = textwrap.dedent(
        """
        const mapId = "map-1";
        const state = {
          mapDisplay: {siteMapId: mapId},
          siteMaps: {entities: {
            [mapId]: {
              waypointIds: ["a", "b"],
              metadata: {displayName: "Test map"},
            },
          }},
          missions: {
            ids: ["mission-1", "mission-other"],
            entities: {
              "mission-1": {siteWalk: {
                uuid: "walk-1",
                name: "Site View Coverage",
                siteElementIds: ["element-b", "element-a"],
                dockIds: ["dock-1"],
                isScanningOnly: true,
                injectSitePanoVisualActions: true,
                maxSitePanosVisual: 9999,
              }},
              "mission-other": {siteWalk: {
                uuid: "walk-other",
                name: "Other map",
                siteElementIds: ["element-x"],
              }},
            },
          },
          siteElements: {
            ids: ["element-a", "element-b", "element-x"],
            entities: {
              "element-a": {
                uuid: "element-a", name: "Pause", waypointId: "a",
                action: {sleep: {duration: {seconds: 2, nanos: 500000000}}},
              },
              "element-b": {
                uuid: "element-b", name: "Inspect", waypointId: "b",
                action: {dataAcquisition: {request: {}}},
                actionDuration: {seconds: 5},
              },
              "element-x": {
                uuid: "element-x", name: "Elsewhere", waypointId: "x",
                action: {sleep: {duration: {seconds: 1}}},
              },
            },
          },
          missionRoutes: {
            ids: ["route-1"],
            entities: {
              "route-1": {
                siteWalkUuid: "walk-1",
                status: "ready",
                route: {
                  deprecatedWaypointIds: [],
                  result: {routeResults: [{
                    target: {
                      siteMapId: mapId,
                      from: {waypointId: "a"},
                      to: {waypointId: "b"},
                    },
                    route: {waypointId: ["a", "b"], edgeId: ["edge-ab"]},
                    warnings: [],
                  }]},
                },
              },
            },
          },
          siteWaypoints: {
            ids: ["a", "b"],
            entities: {
              a: {sitePanoSettings: {
                allowCaptureVisual: true, allowCaptureThermal: false,
                minTimeBetweenCaptureVisual: {seconds: 60},
              }},
              b: {sitePanoSettings: {
                allowCaptureVisual: false, allowCaptureThermal: true,
                minTimeBetweenCaptureThermal: {seconds: 120},
              }},
            },
          },
          siteDocks: {
            ids: ["dock-1"],
            entities: {
              "dock-1": {siteDock: {
                uuid: "dock-1", name: "Main dock", dockedWaypointId: "a",
              }},
            },
          },
        };
        const dispatched = [];
        const store = {
          getState: () => state,
          dispatch: (action) => {dispatched.push(action); return action;},
        };
        const root = {__reactContainer$test: {memoizedProps: {store}}};
        const messages = [];
        let onMessage;
        global.location = {
          origin: "https://orbit.test",
          pathname: `/control_room/maps/${mapId}/edit`,
        };
        global.document = {
          currentScript: null,
          getElementById: (id) => id === "root" ? root : null,
        };
        global.window = {
          addEventListener: (type, listener) => {
            if (type === "message") onMessage = listener;
          },
          removeEventListener: () => {},
          postMessage: (message) => messages.push(message),
          setTimeout,
        };
        require("./extension/orbit-site-map-editor/page-bridge.js");
        (async () => {
          await onMessage({
            source: window,
            origin: location.origin,
            data: {
              channel: "orbit-site-map-editor-v1",
              type: "orbit-site-map-editor-request",
              requestId: "site-view-snapshot",
              command: "site_view_snapshot",
              mapId,
            },
          });
          const response = messages.find(
            (message) => message.requestId === "site-view-snapshot"
          );
          process.stdout.write(JSON.stringify({
            ok: response.ok,
            adapter: response.adapter,
            kind: response.snapshot.kind,
            hasSiteWalks: Object.hasOwn(response.snapshot, "siteWalks"),
            hasSiteElements: Object.hasOwn(response.snapshot, "siteElements"),
            capabilities: response.snapshot.capabilities,
            pano: response.snapshot.sitePanoWaypoints,
            docks: response.snapshot.siteDocks,
            dispatchCount: dispatched.length,
          }));
        })().catch((error) => {
          console.error(error);
          process.exitCode = 1;
        });
        """
    )
    completed = subprocess.run(
        [node, "-e", script],
        cwd=Path.cwd(),
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert result["ok"] is True
    assert result["adapter"] == "orbit-5.1-readonly-site-view-planning-snapshot"
    assert result["kind"] == "orbit_site_view_planning_snapshot"
    assert result["hasSiteWalks"] is False
    assert result["hasSiteElements"] is False
    assert result["capabilities"] == {
        "siteWaypoints": "siteWaypoints",
        "siteDocks": "siteDocks",
    }
    assert result["pano"] == [
        {
            "waypointId": "a",
            "allowCaptureVisual": True,
            "allowCaptureThermal": False,
            "visualCaptureIntervalSeconds": 60,
            "thermalCaptureIntervalSeconds": None,
        },
        {
            "waypointId": "b",
            "allowCaptureVisual": False,
            "allowCaptureThermal": True,
            "visualCaptureIntervalSeconds": None,
            "thermalCaptureIntervalSeconds": 120,
        },
    ]
    assert result["docks"][0]["waypointIds"] == ["a"]
    assert result["dispatchCount"] == 0


def test_walk_ui_is_read_only_and_exposes_coverage_controls() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for JavaScript Walk UI tests")
    script = textwrap.dedent(
        """
        class FakeNode {
          constructor() {
            this.dataset = {};
            this.hidden = false;
            this.disabled = false;
            this.checked = false;
            this.value = "";
            this.textContent = "";
            this.children = [];
            this.nodes = new Map();
            this.listeners = new Map();
          }
          querySelector(selector) {
            if (!this.nodes.has(selector)) this.nodes.set(selector, new FakeNode());
            return this.nodes.get(selector);
          }
          querySelectorAll() {return [];}
          append(...nodes) {this.children.push(...nodes);}
          replaceChildren(...nodes) {this.children = [...nodes];}
          addEventListener(type, listener) {
            if (!this.listeners.has(type)) this.listeners.set(type, []);
            this.listeners.get(type).push(listener);
          }
          closest() {return null;}
          setAttribute() {}
        }
        const panel = new FakeNode();
        const nav = panel.querySelector(".osme-tabs");
        const workspace = panel.querySelector(".osme-workspace");
        const commands = [];
        const statuses = [];
        global.document = {createElement: () => new FakeNode()};
        global.window = {
          addEventListener() {},
          setTimeout,
          clearTimeout,
          URL,
        };
        global.navigator = {clipboard: {writeText: async () => {}}};
        global.OrbitSiteMapEditorExtensionContext = {
          isActive: () => true,
          onInvalidated: () => () => {},
        };
        global.OrbitSiteMapEditorRuntime = {
          currentMapId: () => "map-1",
          disposeEvent: "dispose",
          elements: {panel},
          friendlyError: (message) => message,
          instanceEvents: {snapshot: "snapshot"},
          instanceId: "walk-test",
          isDisposed: () => false,
          model: {shortId: (value) => value},
          requestBridge: async (command) => {
            commands.push(command);
            if (command !== "site_view_snapshot") {
              throw new Error(`unexpected command: ${command}`);
            }
            return {
              ok: true,
              snapshot: {
                map: {id: "map-1", name: "Map"},
                capabilities: {siteWaypoints: "adapter", siteDocks: "adapter"},
                sitePanoWaypoints: [{
                  waypointId: "a",
                  allowCaptureVisual: true,
                  allowCaptureThermal: false,
                }],
                siteDocks: [],
              },
            };
          },
          setStatus: (message, kind) => statuses.push({message, kind}),
          state: {
            lastOverlayKey: "",
            snapshot: {
              map: {id: "map-1", name: "Map"},
              editIndex: 0,
              selectedWaypointIds: [],
              waypoints: [{id: "a", position: {x: 0, y: 0, z: 0}}],
              edges: [],
              docks: [],
            },
          },
        };
        require("./extension/orbit-site-map-editor/walk-planner.js");
        require("./extension/orbit-site-map-editor/walk-ui.js");

        (async () => {
          const pane = workspace.children[0];
          const refresh = pane.querySelector(".osme-walk-refresh");
          await refresh.listeners.get("click")[0]();
          await new Promise((resolve) => setImmediate(resolve));
          const overlay = OrbitSiteMapEditorWalk.overlayState();
          process.stdout.write(JSON.stringify({
            tab: nav.children[0]?.dataset.tab,
            pane: pane.dataset.workspaceTab,
            commands,
            statusKind: statuses.at(-1)?.kind,
            eligible: overlay.siteViewGapWaypointIds,
            planButtonDisabled: pane.querySelector(".osme-walk-plan").disabled,
          }));
        })().catch((error) => {
          console.error(error);
          process.exitCode = 1;
        });
        """
    )
    completed = subprocess.run(
        [node, "-e", script],
        cwd=Path.cwd(),
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {
        "tab": "walk",
        "pane": "walk",
        "commands": ["site_view_snapshot"],
        "statusKind": "ok",
        "eligible": ["a"],
        "planButtonDisabled": False,
    }


def test_editor_bridge_renames_actions_in_one_verified_native_draft() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for JavaScript bridge tests")
    script = textwrap.dedent(
        """
        const mapId = "map-1";
        const waypoint = (id) => ({waypoint: {
          id, annotations: {name: id},
          waypointTformKo: {position: {x: 0, y: 0, z: 0}}
        }});
        const action = (uuid, name, waypointId, futureValue) => ({
          uuid, name, siteMapId: mapId, action: {
            waypointId,
            dataAcquisition: {captureChannel: "thermal", futureValue},
          },
          futureTopLevel: {preserve: futureValue},
        });
        const thermal = action("action-1", "Thermal Inspection - 1", "a", 17);
        const leak = action("action-2", "Acoustic Leak Inspection - 2", "b", 23);
        let dispatchCount = 0;
        const state = {
          mapDisplay: {
            siteMapId: mapId,
            anchoring: {anchors: ["a", "b"].map((id, x) => ({
              id, seedTformWaypoint: {position: {x, y: 0, z: 0}}
            }))},
          },
          siteMaps: {entities: {[mapId]: {
            waypointIds: ["a", "b"], recordingSessionIds: ["r1"],
            metadata: {displayName: "Test"},
          }}},
          siteWaypoints: {
            ids: ["a", "b"], entities: {a: waypoint("a"), b: waypoint("b")},
          },
          siteEdges: {ids: [], entities: {}},
          siteElements: {
            ids: ["action-1", "action-2"],
            entities: {"action-1": thermal, "action-2": leak},
          },
          recordingSessions: {entities: {r1: {
            name: "Run", waypointIds: ["a", "b"],
          }}},
          mapEditor: {
            info: {
              activeTool: "waypoint_selection",
              selectedWaypointIds: ["b", "a"], selectedEdgeIds: [],
              pendingEdgeCreation: {},
            },
            form: {
              present: {index: 0}, past: [], future: [],
              data: {edges: {ids: [], entities: {}, nonEntities: {}}},
            },
          },
          mapMissionsEditor: {form: {
            present: {index: 0}, past: [], future: [],
            data: {actions: {ids: [], entities: {}, nonEntities: {}}},
          }},
        };
        const store = {
          getState: () => state,
          dispatch(event) {
            if (event.type === "missionsAndActionsForm/updateActions") {
              dispatchCount += 1;
              state.mapMissionsEditor.form.past.push({
                index: state.mapMissionsEditor.form.present.index,
              });
              for (const updated of event.payload.updatedActions) {
                const id = updated.uuid;
                state.mapMissionsEditor.form.data.actions.entities[id] =
                  JSON.parse(JSON.stringify(updated));
                if (!state.mapMissionsEditor.form.data.actions.ids.includes(id)) {
                  state.mapMissionsEditor.form.data.actions.ids.push(id);
                }
              }
              state.mapMissionsEditor.form.present.index += 2;
            }
            return event;
          },
        };
        const root = {__reactContainer$test: {memoizedProps: {store}}};
        const messages = [];
        let onMessage;
        global.location = {
          origin: "https://orbit.test",
          pathname: `/control_room/maps/${mapId}/edit`,
        };
        global.document = {getElementById: (id) => id === "root" ? root : null};
        global.window = {
          addEventListener: (type, listener) => {if (type === "message") onMessage = listener;},
          postMessage: (message) => messages.push(message),
          setTimeout,
        };
        require("./extension/orbit-site-map-editor/page-bridge.js");

        async function request(requestId, command, payload = {}) {
          await onMessage({
            source: window,
            origin: location.origin,
            data: {
              channel: "orbit-site-map-editor-v1",
              type: "orbit-site-map-editor-request",
              requestId, command, mapId, ...payload,
            },
          });
          return messages.find((message) => message.requestId === requestId);
        }

        (async () => {
          const before = await request("before", "snapshot");
          const renamed = await request("rename", "rename_actions", {
            actionNameUpdates: [
              {
                id: "action-1", waypointId: "a",
                observedName: "Thermal Inspection - 1",
                desiredName: "SITE1.AREA1/WC02-EQ134-0042-THRM",
              },
              {
                id: "action-2", waypointId: "b",
                observedName: "Acoustic Leak Inspection - 2",
                desiredName: "SITE1.AREA1/WC02-EQ134-0043-LEAK",
              },
            ],
          });
          const after = await request("after", "snapshot");
          const edit = state.mapMissionsEditor.form.data.actions.entities["action-1"];
          const historyBeforeStale = JSON.stringify({
            index: state.mapMissionsEditor.form.present.index,
            undo: state.mapMissionsEditor.form.past.length,
            dispatchCount,
          });
          const stale = await request("stale", "rename_actions", {
            actionNameUpdates: [{
              id: "action-1", waypointId: "a",
              observedName: "Thermal Inspection - 1",
              desiredName: "SITE1-AREA1-WC02-EQ134-0044-THRM",
            }],
          });
          const historyAfterStale = JSON.stringify({
            index: state.mapMissionsEditor.form.present.index,
            undo: state.mapMissionsEditor.form.past.length,
            dispatchCount,
          });
          process.stdout.write(JSON.stringify({
            beforeNames: before.snapshot.actions.map((item) => item.name),
            beforeActionIndex: before.snapshot.actionEditIndex,
            renamed,
            afterNames: after.snapshot.actions.map((item) => item.name).sort(),
            afterActionIndex: after.snapshot.actionEditIndex,
            afterUndoDepth: after.snapshot.actionHistory.undoDepth,
            preservedNested: edit.action.dataAcquisition.futureValue,
            preservedTopLevel: edit.futureTopLevel.preserve,
            staleError: stale.error,
            staleStateUnchanged: historyBeforeStale === historyAfterStale,
            dispatchCount,
          }));
        })().catch((error) => {
          console.error(error);
          process.exitCode = 1;
        });
        """
    )
    completed = subprocess.run(
        [node, "-e", script],
        cwd=Path.cwd(),
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert result["beforeNames"] == [
        "Thermal Inspection - 1",
        "Acoustic Leak Inspection - 2",
    ]
    assert result["beforeActionIndex"] == 0
    assert result["renamed"]["ok"] is True
    assert result["renamed"]["updatedCount"] == 2
    assert result["renamed"]["draftIndexDelta"] == 2
    assert result["afterNames"] == [
        "SITE1.AREA1/WC02-EQ134-0042-THRM",
        "SITE1.AREA1/WC02-EQ134-0043-LEAK",
    ]
    assert result["afterActionIndex"] == 2
    assert result["afterUndoDepth"] == 1
    assert result["preservedNested"] == 17
    assert result["preservedTopLevel"] == 17
    assert result["staleError"] == "action_name_changed"
    assert result["staleStateUnchanged"] is True
    assert result["dispatchCount"] == 1
