<purpose>
Compatibility index for the staged `arxiv-submission` workflow.
</purpose>

<stage_authority_index>
The active authority is selected by `arxiv-submission-stage-manifest.json`. Do not load this index as a stage authority.

- `bootstrap` -> `workflows/arxiv-submission/bootstrap.md`
  Project-aware publication bootstrap, centralized command-context preflight, strict review preflight, manuscript target resolution, response-freshness mapping, and managed package-root setup.
- `manuscript_preflight` -> `workflows/arxiv-submission/manuscript-preflight.md`
  Manuscript-root build refresh, artifact manifest and bibliography audit freshness, reproducibility readiness, and optional LaTeX smoke check.
- `review_gate` -> `workflows/arxiv-submission/review-gate.md`
  Latest staged review ledger / referee decision pair, response-round freshness, and theorem proof-review clearance.
- `package` -> `workflows/arxiv-submission/package.md`
  ArXiv-specific package assembly and executable `gpd --raw validate arxiv-package --materialize` boundary.
- `finalize` -> `workflows/arxiv-submission/finalize.md`
  Validator-backed final checklist and manual arXiv submission handoff.
</stage_authority_index>

<stage_loading_rule>
The public command includes only `workflows/arxiv-submission/bootstrap.md`; later stage loading is manifest-owned.
Never read this root workflow index as active authority.
</stage_loading_rule>

<canonical_references>
- `references/publication/publication-bootstrap-preflight.md`
- `templates/paper/publication-manuscript-root-preflight.md`
- `references/publication/publication-review-round-artifacts.md`
- `references/publication/peer-review-reliability.md`
- `references/publication/publication-response-artifacts.md`
</canonical_references>
