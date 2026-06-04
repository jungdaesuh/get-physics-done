<purpose>
Own Stage 1 claim extraction, Stages 2-5 specialist review, conditional
same-round proof-redteam review, and stage-artifact validation.
</purpose>

<stage_boundary>
Panel stages start only after bootstrap, preflight, artifact discovery, target,
and round state are resolved. Each stage runs in a fresh subagent context and
writes a compact artifact. Apply `{GPD_INSTALL_DIR}/references/publication/stage-recovery-gate.md`
before checkpoint continuation, retry, stale-output rejection, or sequential fallback.

The manifest always loads `references/publication/peer-review-panel.md` for the
machine contract. Load the conditional
`references/publication/peer-review-panel-playbook.md` authority only when
expanded rubric guidance, venue-fit judgment, claim-scope uncertainty, or panel
child recovery needs it. Recovery/proof authorities are conditional. Bundle
guidance enters as handles only: `selected_protocol_bundle_ids` and
`protocol_bundle_load_manifest`. Reader-visible claims, surfaced evidence,
`${MANUSCRIPT_ROOT}/FIGURE_TRACKER.md`, `GPD/comparisons/*-COMPARISON.md`, and review-support artifacts are first-class. Read reference files by handle only for targeted
evidence; do not hydrate broad reference/protocol bodies into panel init.

Handle-first review invariant: before a Stage 4-5 domain or method judgment,
bind the claim or venue issue, choose the relevant selected asset from
`protocol_bundle_load_manifest` (`verification_domains`, `execution_guides`, or
fallback domain/protocol handle), and read that file. Acknowledging a handle or
bundle id is not evidence.
</stage_boundary>

<announce_panel>
Load the staged panel payload before launching Stage 1 through Stage 5 and the
conditional proof audit:

```bash
if [ -n "${ARGUMENTS:-}" ]; then PANEL_INIT=$(gpd --raw init peer-review --stage panel_stages -- "$ARGUMENTS"); else PANEL_INIT=$(gpd --raw init peer-review --stage panel_stages); fi
if [ $? -ne 0 ]; then echo "ERROR: gpd peer-review panel init failed: $PANEL_INIT"; fi
INIT="$PANEL_INIT"
```

Apply `PANEL_INIT.staged_loading.field_access_instruction` before reading it.

```bash
REVIEW_TARGET=$(echo "$INIT" | gpd json get .review_target_input --default "")
MANUSCRIPT_ROOT=$(echo "$INIT" | gpd json get .manuscript_root --default "")
PUBLICATION_ROOT=$(echo "$INIT" | gpd json get .selected_publication_root --default GPD)
REVIEW_ROOT=$(echo "$INIT" | gpd json get .selected_review_root --default "")
REVIEW_ROOT="${REVIEW_ROOT:-${PUBLICATION_ROOT}/review}"
```

Before spawning any reviewer, announce the review with this concise stage map:

`Launching the six-stage review panel: Stage 1 maps the paper's claims; Stages 2-3 check prior work and mathematical soundness in parallel; theorem-style claims also trigger the auxiliary gpd-check-proof audit; Stage 4 checks whether the physical interpretation is supported; Stage 5 judges significance and venue fit; Stage 6 synthesizes everything into the final recommendation.`
</announce_panel>

<child_return_contract>
Use these callsite-owned tuples. Stage identity comes from tuple role, expected
paths, write allowlist, canonical filenames, and validators; never trust a stage
label inside `gpd_return`.

```yaml
peer_review_stage1_reader:
  role: gpd-review-reader
  expected_artifacts: ["${REVIEW_ROOT}/CLAIMS{round_suffix}.json", "${REVIEW_ROOT}/STAGE-reader{round_suffix}.json"]
  validators:
    - "gpd validate review-claim-index ${REVIEW_ROOT}/CLAIMS{round_suffix}.json"
    - "gpd validate review-stage-report ${REVIEW_ROOT}/STAGE-reader{round_suffix}.json with stage_id=reader and stage_kind=reader"
  failure_route: retry_stage_once_then_stop

peer_review_stage2_literature:
  role: gpd-review-literature
  expected_artifacts: ["${REVIEW_ROOT}/STAGE-literature{round_suffix}.json"]
  validators: ["gpd validate review-stage-report ${REVIEW_ROOT}/STAGE-literature{round_suffix}.json with stage_id=literature and stage_kind=literature"]
  failure_route: retry_stage_once_then_stop

peer_review_stage3_math:
  role: gpd-review-math
  expected_artifacts: ["${REVIEW_ROOT}/STAGE-math{round_suffix}.json"]
  validators: ["gpd validate review-stage-report ${REVIEW_ROOT}/STAGE-math{round_suffix}.json with stage_id=math and stage_kind=math"]
  failure_route: retry_stage_once_then_stop

peer_review_proof_redteam:
  role: gpd-check-proof
  return_profile: proof_redteam
  expected_artifacts: ["${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md"]
  validators: ["gpd validate proof-redteam ${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md", "required frontmatter, sections, same-round theorem binding, and reviewer=gpd-check-proof"]
  failure_route: retry_proof_redteam_once_then_stop; favorable_decisions_require_same_round_status_passed

peer_review_stage4_physics:
  role: gpd-review-physics
  expected_artifacts: ["${REVIEW_ROOT}/STAGE-physics{round_suffix}.json"]
  validators: ["gpd validate review-stage-report ${REVIEW_ROOT}/STAGE-physics{round_suffix}.json with stage_id=physics and stage_kind=physics"]
  failure_route: retry_stage_once_then_stop

peer_review_stage5_significance:
  role: gpd-review-significance
  expected_artifacts: ["${REVIEW_ROOT}/STAGE-interestingness{round_suffix}.json"]
  validators: ["gpd validate review-stage-report ${REVIEW_ROOT}/STAGE-interestingness{round_suffix}.json with stage_id=interestingness and stage_kind=interestingness"]
  failure_route: retry_stage_once_then_stop
```
</child_return_contract>

<stage_1_claim_extraction>
Stage 1 reads the whole manuscript once and writes
`${REVIEW_ROOT}/CLAIMS{round_suffix}.json` and
`${REVIEW_ROOT}/STAGE-reader{round_suffix}.json`. Spawn
`gpd-review-reader` with selected manuscript path/hash, journal when known,
round number/suffix, `PUBLICATION_ROOT`, and `REVIEW_ROOT`; preserve exact
`manuscript_path`, `manuscript_sha256`, claim ids, theorem-like claim kind,
theorem assumptions, and theorem parameters.

```bash
gpd validate review-claim-index ${REVIEW_ROOT}/CLAIMS{round_suffix}.json
gpd validate review-stage-report ${REVIEW_ROOT}/STAGE-reader{round_suffix}.json
```

If Stage 1 fails, apply stage-recovery gate and retry once with the
`StageReviewReport` / `ClaimIndex` schema reminder. If validation still fails,
STOP before Stages 2-6.
</stage_1_claim_extraction>

<stage_2_3_and_proof_redteam>
Stage 2 literature reads manuscript, claims, reader stage, bibliography audit,
bib files, comparisons, figure tracker, and targeted web search only when
novelty/positioning is uncertain. It writes
`${REVIEW_ROOT}/STAGE-literature{round_suffix}.json`.

Stage 3 math reads manuscript, claims, reader stage, summaries, verification,
artifact/reproducibility manifests, and proof artifacts when present. It writes
`${REVIEW_ROOT}/STAGE-math{round_suffix}.json`. Require exactly one
`proof_audits[]` entry per reviewed theorem-bearing claim, with each
`proof_audits[].claim_id` also in `claims_reviewed`.

When theorem-bearing claims are present, run `gpd-check-proof` as the auxiliary
proof critique, writing `${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md`. The
conditional proof-redteam workflow gate, protocol, and schema authorities own
same-round theorem binding, frontmatter, status handling, and validation.

Conditional proof prompt:

```text
First, read {GPD_AGENTS_DIR}/gpd-check-proof.md for your role and instructions.
Then read {GPD_INSTALL_DIR}/templates/proof-redteam-schema.md and {GPD_INSTALL_DIR}/references/verification/core/proof-redteam-protocol.md before writing any proof audit artifact.

Operate in adversarial proof-critique mode with a fresh context.
Follow the proof-redteam protocol's one-shot return semantics.
Write to: `${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md`
```

The proof-redteam task and artifact must copy active `manuscript_path`,
`manuscript_sha256`, round, theorem-bearing `claim_ids`, and
`proof_artifact_paths` from `${REVIEW_ROOT}/CLAIMS{round_suffix}.json`; include
the manuscript entrypoint when it is not already listed. Missing, malformed,
wrong-round/root, `status: gaps_found`, or `status: human_needed` proof artifacts
block favorable recommendation. Retry proof-redteam once, then STOP if invalid.

Run Stage 2, Stage 3, and proof critique in parallel when the runtime supports
it; otherwise run literature, math, proof. Treat them as one barriered wave:

```bash
gpd validate review-stage-report ${REVIEW_ROOT}/STAGE-literature{round_suffix}.json
gpd validate review-stage-report ${REVIEW_ROOT}/STAGE-math{round_suffix}.json
```

If proof-bearing review is active, also validate same-round
`${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md`. Before Stage 4, every launched
child must have a typed return, every promised artifact must exist and validate,
and downstream work restarts only from persisted artifacts plus declared
carry-forward inputs.
</stage_2_3_and_proof_redteam>

<stage_4_physics>
Stage 4 checks physical soundness after math. It reads manuscript, reader, math,
literature, proof-redteam artifact if active, summaries, verifications,
comparisons, and figure tracker. It writes
`${REVIEW_ROOT}/STAGE-physics{round_suffix}.json`.
For condensed-matter or other method-specific claims, open the relevant selected
handle before judging support, regime validity, or interpretation.

```bash
gpd validate review-stage-report ${REVIEW_ROOT}/STAGE-physics{round_suffix}.json
```

Apply stage-recovery gate. Retry once from the same persisted inputs; if still
invalid, STOP before Stage 5.
</stage_4_physics>

<stage_5_significance>
Stage 5 judges interestingness and venue fit after technical stages. It reads
manuscript, reader, literature, physics, proof-redteam artifact if active, and
target journal. It writes `${REVIEW_ROOT}/STAGE-interestingness{round_suffix}.json`.

```bash
gpd validate review-stage-report ${REVIEW_ROOT}/STAGE-interestingness{round_suffix}.json
```

After validation, Stage 6 must begin from persisted stage artifacts and declared
carry-forward inputs only.
</stage_5_significance>

<handoff>
Reload before final adjudication:

```bash
if [ -n "$REVIEW_TARGET" ]; then FINAL_ADJUDICATION_INIT=$(gpd --raw init peer-review --stage final_adjudication -- "$REVIEW_TARGET"); else FINAL_ADJUDICATION_INIT=$(gpd --raw init peer-review --stage final_adjudication); fi
if [ $? -ne 0 ]; then
  echo "ERROR: gpd peer-review final-adjudication init failed: $FINAL_ADJUDICATION_INIT"
  # STOP; surface the error.
fi
```
</handoff>
