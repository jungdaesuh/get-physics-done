<purpose>
Own response artifact pair creation, response-template use, synchronized
manuscript edits, paper-writer revision handoffs, bounded verification,
bibliography freshness, and optional manuscript-local response-letter export.
</purpose>

<first_route>
First bind the current-round response pair to `selected_publication_root` and
`selected_review_root`; never write beside `${PAPER_DIR}` or duplicate the pair
across roots in one run.
</first_route>

<stage_boundary>
Load this stage only after revision planning has classified referee points and
routed new-calculation work. This is the first stage allowed to load
`templates/paper/author-response.md`, `templates/paper/referee-response.md`, and
response-writing child handoff authority.

This stage may write the canonical response pair and manuscript revisions under
the manifest write allowlist. It must not run final commit/closeout routing until
finalize loads.
</stage_boundary>

<process>

<step name="create_response_file">
Reload the planning stage before authoring so classification and artifacts share
the same staged authority order:

```bash
if [ -n "${ARGUMENTS:-}" ]; then REVISION_PLANNING_INIT=$(gpd --raw init respond-to-referees --stage revision_planning -- "$ARGUMENTS"); else REVISION_PLANNING_INIT=$(gpd --raw init respond-to-referees --stage revision_planning); fi
if [ $? -ne 0 ]; then echo "ERROR: respond-to-referees revision-planning init failed: $REVISION_PLANNING_INIT"; fi
INIT="$REVISION_PLANNING_INIT"
```

<field_access>
Apply `REVISION_PLANNING_INIT.staged_loading.field_access_instruction` before reading `REVISION_PLANNING_INIT`. Preserve triage; do not draft evidence prose here.
</field_access>

Load response-authoring before any response artifact or manuscript write:

```bash
if [ -n "${ARGUMENTS:-}" ]; then RESPONSE_AUTHORING_INIT=$(gpd --raw init respond-to-referees --stage response_authoring -- "$ARGUMENTS"); else RESPONSE_AUTHORING_INIT=$(gpd --raw init respond-to-referees --stage response_authoring); fi
if [ $? -ne 0 ]; then echo "ERROR: respond-to-referees response-authoring init failed: $RESPONSE_AUTHORING_INIT"; fi
INIT="$RESPONSE_AUTHORING_INIT"
```

<field_access>
Apply `RESPONSE_AUTHORING_INIT.staged_loading.field_access_instruction` before reading `RESPONSE_AUTHORING_INIT`. Use hydrated bodies only for selected evidence-dependent comments.
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

Read `{GPD_INSTALL_DIR}/templates/paper/author-response.md`,
`{GPD_INSTALL_DIR}/templates/paper/referee-response.md`, and the loaded
`publication-response-writer-handoff.md`. Create both current-round artifacts:

- `${RESPONSE_AUTHOR_PATH}`: internal tracker keyed by `REF-*` issue,
  classification, change location, staged-review outcome, and new-work status.
- `${RESPONSE_REFEREE_PATH}`: journal-facing response letter.

Use `selected_publication_root` / `selected_review_root`. Do not write
`AUTHOR-RESPONSE*` or `REFEREE_RESPONSE*` beside `${PAPER_DIR}` or an imported
report source. Do not duplicate the pair across a subject-owned root and the
global project root in one run.

Populate metadata, round binding, issue ids, recommendation-floor context from
`REVIEW-LEDGER*.json` or `REFEREE-DECISION*.json`, and empty response/change
fields. Use `**Evidence:**` for rebuttals and `**Plan:**` for acknowledged or
`needs-calculation` responses.

```bash
PRE_CHECK=$(gpd pre-commit-check --files "${RESPONSE_REFEREE_PATH}" "${RESPONSE_AUTHOR_PATH}" 2>&1) || true
echo "$PRE_CHECK"

gpd commit \
  "docs: create referee response structure" \
  --files "${RESPONSE_REFEREE_PATH}" "${RESPONSE_AUTHOR_PATH}"
```

Treat `${RESPONSE_AUTHOR_PATH}` and `${RESPONSE_REFEREE_PATH}` as the response
success gate. The pair is `current` only when same-round target-bound artifacts
bind to the resolved manuscript/round with no material writes
(`command_execution_state: read_only_inspection`). It is `completed_this_run`
only when both paths were written/refreshed by this invocation or a fresh child
handoff and named in current-run `files_written` / `gpd_return.files_written`;
stale drafts or one-sided files do not count.
</step>

<step name="draft_responses">
If init exposes `protocol_bundle_context` and `selected_protocol_bundle_ids`,
treat them only as additive guidance for benchmark anchors, decisive artifacts,
and estimator caveats; they do not create new claims or replace the review
ledger.

```bash
WRITER_MODEL=$(gpd resolve-model gpd-paper-writer)
```

For Group A response-only items, quote the referee, assess correctness, draft a
specific respectful response, mark "No manuscript change needed", and mirror the
journal-facing prose into `${RESPONSE_REFEREE_PATH}`.

For Group B manuscript revisions, group comments by resolved section file within
the manuscript tree rooted at `${PAPER_DIR}`, load the manifest conditional
`{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md` when
`writer_spawn_needed`, and spawn one paper-writer per section:

```
task(
  prompt="First, read {GPD_AGENTS_DIR}/gpd-paper-writer.md for your role and instructions. Then read both response templates and publication-response-writer-handoff.md. Make manuscript edits first, update both response trackers for the same comments, and return through `respond_to_referees_revision_section` naming the revised section plus `${RESPONSE_AUTHOR_PATH}` and `${RESPONSE_REFEREE_PATH}`.\n\n<autonomy_mode>{AUTONOMY}</autonomy_mode>\n<research_mode>{RESEARCH_MODE}</research_mode>\n" + revision_prompt,
  subagent_type="gpd-paper-writer",
  model="{writer_model}",
  readonly=false,
  description="Revise: {section_name}"
)
```

Revision-section child gate:

```yaml
child_gate:
  id: "respond_to_referees_revision_section"
  role: "gpd-paper-writer"
  return_profile: "response_writer"
  required_status: "completed"
  expected_artifacts:
    - "${PAPER_DIR}/{resolved_section_file}"
    - "${RESPONSE_AUTHOR_PATH}"
    - "${RESPONSE_REFEREE_PATH}"
  allowed_roots:
    - "${PAPER_DIR}"
    - "${selected_publication_root}"
    - "${selected_review_root}"
  freshness_marker: "after $REVISION_SECTION_HANDOFF_STARTED_AT"
  validators:
    - "gpd validate handoff-artifacts for revised section plus both response artifacts"
    - "publication-response-writer-handoff.md frontmatter, round, and manuscript binding"
    - "target section has expected revision markers or substantive edits"
    - "affected comment block updated in both response artifacts"
  applicator: "none"
  failure_route: "continue other sections, then retry failed sections | main-context targeted revision | skip failed sections; checkpoint -> stage-recovery gate and fresh continuation"
```

Each revision agent receives exact comments, current section text, planned
strategy, relevant comparisons/figure tracker entries, and the minimal
targeted-edit rule. Mark changed text with `% REVISED: Referee X, Comment Y`.
If a spawned agent returns `status: checkpoint` or needs user input, apply the
publication stage-recovery gate and continue only from persisted artifacts after
the user responds.

After each return, apply the tuple first. Re-read the section under
`${PAPER_DIR}`, `${RESPONSE_AUTHOR_PATH}`, and `${RESPONSE_REFEREE_PATH}`. If
section edits and tracker updates are not both fresh and consistent, classify
that section as failed and retry/manual/skip via the gate; do not silently
proceed. When checks pass, fill exact change locations and set status to
"Response drafted" in both response artifacts.
</step>

<step name="revision_loop">
Bounded revision verification has at most three consistency iterations after
all Group B edits land:

```bash
cd "${PAPER_DIR}"
pdflatex -interaction=nonstopmode "${MANUSCRIPT_BASENAME}" 2>&1 | tail -20
bibtex "${MANUSCRIPT_BASENAME%.*}" 2>&1 | tail -10
pdflatex -interaction=nonstopmode "${MANUSCRIPT_BASENAME}" 2>&1 | tail -5
```

Compilation-error fixes do not count as iterations. Each counted iteration
checks notation, equation/figure references, citation metadata/markers, touched
comparison verdicts/benchmark anchors, and bibliography freshness. If
bibliography files or citation commands changed, refresh
`${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json` via `gpd paper-build`; use
`derived_manuscript_reference_status` only as a quick read. Confirm the refreshed
JSON artifact exists before treating the round as complete.

If inconsistencies remain and iteration < 3, spawn targeted paper-writers. At
iteration 3, present the remaining issues and offer to proceed with a note or
manual fix.
</step>

<step name="generate_response_letter">
Before completion, read both canonical response files and require every comment
to be "Response drafted" or "Final". The loaded publication response-writer
handoff owns pair freshness and binding.

```yaml
aggregate_child_gate:
  id: respond_to_referees_response_pair_current
  required_child_gates:
    - respond_to_referees_revision_section for every launched Group B section
  expected_artifacts:
    - every required revised section under ${PAPER_DIR}
    - ${RESPONSE_AUTHOR_PATH}
    - ${RESPONSE_REFEREE_PATH}
  validators:
    - expected mirrored artifacts exist on disk
    - response frontmatter binds to the active manuscript path and review round when the subject is explicit
    - every launched section tuple passed with current section and response artifacts
  failure_route: retry failed sections | main-context targeted revision | leave response pair incomplete
```

Those two Markdown artifacts under selected GPD publication/review roots are the
required outputs. `${PAPER_DIR}/response-letter.tex` or
`${PAPER_DIR}/response-letter.md` is optional. If the manuscript subject is an
explicit external artifact, keep auxiliary response outputs under the selected
GPD roots, not beside that external manuscript. Subject-owned publication roots
follow the same rule.

If Group C items remain, warn that the response is incomplete until
`gpd:execute-phase` finishes them. When a project-backed manuscript needs a
local companion, write editor thanks, per-referee/per-comment quotes,
responses, concrete changes, major/minor summary, and signature.
</step>

</process>
