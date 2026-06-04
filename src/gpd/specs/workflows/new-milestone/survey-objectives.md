<purpose>
Survey milestone goals, optionally refresh the literature landscape, and define scoped research objectives for the new milestone.
</purpose>

<process>

Refresh the survey/objectives stage before gathering milestone goals:

```bash
SURVEY_INIT=$(gpd --raw init new-milestone --stage survey_objectives)
if [ $? -ne 0 ]; then
  echo "ERROR: survey/objectives init failed: $SURVEY_INIT"
  exit 1
fi
```

Apply `SURVEY_INIT.staged_loading.field_access_instruction` before reading the survey/objectives payload.

Treat `effective_reference_intake`, `contract_intake`, and `reference_artifact_files` from this survey/objectives init as binding carry-forward handles even when `project_contract` is empty or blocked.

Before defining scope, inspect and preserve the carry-forward keys in
`effective_reference_intake` (`must_read_refs`, prior outputs, user anchors,
baselines, context gaps, crucial inputs) plus `contract_intake`.

If `reference_artifact_files` is non-empty, read the listed reference artifact handles when they are relevant. This handle-first stage does not receive embedded artifact bodies.
Read planning documents by path when their text is needed: `GPD/PROJECT.md`, `GPD/STATE.md`, `GPD/state.json`, and `GPD/MILESTONES.md`.

## 2. Gather Milestone Goals

If `MILESTONE-CONTEXT.md` exists, summarize its directions and confirm. If not,
summarize the previous milestone and ask: "What do you want to investigate
next?" Probe only enough to classify the milestone as analytical extension,
numerical validation, phenomenology, paper preparation, peer-review response, or
another explicit user direction.

## 3. Determine Milestone Version

- Parse last version from MILESTONES.md
- Suggest next version (v1.0 -> v1.1 for incremental, v2.0 for major new direction)
- Confirm with user

## 4. Update PROJECT.md

Add/update the current milestone block in `GPD/PROJECT.md`:

```markdown
## Current Milestone: v[X.Y] [Name]

**Goal:** [One sentence describing milestone focus]

**Target results:**

- [Result 1]
- [Result 2]
- [Result 3]
```

Update active research questions and the "Last updated" footer.

## 5. Update project state

Update STATE.md position fields via gpd (ensures state.json sync):

```bash
gpd state patch \
  "--Status" "Planning" \
  "--Last Activity" "$(date +%Y-%m-%d)"

gpd state add-decision \
  --phase "0" \
  --summary "Started milestone v{milestone_version}: {milestone_name}" \
  --rationale "New milestone cycle"
```

Keep accumulated context from previous milestones.

## 6. Cleanup and Commit

Delete MILESTONE-CONTEXT.md if exists (consumed).
Honor `planning.commit_docs` from init internally when deciding whether milestone artifacts are committed.

```bash
PRE_CHECK=$(gpd pre-commit-check --files GPD/PROJECT.md GPD/STATE.md 2>&1) || true
echo "$PRE_CHECK"

gpd commit "docs: start milestone v[X.Y] [Name]" --files GPD/PROJECT.md GPD/STATE.md
```

## 7. Literature Survey Decision

> **Platform note:** If `ask_user` is not available, present these options in plain text and wait for the user's freeform response.

ask_user: "Survey the research landscape for new investigations before defining objectives?"

- "Survey first (Recommended)" — Discover new results, methods, and open problems for NEW directions
- "Skip survey" — Go straight to objectives

**Persist choice to config** (so future `gpd:plan-phase` honors it):

```bash
# If "Survey first": persist true
gpd config set workflow.research true

# If "Skip survey": persist false
gpd config set workflow.research false
```

**If "Survey first":** create `GPD/literature` and spawn 4 literature scouts
in parallel: Prior Work, Methods, Computational, Pitfalls.

```bash
mkdir -p GPD/literature
```

Spawn 4 parallel gpd-project-researcher agents. Each uses this template with dimension-specific fields:
@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md

**Common structure for all 4 scouts:**

```
task(prompt="First, read {GPD_AGENTS_DIR}/gpd-project-researcher.md for your role and instructions.

<research_type>Literature Survey — {DIMENSION} for [new research direction].</research_type>

<milestone_context>
SUBSEQUENT MILESTONE — Extending research in [new direction] building on existing results.
{EXISTING_CONTEXT}
Focus ONLY on what's needed for the NEW research questions.
</milestone_context>

<question>{QUESTION}</question>

<project_context>[PROJECT.md summary]</project_context>

<downstream_consumer>{CONSUMER}</downstream_consumer>

<quality_gate>{GATES}</quality_gate>

<output>
Write to: GPD/literature/{FILE}
Use template: {GPD_INSTALL_DIR}/templates/research-project/{FILE}
</output>

<handoff_expectation>
Use the researcher `gpd_return` profile from your role prompt. Local completed output is `GPD/literature/{FILE}`.
</handoff_expectation>
", subagent_type="gpd-project-researcher", model="{researcher_model}", readonly=false, description="{DIMENSION} survey")
```

Add this contract inside each spawned scout prompt when adapting it:

```markdown
<spawn_contract>
write_scope:
  mode: scoped_write
  allowed_paths:
    - GPD/literature/{FILE}
expected_artifacts:
  - GPD/literature/{FILE}
shared_state_policy: return_only
</spawn_contract>
```

Each scout contract is task-local. Do not widen the write scope or reuse a shared survey contract across dimensions.

Dimension mapping:
- Prior Work -> `PRIOR-WORK.md`: new results, conditions, assumptions, references.
- Methods -> `METHODS.md`: viable methods, costs, limitations.
- Computational -> `COMPUTATIONAL.md`: algorithms, dependencies, resource estimates.
- Pitfalls -> `PITFALLS.md`: extension-specific mistakes, warnings, prevention.

**Scout child gate:**

```yaml
child_gate:
  id: "milestone_literature_scouts"
  role: "gpd-project-researcher"
  return_profile: "researcher"
  required_status: "completed"
  expected_artifacts:
    - "GPD/literature/PRIOR-WORK.md"
    - "GPD/literature/METHODS.md"
    - "GPD/literature/COMPUTATIONAL.md"
    - "GPD/literature/PITFALLS.md"
  allowed_roots:
    - "GPD/literature"
  freshness_marker: "after $SCOUT_HANDOFF_STARTED_AT per scout"
  validators:
    - "gpd validate handoff-artifacts - --expected GPD/literature/{FILE} --allowed-root GPD/literature --require-status completed --require-files-written --fresh-after \"$SCOUT_HANDOFF_STARTED_AT\""
    - "readable artifact check for GPD/literature/{FILE}"
  applicator: none
  failure_route: "retry missing scout once | repair prompt once | stop survey path | retry missing scout once in the same task-local write scope | repair path once | fail closed | ..."
```

Route `checkpoint`, `blocked`, or final `failed` through
`references/orchestration/child-artifact-gate.md` and
`references/orchestration/continuation-boundary.md` to `## > Next Up` primary
`gpd:new-milestone [milestone name]`, also `gpd:suggest-next`. Do not count a
scout as complete until the tuple passes.

After all 4 complete and required artifacts are present, spawn synthesizer:

```
task(prompt="First, read {GPD_AGENTS_DIR}/gpd-research-synthesizer.md for your role and instructions.

<task>
Synthesize literature survey outputs into SUMMARY.md.
</task>

<files_to_read>
Read these files using the file_read tool:
- GPD/PROJECT.md
- GPD/state.json
- GPD/config.json
- GPD/MILESTONES.md (if exists, skip if not found)
- GPD/literature/PRIOR-WORK.md
- GPD/literature/METHODS.md
- GPD/literature/COMPUTATIONAL.md
- GPD/literature/PITFALLS.md
- GPD/literature/SUMMARY.md (if re-synthesizing an existing survey)
- Files named in `effective_reference_intake.must_include_prior_outputs` when they exist
- Files named in `reference_artifact_files` when they exist and are relevant to summary coverage
</files_to_read>

<survey_context>
Contract intake: {contract_intake}
Effective reference intake: {effective_reference_intake}
Reference artifact file handles: {reference_artifact_files}
Planning file paths: GPD/PROJECT.md, GPD/STATE.md, GPD/state.json, GPD/MILESTONES.md
</survey_context>

<output>
Write to: GPD/literature/SUMMARY.md
Use template: {GPD_INSTALL_DIR}/templates/research-project/SUMMARY.md
Do NOT commit — the orchestrator handles commits.
</output>

<handoff_expectation>
Use the synthesizer `gpd_return` profile from your role prompt. Local completed output is `GPD/literature/SUMMARY.md`.
</handoff_expectation>
", subagent_type="gpd-research-synthesizer", model="{synthesizer_model}", readonly=false, description="Synthesize literature survey")
```

Add this contract inside the spawned synthesizer prompt when adapting it:

```markdown
<spawn_contract>
write_scope:
  mode: scoped_write
  allowed_paths:
    - GPD/literature/SUMMARY.md
expected_artifacts:
  - GPD/literature/SUMMARY.md
shared_state_policy: return_only
</spawn_contract>
```

This synthesizer contract is task-local. Do not reuse survey write scopes or widen the summary handoff.

**Synthesizer child gate:**

```yaml
child_gate:
  id: "milestone_literature_synthesizer"
  role: "gpd-research-synthesizer"
  return_profile: "synthesizer"
  required_status: "completed"
  expected_artifacts:
    - "GPD/literature/SUMMARY.md"
  allowed_roots:
    - "GPD/literature"
  freshness_marker: "after $SYNTHESIZER_HANDOFF_STARTED_AT"
  validators:
    - "gpd validate handoff-artifacts - --expected GPD/literature/SUMMARY.md --allowed-root GPD/literature --require-status completed --require-files-written --fresh-after \"$SYNTHESIZER_HANDOFF_STARTED_AT\""
    - "readable SUMMARY.md"
  applicator: none
  failure_route: "retry once | repair prompt once | stop synth path | repair path once | fail closed | stop; no stale SUMMARY.md or partial scout synthesis | ..."
```

Route `checkpoint`, `blocked`, or final `failed` through the gate to
`## > Next Up` primary `gpd:new-milestone [milestone name]`, also
`gpd:suggest-next`. Do not display or commit `SUMMARY.md`, create it in the
main context, or use a stale summary unless the fresh return names it and the
tuple passes.

Display key findings from fresh SUMMARY.md:

```
**New results:** [from SUMMARY.md]
**Recommended methods:** [from SUMMARY.md]
**Watch Out For:** [from SUMMARY.md]
```

**Commit literature survey:**

```bash
PRE_CHECK=$(gpd pre-commit-check --files GPD/literature/PRIOR-WORK.md GPD/literature/METHODS.md GPD/literature/COMPUTATIONAL.md GPD/literature/PITFALLS.md GPD/literature/SUMMARY.md 2>&1) || true
echo "$PRE_CHECK"

gpd commit "docs: complete literature survey" --files GPD/literature/PRIOR-WORK.md GPD/literature/METHODS.md GPD/literature/COMPUTATIONAL.md GPD/literature/PITFALLS.md GPD/literature/SUMMARY.md
```

**If "Skip survey":** Continue to Step 8.

## 8. Define Research Objectives

Define research requirements after survey choice is resolved.

Read `GPD/PROJECT.md`: core research question, current milestone goals, answered questions (what is established).
Read `effective_reference_intake`, `contract_intake`, and relevant files from `reference_artifact_files` before drafting objectives so contract-critical anchors, prior outputs, baselines, and unresolved gaps carry forward explicitly.

**If literature survey exists:** Read METHODS.md and PRIOR-WORK.md, extract available approaches and known results.

Present objectives by category:

```
## [Category 1: e.g., Analytical Extensions]
**Essential:** Objective A, Objective B
**Extended:** Objective C, Objective D
**Literature notes:** [any relevant notes]
```

**If no survey:** Gather objectives through conversation. Ask: "What are the key results you need to establish for [new direction]?" Clarify, probe for related calculations, group into categories.

**Scope each category** via ask_user (multiSelect: true):

- "[Objective 1]" — [brief description]
- "[Objective 2]" — [brief description]
- "None for this milestone" — Defer entire category

Track: Selected -> this milestone. Unselected essential -> future. Unselected extended -> out of scope.

**Identify gaps** via ask_user:

- "No, survey covered it" — Proceed
- "Yes, let me add some" — Capture additions

**Generate REQUIREMENTS.md:**

- Current Objectives grouped by category (checkboxes, REQ-IDs)
- Future Objectives (deferred)
- Out of Scope (explicit exclusions with reasoning)
- Traceability section (empty, filled by roadmap)

**REQ-ID format:** `[CATEGORY]-[NUMBER]` (ANAL-01, NUMR-02). Continue numbering from existing.

Objective criteria: specific, testable, result-oriented, atomic, and as
independent as the physics permits.

Present FULL objectives list for confirmation:

```
## Milestone v[X.Y] Research Objectives

### [Category 1: Analytical Extensions]
- [ ] **ANAL-04**: Extend the perturbative result to next-to-leading order
- [ ] **ANAL-05**: Derive the crossover scaling function near the critical point

### [Category 2: Numerical Validation]
- [ ] **NUMR-03**: Benchmark NLO correction against Monte Carlo at N=32

Does this capture the research program? (yes / adjust)
```

If "adjust": Return to scoping.

**Commit objectives:**

```bash
PRE_CHECK=$(gpd pre-commit-check --files GPD/REQUIREMENTS.md 2>&1) || true
echo "$PRE_CHECK"

gpd commit "docs: define milestone v[X.Y] objectives" --files GPD/REQUIREMENTS.md
```


</process>
