<purpose>
Route research reuse, refresh, and gap-closure decisions before planner authoring.
</purpose>

<stage_boundary>
Second-stage authority: research handoff context, research mode routing, researcher spawn/return handling, and numerical planning guard. Do not load planner or checker authority files here.
</stage_boundary>

<process>

## 4.7 Load Research Routing Slice

Load the routing slice first. This stage chooses reuse, refresh, gap mode, or
skip from handles and scalar status fields; it must not hydrate planner
authoring bodies before the route is known.

```bash
INIT=$(gpd --raw init plan-phase "$PHASE" --stage research_routing)
if [ $? -ne 0 ]; then
  echo "ERROR: staged plan-phase init failed: $INIT"
  exit 1
fi
# Apply INIT.staged_loading.field_access_instruction before using this payload.
```

## 5. Handle Research

**Skip if:** `--gaps` flag, `--skip-research` flag, or `research_enabled` is false (from init) without `--research` override.

### Research Mode Decision

<event name="research_route_decision">
Choose the route from `has_research`, `has_context`, `research_enabled`,
`research_mode`, `project_contract_gate`, phase target fields, and explicit
flags. Do not parse `*_content` fields, `active_reference_context`, protocol
bundle bodies, planner templates, or checker controls in this event.

**If `has_research` is true (from init) AND no `--research` flag:**

- `explore`: refresh research; broaden method comparisons and anchors.
- `exploit`: if handles/status make reuse plausible but not certain, route to
  `research_handoff_context_needed` for a targeted comparison against the
  current method family, anchor set, and decisive-evidence path; otherwise
  refresh targeted method context.
- `adaptive`: use a small SUMMARY.md handle/header scan for decisive-evidence
  signals before reusing research; otherwise refresh before planning.
- `balanced`: skip by default, but route to refresh or targeted comparison when
  state, contract, references, or roadmap changes make existing research
  plausibly stale for this phase.
</event>

**If RESEARCH.md missing OR `--research` flag OR explore mode with existing research:**

Display banner:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 GPD > RESEARCHING PHASE {X}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

* Spawning researcher...
```

<event name="research_handoff_context_needed">
Only after `research_route_decision` chooses refresh/spawn/continue, load the
stage-local authoring payload needed to assemble the researcher handoff. This is
context hydration for the chosen handoff, not permission to load planner or
checker authority prose in this stage.

```bash
INIT=$(gpd --raw init plan-phase "$PHASE" --stage planner_authoring)
if [ $? -ne 0 ]; then
  echo "ERROR: staged plan-phase init failed: $INIT"
  exit 1
fi
# Apply INIT.staged_loading.field_access_instruction before using this payload.
```
</event>

### Spawn gpd-phase-researcher

Apply the shared runtime delegation note at task-construction time:
@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md

```bash
PHASE_DESC=$(gpd --raw roadmap get-phase "${PHASE}" | gpd json get .section --default "")
# Use requirements_content from the stage-local planner_authoring payload above.
REQUIREMENTS=$(echo "$INIT" | gpd json get .requirements_content --default "")
STATE_SNAP=$(gpd state snapshot)
# Extract decisions from gpd state snapshot JSON: echo "$STATE_SNAP" | gpd json list .decisions
```

Research prompt:

```markdown
<objective>
Research Phase {phase_number}: {phase_name} well enough to plan it rigorously.
</objective>

<phase_context>
{context_content}
</phase_context>

<additional_context>
Phase description: {phase_description}
Requirements: {requirements}
Prior decisions: {decisions}
Project contract: {project_contract}
Active references: {active_reference_context}
Reference artifact handles: {reference_artifact_files}
</additional_context>

<protocol_bundle_handoff>
<selected_protocol_bundle_ids>{selected_protocol_bundle_ids}</selected_protocol_bundle_ids>
<protocol_bundle_load_manifest>{protocol_bundle_load_manifest}</protocol_bundle_load_manifest>
<protocol_bundle_verifier_extensions>{protocol_bundle_verifier_extensions}</protocol_bundle_verifier_extensions>
</protocol_bundle_handoff>

Use the protocol bundle handoff as the primary specialized method/domain surface when `selected_protocol_bundle_ids` is non-empty. Read only bundle-listed assets needed for this phase research question. Use generic broad research scanning only as fallback for uncovered areas or when no bundle is selected.

<research_mode>{RESEARCH_MODE}</research_mode>

<hypothesis_constraint>
If this phase belongs to a hypothesis branch, include the hypothesis constraint block below verbatim. Otherwise omit this section.
{hypothesis_constraint}
</hypothesis_constraint>

<output>
Write to: {phase_dir}/{phase_number}-RESEARCH.md
</output>

<spawn_contract>
write_scope:
  mode: scoped_write
  allowed_paths:
    - "{phase_dir}/{phase_number}-RESEARCH.md"
expected_artifacts:
  - "{phase_dir}/{phase_number}-RESEARCH.md"
shared_state_policy: return_only
</spawn_contract>
```

```
RESEARCH_HANDOFF_STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
RESEARCH_RETURN=$(
task(
  prompt="First, read {GPD_AGENTS_DIR}/gpd-phase-researcher.md for your role and instructions.\n\n" + research_prompt,
  subagent_type="gpd-phase-researcher",
  model="{researcher_model}",
  readonly=false,
  description="Research Phase {phase_number}"
)
)
```

**If the researcher agent fails to spawn or returns an error:** Report the failure. Offer: 1) Retry with the same context, 2) Execute the research in the main context (slower but reliable), 3) Skip research and proceed directly to planning (planner will work with less context). Do not silently continue without research output.

### Handle Researcher Return

Run this `child_gate`; shared gate and continuation rules live in `references/orchestration/child-artifact-gate.md` and `references/orchestration/continuation-boundary.md`.

```yaml
child_gate:
  id: "phase_researcher_context_refresh"
  role: "gpd-phase-researcher"
  return_profile: "researcher"
  required_status: "completed"
  expected_artifacts:
    - "${PHASE_DIR}/${PHASE_NUMBER}-RESEARCH.md"
  allowed_roots:
    - "${PHASE_DIR}"
  freshness_marker: "after $RESEARCH_HANDOFF_STARTED_AT"
  validators:
    - "gpd validate handoff-artifacts - --expected '${PHASE_DIR}/${PHASE_NUMBER}-RESEARCH.md' --allowed-root '${PHASE_DIR}' --require-files-written --require-status completed --fresh-after \"$RESEARCH_HANDOFF_STARTED_AT\""
    - "readable artifact check"
  applicator: none
  failure_route: "retry_or_main_context_research_or_skip | repair_prompt_once | skip_or_abort | retry_once | repair_path_once | abort | ..."
  status_route:
    checkpoint: "fresh researcher continuation after user response"
    blocked: "ask for context, skip, or abort"
    failed: "ask for context, skip, or abort"
```

Non-completed: use `status_route`; completed must pass the tuple before step 6.

**Verify RESEARCH.md was written (guard against silent researcher failure):**

Use the `phase_researcher_context_refresh` child_gate tuple above as the only researcher success gate. After it passes, re-read the research file from disk: `${PHASE_DIR}/${PHASE_NUMBER}-RESEARCH.md`; the earlier init `research_content` is no longer current.

## 5.1 Handle Researcher Checkpoint

If the researcher checkpoints, present it to the user and use the continuation handoff:

```markdown
<objective>
Continue research as a fresh continuation handoff for Phase {phase_number}: {phase_name}
</objective>

<prior_state>
Research file path: {phase_dir}/{phase_number}-RESEARCH.md
Read that file before continuing so you inherit the prior research state instead of relying on inline prompt state.
</prior_state>

<checkpoint_response>
**Type:** {checkpoint_type}
**Response:** {user_response}
</checkpoint_response>

<protocol_bundle_handoff>
<selected_protocol_bundle_ids>{selected_protocol_bundle_ids}</selected_protocol_bundle_ids>
<protocol_bundle_load_manifest>{protocol_bundle_load_manifest}</protocol_bundle_load_manifest>
<protocol_bundle_verifier_extensions>{protocol_bundle_verifier_extensions}</protocol_bundle_verifier_extensions>
</protocol_bundle_handoff>

<hypothesis_constraint>
If this phase belongs to a hypothesis branch, include the hypothesis constraint block below verbatim. Otherwise omit this section.
{hypothesis_constraint}
</hypothesis_constraint>

<spawn_contract>
write_scope:
  mode: scoped_write
  allowed_paths:
    - "{phase_dir}/{phase_number}-RESEARCH.md"
expected_artifacts:
  - "{phase_dir}/{phase_number}-RESEARCH.md"
shared_state_policy: return_only
</spawn_contract>
```

```bash
RESEARCH_RETURN=$(
task(
  prompt="First, read {GPD_AGENTS_DIR}/gpd-phase-researcher.md for your role and instructions.\n\n" + continuation_prompt,
  subagent_type="gpd-phase-researcher",
  model="{researcher_model}",
  readonly=false,
  description="Continue research Phase {phase_number}"
)
)
```

After the continuation returns, rerun the same researcher `child_gate` before advancing.

## 5.5. Numerical/Computational Planning Guard

Numerical phases need explicit experiment obligations, but plan-phase should not add a second design handoff by default. Keep the planner path bounded:

- Detect numerical work from the phase title/goal, project contract, context, existing research summary, and small filename/header scans. Do not `cat` large research, data, notebook, CSV, or generated-result files just to decide that a phase is numerical.
- If an `*-EXPERIMENT-DESIGN.md` already exists, pass its staged `experiment_design_content` to the planner.
- If no design file exists, the planner must encode the necessary numerical protocol directly in the PLAN: convergence/refinement grid, benchmark or limiting-case anchors, uncertainty propagation, seed/reproducibility policy, generated-artifact paths, and stop/rethink conditions.
- Do not spawn `gpd-experiment-designer` from plan-phase unless the user, context, or project contract explicitly requires a standalone `EXPERIMENT-DESIGN.md`. If a standalone design is required but missing, checkpoint or route to that specialist instead of doing unbounded extra reading inside plan-phase.

Scan for indicators such as "Monte Carlo", "simulation", "numerical", "finite-size", "convergence", "parameter sweep", "benchmark", "grid", "discretization", "timestep", and "sampling". In `--light` mode, keep the numerical protocol compact but still include the decisive convergence, uncertainty, benchmark, and forbidden-proxy obligations in the PLAN contract.

Next, reload `gpd --raw init plan-phase "$PHASE" --stage planner_authoring` and apply the active staged payload instructions.

</process>
