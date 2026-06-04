<purpose>
Own referee report ingestion, active-round detection, latest-round artifact discovery, decision-artifact calibration, and parsed issue inventory before revision planning authority can load.
</purpose>

<stage_boundary>
Load this stage only after bootstrap resolves the manuscript subject and selected response roots. This stage may read referee reports, latest review artifacts, and the eagerly loaded `publication-response-writer-handoff.md`. Load `{GPD_INSTALL_DIR}/references/publication/peer-review-reliability.md` or `stage-recovery-gate.md` only through the matching conditional authority when integrity recovery or checkpoint recovery is actually needed.

This stage is read-only. It must not create response artifacts, load response templates, edit the manuscript, spawn paper-writer agents, or run finalization gates.
</stage_boundary>

<process>

<step name="parse_referee_reports">
Load the report-triage stage before parsing referee reports or latest-round artifacts:

```bash
if [ -n "${ARGUMENTS:-}" ]; then REPORT_TRIAGE_INIT=$(gpd --raw init respond-to-referees --stage report_triage -- "$ARGUMENTS"); else REPORT_TRIAGE_INIT=$(gpd --raw init respond-to-referees --stage report_triage); fi
if [ $? -ne 0 ]; then echo "ERROR: respond-to-referees report-triage init failed: $REPORT_TRIAGE_INIT"; fi
INIT="$REPORT_TRIAGE_INIT"
```

<field_access>
Apply `REPORT_TRIAGE_INIT.staged_loading.field_access_instruction` before reading `REPORT_TRIAGE_INIT`. Select report/round before evidence bodies load.
</field_access>

```bash
RESPONSE_ARGUMENTS=$(echo "$INIT" | gpd json get .response_intake_input --default "")
PAPER_DIR=$(echo "$INIT" | gpd json get .manuscript_root --default "")
MANUSCRIPT_ENTRYPOINT=$(echo "$INIT" | gpd json get .manuscript_entrypoint --default "")
MANUSCRIPT_BASENAME="${MANUSCRIPT_ENTRYPOINT##*/}"
RESPONSE_PUBLICATION_ROOT=$(echo "$INIT" | gpd json get .selected_publication_root --default GPD)
RESPONSE_REVIEW_ROOT=$(echo "$INIT" | gpd json get .selected_review_root --default "")
RESPONSE_REVIEW_ROOT="${RESPONSE_REVIEW_ROOT:-${RESPONSE_PUBLICATION_ROOT}/review}"
ROUND_SUFFIX=$(echo "$INIT" | gpd json get .latest_response_round_suffix --default "")
ROUND_SUFFIX="${ROUND_SUFFIX:-$(echo "$INIT" | gpd json get .latest_review_round_suffix --default "")}"
RESPONSE_AUTHOR_PATH=$(echo "$INIT" | gpd json get .latest_author_response --default "")
RESPONSE_AUTHOR_PATH="${RESPONSE_AUTHOR_PATH:-${RESPONSE_PUBLICATION_ROOT}/AUTHOR-RESPONSE${ROUND_SUFFIX}.md}"
RESPONSE_REFEREE_PATH=$(echo "$INIT" | gpd json get .latest_referee_response --default "")
RESPONSE_REFEREE_PATH="${RESPONSE_REFEREE_PATH:-${RESPONSE_REVIEW_ROOT}/REFEREE_RESPONSE${ROUND_SUFFIX}.md}"
```

Apply `{GPD_INSTALL_DIR}/references/publication/publication-response-writer-handoff.md` from this stage exactly.
Use that shared handoff for `round_suffix`, sibling-artifact discovery, and the canonical response-artifact pair for the active round.
If latest-round artifacts are inconsistent, stale, or partially written, load the
`review_integrity_recovery_needed` conditional authority before diagnosing the
round. If a checkpoint or child-return recovery path is reached, load
`checkpoint_or_child_recovery_needed` before presenting recovery choices.

**Obtain referee reports from the user:**

Accepted report sources: explicit `--report PATH` inputs, pasted text, canonical `${RESPONSE_PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.md`, or one positional report path only when the manuscript subject resolves from the current GPD project.

If the active report source is external to the canonical round artifact set, import or normalize it into `${RESPONSE_PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.md` before parsing comments. Use that canonical Markdown file as the durable issue-ID source for the rest of the workflow. Do not keep manuscript-local or external `AUTHOR-RESPONSE*` / `REFEREE_RESPONSE*` sidecars beside the source report.

**Parse each referee's comments into structured items:**

For each comment, extract:

- **Referee number** (1, 2, 3, ...)
- **Comment number** (sequential within referee)
- **Full text** of the comment
- **Category:** Physics concern | Clarity | Missing reference | Technical error | Presentation | Additional calculation requested
- **Priority:** Must address (could lead to rejection) | Should address (editor expects it) | Optional (nice to have)
- **Affected section(s):** Which manuscript section(s) the comment targets

**Also parse editor comments** (if present) as a separate section -- editor guidance often indicates which referee points are critical vs. optional.

**If staged peer-review artifacts exist, extract additional decision context:**

- Final recommendation from `REFEREE-DECISION*.json`
- Blocking issues and unresolved issue IDs from `REVIEW-LEDGER*.json`
- Any finding that the paper's claim scope outruns the evidence, that physical interpretation is unsupported, or that venue fit/significance is inadequate

Do not invent new `REF-*` identifiers from the JSON artifacts. Instead, use them to prioritize and calibrate the responses to the issues already surfaced in the canonical `${RESPONSE_PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.md`.

Present the parsed structure. Ask for explicit user confirmation only in supervised mode or when the report source is ambiguous; balanced mode should treat the parse as working context and continue unless ambiguity or missing source requires a checkpoint:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 GPD > REFEREE REPORTS PARSED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Editor decision:** {Major revision / Minor revision / Reject and resubmit}

| Referee | Comments | Must Address | New Calc Needed |
|---------|----------|-------------|-----------------|
| Referee 1 | {N} | {M} | {K} |
| Referee 2 | {N} | {M} | {K} |

### Critical Points (Must Address)

1.{N}: {brief summary} — {affected section}
2.{N}: {brief summary} — {affected section}
...

### Decision Context (if available)

- Recommendation floor: {major_revision / reject / etc.}
- Blocking issues from review ledger: {count}
- Central claims needing narrowed scope or stronger support: {summary}

Confirm parsing is correct, or paste corrections.
```

</step>

</process>
