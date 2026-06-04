<purpose>
Own response-round closeout, final artifact consistency checks, commit file selection, next-command routing, anti-pattern review, and success criteria.
</purpose>

<stage_boundary>
Load this stage only after response authoring has produced or inspected the canonical response pair. Finalize may verify and commit response/manuscript artifacts and route the next publication command. It should rely on the completed response pair and final-stage checks instead of reloading response-authoring authority.
</stage_boundary>

<process>

<step name="commit_and_present">
Load the finalize stage before closeout checks and next-command routing:

```bash
if [ -n "${ARGUMENTS:-}" ]; then FINALIZE_INIT=$(gpd --raw init respond-to-referees --stage finalize -- "$ARGUMENTS"); else FINALIZE_INIT=$(gpd --raw init respond-to-referees --stage finalize); fi
if [ $? -ne 0 ]; then echo "ERROR: respond-to-referees finalize init failed: $FINALIZE_INIT"; fi
INIT="$FINALIZE_INIT"
```

<field_access>
Apply `FINALIZE_INIT.staged_loading.field_access_instruction` before reading `FINALIZE_INIT`. Read exact response files before closeout.
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

**Commit all revision artifacts:**

```bash
COMMIT_FILES=("${RESPONSE_REFEREE_PATH}" "${RESPONSE_AUTHOR_PATH}")
if [ -f "${PAPER_DIR}/response-letter.tex" ]; then
  COMMIT_FILES+=("${PAPER_DIR}/response-letter.tex")
elif [ -f "${PAPER_DIR}/response-letter.md" ]; then
  COMMIT_FILES+=("${PAPER_DIR}/response-letter.md")
fi
while IFS= read -r FILE; do
  COMMIT_FILES+=("$FILE")
done < <(find "${PAPER_DIR}" -type f -name '*.tex' -print)
while IFS= read -r FILE; do
  COMMIT_FILES+=("$FILE")
done < <(find "${PAPER_DIR}" -type f -name '*.bib' -print)

PRE_CHECK=$(gpd pre-commit-check --files "${COMMIT_FILES[@]}" 2>&1) || true
echo "$PRE_CHECK"

gpd commit \
  "docs: referee response and manuscript revisions" \
  --files "${COMMIT_FILES[@]}"
```

**Present completion summary:** report response counts, new-calculation status, manuscript/response-letter/compile status, canonical response paths, optional local response letter, and revised manuscript files.

Closeout routing:

| Round result | Next step |
|---|---|
| response-only, no manuscript/figure/citation/reproducibility changes | `package_state: not_applicable`; after citation/claim evidence is inspected and strict preflight agrees, `gpd:arxiv-submission <resolved-manuscript>` |
| manuscript/figure/citation/evidence changed | fresh `gpd:peer-review` before any `gpd:arxiv-submission` |
| citation or claim evidence not inspected | `bibliography_gate`, `claim_evidence_gate`, or `gpd:peer-review`; do not claim arXiv readiness |
| new calculations pending | `gpd:plan-phase {N}`, `gpd:execute-phase {N}`, then `gpd:respond-to-referees` |

Use the documented positional arXiv form only: `gpd:arxiv-submission <resolved-manuscript>`; for example, `gpd:arxiv-submission paper/curvature_flow_bounds.tex`. Do not use bare `gpd:arxiv-submission` or invent `--manuscript`.

</step>

</process>

<anti_patterns>

- Don't ignore any referee comment, even trivial ones -- every point gets a response
- Don't be defensive or dismissive in responses (even when the referee is wrong)
- Don't make changes beyond what the referee requests (scope creep introduces new issues)
- Don't rewrite entire sections when a targeted edit suffices
- Don't skip the compilation check after revisions
- Don't submit without completing all "must address" items
- Don't generate the optional manuscript-local response letter companion before all Group A and B items are drafted
</anti_patterns>

<success_criteria>

- [ ] Referee reports parsed and structured
- [ ] All comments categorized (physics concern, clarity, etc.) and prioritized
- [ ] `${RESPONSE_REFEREE_PATH}` and `${RESPONSE_AUTHOR_PATH}` created with complete point-by-point structure
- [ ] Comments triaged into Groups A (response-only), B (revision), C (new calculation)
- [ ] Group C items routed to research phases (if any)
- [ ] All Group A responses drafted
- [ ] All Group B revisions applied via paper-writer agents
- [ ] Revised manuscript compiles without errors
- [ ] Internal consistency verified after revisions (max 3 iterations)
- [ ] Canonical response artifacts under the selected GPD publication/review roots finalized, with an optional manuscript-local response letter generated only when requested
- [ ] All artifacts committed
- [ ] Manuscript-changing rounds route back through `gpd:peer-review` before `gpd:arxiv-submission`
- [ ] User informed of next steps (resubmission or pending calculations)
</success_criteria>
