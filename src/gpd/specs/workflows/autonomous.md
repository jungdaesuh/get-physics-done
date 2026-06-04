<purpose>
Compatibility index for the staged `autonomous` workflow.
</purpose>

<stage_authorities>
The active authority is selected by `autonomous-stage-manifest.json`.
Do not load this index as a stage authority.

- `initialize_discover` -> `workflows/autonomous/initialize-discover.md`
  Launch parsing, milestone snapshot, and phase discovery.
- `phase_route` -> `workflows/autonomous/phase-route.md`
  Current-phase selection and paper-phase routing.
- `discuss_delegate` -> `workflows/autonomous/discuss-delegate.md`
  Context-existence check and `gpd:discuss-phase` delegation.
- `plan_execute_child_cycle` -> `workflows/autonomous/plan-execute-child-cycle.md`
  Plan/execute child-command orchestration and checkpoint routing.
- `verification_route` -> `workflows/autonomous/verification-route.md`
  `gpd:verify-work` delegation and canonical status routing.
- `gap_route` -> `workflows/autonomous/gap-route.md`
  Single gap-closure attempt and fresh verification handoff.
- `convention_lifecycle_closeout` -> `workflows/autonomous/convention-lifecycle-closeout.md`
  Convention validation, next-phase reload, audit, and completion routing.
- `blocked_recovery` -> `workflows/autonomous/blocked-recovery.md`
  Shared retry, skip, or stop recovery menu.
</stage_authorities>

<stage_loading_rule>
The public command includes only `workflows/autonomous/initialize-discover.md`.
Later stages are loaded from the manifest-selected staged init payload. Use only
the active stage's `staged_loading.eager_authorities`; this root remains an
index, never executable authority.
</stage_loading_rule>

<child_command_index>
- runtime-installed `gpd:write-paper` child command
- runtime-installed `gpd:plan-phase` child command
- runtime-installed `gpd:execute-phase` child command
- runtime-installed `gpd:verify-work` child command
- runtime-installed `gpd:audit-milestone` child command
- runtime-installed `gpd:complete-milestone` child command

Use these only when selected by the active authority.
</child_command_index>
