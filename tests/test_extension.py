import json
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.chrome_version import validate_chrome_version  # noqa: E402

EXTENSION = ROOT / "extension" / "orbit-graph-repair"


def test_orbit_graph_repair_extension_manifest_is_minimal() -> None:
    manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["manifest_version"] == 3
    assert validate_chrome_version(manifest["version"]) == manifest["version"]
    assert "version_name" not in manifest
    assert manifest["permissions"] == ["storage", "unlimitedStorage"]
    assert "host_permissions" not in manifest
    assert "background" not in manifest
    assert len(manifest["content_scripts"]) == 1
    content_script = manifest["content_scripts"][0]
    assert content_script["matches"] == ["https://*/control_room/maps/*/edit*"]
    assert content_script["run_at"] == "document_idle"
    assert len(content_script["css"]) == len(set(content_script["css"]))
    assert len(content_script["js"]) == len(set(content_script["js"]))
    assert content_script["js"].index("baseline.js") < content_script["js"].index("content.js")

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


def test_orbit_graph_repair_extension_has_no_direct_write_or_network_sink() -> None:
    sources = [path.read_text(encoding="utf-8") for path in sorted(EXTENSION.glob("*.js"))]

    for source in sources:
        for forbidden in (
            "fetch(",
            "XMLHttpRequest",
            "WebSocket",
            "chrome.tabs",
            "chrome.scripting",
            "/api/",
            "saveMapEdit",
            "saveMapEditComplete",
        ):
            assert forbidden not in source


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
          siteMaps: {entities: {[mapId]: {waypointIds: ['a', 'b', 'c', 'd', 'e', 'f']}}},
          siteWaypoints: {entities: {}, ids: []},
          siteEdges: {entities: {}, ids: []},
          recordingSessions: {entities: {}},
          mapEditor: {
            info: {
              selectedWaypointIds: [], selectedEdgeIds: [],
              pendingEdgeCreation: {errors: [], warnings: [], validating: false},
            },
            form: {present: {index: 0}, past: [], data: {edges: {entities: {}, ids: []}}},
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
                if (action.payload.includes('e')) {
                  state.mapEditor.form.past.push({
                    index: state.mapEditor.form.present.index,
                  });
                  state.mapEditor.form.present.index += 1;
                }
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
              state.mapEditor.form.present.index += 3;
              state.mapEditor.form.past.push({index: 0});
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
          if (
            !added?.ok ||
            !added.added ||
            added.editIndex !== 3 ||
            added.undoDepth !== 1 ||
            added.draftIndexDelta !== 3
          ) {
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
          if (state.mapEditor.form.present.index !== 3) {
            throw new Error('duplicate changed history');
          }

          const warned = await request('warning', ['c', 'd']);
          if (warned?.ok || warned?.error !== 'edge_validation_warning') {
            throw new Error(`warning did not fail closed: ${JSON.stringify(warned)}`);
          }
          if (state.mapEditor.form.present.index !== 3) throw new Error('warning changed history');

          const changed = await request('validation-history-change', ['e', 'f']);
          if (
            changed?.ok ||
            changed?.error !== 'validation_changed_draft' ||
            changed?.mutationMayExist !== true ||
            changed?.beforeEditIndex !== 3 ||
            changed?.afterEditIndex !== 4 ||
            changed?.beforeUndoDepth !== 1 ||
            changed?.afterUndoDepth !== 2
          ) {
            throw new Error(
              `validation history change was not detected: ${JSON.stringify(changed)}`,
            );
          }
          if (
            dispatched.filter(
              (type) => type === 'mapEditorFormSlice/addSiteEdge'
            ).length !== 1
          ) throw new Error('validation history change dispatched another edge');
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
            form: {present: {index: 4}, past: [{}, {}, {}, {}], data: {edges: {
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
              state.mapEditor.form.present.index += 2;
              state.mapEditor.form.past.push({index: 4});
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
            archived.editIndex !== 6 ||
            archived.undoDepth !== 5 ||
            archived.draftIndexDelta !== 2
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
            form: {present: {index: 8}, past: Array.from({length: 8}, () => ({})), data: {edges: {
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
              state.mapEditor.form.present.index += 2;
              state.mapEditor.form.past.push({index: 8});
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
            restored.editIndex !== 10 ||
            restored.undoDepth !== 9 ||
            restored.draftIndexDelta !== 2
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
          if (state.mapEditor.form.present.index !== 10 || dispatched.length !== 1) {
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


def test_repair_bridge_reports_dispatch_and_readback_failures_as_ambiguous() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is unavailable for the extension bridge test")
    source = json.dumps((EXTENSION / "page-bridge.js").read_text(encoding="utf-8"))

    for mode in ("dispatch_throw", "readback_throw", "unchanged_undo"):
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
                  siteWaypoints: {entities: {}, ids: []},
                  siteEdges: {ids: ["a|b"], entities: {"a|b": edge}},
                  recordingSessions: {entities: {}},
                  mapEditor: {
                    info: {selectedWaypointIds: [], selectedEdgeIds: []},
                    form: {
                      present: {index: 4}, past: [{}, {}], future: [],
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
                    } else if (action.type === "mapEditorFormSlice/archiveSiteEdges") {
                      state.mapEditor.form.present.index = 6;
                      state.mapEditor.form.data.edges.nonEntities["a|b"] = {
                        ...action.payload[0], archived: true,
                      };
                      if (failureMode !== "unchanged_undo") {
                        state.mapEditor.form.past.push({index: 4});
                      }
                      if (failureMode === "readback_throw") {
                        throwOnReadback = true;
                      } else if (failureMode === "dispatch_throw") {
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
                  currentScript: {dataset: {ogrSession: "session-1"}},
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
                      channel: "orbit-graph-repair-v1",
                      type: "orbit-graph-repair-request",
                      sessionId: "session-1",
                      requestId: "archive-failure",
                      command: "archive_many",
                      mapId,
                      waypointPairs: [["a", "b"]],
                    },
                  });
                  const response = messages.find(
                    (message) => message.requestId === "archive-failure"
                  );
                  const expectedError = failureMode === "unchanged_undo"
                    ? "edge_archive_batch_not_created"
                    : "native_mutation_exception";
                  if (
                    response?.ok ||
                    response?.error !== expectedError ||
                    response?.mutationMayExist !== true ||
                    response?.beforeEditIndex !== 4 ||
                    response?.afterEditIndex !== 6 ||
                    response?.beforeUndoDepth !== 2 ||
                    response?.afterUndoDepth !== (
                      failureMode === "unchanged_undo" ? 2 : 3
                    ) ||
                    response?.targetKeys?.join(",") !== "a|b" ||
                    state.mapEditor.form.present.index !== 6 ||
                    !state.mapEditor.form.data.edges.nonEntities["a|b"]?.archived
                  ) throw new Error(JSON.stringify({failureMode, response, state}));
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


def test_repair_bridge_reinjection_aborts_pending_connect_before_dispatch() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is unavailable for the extension bridge test")
    source = json.dumps((EXTENSION / "page-bridge.js").read_text(encoding="utf-8"))
    script = f"const bridgeSource = {source};\n" + textwrap.dedent(
        """
        const vm = require("node:vm");
        const mapId = "map-1";
        const state = {
          mapDisplay: {siteMapId: mapId, anchoring: {anchors: []}},
          siteMaps: {entities: {[mapId]: {
            waypointIds: ["a", "b"], recordingSessionIds: [],
          }}},
          siteWaypoints: {entities: {}, ids: []},
          siteEdges: {entities: {}, ids: []},
          recordingSessions: {entities: {}},
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
            console.error("pending repair Connect test did not reach its assertions");
            process.exitCode = 1;
          }
        });
        const root = {__reactContainer$test: {memoizedProps: {store}}};
        global.location = {
          origin: "https://orbit.test",
          pathname: `/control_room/maps/${mapId}/edit`,
        };
        global.document = {
          currentScript: {dataset: {ogrSession: "session-1"}},
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
            channel: "orbit-graph-repair-v1",
            type: "orbit-graph-repair-request",
            sessionId: "session-1",
            requestId: "stale-connect",
            command: "connect",
            mapId,
            waypointIds: ["a", "b"],
          },
        });
        const duplicateRequest = oldListener({
          source: window,
          origin: location.origin,
          data: {
            channel: "orbit-graph-repair-v1",
            type: "orbit-graph-repair-request",
            sessionId: "session-1",
            requestId: "stale-connect",
            command: "connect",
            mapId,
            waypointIds: ["a", "b"],
          },
        });
        const concurrentRequest = oldListener({
          source: window,
          origin: location.origin,
          data: {
            channel: "orbit-graph-repair-v1",
            type: "orbit-graph-repair-request",
            sessionId: "session-1",
            requestId: "concurrent-connect",
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

        document.currentScript = {dataset: {ogrSession: "session-2"}};
        vm.runInThisContext(bridgeSource);
        if (listeners.size !== 1) {
          throw new Error(`listener count ${listeners.size}`);
        }
        for (const callback of timers.splice(0)) callback();

        (async () => {
          await duplicateRequest;
          await concurrentRequest;
          await oldRequest;
          await Promise.resolve();
          const oldSuccess = messages.find(
            (message) => message.requestId === "stale-connect" && message.ok
          );
          const duplicate = messages.find(
            (message) =>
              message.requestId === "stale-connect" &&
              message.error === "duplicate_request"
          );
          const concurrent = messages.find(
            (message) => message.requestId === "concurrent-connect"
          );
          if (
            addCount !== 0 ||
            oldSuccess ||
            !duplicate ||
            concurrent?.error !== "native_mutation_in_progress"
          ) {
            throw new Error(JSON.stringify({
              addCount, oldSuccess, duplicate, concurrent, messages,
            }));
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


def test_repair_content_latches_unverified_mutations_and_locks_later_edits() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is unavailable for the extension content-script test")
    script = textwrap.dedent(
        """
        class FakeNode {
          constructor() {
            this.dataset = {};
            this.style = {};
            this.hidden = false;
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
            if (!this.nodes.has(selector)) this.nodes.set(selector, new FakeNode());
            return this.nodes.get(selector);
          }
          querySelectorAll() {return [];}
          append(...nodes) {this.children.push(...nodes);}
          replaceChildren(...nodes) {this.children = [...nodes];}
          addEventListener() {}
          setAttribute() {}
          remove() {}
          closest() {return null;}
          scrollIntoView() {}
          getBoundingClientRect() {
            return {left: 0, top: 0, width: 100, height: 100};
          }
        }
        const documentElement = new FakeNode();
        const body = new FakeNode();
        const listeners = new Map();
        const postedMessages = [];
        global.document = {
          documentElement,
          body,
          head: new FakeNode(),
          createElement: () => new FakeNode(),
          createElementNS: () => new FakeNode(),
          createDocumentFragment: () => new FakeNode(),
          getElementById: () => null,
          querySelector: () => null,
          execCommand: () => true,
        };
        global.location = {
          origin: "https://orbit.test",
          pathname: "/control_room/maps/map-1/edit",
          href: "https://orbit.test/control_room/maps/map-1/edit",
        };
        global.window = {
          addEventListener(type, listener) {
            if (!listeners.has(type)) listeners.set(type, []);
            listeners.get(type).push(listener);
          },
          postMessage(message) {postedMessages.push(message);},
          setTimeout,
          clearTimeout,
          setInterval: () => 1,
          confirm: () => true,
        };
        global.requestAnimationFrame = () => 1;
        global.navigator = {clipboard: {writeText: async () => {}}};
        global.chrome = {
          runtime: {
            getURL: (path) => `chrome-extension://repair/${path}`,
            lastError: undefined,
          },
          storage: {local: {
            get: (_keys, callback) => callback({}),
            set: (_value, callback) => callback(),
            remove: (_keys, callback) => callback(),
          }},
        };
        require("./extension/orbit-graph-repair/baseline.js");
        require("./extension/orbit-graph-repair/content.js");
        const runtime = global.OrbitGraphRepairRuntime;
        const action = {
          index: 1,
          operation: "connect",
          coordinate_scope: "map",
          from: "a",
          to: "b",
        };
        runtime.state.guide = {
          kind: "orbit_graph_reconciliation_guide",
          after_site_map: {id: "map-1", name: "Map"},
          actions: [action],
          counts: {},
        };
        runtime.state.bridgeReady = true;
        const messageListener = listeners.get("message")[0];
        const serial = (error) => ({
          message: error.message,
          mutationMayExist: Boolean(error.mutationMayExist),
          targetKeys: error.mutationContext?.targetKeys || [],
        });

        (async () => {
          const pending = runtime.requestBridge("connect", action, 1000)
            .then(() => null, serial);
          const request = postedMessages.at(-1);
          messageListener({
            source: window,
            origin: location.origin,
            data: {
              channel: "orbit-graph-repair-v1",
              type: "orbit-graph-repair-response",
              requestId: request.requestId,
              sessionId: request.sessionId,
              ok: false,
              error: "edge_draft_not_created",
              mutationMayExist: true,
              beforeEditIndex: 4,
              afterEditIndex: 7,
              beforeUndoDepth: 2,
              afterUndoDepth: 2,
              targetKeys: ["a|b"],
            },
          });
          const ambiguous = await pending;
          const blocked = await runtime.requestBridge("connect", action, 1)
            .then(() => null, serial);

          const focusPending = runtime.requestBridge("focus", action, 1000)
            .then((value) => value.ok, serial);
          const focusRequest = postedMessages.at(-1);
          messageListener({
            source: window,
            origin: location.origin,
            data: {
              channel: "orbit-graph-repair-v1",
              type: "orbit-graph-repair-response",
              requestId: focusRequest.requestId,
              sessionId: focusRequest.sessionId,
              ok: true,
              positions: {},
            },
          });
          const focusAllowed = await focusPending;
          runtime.acknowledgeMutationUncertainty();
          const timedOut = await runtime.requestBridge("connect", action, 0)
            .then(() => null, serial);

          process.stdout.write(JSON.stringify({
            ambiguous,
            blocked,
            focusAllowed,
            timedOut,
            locked: Boolean(runtime.state.mutationUncertain),
            lockVisible: runtime.state.mutationUncertain !== null,
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
        "ambiguous": {
            "message": "Orbit did not add the validated edge to its edit history.",
            "mutationMayExist": True,
            "targetKeys": ["a|b"],
        },
        "blocked": {
            "message": "unverified_mutation_pending",
            "mutationMayExist": True,
            "targetKeys": ["a|b"],
        },
        "focusAllowed": True,
        "timedOut": {
            "message": "Orbit edge mutation did not respond.",
            "mutationMayExist": True,
            "targetKeys": ["a|b"],
        },
        "locked": True,
        "lockVisible": True,
    }


def test_repair_and_editor_bridges_share_native_mutation_response_contracts() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is unavailable for the extension bridge drift test")
    repair_source = json.dumps((EXTENSION / "page-bridge.js").read_text(encoding="utf-8"))
    editor_source = json.dumps(
        Path("extension/orbit-site-map-editor/page-bridge.js").read_text(encoding="utf-8")
    )
    script = (
        f"const repairSource = {repair_source};\n"
        f"const editorSource = {editor_source};\n"
        + textwrap.dedent(
            """
            const vm = require("node:vm");
            const mapId = "map-1";
            const edgeKey = (a, b) => a < b ? `${a}|${b}` : `${b}|${a}`;

            async function runCase(source, bridgeKind, operation, failureMode) {
              const rawEdge = (fromWaypoint, toWaypoint, annotations) => ({
                siteMapId: mapId,
                archived: false,
                disabled: false,
                edge: {id: {fromWaypoint, toWaypoint}, annotations},
              });
              const settingsEdge = rawEdge("a", "b", {
                edgeSource: 5,
                pathFollowingMode: 1,
                futureAnnotation: {preserve: true},
              });
              const archiveEdge = rawEdge("c", "d", {edgeSource: 1});
              const state = {
                mapDisplay: {siteMapId: mapId, anchoring: {anchors: []}},
                siteMaps: {entities: {[mapId]: {
                  waypointIds: ["a", "b", "c", "d", "e", "f"],
                  recordingSessionIds: [],
                }}},
                siteWaypoints: {entities: {}, ids: []},
                siteEdges: {
                  entities: {
                    [edgeKey("a", "b")]: settingsEdge,
                    [edgeKey("c", "d")]: archiveEdge,
                  },
                  ids: [edgeKey("a", "b"), edgeKey("c", "d")],
                },
                recordingSessions: {entities: {}},
                mapEditor: {
                  info: {
                    selectedWaypointIds: [],
                    selectedEdgeIds: [],
                    pendingEdgeCreation: {
                      errors: [], warnings: [], validating: false,
                    },
                  },
                  form: {
                    present: {index: 4},
                    past: failureMode === "missing_undo"
                      ? undefined
                      : [{}, {}],
                    future: [],
                    data: {edges: {ids: [], entities: {}, nonEntities: {}}},
                  },
                },
              };
              const completeMutation = (nextIndex) => {
                state.mapEditor.form.present.index = nextIndex;
                if (
                  failureMode !== "unchanged_undo" &&
                  failureMode !== "missing_undo"
                ) {
                  state.mapEditor.form.past.push({index: 4});
                }
                if (failureMode === "dispatch_throw") {
                  throw new Error("reducer wrote before throwing");
                }
              };
              const store = {
                getState: () => state,
                dispatch(action) {
                  if (action.type === "mapEditorInfoSlice/setSelectedWaypoints") {
                    state.mapEditor.info.selectedWaypointIds = [...action.payload];
                    if (action.payload.length === 2) {
                      const [fromWaypoint, toWaypoint] = [...action.payload].sort();
                      state.mapEditor.info.pendingEdgeCreation = {
                        errors: [],
                        warnings: [],
                        validating: false,
                        createdEdgeCandidate: rawEdge(
                          fromWaypoint,
                          toWaypoint,
                          {edgeSource: 5},
                        ),
                      };
                    }
                  } else if (action.type === "mapEditorInfoSlice/setSelectedEdges") {
                    state.mapEditor.info.selectedEdgeIds = [...action.payload];
                  } else if (action.type === "mapEditorFormSlice/addSiteEdge") {
                    const id = action.payload.edge.id;
                    state.mapEditor.form.data.edges.entities[
                      edgeKey(id.fromWaypoint, id.toWaypoint)
                    ] = action.payload;
                    completeMutation(7);
                  } else if (action.type === "mapEditorFormSlice/archiveSiteEdges") {
                    const archived = action.payload[0];
                    const id = archived.edge.id;
                    state.mapEditor.form.data.edges.nonEntities[
                      edgeKey(id.fromWaypoint, id.toWaypoint)
                    ] = {...archived, archived: true};
                    completeMutation(6);
                  } else if (action.type === "mapEditorFormSlice/updateSiteEdges") {
                    const updated = action.payload.updatedEdges[0];
                    if (failureMode === "annotation_loss") {
                      delete updated.edge.annotations.futureAnnotation;
                    }
                    const id = updated.edge.id;
                    state.mapEditor.form.data.edges.entities[
                      edgeKey(id.fromWaypoint, id.toWaypoint)
                    ] = updated;
                    completeMutation(8);
                  }
                  return action;
                },
              };
              const listeners = new Set();
              const messages = [];
              const root = {__reactContainer$test: {memoizedProps: {store}}};
              const sessionId = `${bridgeKind}-${operation}-${failureMode}`;
              const dataset = bridgeKind === "editor"
                ? {osmeSession: sessionId}
                : {ogrSession: sessionId};
              const location = {
                origin: "https://orbit.test",
                pathname: `/control_room/maps/${mapId}/edit`,
              };
              const document = {
                currentScript: {dataset},
                getElementById: (id) => id === "root" ? root : null,
              };
              const window = {
                addEventListener(type, listener) {
                  if (type === "message") listeners.add(listener);
                },
                removeEventListener(type, listener) {
                  if (type === "message") listeners.delete(listener);
                },
                postMessage(message) {messages.push(message);},
                setTimeout,
              };
              const context = vm.createContext({
                console,
                document,
                location,
                setTimeout,
                window,
              });
              vm.runInContext(source, context);
              const listener = [...listeners][0];
              const isEditor = bridgeKind === "editor";
              const command = operation === "connect"
                ? "connect"
                : operation === "archive"
                  ? (isEditor ? "archive_edges" : "archive_many")
                  : (isEditor ? "update_edge_settings" : "update_settings_many");
              const data = {
                channel: isEditor
                  ? "orbit-site-map-editor-v1"
                  : "orbit-graph-repair-v1",
                type: isEditor
                  ? "orbit-site-map-editor-request"
                  : "orbit-graph-repair-request",
                sessionId,
                requestId: `${sessionId}-request`,
                command,
                mapId,
              };
              if (operation === "connect") data.waypointIds = ["e", "f"];
              if (operation === "archive") data.waypointPairs = [["c", "d"]];
              if (operation === "settings") {
                data.settingsUpdates = [{
                  waypointIds: ["a", "b"],
                  storedFrom: "a",
                  storedTo: "b",
                  observedSourceValue: 5,
                  observedSettings: {pathFollowingMode: 1},
                  desiredSettings: {pathFollowingMode: 2},
                }];
              }
              if (operation === "connect" && isEditor) {
                const validationData = {
                  ...data,
                  requestId: `${sessionId}-validation`,
                  command: "validate_connect",
                };
                await listener({
                  source: window,
                  origin: location.origin,
                  data: validationData,
                });
                const validationResponse = messages.find(
                  (message) => message.requestId === validationData.requestId
                );
                if (!validationResponse?.ok) return validationResponse;
              }
              await listener({
                source: window,
                origin: location.origin,
                data,
              });
              return messages.find((message) => message.requestId === data.requestId);
            }

            function contractPayload(response) {
              const ignored = new Set([
                "adapter", "channel", "ok", "requestId", "sessionId", "type",
              ]);
              return Object.fromEntries(
                Object.entries(response)
                  .filter(([key]) => !ignored.has(key))
                  .sort(([left], [right]) => left.localeCompare(right))
              );
            }

            (async () => {
              const results = [];
              for (const operation of ["connect", "archive", "settings"]) {
                for (const failureMode of [
                  "success",
                  "unchanged_undo",
                  "missing_undo",
                  "dispatch_throw",
                ]) {
                  const editor = contractPayload(
                    await runCase(editorSource, "editor", operation, failureMode)
                  );
                  const repair = contractPayload(
                    await runCase(repairSource, "repair", operation, failureMode)
                  );
                  const editorJson = JSON.stringify(editor);
                  const repairJson = JSON.stringify(repair);
                  if (editorJson !== repairJson) {
                    throw new Error(JSON.stringify({
                      operation, failureMode, editor, repair,
                    }));
                  }
                  results.push({operation, failureMode, contract: editor});
                }
              }
              const editor = contractPayload(
                await runCase(editorSource, "editor", "settings", "annotation_loss")
              );
              const repair = contractPayload(
                await runCase(repairSource, "repair", "settings", "annotation_loss")
              );
              if (JSON.stringify(editor) !== JSON.stringify(repair)) {
                throw new Error(JSON.stringify({
                  operation: "settings", failureMode: "annotation_loss", editor, repair,
                }));
              }
              results.push({
                operation: "settings",
                failureMode: "annotation_loss",
                contract: editor,
              });
              process.stdout.write(JSON.stringify(results));
            })().catch((error) => {
              console.error(error);
              process.exitCode = 1;
            });
            """
        )
    )
    completed = subprocess.run(
        [node, "-e", script],
        cwd=Path.cwd(),
        check=True,
        capture_output=True,
        text=True,
    )
    results = json.loads(completed.stdout)

    assert len(results) == 13
    assert {
        (row["operation"], row["failureMode"], row["contract"].get("error")) for row in results
    } >= {
        ("connect", "unchanged_undo", "edge_draft_not_created"),
        ("archive", "unchanged_undo", "edge_archive_batch_not_created"),
        ("settings", "unchanged_undo", "edge_settings_batch_not_created"),
        ("connect", "missing_undo", "validation_changed_draft"),
        ("archive", "missing_undo", "edge_archive_batch_not_created"),
        ("settings", "missing_undo", "edge_settings_batch_not_created"),
        ("connect", "dispatch_throw", "native_mutation_exception"),
        ("archive", "dispatch_throw", "native_mutation_exception"),
        ("settings", "dispatch_throw", "native_mutation_exception"),
        ("settings", "annotation_loss", "edge_annotation_readback_failed"),
    }


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
