<purpose>
Compatibility index for the staged `quick` workflow.
</purpose>

<stage_authority_index>
The active authority is selected by `quick-stage-manifest.json`. Do not load this index as a stage authority.

- `task_bootstrap` -> `workflows/quick/task-bootstrap.md`
  Freeform quick-task intake, bootstrap gates, reroute rules, and quick
  directory creation. The bootstrap authority asks: `Ask ONE question inline (freeform, NOT ask_user):`; there are no fixed option labels to preserve.
- `task_authoring` -> `workflows/quick/task-authoring.md`
  Default planner/executor handoffs, durable state update, and commit.
- `reference_context` -> `workflows/quick/reference-context.md`
  Reference-aware quick authoring when project anchors, reference artifacts,
  literature/research-map files, or targeted source lookup are required.
</stage_authority_index>
