<purpose>
Own manuscript artifact loading, target-aware round detection, response freshness
checks, and proof-bearing routing state before panel agents launch.
</purpose>

<stage_boundary>
Artifact discovery is read-only. It may inspect manuscript and prior round state, but
it does not spawn reviewer agents, write `CLAIMS` or `STAGE-*` artifacts, run the
proof-redteam protocol, adjudicate the recommendation, or route response authoring.
</stage_boundary>

<artifact_discovery>
Read staged init from:

```bash
if [ -n "${ARGUMENTS:-}" ]; then ARTIFACT_DISCOVERY_INIT=$(gpd --raw init peer-review --stage artifact_discovery -- "$ARGUMENTS"); else ARTIFACT_DISCOVERY_INIT=$(gpd --raw init peer-review --stage artifact_discovery); fi
if [ $? -ne 0 ]; then echo "ERROR: gpd peer-review artifact-discovery init failed: $ARTIFACT_DISCOVERY_INIT"; fi
INIT="$ARTIFACT_DISCOVERY_INIT"
```

Apply `ARTIFACT_DISCOVERY_INIT.staged_loading.field_access_instruction` before reading it, then bind the selected manuscript and roots:

```bash
REVIEW_TARGET=$(echo "$INIT" | gpd json get .review_target_input --default "")
MANUSCRIPT_ROOT=$(echo "$INIT" | gpd json get .manuscript_root --default "")
MANUSCRIPT_PATH=$(echo "$INIT" | gpd json get .manuscript_entrypoint --default "")
MANUSCRIPT_PATH="${MANUSCRIPT_PATH:-$(echo "$INIT" | gpd json get .resolved_review_target --default "")}"
RESOLVED_MANUSCRIPT="$MANUSCRIPT_PATH"
PUBLICATION_ROOT=$(echo "$INIT" | gpd json get .selected_publication_root --default GPD)
REVIEW_ROOT=$(echo "$INIT" | gpd json get .selected_review_root --default "")
REVIEW_ROOT="${REVIEW_ROOT:-${PUBLICATION_ROOT}/review}"
```

After resolution, read only the selected manuscript surface and manuscript-local
support artifacts from the same explicit manuscript directory. Do not discover a
different manuscript by scanning. Preserve the active `manuscript_path` and
`manuscript_sha256` for downstream claim and referee artifacts.
After resolution, manuscript-local support artifacts stay rooted in the same
explicit manuscript directory.
BIBLIOGRAPHY_AUDIT_PATH and `bibliography_audit_path` resolve to
`${MANUSCRIPT_ROOT}/BIBLIOGRAPHY-AUDIT.json` when manuscript-local support exists.

Accepted explicit artifacts are `.tex`, `.md`, `.txt`, `.pdf`, `.docx`, `.csv`,
`.tsv`, `.xlsx`, and `.xlsm`; a manuscript directory path is allowed when it
resolves to one current entrypoint. For `.pdf`, `.docx`, `.xlsx`, or `.xlsm`,
first look for a nearby `.txt` companion. If none exists, create
`${REVIEW_ROOT}/` if needed, run
`gpd validate artifact-text "$RESOLVED_MANUSCRIPT" --output ${REVIEW_ROOT}/MANUSCRIPT-TEXT.txt`,
and use that extracted file while keeping the original artifact as canonical
`RESOLVED_MANUSCRIPT`. If extraction fails, STOP and ask for `.txt`, `.md`,
`.tex`, `.csv`, `.tsv`, or a matching extracted `.txt` companion file.
</artifact_discovery>

<proof_bearing_routing>
Classify proof-bearing routing state from manuscript/formal metadata and later from
the Stage 1 claim record. A generic Paper `ClaimRecord.claim_kind: claim` is not
theorem-bearing by itself; require theorem/proof/formal metadata before routing generic
manuscript claims through proof-redteam.

Do not run the proof critic in artifact discovery. The same-round proof-redteam
requirement is enforced by `panel_stages` and `final_adjudication`.
Use `derived_manuscript_proof_review_status` only as theorem/proof freshness
context; the same-round proof-redteam artifact remains authoritative.
review-support artifacts are scaffolding, not decisive evidence.
</proof_bearing_routing>

<round_detection>
Use the subject-aware `INIT` payload as the source of truth for prior review and
response state. Do not infer rounds by scanning `GPD/REFEREE-REPORT*`,
`GPD/AUTHOR-RESPONSE*`, or `${REVIEW_ROOT}/REFEREE_RESPONSE*` filenames in isolation.

Read from the staged payload:

- `latest_review_round`, `latest_review_round_suffix`, `latest_review_artifacts`
- `latest_referee_decision`, `latest_review_ledger`, `latest_referee_report_md`,
  `latest_referee_report_tex`, `latest_proof_redteam`
- `latest_response_round`, `latest_response_round_suffix`, `latest_response_artifacts`
- `latest_author_response`, `latest_referee_response`

If a complete response bundle exists for a later round than the latest complete review,
start from `latest_response_round + 1`; the response round records manuscript-change
scope that now needs review.

If `INIT` reports a partial or invalid latest review/response bundle, stop fail-closed
and repair it before advancing. A response bundle without a complete target-bound
review bundle is a hard blocker.
Repair the target-bound response artifacts; do not require a response package for
initial review runs.
Do not require a response package for initial review runs.

Use these target-bound round artifact families:

- `${REVIEW_ROOT}/CLAIMS{round_suffix}.json`
- `${REVIEW_ROOT}/STAGE-reader{round_suffix}.json`
- `${REVIEW_ROOT}/STAGE-literature{round_suffix}.json`
- `${REVIEW_ROOT}/STAGE-math{round_suffix}.json`
- `${REVIEW_ROOT}/STAGE-physics{round_suffix}.json`
- `${REVIEW_ROOT}/STAGE-interestingness{round_suffix}.json`
- `${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json`
- `${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json`
- `${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.md`
- `${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.tex`

Use the same `-R2` / `-R3` suffix convention for downstream response artifacts:

- `${PUBLICATION_ROOT}/AUTHOR-RESPONSE{round_suffix}.md`
- `${REVIEW_ROOT}/REFEREE_RESPONSE{round_suffix}.md`
</round_detection>

<handoff>
After target artifacts and round state are resolved, reload before launching the panel:

```bash
if [ -n "$REVIEW_TARGET" ]; then PANEL_INIT=$(gpd --raw init peer-review --stage panel_stages -- "$REVIEW_TARGET"); else PANEL_INIT=$(gpd --raw init peer-review --stage panel_stages); fi
if [ $? -ne 0 ]; then
  echo "ERROR: gpd peer-review panel init failed: $PANEL_INIT"
  # STOP; surface the error.
fi
```
</handoff>
