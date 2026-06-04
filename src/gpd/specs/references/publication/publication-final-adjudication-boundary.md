---
load_when:
  - "Stage 6 final adjudication"
  - "final referee decision"
  - "referee-decision validation"
  - "proof-redteam clearance"
type: publication-final-adjudication-boundary
tier: 2
context_cost: low
---

# Publication Final Adjudication Boundary

Compact Stage 6 reference for the final `gpd-referee` adjudication pass. This reference is additive: the workflow callsite and referee prompt must still keep the local write allowlist, strict validators, proof-redteam gate, selected-root routing, and fresh `gpd_return.files_written` gate visible.

## Selected Roots

Derive every Stage 6 output from the invoking workflow's selected roots:

- `selected_publication_root`
- `selected_review_root`
- `round_suffix`

Default project-backed roots may resolve to `GPD` and `GPD/review`, but managed or explicit external publication subjects bind under the selected subject-owned roots. Do not infer roots from launch cwd or scan global `GPD/review` as a fallback.

## Stage 6 Write Allowlist

Stage 6 may write only the applicable subset of:

- `${selected_publication_root}/REFEREE-REPORT{round_suffix}.md`
- `${selected_publication_root}/REFEREE-REPORT{round_suffix}.tex`
- `${selected_review_root}/REVIEW-LEDGER{round_suffix}.json`
- `${selected_review_root}/REFEREE-DECISION{round_suffix}.json`
- `${selected_publication_root}/CONSISTENCY-REPORT.md` only as a diagnostic sidecar

Treat any fresh `gpd_return.files_written` path outside that set as a failed handoff. Preexisting files are stale unless the same paths appear in fresh `gpd_return.files_written` from the current Stage 6 run and exist on disk.

## Upstream Read-Only Inputs

Never create, rewrite, patch, rename, backfill, or list in `files_written`:

- `${selected_review_root}/CLAIMS{round_suffix}.json`
- any `${selected_review_root}/STAGE-*.json`
- `${selected_review_root}/PROOF-REDTEAM{round_suffix}.md`

If any upstream staged-review artifact is missing, unreadable, malformed, stale, suffix-inconsistent, manuscript-inconsistent, or mutually inconsistent, return `gpd_return.status: blocked`, name the earliest failing upstream stage or artifact, and stop. The optional consistency report may diagnose the inconsistency, but it does not authorize upstream repair.

## Strict Decision Validators

Before trusting a final recommendation, run:

```bash
gpd validate review-ledger ${selected_review_root}/REVIEW-LEDGER{round_suffix}.json
gpd validate referee-decision ${selected_review_root}/REFEREE-DECISION{round_suffix}.json --strict --ledger ${selected_review_root}/REVIEW-LEDGER{round_suffix}.json
```

The strict decision validator must remain the guardrail for blank `manuscript_path`, missing policy fields, noncanonical or mixed-round `stage_artifacts`, `CLAIMS{round_suffix}.json` listed as a stage artifact, unknown blocking issue IDs, and unresolved blocking ledger issues not reflected in the decision.

## Proof-Redteam Clearance

For theorem-bearing review, same-round `${selected_review_root}/PROOF-REDTEAM{round_suffix}.md` is mandatory. It must be authored and validated as `gpd-check-proof`, bind to the active manuscript snapshot and round, cover the relevant proof claim IDs and proof artifact paths, report `status: passed`, and support the `REFEREE-DECISION{round_suffix}.json` fields `proof_audit_coverage_complete` and `theorem_proof_alignment_adequate`.

Stage-review validation alone is not proof-redteam clearance. Missing or invalid proof-redteam evidence is a blocking stage-integrity failure, not a Stage 6 repair opportunity.

## Final Report And Decision Alignment

Align markdown report, ledger, and decision on recommendation, confidence, issue IDs, blocking issues, and counts. Artifacts are the source of truth.
