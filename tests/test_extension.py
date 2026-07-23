import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

EXTENSION = Path("extension/orbit-graph-repair")


def test_orbit_graph_repair_extension_manifest_is_minimal() -> None:
    manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["manifest_version"] == 3
    assert manifest["version"] == "0.8.1"
    assert manifest["permissions"] == ["storage", "unlimitedStorage"]
    assert "host_permissions" not in manifest
    assert "background" not in manifest
    assert "unlimitedStorage" in manifest["permissions"]
    assert manifest["content_scripts"] == [
        {
            "matches": ["https://*/control_room/maps/*/edit*"],
            "css": ["panel.css"],
            "js": ["baseline.js", "content.js"],
            "run_at": "document_idle",
        }
    ]
    assert manifest["web_accessible_resources"] == [
        {
            "resources": ["page-bridge.js"],
            "matches": ["https://*/*"],
        }
    ]


def test_orbit_graph_repair_extension_uses_only_native_unsaved_edit_actions() -> None:
    script = "\n".join(
        (EXTENSION / name).read_text(encoding="utf-8") for name in ("baseline.js", "content.js")
    )

    for forbidden in (
        "fetch(",
        "XMLHttpRequest",
        "WebSocket",
        "chrome.tabs",
        "chrome.scripting",
        "/api/",
    ):
        assert forbidden not in script
    assert 'value.kind !== "orbit_graph_reconciliation_guide"' in script
    assert "currentMapId() === state.guide.after_site_map.id" in script

    bridge = (EXTENSION / "page-bridge.js").read_text(encoding="utf-8")
    assert 'const FOCUS_ACTION_TYPE = "mapDisplay/updateNeedsZoomToWaypoints"' in bridge
    assert (
        'const SELECT_WAYPOINTS_ACTION_TYPE = "mapEditorInfoSlice/setSelectedWaypoints"'
    ) in bridge
    assert ('const ADD_SITE_EDGE_ACTION_TYPE = "mapEditorFormSlice/addSiteEdge"') in bridge
    assert (
        'const ARCHIVE_SITE_EDGES_ACTION_TYPE = "mapEditorFormSlice/archiveSiteEdges"'
    ) in bridge
    assert ('const UPDATE_SITE_EDGES_ACTION_TYPE = "mapEditorFormSlice/updateSiteEdges"') in bridge
    assert 'const SELECT_EDGES_ACTION_TYPE = "mapEditorInfoSlice/setSelectedEdges"' in bridge
    assert "store.dispatch({ type: FOCUS_ACTION_TYPE, payload: waypointIds })" in bridge
    assert "type: SELECT_WAYPOINTS_ACTION_TYPE, payload: waypointIds" in bridge
    assert "type: ADD_SITE_EDGE_ACTION_TYPE" in bridge
    assert "type: ARCHIVE_SITE_EDGES_ACTION_TYPE, payload: activeEdges" in bridge
    assert "type: SELECT_EDGES_ACTION_TYPE, payload: keys" in bridge
    assert bridge.count("store.dispatch(") == 9
    for forbidden in (
        "fetch(",
        "XMLHttpRequest",
        "WebSocket",
        "/api/",
        "saveMapEdit",
        "saveMapEditComplete",
    ):
        assert forbidden not in bridge


def test_orbit_map_assistant_inspector_is_read_only_and_selection_bounded() -> None:
    content = (EXTENSION / "content.js").read_text(encoding="utf-8")
    bridge = (EXTENSION / "page-bridge.js").read_text(encoding="utf-8")

    assert 'command: "inspect"' in content
    assert "renderInspector" in content
    assert "crossRecordingManualEdges" in content
    assert "WAYPOINT_ADVISORY_LIMIT = 3000" in content

    for command in (
        '"resolve"',
        '"focus"',
        '"inspect"',
        '"snapshot"',
        '"connect"',
        '"archive"',
        '"archive_many"',
        '"update_settings_many"',
    ):
        assert command in bridge
    assert 'adapter: "orbit-5.1-readonly-map-inspector"' in bridge
    assert 'adapter: "orbit-5.1-readonly-graph-snapshot"' in bridge
    assert ".slice(0, 20)" in bridge
    for field in (
        "recordingSessionIds",
        "selectedWaypointIds",
        "selectedEdgeIds",
        "edgeSource",
        "crossRecording",
        "mapPosition",
        "neighbors",
    ):
        assert field in bridge
    assert "Copy neighbor IDs" in content
    assert "Crosswalk" in content
    assert "areaCallbacks" in bridge


def test_connect_button_fails_closed_before_adding_an_orbit_edge_draft() -> None:
    content = (EXTENSION / "content.js").read_text(encoding="utf-8")
    bridge = (EXTENSION / "page-bridge.js").read_text(encoding="utf-8")

    assert "connect.textContent = state.connectingIndex === action.index" in content
    assert 'requestBridge("connect", action)' in content
    assert "state.done.add(action.index)" in content
    assert "if (!response.added)" in content

    for guard in (
        "map_or_waypoint_mismatch",
        "edge_already_exists",
        "edge_validation_failed",
        "edge_validation_warning",
        "edge_validation_timeout",
        "orbit_map_changed",
        "orbit_selection_changed",
        "edge_draft_not_created",
    ):
        assert guard in bridge
        assert guard in content
    assert "effectiveEdgeEntity(initialState, waypointIds)" in bridge
    assert "candidate?.siteMapId === mapId" in bridge
    assert "afterIndex !== beforeIndex + 1" in bridge
    assert 'adapter: "orbit-5.1-native-edge-draft"' in bridge


def test_archive_button_requires_confirmation_and_verifies_native_tombstone() -> None:
    content = (EXTENSION / "content.js").read_text(encoding="utf-8")
    bridge = (EXTENSION / "page-bridge.js").read_text(encoding="utf-8")

    assert "archive.textContent = state.archivingIndex === action.index" in content
    assert '"Archive in Orbit"' in content
    assert "window.confirm(" in content
    assert "may alter recording orientation" in content
    assert 'requestBridge("archive", action)' in content
    assert "if (!response.archived)" in content

    for guard in (
        "map_or_waypoint_mismatch",
        "edge_not_found",
        "edge_already_archived",
        "orbit_selection_changed",
        "edge_archive_not_created",
    ):
        assert guard in bridge
        assert guard in content
    assert "edges?.nonEntities?.[key]" in bridge
    assert "payload: EDGE_SELECTION_TOOL" in bridge
    assert "payload: keys" in bridge
    assert "payload: activeEdges" in bridge
    assert "afterIndex !== beforeIndex + 1" in bridge
    assert 'adapter: "orbit-5.1-native-edge-archive-draft"' in bridge


def test_bulk_archive_uses_one_native_multiselect_and_one_history_step() -> None:
    content = (EXTENSION / "content.js").read_text(encoding="utf-8")
    bridge = (EXTENSION / "page-bridge.js").read_text(encoding="utf-8")

    assert "Archive all pending edges" in content
    assert "Site Map Assistant" in content
    assert "Delete in Orbit" not in content
    assert "pending DELETE" not in content
    assert "pendingArchiveActions" in content
    assert 'command: "archive_many"' in content
    assert "waypointPairs: actions.map" in content
    assert "response.archivedCount !== actions.length" in content
    assert "for (const action of actions) state.done.add(action.index)" in content

    assert "MAX_ARCHIVE_BATCH_SIZE = 5000" in bridge
    assert "function archiveWaypointPairs" in bridge
    assert "duplicate_edge_pair" in bridge
    assert "payload: keys" in bridge
    assert "payload: activeEdges" in bridge
    assert "keys.some((key, index)" in bridge
    assert "afterIndex !== beforeIndex + 1" in bridge
    assert 'adapter: "orbit-5.1-native-edge-batch-archive-draft"' in bridge


def test_edge_settings_restore_uses_native_update_and_one_history_step() -> None:
    content = (EXTENSION / "content.js").read_text(encoding="utf-8")
    bridge = (EXTENSION / "page-bridge.js").read_text(encoding="utf-8")
    baseline = (EXTENSION / "baseline.js").read_text(encoding="utf-8")

    assert "Restore settings in Orbit" in content
    assert "Restore pending crosswalk settings" in content
    assert "Restore all pending edge settings" in content
    assert 'command: "update_settings_many"' in content
    assert "observedSettings: action.observed_settings" in content
    assert "desiredSettings: action.desired_settings" in content

    assert "type: UPDATE_SITE_EDGES_ACTION_TYPE" in bridge
    assert "payload: { updatedEdges, originalEdgesById }" in bridge
    assert "edge_direction_mismatch" in bridge
    assert "edge_settings_changed" in bridge
    assert "afterIndex !== beforeIndex + 1" in bridge
    assert 'adapter: "orbit-5.1-native-edge-settings-batch-draft"' in bridge

    assert "edge_settings_mismatch" in baseline
    assert "settingsCategories" in baseline
    assert "crosswalk_update_edges" in baseline
    assert "private SiteEdge wrapper fields" in baseline


def test_deleted_edge_overview_is_read_only_durable_and_compound() -> None:
    baseline = (EXTENSION / "baseline.js").read_text(encoding="utf-8")
    content = (EXTENSION / "content.js").read_text(encoding="utf-8")

    assert "function buildDeletedEdgeOverlay" in baseline
    assert "missing_position_edges" in baseline
    assert "buildDeletedEdgeOverlay," in baseline

    assert "state.deleteOverlay = baselineTools().buildDeletedEdgeOverlay(" in content
    assert "Show edges pending Archive" in content
    assert '"B0 archived edges"' in content
    assert "state.showAllDeleteEdges" in content
    assert 'class: "ogr-delete-overview"' in content
    assert 'const pathData = segments.join(" ")' in content
    assert content.count('svgElement("path"') == 2
    assert content.index("if (state.showAllDeleteEdges)") < content.index(
        "const action = selectedAction();", content.index("function drawOverlay()")
    )
    assert "missingDeletePositions" in content


def test_native_connect_bridge_validates_adds_and_blocks_duplicates() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is unavailable for the extension bridge test")
    script = textwrap.dedent(
        """
        const mapId = 'map-1';
        const edgeKey = (a, b) => a < b ? `${a}|${b}` : `${b}|${a}`;
        const state = {
          mapDisplay: {siteMapId: mapId, anchoring: {anchors: []}},
          siteMaps: {entities: {[mapId]: {waypointIds: ['a', 'b', 'c', 'd']}}},
          siteWaypoints: {entities: {}, ids: []},
          siteEdges: {entities: {}, ids: []},
          recordingSessions: {entities: {}},
          mapEditor: {
            info: {
              selectedWaypointIds: [], selectedEdgeIds: [],
              pendingEdgeCreation: {errors: [], warnings: [], validating: false},
            },
            form: {present: {index: 0}, data: {edges: {entities: {}, ids: []}}},
          },
        };
        const dispatched = [];
        const store = {
          getState: () => state,
          dispatch(action) {
            dispatched.push(action.type);
            if (action.type === 'mapEditorInfoSlice/setSelectedWaypoints') {
              state.mapEditor.info.selectedWaypointIds = [...action.payload];
              state.mapEditor.info.pendingEdgeCreation = {
                errors: [], warnings: [], validating: true,
              };
              setTimeout(() => {
                const [fromWaypoint, toWaypoint] = [...action.payload].sort();
                state.mapEditor.info.pendingEdgeCreation = {
                  errors: [],
                  warnings: action.payload.includes('c') ? [{testWarning: true}] : [],
                  validating: false,
                  showModal: false,
                  createdEdgeCandidate: {
                    siteMapId: mapId,
                    archived: false,
                    disabled: false,
                    edge: {id: {fromWaypoint, toWaypoint}, annotations: {edgeSource: 5}},
                  },
                };
              }, 5);
            }
            if (action.type === 'mapEditorFormSlice/addSiteEdge') {
              const {fromWaypoint, toWaypoint} = action.payload.edge.id;
              const key = edgeKey(fromWaypoint, toWaypoint);
              state.mapEditor.form.data.edges.entities[key] = action.payload;
              state.mapEditor.form.data.edges.ids.push(key);
              state.mapEditor.form.present.index += 1;
            }
            return action;
          },
        };
        const root = {__reactContainer$test: {memoizedProps: {store}}};
        const messages = [];
        let onMessage;
        global.location = {
          origin: 'https://orbit.test',
          pathname: `/control_room/maps/${mapId}/edit`,
        };
        global.document = {getElementById: (id) => id === 'root' ? root : null};
        global.window = {
          addEventListener: (type, listener) => { if (type === 'message') onMessage = listener; },
          postMessage: (message) => messages.push(message),
          setTimeout,
        };
        require('./extension/orbit-graph-repair/page-bridge.js');

        async function request(requestId, waypointIds) {
          await onMessage({
            source: window,
            origin: location.origin,
            data: {
              channel: 'orbit-graph-repair-v1',
              type: 'orbit-graph-repair-request',
              requestId,
              command: 'connect',
              mapId,
              waypointIds,
            },
          });
          return messages.find((message) => message.requestId === requestId);
        }

        (async () => {
          const added = await request('add', ['b', 'a']);
          if (!added?.ok || !added.added || added.editIndex !== 1) {
            throw new Error(`edge was not added: ${JSON.stringify(added)}`);
          }
          if (added.edgeKey !== 'a|b') throw new Error('edge key was not canonical');
          if (dispatched.join(',') !== [
            'mapEditorInfoSlice/setSelectedWaypoints',
            'mapEditorFormSlice/addSiteEdge',
          ].join(',')) throw new Error(`unexpected dispatches: ${dispatched}`);

          const duplicate = await request('duplicate', ['a', 'b']);
          if (duplicate?.ok || duplicate?.error !== 'edge_already_exists') {
            throw new Error(`duplicate was not blocked: ${JSON.stringify(duplicate)}`);
          }
          if (state.mapEditor.form.present.index !== 1) {
            throw new Error('duplicate changed history');
          }

          const warned = await request('warning', ['c', 'd']);
          if (warned?.ok || warned?.error !== 'edge_validation_warning') {
            throw new Error(`warning did not fail closed: ${JSON.stringify(warned)}`);
          }
          if (state.mapEditor.form.present.index !== 1) throw new Error('warning changed history');
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
        capture_output=True,
        text=True,
    )


def test_native_archive_bridge_multiselects_edges_in_one_history_step() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is unavailable for the extension bridge test")
    script = textwrap.dedent(
        """
        const mapId = 'map-1';
        const edgeKey = (a, b) => a < b ? `${a}|${b}` : `${b}|${a}`;
        const raw = (fromWaypoint, toWaypoint) => ({
          siteMapId: mapId, archived: false, disabled: false,
          edge: {
            id: {fromWaypoint, toWaypoint},
            annotations: {edgeSource: 1},
          },
        });
        const keyAB = edgeKey('a', 'b');
        const keyCD = edgeKey('c', 'd');
        const waypoint = (id) => ({waypoint: {id, annotations: {name: id}}});
        const state = {
          mapDisplay: {siteMapId: mapId, anchoring: {anchors: []}},
          siteMaps: {entities: {[mapId]: {
            waypointIds: ['a', 'b', 'c', 'd'], recordingSessionIds: [], metadata: {id: mapId},
          }}},
          siteWaypoints: {
            entities: {a: waypoint('a'), b: waypoint('b'), c: waypoint('c'), d: waypoint('d')},
            ids: ['a', 'b', 'c', 'd'],
          },
          siteEdges: {
            entities: {[keyAB]: raw('b', 'a'), [keyCD]: raw('c', 'd')},
            ids: [keyAB, keyCD],
          },
          recordingSessions: {entities: {}},
          mapEditor: {
            info: {
              activeTool: 'waypoint_selection', selectedWaypointIds: [], selectedEdgeIds: [],
              pendingEdgeCreation: {errors: [], warnings: [], validating: false},
            },
            form: {present: {index: 4}, data: {edges: {
              entities: {}, nonEntities: {}, ids: [],
            }}},
          },
        };
        const dispatched = [];
        const store = {
          getState: () => state,
          dispatch(action) {
            dispatched.push({type: action.type, payload: action.payload});
            if (action.type === 'mapEditorInfoSlice/activateTool') {
              state.mapEditor.info.activeTool = action.payload;
            }
            if (action.type === 'mapEditorInfoSlice/setSelectedEdges') {
              state.mapEditor.info.selectedEdgeIds = [...action.payload];
            }
            if (action.type === 'mapEditorFormSlice/archiveSiteEdges') {
              for (const entity of action.payload) {
                const id = edgeKey(entity.edge.id.fromWaypoint, entity.edge.id.toWaypoint);
                state.mapEditor.form.data.edges.nonEntities[id] = {
                  ...entity, archived: true,
                };
              }
              state.mapEditor.form.present.index += 1;
            }
            return action;
          },
        };
        const root = {__reactContainer$test: {memoizedProps: {store}}};
        const messages = [];
        let onMessage;
        global.location = {
          origin: 'https://orbit.test',
          pathname: `/control_room/maps/${mapId}/edit`,
        };
        global.document = {getElementById: (id) => id === 'root' ? root : null};
        global.window = {
          addEventListener: (type, listener) => { if (type === 'message') onMessage = listener; },
          postMessage: (message) => messages.push(message),
          setTimeout,
        };
        require('./extension/orbit-graph-repair/page-bridge.js');

        async function request(requestId, command, waypointIds, waypointPairs) {
          await onMessage({
            source: window,
            origin: location.origin,
            data: {
              channel: 'orbit-graph-repair-v1',
              type: 'orbit-graph-repair-request',
              requestId, command, mapId, waypointIds, waypointPairs,
            },
          });
          return messages.find((message) => message.requestId === requestId);
        }

        (async () => {
          const rejected = await request(
            'duplicate-batch',
            'archive_many',
            undefined,
            [['a', 'b'], ['b', 'a']],
          );
          if (rejected?.ok || rejected?.error !== 'duplicate_edge_pair') {
            throw new Error(`duplicate batch was not rejected: ${JSON.stringify(rejected)}`);
          }
          if (dispatched.length !== 0 || state.mapEditor.form.present.index !== 4) {
            throw new Error('rejected batch changed the Orbit editor');
          }

          const archived = await request(
            'archive-many',
            'archive_many',
            undefined,
            [['a', 'b'], ['d', 'c']],
          );
          if (
            !archived?.ok ||
            !archived.archived ||
            archived.archivedCount !== 2 ||
            archived.editIndex !== 5
          ) {
            throw new Error(`edges were not archived: ${JSON.stringify(archived)}`);
          }
          if (
            !state.mapEditor.form.data.edges.nonEntities[keyAB]?.archived ||
            !state.mapEditor.form.data.edges.nonEntities[keyCD]?.archived
          ) {
            throw new Error('archive tombstones are missing');
          }
          const expectedTypes = [
            'mapEditorInfoSlice/activateTool',
            'mapEditorInfoSlice/setSelectedEdges',
            'mapEditorFormSlice/archiveSiteEdges',
            'mapEditorInfoSlice/setSelectedEdges',
          ];
          if (dispatched.map((row) => row.type).join(',') !== expectedTypes.join(',')) {
            throw new Error(`unexpected dispatches: ${JSON.stringify(dispatched)}`);
          }
          if (state.mapEditor.info.activeTool !== 'edge_selection') {
            throw new Error('edge selection mode was not activated');
          }
          if (state.mapEditor.info.selectedEdgeIds.length !== 0) {
            throw new Error('edge selection was not cleared');
          }
          if (
            dispatched[1].payload.length !== 2 ||
            dispatched[2].payload.length !== 2
          ) {
            throw new Error(
              `native multi-selection was not preserved: ${JSON.stringify(dispatched)}`,
            );
          }

          const duplicate = await request('duplicate', 'archive', ['b', 'a']);
          if (duplicate?.ok || duplicate?.error !== 'edge_already_archived') {
            throw new Error(`duplicate archive was not blocked: ${JSON.stringify(duplicate)}`);
          }
          const missing = await request('missing', 'archive', ['a', 'c']);
          if (missing?.ok || missing?.error !== 'edge_not_found') {
            throw new Error(`missing edge was not blocked: ${JSON.stringify(missing)}`);
          }

          const snapshot = await request('snapshot', 'snapshot');
          if (!snapshot?.ok || snapshot.snapshot.edges.length !== 0) {
            throw new Error(`tombstone was not applied to snapshot: ${JSON.stringify(snapshot)}`);
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
        capture_output=True,
        text=True,
    )


def test_native_settings_bridge_updates_exact_edges_and_rejects_stale_state() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is unavailable for the extension bridge test")
    script = textwrap.dedent(
        """
        const mapId = 'map-1';
        const edgeKey = (a, b) => a < b ? `${a}|${b}` : `${b}|${a}`;
        const keyAB = edgeKey('a', 'b');
        const keyCD = edgeKey('c', 'd');
        const siteEdge = (fromWaypoint, toWaypoint, annotations) => ({
          siteMapId: mapId, archived: false, disabled: false,
          edge: {id: {fromWaypoint, toWaypoint}, annotations},
        });
        const originalAB = siteEdge('a', 'b', {
          edgeSource: 1, pathFollowingMode: 1,
        });
        const originalCD = siteEdge('c', 'd', {
          edgeSource: 1, pathFollowingMode: 2,
        });
        const state = {
          mapDisplay: {siteMapId: mapId, anchoring: {anchors: []}},
          siteMaps: {entities: {[mapId]: {
            waypointIds: ['a', 'b', 'c', 'd'], recordingSessionIds: [], metadata: {id: mapId},
          }}},
          siteWaypoints: {entities: {}, ids: []},
          siteEdges: {
            entities: {[keyAB]: originalAB, [keyCD]: originalCD},
            ids: [keyAB, keyCD],
          },
          recordingSessions: {entities: {}},
          mapEditor: {
            info: {selectedWaypointIds: [], selectedEdgeIds: []},
            form: {present: {index: 8}, data: {edges: {
              entities: {}, nonEntities: {}, ids: [],
            }}},
          },
        };
        const dispatched = [];
        const store = {
          getState: () => state,
          dispatch(action) {
            dispatched.push(action);
            if (action.type === 'mapEditorFormSlice/updateSiteEdges') {
              for (const updated of action.payload.updatedEdges) {
                const key = edgeKey(
                  updated.edge.id.fromWaypoint,
                  updated.edge.id.toWaypoint,
                );
                state.mapEditor.form.data.edges.entities[key] = updated;
                if (!state.mapEditor.form.data.edges.ids.includes(key)) {
                  state.mapEditor.form.data.edges.ids.push(key);
                }
              }
              state.mapEditor.form.present.index += 1;
            }
            return action;
          },
        };
        const root = {__reactContainer$test: {memoizedProps: {store}}};
        const messages = [];
        let onMessage;
        global.location = {
          origin: 'https://orbit.test',
          pathname: `/control_room/maps/${mapId}/edit`,
        };
        global.document = {getElementById: (id) => id === 'root' ? root : null};
        global.window = {
          addEventListener: (type, listener) => { if (type === 'message') onMessage = listener; },
          postMessage: (message) => messages.push(message),
          setTimeout,
        };
        require('./extension/orbit-graph-repair/page-bridge.js');

        async function request(requestId, settingsUpdates) {
          await onMessage({
            source: window,
            origin: location.origin,
            data: {
              channel: 'orbit-graph-repair-v1',
              type: 'orbit-graph-repair-request',
              requestId,
              command: 'update_settings_many',
              mapId,
              settingsUpdates,
            },
          });
          return messages.find((message) => message.requestId === requestId);
        }

        const update = ({
          waypointIds: ['a', 'b'],
          storedFrom: 'a',
          storedTo: 'b',
          observedSourceValue: 1,
          observedSettings: {pathFollowingMode: 1},
          desiredSettings: {
            areaCallbacks: {
              region: {serviceName: 'spot-crosswalk', description: 'crosswalk007'},
            },
            disableAlternateRouteFinding: true,
            pathFollowingMode: 1,
          },
        });

        (async () => {
          const restored = await request('restore', [update]);
          if (
            !restored?.ok ||
            !restored.updated ||
            restored.updatedCount !== 1 ||
            restored.editIndex !== 9
          ) {
            throw new Error(`settings were not restored: ${JSON.stringify(restored)}`);
          }
          if (
            dispatched.length !== 1 ||
            dispatched[0].type !== 'mapEditorFormSlice/updateSiteEdges' ||
            dispatched[0].payload.updatedEdges.length !== 1 ||
            dispatched[0].payload.originalEdgesById[keyAB] !== originalAB
          ) {
            throw new Error(`native update payload was wrong: ${JSON.stringify(dispatched)}`);
          }
          const edited = state.mapEditor.form.data.edges.entities[keyAB];
          if (
            edited.edge.annotations.edgeSource !== 1 ||
            edited.edge.annotations.areaCallbacks.region.serviceName !== 'spot-crosswalk' ||
            edited.edge.annotations.disableAlternateRouteFinding !== true
          ) {
            throw new Error(`restored settings are wrong: ${JSON.stringify(edited)}`);
          }

          const stale = await request('stale', [{
            ...update,
            waypointIds: ['c', 'd'],
            storedFrom: 'c',
            storedTo: 'd',
            observedSettings: {pathFollowingMode: 1},
          }]);
          if (stale?.ok || stale?.error !== 'edge_settings_changed') {
            throw new Error(`stale settings were not rejected: ${JSON.stringify(stale)}`);
          }
          if (state.mapEditor.form.present.index !== 9 || dispatched.length !== 1) {
            throw new Error('stale request changed Orbit edit history');
          }

          const reversed = await request('reversed', [{
            ...update,
            waypointIds: ['b', 'a'],
            storedFrom: 'b',
            storedTo: 'a',
            observedSettings: {
              areaCallbacks: {
                region: {serviceName: 'spot-crosswalk', description: 'crosswalk007'},
              },
              disableAlternateRouteFinding: true,
              pathFollowingMode: 1,
            },
          }]);
          if (reversed?.ok || reversed?.error !== 'edge_direction_mismatch') {
            throw new Error(`reversed edge was not rejected: ${JSON.stringify(reversed)}`);
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
        capture_output=True,
        text=True,
    )


def test_live_baseline_comparison_is_exact_id_based_and_scopes_extra_recordings() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is unavailable for the extension logic test")
    script = textwrap.dedent(
        """
        require('./extension/orbit-graph-repair/baseline.js');
        const tools = globalThis.OrbitGraphBaseline;
        const baseline = {
          kind: 'orbit_graph_baseline_inventory',
          site_map: {id: 'original-map', name: 'B0'},
          waypoint_ids: ['a', 'b', 'c'],
          effective_edges: [
            {from: 'a', to: 'b', edge_source: 'EDGE_SOURCE_USER_REQUEST', provenance: 'site_only'},
            {from: 'b', to: 'c', edge_source: 'EDGE_SOURCE_ODOMETRY', provenance: 'raw_fallback'},
          ],
          tombstones: [{from: 'a', to: 'c', edge_source: 'EDGE_SOURCE_ODOMETRY'}],
        };
        const waypoint = (id) => ({
          id, name: id.toUpperCase(), recordingId: `r-${id}`, recordingName: `R ${id}`,
          position: {x: id.charCodeAt(0), y: 1, z: 0},
        });
        const snapshot = {
          kind: 'orbit_live_graph_snapshot', map: {id: 'split-map', name: 'Split'},
          recordingCount: 3, waypoints: ['a', 'b', 'c'].map(waypoint),
          edges: [
            {from: 'b', to: 'c', source: 'odometry'},
            {from: 'a', to: 'c', source: 'odometry'},
          ],
        };
        const guide = tools.buildGuide(baseline, snapshot);
        if (guide.after_site_map.id !== 'split-map') throw new Error('wrong current map');
        if (guide.actions.length !== 2) throw new Error('wrong action count');
        if (guide.actions[0].reason !== 'missing_manual_edge') throw new Error('manual edge lost');
        if (guide.actions[1].reason !== 'resurrected_deleted_edge') {
          throw new Error('tombstone lost');
        }

        const partition = tools.buildGuide(baseline, {
          ...snapshot, recordingCount: 2, waypoints: ['a', 'b'].map(waypoint),
          edges: [{from: 'a', to: 'b', source: 'manual'}],
        });
        if (partition.actions.length !== 0) throw new Error('boundary edge became an action');
        if (partition.intentional_cuts.length !== 1) throw new Error('boundary cut missing');

        const reconciledSnapshot = {
          ...snapshot,
          edges: [
            {from: 'a', to: 'b', source: 'manual'},
            {from: 'b', to: 'c', source: 'odometry'},
          ],
        };
        const reconciled = tools.buildGuide(baseline, reconciledSnapshot);
        if (!reconciled.graph_reconciled || reconciled.actions.length !== 0) {
          throw new Error('reconciled guide is not empty');
        }
        const settingsBaseline = {
          ...baseline,
          effective_edges: [
            {
              from: 'a', to: 'b', edge_source: 'EDGE_SOURCE_USER_REQUEST',
              provenance: 'site_only', has_crosswalk: true,
              settings: {
                areaCallbacks: {
                  region: {serviceName: 'spot-crosswalk', description: 'crosswalk007'},
                },
                disableAlternateRouteFinding: true,
              },
            },
            baseline.effective_edges[1],
          ],
        };
        const settingsGuide = tools.buildGuide(settingsBaseline, {
          ...reconciledSnapshot,
          edges: [
            {
              from: 'a', to: 'b', source: 'manual', sourceValue: 5,
              settings: {disableAlternateRouteFinding: false},
            },
            {from: 'b', to: 'c', source: 'odometry'},
          ],
        });
        const settingsAction = settingsGuide.actions.find(
          (action) => action.operation === 'update'
        );
        if (
          !settingsGuide.graph_reconciled ||
          settingsGuide.settings_reconciled ||
          settingsGuide.fully_reconciled ||
          settingsGuide.counts.update_edges !== 1 ||
          settingsGuide.counts.crosswalk_update_edges !== 1 ||
          !settingsAction?.crosswalk ||
          !settingsAction.settings_categories.includes('crosswalk') ||
          settingsAction.observed_source_value !== 5 ||
          settingsAction.stored_direction_matches !== true
        ) {
          throw new Error(`settings diff was not preserved: ${JSON.stringify(settingsGuide)}`);
        }
        const reversedSettings = tools.buildGuide(settingsBaseline, {
          ...reconciledSnapshot,
          edges: [
            {
              from: 'b', to: 'a', source: 'manual', sourceValue: 5,
              settings: {disableAlternateRouteFinding: false},
            },
            {from: 'b', to: 'c', source: 'odometry'},
          ],
        });
        if (
          reversedSettings.counts.direction_blocked_update_edges !== 1 ||
          reversedSettings.actions.find((action) => action.operation === 'update')
            ?.stored_direction_matches !== false
        ) {
          throw new Error('reversed stored direction did not fail closed');
        }
        const overlay = tools.buildDeletedEdgeOverlay(baseline, reconciledSnapshot);
        if (
          overlay.kind !== 'orbit_deleted_edge_overlay' ||
          overlay.edges.length !== 1 ||
          overlay.edges[0].from !== 'a' ||
          overlay.edges[0].to !== 'c' ||
          overlay.counts.internal_edges !== 1 ||
          overlay.counts.missing_position_edges !== 0
        ) {
          throw new Error(`reconciled tombstone overlay was lost: ${JSON.stringify(overlay)}`);
        }

        const partitionOverlay = tools.buildDeletedEdgeOverlay(baseline, {
          ...reconciledSnapshot,
          recordingCount: 2,
          waypoints: ['a', 'b'].map(waypoint),
          edges: [{from: 'a', to: 'b', source: 'manual'}],
        });
        if (
          partitionOverlay.edges.length !== 0 ||
          partitionOverlay.counts.boundary_edges !== 1
        ) {
          throw new Error(
            `partition tombstone was not a boundary: ${JSON.stringify(partitionOverlay)}`,
          );
        }

        const outsideOverlay = tools.buildDeletedEdgeOverlay(baseline, {
          ...reconciledSnapshot,
          recordingCount: 1,
          waypoints: ['b'].map(waypoint),
          edges: [],
        });
        if (
          outsideOverlay.edges.length !== 0 ||
          outsideOverlay.counts.excluded_outside_edges !== 1
        ) {
          throw new Error(`outside tombstone was not excluded: ${JSON.stringify(outsideOverlay)}`);
        }

        const missingPositionOverlay = tools.buildDeletedEdgeOverlay(baseline, {
          ...reconciledSnapshot,
          waypoints: reconciledSnapshot.waypoints.map((row) =>
            row.id === 'c' ? {...row, position: null} : row
          ),
        });
        if (
          missingPositionOverlay.edges.length !== 0 ||
          missingPositionOverlay.counts.internal_edges !== 1 ||
          missingPositionOverlay.counts.missing_position_edges !== 1
        ) {
          throw new Error(`missing anchor was hidden: ${JSON.stringify(missingPositionOverlay)}`);
        }

        const extraScope = tools.buildGuide(baseline, {
          ...snapshot,
          waypoints: [...snapshot.waypoints, waypoint('x')],
          edges: [...snapshot.edges, {from: 'a', to: 'x', source: 'manual'}],
        });
        if (
          extraScope.actions.length !== guide.actions.length ||
          extraScope.counts.ignored_extra_waypoints !== 1 ||
          extraScope.counts.ignored_extra_edges !== 1 ||
          extraScope.counts.observed_edges !== 2 ||
          extraScope.counts.observed_edges_total !== 3
        ) {
          throw new Error(`extra recording scope was not ignored: ${JSON.stringify(extraScope)}`);
        }
        """
    )
    subprocess.run(
        [node, "-e", script],
        cwd=Path.cwd(),
        check=True,
        capture_output=True,
        text=True,
    )
