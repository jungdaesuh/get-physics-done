<purpose>
Compatibility index for the staged `sync-state` workflow.
</purpose>

<stage_authorities>
The active authority is selected by `sync-state-stage-manifest.json`.
Do not load this index as a stage authority.

- `sync_bootstrap` -> `workflows/sync-state/sync-bootstrap.md`
  State-file existence detection, current-workspace reentry policy, fail-closed bad-backup routing, and recovery path selection.
- `single_source_recovery` -> `workflows/sync-state/single-source-recovery.md`
  Missing-file regeneration through the tested backend repair path.
- `conflict_analysis` -> `workflows/sync-state/conflict-analysis.md`
  Mirrored-field comparison and deterministic source-of-truth classification.
- `reconcile_and_validate` -> `workflows/sync-state/reconcile-and-validate.md`
  Backend reconciliation, validation, reporting, and optional caller-controlled commit.
</stage_authorities>

<stage_loading_rule>
The public command includes only `workflows/sync-state/sync-bootstrap.md`; later stage loading is manifest-owned.
Bootstrap and backend repair stages keep the state JSON schema lazy until a conditional manual schema-drift or backend validation-failure diagnosis path is selected.
Raw state bodies are reserved for `conflict_analysis` read-only drift reporting;
repair and validation stages rely on compact status fields plus backend repair
commands.
</stage_loading_rule>
