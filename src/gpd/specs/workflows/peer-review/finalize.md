<purpose>
Own completed-review summarization, optional PDF note, and next-action routing.
</purpose>

<stage_boundary>
Finalize is read-only. It reads completed target-bound review artifacts and tells the
user what to do next. It does not mutate manuscript files, rewrite upstream stage
artifacts, author response packages, or change the final recommendation.
</stage_boundary>

<optional_pdf_compile>
If TeX is missing, do not block review: Continue now with
`${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.md` and
`${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.tex` only. If a polished PDF is
required, ask the user to choose whether to authorize TeX installation now or compile
the `.tex` later in an environment that already has TeX.
If a polished PDF is required, ask whether to install TeX now or compile later.
</optional_pdf_compile>

<summarize_report>
Load the staged finalize payload before summarizing the report and routing the next
action:

```bash
if [ -n "${ARGUMENTS:-}" ]; then FINALIZE_INIT=$(gpd --raw init peer-review --stage finalize -- "$ARGUMENTS"); else FINALIZE_INIT=$(gpd --raw init peer-review --stage finalize); fi
if [ $? -ne 0 ]; then echo "ERROR: gpd peer-review finalize init failed: $FINALIZE_INIT"; fi
INIT="$FINALIZE_INIT"
```

Apply `FINALIZE_INIT.staged_loading.field_access_instruction` before reading it.

```bash
REVIEW_TARGET=$(echo "$INIT" | gpd json get .review_target_input --default "")
PUBLICATION_ROOT=$(echo "$INIT" | gpd json get .selected_publication_root --default GPD)
REVIEW_ROOT=$(echo "$INIT" | gpd json get .selected_review_root --default "")
REVIEW_ROOT="${REVIEW_ROOT:-${PUBLICATION_ROOT}/review}"
ROUND_SUFFIX=$(echo "$INIT" | gpd json get .latest_review_round_suffix --default "")
REPORT_PATH=$(echo "$INIT" | gpd json get .latest_referee_report_md --default "")
REPORT_PATH="${REPORT_PATH:-${PUBLICATION_ROOT}/REFEREE-REPORT${ROUND_SUFFIX}.md}"
REPORT_TEX_PATH=$(echo "$INIT" | gpd json get .latest_referee_report_tex --default "")
REPORT_TEX_PATH="${REPORT_TEX_PATH:-${PUBLICATION_ROOT}/REFEREE-REPORT${ROUND_SUFFIX}.tex}"
LATEST_RESPONSE_SUFFIX=$(echo "$INIT" | gpd json get .latest_response_round_suffix --default "")
LATEST_AUTHOR_RESPONSE=$(echo "$INIT" | gpd json get .latest_author_response --default "")
LATEST_REFEREE_RESPONSE=$(echo "$INIT" | gpd json get .latest_referee_response --default "")
```

Read the target-bound referee report for the active round from `${REPORT_PATH}`
and, when present, `${REPORT_TEX_PATH}`. Treat `latest_referee_report_md` and
`latest_referee_report_tex` from the finalize payload as authoritative before
deriving selected-root fallback paths such as:

- `${PUBLICATION_ROOT}/REFEREE-REPORT.md`
- `${PUBLICATION_ROOT}/REFEREE-REPORT-R2.md`
- `${PUBLICATION_ROOT}/REFEREE-REPORT-R3.md`

Summarize with:

```markdown
## Peer Review Summary

- Recommendation:
- Main blocking issues:
- Proof-redteam status when applicable:
- Stage artifacts:
- Next action:
```
</summarize_report>

<route_next_action>
A completed staged review of a rejected manuscript is still a completed review run.

- `accept` routes toward `gpd:arxiv-submission`.
- `minor_revision` routes to targeted edits or `gpd:respond-to-referees`.
- `major_revision` routes to `gpd:respond-to-referees` with blocking findings.
- `reject` presents highest-severity issues and avoids automatic project authoring for
  standalone explicit-artifact review unless rewriting was explicitly requested.

If the report finds unverified bibliography sources, do not present `BIBLIOGRAPHY-AUDIT.json` with no failed or unverified sources as verified. If the report
finds overclaiming, classify the manuscript claim state as overclaim-blocked rather than evidence-bound; do not turn a terminal `reject` recommendation into an automatic project-authoring command.

Response packages are atomic pairs:

- `latest_author_response` when set, otherwise `${PUBLICATION_ROOT}/AUTHOR-RESPONSE${LATEST_RESPONSE_SUFFIX}.md`
- `latest_referee_response` when set, otherwise `${REVIEW_ROOT}/REFEREE_RESPONSE${LATEST_RESPONSE_SUFFIX}.md`

Same-round or newer response artifacts require a newer staged peer review before
submission packaging.
</route_next_action>
