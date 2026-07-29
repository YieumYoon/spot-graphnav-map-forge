"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const ROOT = path.resolve(__dirname, "../..");
const EDITOR = path.join(ROOT, "extension/orbit-site-map-editor");
const ASSISTANT = path.join(ROOT, "extension/orbit-graph-repair");

function source(directory, name) {
  return fs.readFileSync(path.join(directory, name), "utf8");
}

function declaredFields(directory, name, declaration) {
  const value = source(directory, name);
  const start = value.indexOf(`const ${declaration}`);
  assert.notEqual(start, -1, `${declaration} is declared in ${name}`);
  const block = value.slice(start, value.indexOf("]", start) + 1);
  return [...block.matchAll(/"([A-Za-z][A-Za-z0-9]*)"/g)].map((match) => match[1]);
}

test("workspace templates own complete, non-overlapping controller descriptors", () => {
  for (const name of [
    "workspace-select.js",
    "workspace-action-names.js",
    "workspace-edit.js",
    "workspace-validate.js",
  ]) require(path.join(EDITOR, name));

  const panes = [
    global.OrbitSiteMapEditorSelectWorkspace,
    global.OrbitSiteMapEditorActionNamesWorkspace,
    global.OrbitSiteMapEditorEditWorkspace,
    global.OrbitSiteMapEditorValidateWorkspace,
  ];
  const selectors = panes.flatMap((pane) => pane.selectors);
  assert.deepEqual(panes.map((pane) => pane.id), [
    "select",
    "action-names",
    "edit",
    "validate",
  ]);
  assert.deepEqual(panes.map((pane) => pane.label), [
    "Select",
    "Action Names",
    "Edit",
    "Validate",
  ]);
  assert.equal(new Set(selectors).size, selectors.length);
  for (const pane of panes) {
    const markup = pane.render();
    assert.ok(pane.selectors.every((selector) => markup.includes(`osme-${selector}`)));
  }
});

test("workspace registry activates one controller and disposes each once", () => {
  class FakeNode {
    constructor(id = "") {
      this.dataset = id ? {workspaceTab: id} : {};
      this.hidden = false;
      this.children = [];
      this.textContent = "";
    }
    append(node) { this.children.push(node); }
  }
  const panes = [new FakeNode("select"), new FakeNode("edit")];
  const root = {
    querySelectorAll(selector) {
      const id = selector.match(/"([^"]+)"/)?.[1];
      return panes.filter((pane) => pane.dataset.workspaceTab === id);
    },
  };
  const nav = new FakeNode();
  global.document = {createElement: () => new FakeNode()};
  require(path.join(EDITOR, "workspace-controller.js"));
  const calls = [];
  const registry = global.OrbitSiteMapEditorWorkspaceController.createRegistry({
    root,
    nav,
    host: new FakeNode(),
  });
  registry.register({id: "select", label: "Select", render: () => calls.push("select")});
  registry.register({
    id: "edit",
    label: "Edit",
    render: () => calls.push("edit"),
    dispose: () => calls.push("dispose"),
  });
  assert.equal(registry.activate("edit"), true);
  assert.equal(panes[0].hidden, true);
  assert.equal(panes[1].hidden, false);
  assert.deepEqual(calls, ["edit"]);
  registry.dispose();
  registry.dispose();
  assert.deepEqual(calls, ["edit", "dispose"]);
});

test("edge setting contract matches isolated bridges and the independent assistant", () => {
  const canonical = declaredFields(EDITOR, "edge-settings-contract.js", "FIELDS");
  assert.deepEqual(canonical, declaredFields(EDITOR, "page-bridge.js", "EDGE_SETTING_FIELDS"));
  assert.deepEqual(canonical, declaredFields(ASSISTANT, "baseline.js", "EDGE_SETTING_FIELDS"));
  assert.deepEqual(canonical, declaredFields(ASSISTANT, "page-bridge.js", "EDGE_SETTING_FIELDS"));
  assert.match(source(EDITOR, "workflow.js"), /edgeSettingsContract\.FIELDS/);
  assert.match(source(EDITOR, "area-settings.js"), /edgeSettingsContract\.FIELD_SET/);
  assert.match(
    source(EDITOR, "overlay-settings.js"),
    /EDGE_SETTING_FIELDS: edgeSettingsContract\.FIELDS/,
  );
});

test("snapshot and mutation boundaries avoid repeated full work", () => {
  const content = source(EDITOR, "content.js");
  const advanced = source(EDITOR, "advanced.js");
  const areas = source(EDITOR, "areas-ui.js");
  const bridge = source(EDITOR, "page-bridge.js");
  assert.match(content, /if \(!snapshotChanged && !force\) return state\.snapshot;/);
  assert.match(advanced, /findingsSnapshotRevision/);
  assert.match(advanced, /function renderWorkspace\(tab\)/);
  assert.match(areas, /workspaceRegistry\.activeId\(\) === "areas"/);
  assert.equal((bridge.match(/const execution = executeNativeMutation\(\{/g) || []).length, 4);
  for (const readback of [
    "edge_draft_not_created",
    "edge_archive_batch_not_created",
    "edge_settings_batch_not_created",
    "edge_annotation_readback_failed",
    "action_name_batch_not_created",
    "action_name_readback_failed",
  ]) assert.match(bridge, new RegExp(readback));
});
