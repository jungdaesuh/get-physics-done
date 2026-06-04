<purpose>
Compatibility index for the staged `respond-to-referees` workflow.
This workflow is project-aware: it may revise the active manuscript from the current GPD project or an explicit manuscript subject, while canonical GPD-authored response artifacts live under the selected publication/review roots.
</purpose>

<stage_authority_index>
Do not use this index as active stage authority. The public command and `respond-to-referees-stage-manifest.json` load the stage-specific files below:

- `bootstrap` -> `workflows/respond-to-referees/bootstrap.md`
  Manuscript subject resolution, report-source policy, publication/review root selection, command-context and review preflight, publication bootstrap preflight, convention checks, and response-root binding.
- `report_triage` -> `workflows/respond-to-referees/report-triage.md`
  Referee report ingestion, latest-round detection, sibling artifact discovery, decision-artifact calibration, and parsed issue inventory.
- `revision_planning` -> `workflows/respond-to-referees/revision-planning.md`
  Protocol-bundle context, Groups A/B/C triage, new-calculation routing, claim narrowing versus new evidence, and scoped revision planning.
- `response_authoring` -> `workflows/respond-to-referees/response-authoring.md`
  Canonical author/referee response artifact pair creation, response templates, paper-writer section handoffs, revision verification, bibliography freshness, and optional manuscript-local response-letter generation.
- `finalize` -> `workflows/respond-to-referees/finalize.md`
  Final response-pair checks, commit file selection, closeout routing, anti-patterns, and success criteria.
</stage_authority_index>

<stage_loading_rule>
The public command includes only `workflows/respond-to-referees/bootstrap.md`; later stage loading is manifest-owned.
Keep downstream response-authoring, paper-writer spawn, response-template, aggregate response-pair, and finalization authority lazy until the matching stage.
</stage_loading_rule>

<canonical_references>
The staged authorities reference these canonical contracts as needed:

- `references/publication/publication-bootstrap-preflight.md`
- `references/publication/peer-review-reliability.md`
- `references/publication/publication-response-writer-handoff.md`
- `references/publication/stage-recovery-gate.md`
- `templates/paper/author-response.md`
- `templates/paper/referee-response.md`
- `references/orchestration/runtime-delegation-note.md`
</canonical_references>
