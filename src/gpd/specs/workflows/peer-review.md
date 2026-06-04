<purpose>
Compatibility index for the staged `peer-review` workflow.
</purpose>

<stage_authority_index>
Do not use this index as active stage authority. The command wrapper and staged
manifest `peer-review-stage-manifest.json` load the stage-specific files below:

- `bootstrap`: `workflows/peer-review/bootstrap.md`
- `preflight`: `workflows/peer-review/preflight.md`
- `artifact_discovery`: `workflows/peer-review/artifact-discovery.md`
- `panel_stages`: `workflows/peer-review/panel-stages.md`
- `final_adjudication`: `workflows/peer-review/final-adjudication.md`
- `finalize`: `workflows/peer-review/finalize.md`
</stage_authority_index>

<boundary_summary>
Bootstrap resolves target mode, contract-gate visibility, selected publication root,
selected review root, manuscript root, and the active manuscript entrypoint. Later
stage loading is manifest-owned.

Artifact preflight, claim extraction, specialist review, proof/stage validation,
final adjudication, and response routing are separated by stage authority. Stage ids
remain unchanged for compatibility.

Bundle guidance is additive only: Reader-visible claims, surfaced evidence, and
review-support artifacts stay first-class.
</boundary_summary>
