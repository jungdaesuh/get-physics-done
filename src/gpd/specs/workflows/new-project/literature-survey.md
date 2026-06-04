<purpose>
Own the optional full-mode literature survey after `GPD/PROJECT.md` exists and
before requirements authoring begins.
</purpose>

<stage_boundary>
This stage is post-approval and post-project-artifact only. It must not perform
scope intake, scope approval, workflow preference setup, requirements writing,
roadmapping, conventions setup, or completion cleanup. If approved scope,
`GPD/PROJECT.md`, or the staged init fields are missing, stop and reload the
correct earlier stage.
</stage_boundary>

<stage_init>
Run a fresh stage init before survey decisions or handoffs:

```bash
LITERATURE_SURVEY_INIT=$(gpd --raw init new-project --stage literature_survey)
if [ $? -ne 0 ]; then
  echo "ERROR: literature survey init failed: $LITERATURE_SURVEY_INIT"
  exit 1
fi
```

Follow `LITERATURE_SURVEY_INIT.staged_loading.field_access_instruction`; `<INIT>` there means `LITERATURE_SURVEY_INIT`. Requirements, roadmap, and convention authorities remain unavailable.

Use the staged `research_mode` from `LITERATURE_SURVEY_INIT` for all scout
handoffs. Do not reread config inside scouts.
</stage_init>

## 6. Literature Survey Decision

If auto mode is active, default to "Survey first" without asking.

Otherwise ask:

- header: "Literature Survey"
- question: "Survey the research landscape before defining the investigation plan?"
- options:
  - "Survey first (Recommended)" - Discover known results, standard methods, open problems, available data
  - "Skip survey" - I know this field well; go straight to planning

If the user skips the survey, checkpoint the explicit skip and continue to
`requirements_authoring`.

If "Survey first", display a survey banner, create `GPD/literature`, determine
whether `GPD/PROJECT.md` is a fresh project or continuation, and spawn the four
scouts below in parallel.

```bash
mkdir -p GPD/literature
SCOUT_HANDOFF_STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
```

@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md

```
task(prompt="First, read {GPD_AGENTS_DIR}/gpd-project-researcher.md for your role and instructions.

<research_type>
Literature Survey - Known Results dimension for [research domain].
</research_type>

<project_context_type>
[fresh project OR continuation]

Fresh project: Survey the landscape of known results in [research domain].
Continuation: Survey what is new since the existing results. Do not re-survey established ground.
</project_context_type>

<question>
What are the key known results, exact solutions, and established techniques in [research domain]?
</question>

<project_context>
[PROJECT.md summary - research question, physical system, theoretical framework, key parameters]
</project_context>

Research mode from the staged literature survey init: {research_mode}. Use it as authoritative for this scout.

<downstream_consumer>
Your PRIOR-WORK.md feeds into research planning. Include specific references,
conditions, assumptions, limitations, and what remains open.
</downstream_consumer>

<output>
Write to: GPD/literature/PRIOR-WORK.md
Use template: {GPD_INSTALL_DIR}/templates/research-project/PRIOR-WORK.md
</output>
<spawn_contract>
write_scope:
  mode: scoped_write
  allowed_paths:
    - GPD/literature/PRIOR-WORK.md
expected_artifacts:
  - GPD/literature/PRIOR-WORK.md
shared_state_policy: return_only
</spawn_contract>
", subagent_type="gpd-project-researcher", model="{researcher_model}", readonly=false, description="Prior work research")

task(prompt="First, read {GPD_AGENTS_DIR}/gpd-project-researcher.md for your role and instructions.

<research_type>
Literature Survey - Methods dimension for [research domain].
</research_type>

<project_context_type>
[fresh project OR continuation]

Fresh project: What methods and computational tools are standard for [research domain]?
Continuation: What methods are appropriate for the new research questions?
</project_context_type>

<question>
What analytical techniques, numerical methods, and computational tools are standard for [research domain]?
</question>

<project_context>
[PROJECT.md summary]
</project_context>

Research mode from the staged literature survey init: {research_mode}. Use it as authoritative for this scout.

<downstream_consumer>
Your METHODS.md feeds into approach selection. Categorize analytical methods,
numerical methods, computational tools, validation techniques, cost, scaling,
and limitations.
</downstream_consumer>

<output>
Write to: GPD/literature/METHODS.md
Use template: {GPD_INSTALL_DIR}/templates/research-project/METHODS.md
</output>
<spawn_contract>
write_scope:
  mode: scoped_write
  allowed_paths:
    - GPD/literature/METHODS.md
expected_artifacts:
  - GPD/literature/METHODS.md
shared_state_policy: return_only
</spawn_contract>
", subagent_type="gpd-project-researcher", model="{researcher_model}", readonly=false, description="Methods research")

task(prompt="First, read {GPD_AGENTS_DIR}/gpd-project-researcher.md for your role and instructions.

<research_type>
Literature Survey - Computational Approaches dimension for [research domain].
</research_type>

<project_context_type>
[fresh project OR continuation]

Fresh project: What computational tools and algorithms are available for [research domain]?
Continuation: What computational extensions are needed for the new questions?
</project_context_type>

<question>
What computational approaches, algorithms, and software tools are available for [research domain]? What are the convergence criteria and resource requirements?
</question>

<project_context>
[PROJECT.md summary]
</project_context>

Research mode from the staged literature survey init: {research_mode}. Use it as authoritative for this scout.

<downstream_consumer>
Your COMPUTATIONAL.md informs the computational strategy. Include algorithms,
software, integration constraints, resource estimates, convergence criteria,
and numerical stability issues.
</downstream_consumer>

<output>
Write to: GPD/literature/COMPUTATIONAL.md
Use template: {GPD_INSTALL_DIR}/templates/research-project/COMPUTATIONAL.md
</output>
<spawn_contract>
write_scope:
  mode: scoped_write
  allowed_paths:
    - GPD/literature/COMPUTATIONAL.md
expected_artifacts:
  - GPD/literature/COMPUTATIONAL.md
shared_state_policy: return_only
</spawn_contract>
", subagent_type="gpd-project-researcher", model="{researcher_model}", readonly=false, description="Computational approaches research")

task(prompt="First, read {GPD_AGENTS_DIR}/gpd-project-researcher.md for your role and instructions.

<research_type>
Literature Survey - Open Problems and Pitfalls dimension for [research domain].
</research_type>

<project_context_type>
[fresh project OR continuation]

Fresh project: What are the known open problems and common pitfalls in [research domain]?
Continuation: What pitfalls are specific to extending existing results in the new directions?
</project_context_type>

<question>
What are the open problems, common mistakes, and known pitfalls in [research domain]?
</question>

<project_context>
[PROJECT.md summary]
</project_context>

Research mode from the staged literature survey init: {research_mode}. Use it as authoritative for this scout.

<downstream_consumer>
Your PITFALLS.md prevents wasted effort. Include warning signs, prevention
strategies, phase-specific checks, and references to known wrong turns.
</downstream_consumer>

<output>
Write to: GPD/literature/PITFALLS.md
Use template: {GPD_INSTALL_DIR}/templates/research-project/PITFALLS.md
</output>
<spawn_contract>
write_scope:
  mode: scoped_write
  allowed_paths:
    - GPD/literature/PITFALLS.md
expected_artifacts:
  - GPD/literature/PITFALLS.md
shared_state_policy: return_only
</spawn_contract>
", subagent_type="gpd-project-researcher", model="{researcher_model}", readonly=false, description="Pitfalls research")
```

**Scout child gate:**

```yaml
child_gate:
  id: "literature_scouts"
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
  failure_route: "retry missing scout once | repair prompt once | stop this scout path | repair path once | fail closed | stop survey path | ..."
```

Route non-completed returns through
`references/orchestration/child-artifact-gate.md` and
`references/orchestration/continuation-boundary.md`: `checkpoint` -> fresh
continuation, `blocked` -> surface blocker and stop this scout path, `failed`
-> retry once then stop. Do not proceed with a partial literature survey,
synthesize from incomplete scout output, or silently downgrade to manual
main-context research.

After all 4 scout artifacts pass the gate, spawn synthesizer to create
`GPD/literature/SUMMARY.md`:

```bash
SYNTHESIZER_HANDOFF_STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
```

```
task(prompt="First, read {GPD_AGENTS_DIR}/gpd-research-synthesizer.md for your role and instructions.

<task>
Synthesize literature survey outputs into SUMMARY.md.
</task>

<research_files>
Read these files:
- GPD/PROJECT.md
- GPD/config.json
- GPD/literature/PRIOR-WORK.md
- GPD/literature/METHODS.md
- GPD/literature/COMPUTATIONAL.md
- GPD/literature/PITFALLS.md
- GPD/literature/SUMMARY.md (if re-synthesizing an existing survey)
</research_files>

<output>
Write to: GPD/literature/SUMMARY.md
Use template: {GPD_INSTALL_DIR}/templates/research-project/SUMMARY.md
Do NOT commit - the orchestrator handles commits.
</output>
<spawn_contract>
write_scope:
  mode: scoped_write
  allowed_paths:
    - GPD/literature/SUMMARY.md
expected_artifacts:
  - GPD/literature/SUMMARY.md
shared_state_policy: return_only
</spawn_contract>
", subagent_type="gpd-research-synthesizer", model="{synthesizer_model}", readonly=false, description="Synthesize research")
```

**Synthesizer child gate:**

```yaml
child_gate:
  id: "literature_synthesizer"
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
  failure_route: "retry once | repair prompt once | stop synth path | retry once for fresh SUMMARY.md proof | repair path once | fail closed | ..."
```

Run the synthesizer gate before displaying or committing `SUMMARY.md`. Route
`checkpoint` through `references/orchestration/continuation-boundary.md`,
`blocked` -> surface blocker and stop synth path until resolved, `failed` ->
retry once then stop. If scout output is
incomplete, stop before the synthesizer. If the synthesizer gate remains
incomplete after retry, surface the blocker rather than creating a fallback
summary in the main context.

Display a concise literature-survey-complete banner and summarize key findings
from `GPD/literature/SUMMARY.md`.

**Commit research files:** pre-check the four scout files and `SUMMARY.md`, then
commit them with message `docs: literature survey complete` when commit policy
allows it.

**Checkpoint step 6:** update `GPD/init-progress.json` to step `6` with the
current UTC timestamp and description `Literature survey completed`.
