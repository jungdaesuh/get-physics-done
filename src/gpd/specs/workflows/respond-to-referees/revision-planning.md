<purpose>
Own protocol-bundle handle awareness, comment triage, new-calculation routing, claim narrowing versus new evidence, and scoped revision planning before response-authoring authority can load.
</purpose>

<stage_boundary>
Load this stage only after report triage has selected the active report source and produced a parsed issue inventory. This stage may classify comments and plan manuscript/research work, but it must not load response templates, create response artifacts, spawn paper-writer agents, or run finalization gates.
</stage_boundary>

<process>

<step name="load_specialized_revision_context">
Load the revision-planning stage before classifying comments or routing new work:

```bash
if [ -n "${ARGUMENTS:-}" ]; then REVISION_PLANNING_INIT=$(gpd --raw init respond-to-referees --stage revision_planning -- "$ARGUMENTS"); else REVISION_PLANNING_INIT=$(gpd --raw init respond-to-referees --stage revision_planning); fi
if [ $? -ne 0 ]; then echo "ERROR: respond-to-referees revision-planning init failed: $REVISION_PLANNING_INIT"; fi
INIT="$REVISION_PLANNING_INIT"
```

<field_access>
Apply `REVISION_PLANNING_INIT.staged_loading.field_access_instruction` before reading `REVISION_PLANNING_INIT`. Select reviewer issues from handles before evidence bodies load.
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

- If `selected_protocol_bundle_ids` is non-empty, keep the bundle's decisive artifact expectations, benchmark anchors, estimator caveats, and reference prompts visible while triaging referee requests.
- Use bundle guidance to distinguish "missing decisive evidence we already owed" from "new side quest the referee is asking for."
- Do **not** let bundle guidance justify broader claims, waive review-ledger blockers, or replace the manuscript's actual evidence trail in `GPD/comparisons/*-COMPARISON.md`, `${PAPER_DIR}/FIGURE_TRACKER.md`, phase summary artifacts, or `VERIFICATION.md`.
- Keep revisions tied to claims the manuscript still intends to make. Review ledgers and bundle hints help prioritize, but they do not force new side analyses once honest claim narrowing resolves the concern.
- Use `derived_manuscript_reference_status` as the first-pass triage signal for citation and bibliography changes, but do not let it override the manuscript-root audit or publication-manifest checks.
</step>

<step name="triage_comments">
Use the already loaded revision-planning stage before assigning comments to response-only, manuscript-revision, or new-calculation work.

**Triage comments into actionable categories:**

Sort all comments into three groups:

**Group A -- Text-only responses (no manuscript change needed):**
- Referee misunderstandings that can be clarified in the response letter
- Comments where the current manuscript already addresses the concern
- Requests for clarification that are best handled in the response letter

**Group B -- Manuscript revisions (existing content needs editing):**
- Clarity improvements, additional explanation, notation fixes
- Missing references to add
- Figure improvements, caption changes
- Reorganization of existing material

**Group C -- New calculations required:**
- Additional derivations requested by referee
- New comparisons with published results
- Extended parameter ranges or new limiting cases
- Additional numerical checks or convergence tests

**Mandatory override from staged peer-review artifacts:**

If `REVIEW-LEDGER*.json` or `REFEREE-DECISION*.json` marks an issue as blocking, unsupported, or central to the recommendation floor, classify it as Must Address even if the prose report sounds mild. If the decision artifacts say the paper's claims outrun the evidence, do not triage that as response-only; it requires either manuscript revision, claim narrowing, or new evidence.
Treat referee requests beyond the manuscript's honest scope as optional unless they expose a real support gap for a claim you still want to keep.

Present triage:

```
### Triage Summary

| Group | Count | Action |
|-------|-------|--------|
| A: Response-only | {N} | Draft responses (no manuscript change) |
| B: Manuscript revision | {N} | Spawn paper-writer agents for section edits |
| C: New calculations | {N} | Create research phases via gpd:add-phase |

Group C items require research work before the response can be completed.
Address Group-C new-calculation items first? [Y/n/e]  (Enter = Y; e opens freeform to re-triage)
```

**Edit branch:** If the user chooses `e`, collect revised triage instructions, update the Group-C ordering or classification, and re-present the updated `[Y/n/e]` prompt once before creating phases or changing response trackers. Do not treat the edit text itself as approval.

Track response scope from this triage: Group A-only rounds are response-only; any Group B manuscript edit, Group C calculation/evidence change, figure change, citation change, or reproducibility change makes the round manuscript-changing until proven otherwise.

</step>

<step name="handle_new_calculations">
**For Group C items (new calculations requested by referees):**

If no Group C items: skip to draft_responses.

For each new calculation:

1. Create matching entries in the "New Calculations Summary" sections of `${RESPONSE_REFEREE_PATH}` and `${RESPONSE_AUTHOR_PATH}`
2. Suggest a research phase to execute the calculation:

```
### New Calculations Needed

| ID | Requested By | Description | Suggested Phase |
|----|-------------|-------------|-----------------|
| NC-1 | Referee 1, Comment 3 | Extend to next-to-leading order | gpd:insert-phase {N}.1 |
| NC-2 | Referee 2, Comment 5 | Compare with Monte Carlo results | gpd:add-phase |

Create these phases now? The referee response will be incomplete until
new calculations are done.

Options:
1. Create phases now — then execute them before continuing response
2. Skip for now — draft responses for Groups A and B first, return to C later
3. Mark as "beyond scope" — explain in response why calculation is not feasible
```

If user chooses option 1:

```bash
# For each new calculation, create a phase
gpd phase add "Referee revision: {description}"
```

The user should run `gpd:plan-phase` and `gpd:execute-phase` for each new phase, then return to `gpd:respond-to-referees` to continue.

If the staged decision artifacts indicate that the main problem is overclaiming rather than missing computation, prefer narrowing the claim set or venue framing before creating new research phases.
If selected protocol bundles already identify a decisive comparison, benchmark anchor, or estimator caveat that the manuscript failed to surface, prefer fulfilling that existing obligation or narrowing the claim before creating broader new-computation work.
Do not create new phases solely to satisfy a speculative side quest once narrowing the manuscript claim would fully resolve the issue.

</step>

</process>
