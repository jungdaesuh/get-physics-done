<purpose>
Require latest review-round evidence and proof-review clearance before submission packaging.
</purpose>

<stage_boundary>
This authority starts only after `manuscript_preflight` has refreshed and validated manuscript-root build artifacts. It is read-only and must not package anything.
</stage_boundary>

<process>
<step name="review_gate">
**Require the latest review-round evidence before submission packaging.**

```bash
if [ -n "${ARGUMENTS:-}" ]; then
  REVIEW_GATE_INIT=$(gpd --raw init arxiv-submission --stage review_gate -- "$ARGUMENTS")
else
  REVIEW_GATE_INIT=$(gpd --raw init arxiv-submission --stage review_gate)
fi
if [ $? -ne 0 ]; then
  echo "ERROR: arxiv-submission review_gate init failed: $REVIEW_GATE_INIT"
  exit 1
fi
INIT="$REVIEW_GATE_INIT"
```

Apply `REVIEW_GATE_INIT.staged_loading.field_access_instruction` before reading `REVIEW_GATE_INIT`.

```bash
PAPER_DIR=$(echo "$INIT" | gpd json get .manuscript_root --default "")
MAIN_SOURCE=$(echo "$INIT" | gpd json get .manuscript_entrypoint --default "")
SUBJECT_SLUG=$(echo "$INIT" | gpd json get .publication_subject_slug --default "")
PUBLICATION_ROOT=$(echo "$INIT" | gpd json get .managed_publication_root --default "")
[ -n "$PUBLICATION_ROOT" ] || [ -z "$SUBJECT_SLUG" ] || PUBLICATION_ROOT="GPD/publication/${SUBJECT_SLUG}"
REVIEW_ROOT=$(echo "$INIT" | gpd json get .selected_review_root --default GPD/review)
```

Load the shared latest-round publication contract from `{GPD_INSTALL_DIR}/references/publication/publication-review-round-artifacts.md`.
Load the staged `peer-review-reliability.md` reference only as a conditional
authority when strict preflight reports degraded review integrity or review-gate
recovery/debug needs expanded reliability guidance.

Require the latest staged `REVIEW-LEDGER*.json` and `REFEREE-DECISION*.json` pair for the active manuscript. Packaging may continue only when the latest recommendation is `accept` or `minor_revision` and there are no unresolved blocking issues.
Strict preflight also requires the latest round-specific staged `REVIEW-LEDGER*.json` / `REFEREE-DECISION*.json` pair as authoritative submission-gate input.
If newest round artifacts are `AUTHOR-RESPONSE*.md` / `REFEREE_RESPONSE*.md` but no newer staged `REVIEW-LEDGER*.json` / `REFEREE-DECISION*.json` pair exists, STOP and route back to `gpd:peer-review`. This all-response freshness policy treats response artifacts as revision records, not staged review clearance, until durable manuscript-change scope metadata exists.

If the manuscript is theorem-bearing, `manuscript_proof_review` must also already be cleared. Require a current `PROOF-REDTEAM*.md` artifact. A stale or missing proof review is a hard stop.

Do not mix round suffixes across review artifacts, response artifacts, or manuscript-root outputs.
</step>

<step name="handoff_to_package">
After review-gate clearance passes, reload `package` and start from its staged payload.
</step>

</process>
