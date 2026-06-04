<purpose>
Compatibility index for the staged `resume-work` workflow.
</purpose>

<stage_authorities>
The active authority is selected by `resume-work-stage-manifest.json`.
Do not load this index as a stage authority.

- `resume_bootstrap` -> `workflows/resume-work/resume-bootstrap.md`
  Project reentry resolution, canonical resume target selection, immediate recovery summary, and resume vocabulary.
- `state_restore` -> `workflows/resume-work/state-restore.md`
  State authority restoration, contract-gate visibility, machine-change notice, and blocked-contract routing.
- `derivation_restore` -> `workflows/resume-work/derivation-restore.md`
  Derivation history restoration, continuity-anchor recovery, and convention status.
- `resume_routing` -> `workflows/resume-work/resume-routing.md`
  Incomplete-work detection, status presentation, next-action selection, optional reconstruction, quick-resume guardrails, and continuation update rules.
</stage_authorities>

<stage_loading_rule>
The public command includes only `workflows/resume-work/resume-bootstrap.md`; later stage loading is manifest-owned.
Bootstrap keeps continuation format, state portability, schema, derivation restoration, routing, reconstruction, quick-resume, and continuation-update authority lazy until the matching stage.
</stage_loading_rule>
