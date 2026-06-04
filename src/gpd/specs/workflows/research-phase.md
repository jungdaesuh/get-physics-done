<purpose>
Compatibility index for the staged `research-phase` workflow.
</purpose>

<stage_authority_index>
The active authority is selected by `research-phase-stage-manifest.json`. Do not load this index as a stage authority.

- `phase_bootstrap` -> `workflows/research-phase/phase-bootstrap.md`
  Phase argument validation, staged bootstrap init, existing research routing, phase context gathering, and model-profile setup.
- `research_handoff` -> `workflows/research-phase/research-handoff.md`
  Reference/contract handoff refresh, `gpd-phase-researcher` spawn, `RESEARCH.md` artifact gate, typed return routing, and continuation handoff.
</stage_authority_index>

<stage_loading_rule>
The public command includes only `workflows/research-phase/phase-bootstrap.md`; research handoff loading is manifest-owned by the active staged payload.
</stage_loading_rule>

<canonical_references>
- `references/orchestration/model-profile-resolution.md`
- `references/orchestration/runtime-delegation-note.md`
- `references/orchestration/continuation-boundary.md`
- `references/orchestration/child-artifact-gate.md`
</canonical_references>
