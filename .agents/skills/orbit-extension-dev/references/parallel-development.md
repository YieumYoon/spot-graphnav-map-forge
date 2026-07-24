# Parallel extension development

## Isolation model

- Use one Git worktree and one `codex/<feature>` branch per independently mergeable feature.
- Do not have multiple agents switch branches in the same checkout.
- Assign each writing agent an owning file set. Use read-only agents for cross-cutting exploration,
  test review, or compatibility research.
- Treat the live Orbit Chrome session as a serialized integration resource, not a parallel test
  worker.

## Suggested ownership

| Feature area | Primary files |
| --- | --- |
| Explore, Inspector, base overlay | `content.js`, query/model helpers |
| Select | `workspace-select.js`, `selection.js`, Select wiring/tests |
| Edit | `workspace-edit.js`, `workflow.js`, Edit wiring/tests |
| Validate | `workspace-validate.js`, `validation.js`, Validate wiring/tests |
| Walk | `walk-ui.js`, `walk-planner.js`, Walk tests |
| Native Orbit compatibility | `page-bridge.js`, adapter qualification tests |
| Shared shell/lifecycle | `advanced.js`, `extension-context.js`, `manifest.json` |

Changes to shared shell or adapter files should be integrated sequentially.

## Branch flow

1. Start each feature from the same clean `main` or agreed integration commit.
2. Implement and run `scripts/check_editor_extension.py` inside that worktree.
3. Commit a focused branch without transient `version_name`.
4. Merge or cherry-pick one feature at a time into an integration branch.
5. Resolve shared-file conflicts before live testing.
6. On the integration branch, set a development label and run the live qualification.
7. Restore the label, run `--full`, then merge to `main`.

Use subagents inside one feature for bounded research, tests, or review. Use separate Worktree tasks
for independent write-heavy features.
