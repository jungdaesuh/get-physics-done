<purpose>
Compatibility index for the staged `new-milestone` workflow.
</purpose>

<stage_authorities>
The active authority is selected by `new-milestone-stage-manifest.json`.
Do not load this index as a stage authority.

- `milestone_bootstrap` -> `workflows/new-milestone/milestone-bootstrap.md`
  Milestone lookup, command context preflight, contract-gate visibility, and staged routing.
- `survey_objectives` -> `workflows/new-milestone/survey-objectives.md`
  Goal gathering, milestone version and state updates, optional literature survey, and scoped objective authoring.
- `roadmap_authoring` -> `workflows/new-milestone/roadmap-authoring.md`
  Fresh roadmap init, roadmapper continuation handoff, roadmap artifact gate, approval loop, optional commit, and next-step display.
</stage_authorities>

<stage_loading_rule>
The public command includes only `workflows/new-milestone/milestone-bootstrap.md`; later stage loading is manifest-owned by the active staged payload. The first stage must not eagerly load survey, objective, roadmapper, template, UI, or runtime-delegation authorities.
</stage_loading_rule>

<compatibility_note>
This workflow remains the continuation equivalent of `new-project`: it honors `planning.commit_docs`, creates the new milestone roadmap, and routes the next step to `gpd:discuss-phase [N]` unless the user explicitly chooses another path.
</compatibility_note>
