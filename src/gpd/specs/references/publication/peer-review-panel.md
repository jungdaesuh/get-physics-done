---
load_when:
  - "peer review"
  - "panel review"
  - "referee adjudication"
  - "review stage artifact"
type: peer-review-panel-contract
tier: 2
context_cost: low
---

# Peer Review Panel Contract

Peer Review Panel Protocol.

Compact machine contract for staged peer review: stages, artifacts, roots,
validators, and theorem-bearing rules. Reviewer judgment guidance lives in
`references/publication/peer-review-panel-playbook.md`.

## Selected Roots

All runtime paths bind to the active staged-init payload:

- `PUBLICATION_ROOT`: selected publication output root.
- `REVIEW_ROOT`: selected review-artifact root.
- `round_suffix`: empty for round 1, otherwise `-R<round>`.
- `selected_publication_root` / `selected_review_root`: target-aware aliases.

Do not infer latest review state from global `GPD/review` when staged init has
resolved a subject-owned or explicit-artifact review root.

## Stage And Artifact Index

| Stage | Agent | Required artifacts |
| --- | --- | --- |
| 1 reader | `gpd-review-reader` | `${REVIEW_ROOT}/CLAIMS{round_suffix}.json`, `${REVIEW_ROOT}/STAGE-reader{round_suffix}.json` |
| 2 literature | `gpd-review-literature` | `${REVIEW_ROOT}/STAGE-literature{round_suffix}.json` |
| 3 math | `gpd-review-math` | `${REVIEW_ROOT}/STAGE-math{round_suffix}.json` |
| proof gate | `gpd-check-proof` | `${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md` when theorem-bearing claims exist |
| 4 physics | `gpd-review-physics` | `${REVIEW_ROOT}/STAGE-physics{round_suffix}.json` |
| 5 interestingness | `gpd-review-significance` | `${REVIEW_ROOT}/STAGE-interestingness{round_suffix}.json` |
| 6 referee | `gpd-referee` | `${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json`, `${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json`, `${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.md`, `${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.tex`, optional `${PUBLICATION_ROOT}/CONSISTENCY-REPORT.md` |

Strict-stage specialist artifacts must use canonical names `STAGE-reader`, `STAGE-literature`, `STAGE-math`, `STAGE-physics`, `STAGE-interestingness`.
In strict mode, all five must share the same optional `-R<round>` suffix.
`CLAIMS{round_suffix}.json` is the separate claim index and is not a
`stage_artifacts` entry in `REFEREE-DECISION{round_suffix}.json`.

## Dependency Graph

- Stage 1 runs first and is mandatory.
- Stages 2, 3, and the conditional proof critique form one barriered wave.
- The proof critique is required only when Stage 1 contains theorem-bearing
  claims, but a launched proof critique is mandatory same-round Stage 6 input.
- Stage 4 starts only after the Stage 2/3/proof barrier validates.
- Stage 5 starts only after Stage 4 validates.
- Stage 6 reads persisted Stage 1-5 and proof artifacts only; it does not use
  live child memory or prose success text as evidence.

Use `references/publication/stage-recovery-gate.md` for retry freshness,
stale-output rejection, and parallel-wave cleanup.

## Stage 6 Read-Only Boundary

Stage 6 may write only its adjudication artifacts for the active round. Treat `${REVIEW_ROOT}/CLAIMS{round_suffix}.json`, every `${REVIEW_ROOT}/STAGE-*.json`, and `${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md` as read-only upstream evidence. Do not repair, rewrite, replace, or backfill them inside Stage 6.

If any upstream artifact is missing, malformed, stale, wrong-root, wrong-round, or mutually inconsistent, Stage 6 must fail closed with `gpd_return.status: blocked` and route the inconsistency back to the earliest failing upstream stage.
Never repair upstream stage artifacts in final adjudication or list them in
fresh `gpd_return.files_written`.

Use `references/publication/publication-final-adjudication-boundary.md` for the
Stage 6 checklist, strict final-decision validation, proof-redteam clearance,
and write allowlist. `${PUBLICATION_ROOT}/CONSISTENCY-REPORT.md` is a diagnostic
sidecar only.

## ClaimIndex Contract

Stage 1 `CLAIMS{round_suffix}.json` is a closed schema `ClaimIndex` with:

- `version`
- `manuscript_path`
- `manuscript_sha256`
- `claims[]`

Each `claims[]` entry is a closed `ClaimRecord` with:

- `claim_id`: `CLM-[A-Za-z0-9][A-Za-z0-9_-]*`
- `claim_type`: `main_result | novelty | significance | physical_interpretation | generality | method`
- `claim_kind`: `theorem | lemma | corollary | proposition | result | claim | other`
- `text`
- `artifact_path`
- `section`
- `equation_refs[]`
- `figure_refs[]`
- `supporting_artifacts[]`
- `theorem_assumptions[]`
- `theorem_parameters[]`

`manuscript_path` must be non-empty and name the exact manuscript snapshot under
review. `manuscript_sha256` is the lowercase 64-hex digest. Keep unavailable
reference arrays empty.

## StageReviewReport Contract

Every specialist stage writes a closed `StageReviewReport` with:

- `version`
- `round`
- `stage_id`
- `stage_kind`
- `manuscript_path`
- `manuscript_sha256`
- `claims_reviewed[]`
- `summary`
- `strengths[]`
- `findings[]`
- `proof_audits[]`
- `confidence`
- `recommendation_ceiling`

Closed vocabularies:

- `stage_kind: reader | literature | math | physics | interestingness | meta`
- `findings[].severity: critical | major | minor | suggestion`
- `findings[].support_status: supported | partially_supported | unsupported | unclear`
- `findings[].blocking`: JSON boolean `true` or `false`; use literal `blocking`, `true`, and `false`, never `"yes"` or `"no"`
- `confidence: high | medium | low`
- `recommendation_ceiling: accept | minor_revision | major_revision | reject`
- `issues[].opened_by_stage: reader | literature | math | physics | interestingness | meta`
- `issues[].status: open | carried_forward | resolved`
- `final_recommendation: accept | minor_revision | major_revision | reject`
- `final_confidence: high | medium | low`
- `proof_audits[].alignment_status: aligned | partially_aligned | misaligned | not_applicable`

`proof_audits[].alignment_status` must be one of: `aligned`, `partially_aligned`, `misaligned`, `not_applicable`.
Every `StageReviewReport` includes the JSON `round` field and must match the
sibling `CLAIMS{round_suffix}.json` for manuscript path and hash.

`claims_reviewed[]`, every `findings[].claim_ids[]`, and every
`proof_audits[].claim_id` reuse Stage 1 `CLM-...` ids. Stages 2-5 must exactly
match the sibling `CLAIMS{round_suffix}.json` manuscript path/hash.

In Stage 3, `proof_audits[]` coverage is exact: every theorem-bearing Stage 1 claim must be reviewed and proof-audited.
Emit exactly one proof audit for each reviewed theorem-bearing claim, emit none for unreviewed claims, and do not repeat
`claim_id` values. Every `proof_audits[].claim_id` must also appear in
`claims_reviewed`.

## Theorem-Bearing Classification

Treat theorem-bearing status from the full Stage 1 Paper `ClaimRecord`, not from the `ProjectContract` `ContractClaim` vocabulary and not only non-empty theorem metadata. Only
`claim_kind: theorem | lemma | corollary | proposition` is theorem-bearing by
kind alone; `claim_kind: claim | result | other` becomes theorem-bearing only
when theorem metadata or theorem-like text makes the proof obligation explicit.

The theorem-style `claim_kind` values are limited to `theorem`, `lemma`, `corollary`, and `proposition`. Do not treat `claim_kind: claim` as theorem-bearing by default. This Paper `ClaimRecord` rule is intentionally different from `ProjectContract.claims[]`, where `claim_kind: claim` is proof-bearing contract vocabulary.

When a claim is theorem-bearing, preserve explicit hypotheses in
`theorem_assumptions[]` and quantified/free target parameters in
`theorem_parameters[]`; do not drop parameters because a later derivation
normalizes or specializes the algebra.

For theorem-bearing reviews, a missing, malformed, wrong-round, wrong-root, or
non-passing same-round `PROOF-REDTEAM{round_suffix}.md` blocks favorable final
recommendations. Stage 3 `proof_audits[]` evidence is necessary but is not a
substitute for the same-round proof-redteam artifact plus strict final-decision
validation.

## Final Artifacts

Final adjudicator schemas are authoritative in:

- `templates/paper/review-ledger-schema.md`
- `templates/paper/referee-decision-schema.md`

Before trusting a final recommendation, validate:

```bash
gpd validate review-ledger ${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json
gpd validate referee-decision ${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json --strict --ledger ${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json
```

`REFEREE-DECISION{round_suffix}.json` `stage_artifacts` may list only the five
canonical `STAGE-*.json` specialist reports for the active round. The final
referee report files are required Stage 6 artifacts, not optional summaries.
