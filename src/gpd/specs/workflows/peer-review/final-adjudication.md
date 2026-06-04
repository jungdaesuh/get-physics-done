<purpose>
Own Stage 6 final adjudication, referee report writing, review-ledger and
referee-decision validation, and upstream read-only enforcement.
</purpose>

<stage_boundary>
Stage 6 reads prior stage artifacts and spot-checks the manuscript. It may write
only Stage 6-owned adjudication artifacts for this round and must never modify or
list upstream staged-review artifacts in `gpd_return.files_written`.

The manifest loads the Stage 6 boundary, stage-recovery gate, review-ledger
schema, and referee-decision schema. The compact panel contract is conditional
when the upstream stage artifact index needs lookup.
</stage_boundary>

<final_adjudication>
Load staged final-adjudication before spawning `gpd-referee`:

```bash
if [ -n "${ARGUMENTS:-}" ]; then FINAL_ADJUDICATION_INIT=$(gpd --raw init peer-review --stage final_adjudication -- "$ARGUMENTS"); else FINAL_ADJUDICATION_INIT=$(gpd --raw init peer-review --stage final_adjudication); fi
if [ $? -ne 0 ]; then echo "ERROR: gpd peer-review final-adjudication init failed: $FINAL_ADJUDICATION_INIT"; fi
INIT="$FINAL_ADJUDICATION_INIT"
```

Apply `FINAL_ADJUDICATION_INIT.staged_loading.field_access_instruction` before reading it.

```bash
REVIEW_TARGET=$(echo "$INIT" | gpd json get .review_target_input --default "")
PUBLICATION_ROOT=$(echo "$INIT" | gpd json get .selected_publication_root --default GPD)
REVIEW_ROOT=$(echo "$INIT" | gpd json get .selected_review_root --default "")
REVIEW_ROOT="${REVIEW_ROOT:-${PUBLICATION_ROOT}/review}"
```

Spawn `gpd-referee` over persisted artifacts only: selected manuscript path/hash,
`${REVIEW_ROOT}/CLAIMS{round_suffix}.json`, all
`${REVIEW_ROOT}/STAGE-*{round_suffix}.json`, proof-redteam artifact when active,
and target-aware `latest_referee_report_md` / `latest_author_response` for
revision rounds.

Stage 6 writes:

- `${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.md`
- `${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.tex`
- `${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json`
- `${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json`
- `${PUBLICATION_ROOT}/CONSISTENCY-REPORT.md` when supported as a diagnostic sidecar

Stage 6 child gate:

```yaml
child_gate:
  id: "peer_review_stage6_referee"
  role: "gpd-referee"
  required_status: "completed"
  expected_artifacts:
    - "${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.md"
    - "${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.tex"
    - "${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json"
    - "${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json"
    - "${PUBLICATION_ROOT}/CONSISTENCY-REPORT.md when produced"
  validators:
    - "gpd validate review-ledger ${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json"
    - "gpd validate referee-decision ${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json --strict --ledger ${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json"
  failure_route: "stage-recovery-gate -> retry Stage 6-owned artifacts | fail back upstream"
```

Return through `peer_review_stage6_referee`. Do not trust the referee's success
text until that typed return, the on-disk files, and the validators all agree.
</final_adjudication>

<adjudication_rules>
If any required staged-review artifact is missing, malformed, or wrong-round,
STOP before final recommendation and fail back to the earliest failing upstream
stage. Do not repair upstream stage artifacts inside final adjudication.

For proof-bearing claims, a missing, malformed, wrong-round, wrong-root, or
non-passing same-round `${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md` artifact
blocks any favorable recommendation. Recommendation floor: `major_revision` or
`reject`. A passing math stage with aligned `proof_audits[]` is necessary review
evidence but not a substitute for same-round proof-redteam clearance plus strict
referee-decision validation.

Use `publication-final-adjudication-boundary.md` for upstream read-only policy,
strict decision validation, same-round proof-redteam clearance, and fresh
`gpd_return.files_written` enforcement. Keep `manuscript_path` non-empty and
identical across ledger, decision, and staged-review artifacts for this round;
set every strict `REFEREE-DECISION{round_suffix}.json` policy field.

Writable scope is limited to Stage 6-owned report `.md`/`.tex`, ledger,
decision, and optional consistency report. Do not modify
`${REVIEW_ROOT}/CLAIMS{round_suffix}.json`, any `${REVIEW_ROOT}/STAGE-*.json`,
or `${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md`. If those upstream artifacts
are missing, malformed, stale, or inconsistent, return `gpd_return.status:
blocked` and hand failure back instead of repairing it inside Stage 6.

`gpd_return.files_written` stays within the Stage 6 write allowlist; any upstream
path is a failed handoff.
</adjudication_rules>

<stage_recovery_6>
Require both JSON artifacts and both referee report files:

```bash
gpd validate review-ledger ${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json
gpd validate referee-decision ${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json --strict --ledger ${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json
```

For proof-bearing reviews, this strict final-decision validator is the favorable
decision guardrail. Do not treat `gpd validate review-stage-report
${REVIEW_ROOT}/STAGE-math{round_suffix}.json`, even with aligned
`proof_audits[]`, as clearance without same-round
`${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md` plus strict decision validation.

Apply the `peer_review_stage6_referee` tuple and publication stage-recovery gate
before classifying outcome as recovery-eligible, upstream-blocked, or complete.
Only retry Stage 6 for Stage 6-owned artifact failures. If errors point at
`CLAIMS{round_suffix}.json`, `STAGE-*.json`, or
`PROOF-REDTEAM{round_suffix}.md`, STOP fail-closed and rerun the earliest failing
upstream stage. If the eligible Stage 6 retry also fails, do not proceed.

Upstream fail-back table:
- `CLAIMS{round_suffix}.json` or `STAGE-reader{round_suffix}.json` -> rerun Stage 1
- `STAGE-literature{round_suffix}.json` -> rerun Stage 2
- `STAGE-math{round_suffix}.json` or `PROOF-REDTEAM{round_suffix}.md` -> rerun Stage 3 and proof critique when applicable
- `STAGE-physics{round_suffix}.json` -> rerun Stage 4
- `STAGE-interestingness{round_suffix}.json` -> rerun Stage 5

Treat blank `manuscript_path` values in either
`${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json` or
`${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json` as validation failures, not
optional bookkeeping.
</stage_recovery_6>

<handoff>
When Stage 6 validates, reload before final summary and routing:

```bash
if [ -n "$REVIEW_TARGET" ]; then FINALIZE_INIT=$(gpd --raw init peer-review --stage finalize -- "$REVIEW_TARGET"); else FINALIZE_INIT=$(gpd --raw init peer-review --stage finalize); fi
if [ $? -ne 0 ]; then
  echo "ERROR: gpd peer-review finalize init failed: $FINALIZE_INIT"
  # STOP; surface the error.
fi
```
</handoff>
