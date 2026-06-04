<purpose>
Own the reference-aware quick path after bootstrap selects `reference_context`.
</purpose>

<stage_boundary>
Use this authority only when the quick task needs targeted source lookup, active project anchors, reference artifact handles, literature/research-map files, or protocol/reference load manifests. Do not read `workflows/quick.md`; it is only the staged-file index.
</stage_boundary>

<quick_authorities>
@{GPD_INSTALL_DIR}/references/quick/quick-mode-boundary.md
@{GPD_INSTALL_DIR}/references/quick/quick-durability-minimum.md
@{GPD_INSTALL_DIR}/references/quick/quick-reroute-rules.md
</quick_authorities>

<process>
**Step 4R: Load reference-aware authoring payload**

```bash
TASK_AUTHORING_INIT=$(gpd --raw init quick "$DESCRIPTION" --stage reference_context)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd quick reference-context init failed: $TASK_AUTHORING_INIT"
  # STOP; surface the error.
fi
INIT="$TASK_AUTHORING_INIT"
```

Follow `TASK_AUTHORING_INIT.staged_loading.field_access_instruction`; `<INIT>` there means `TASK_AUTHORING_INIT`.

@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md

Set `QUICK_PLANNER_HANDOFF_STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")` immediately before spawning.

```
task(
  prompt="First, read {GPD_AGENTS_DIR}/gpd-planner.md for your role and instructions.

<planning_context>

**Mode:** quick
**Directory:** ${QUICK_DIR}
**Description:** ${DESCRIPTION}

**Project State:** read GPD/STATE.md
**Project Exists:** {project_exists}
**Project Contract:** {project_contract}
**Project Contract Gate:** {project_contract_gate}
**Project Contract Load Info:** {project_contract_load_info}
**Project Contract Validation:** {project_contract_validation}

If `TASK_AUTHORING_INIT.staged_loading.stage_id` is `reference_context`, append this selected reference payload:
**Contract Intake:** {contract_intake}
**Effective Reference Intake:** {effective_reference_intake}
**Reference Artifact Files:** {reference_artifact_files}
**Literature Review Files:** {literature_review_files}
**Literature Review Count:** {literature_review_count}
**Research Map Reference Files:** {research_map_reference_files}
**Research Map Reference Count:** {research_map_reference_count}
**Manuscript Proof Review Status:** {derived_manuscript_proof_review_status}
<protocol_bundle_handoff>
<selected_protocol_bundle_ids>{selected_protocol_bundle_ids}</selected_protocol_bundle_ids>
<protocol_bundle_count>{protocol_bundle_count}</protocol_bundle_count>
<protocol_bundle_load_manifest>{protocol_bundle_load_manifest}</protocol_bundle_load_manifest>
<protocol_bundle_verifier_extensions>{protocol_bundle_verifier_extensions}</protocol_bundle_verifier_extensions>
</protocol_bundle_handoff>

</planning_context>

<constraints>
- Create one plan with 1-3 focused tasks.
- Use the selected reference handles only for the lookup or project-anchor dependency that justified `reference_context`.
- Do not treat absent eager reference bodies or rendered protocol/reference contexts as missing evidence; read the exact source path from the handles or load manifest only when the plan depends on its body.
- If contract load or validation is blocked, return checkpoint instead of drafting from guessed scope.
- If the task is theorem-style or proof-bearing, return `checkpoint` and route to the full proof-redteam workflow.
- Target about 30% context usage.
</constraints>

<output>
Write plan to `${QUICK_DIR}/${next_num}-PLAN.md`. Return the planner handoff; completed output must list that path in `files_written`.
</output>
",
  subagent_type="gpd-planner",
  model="{planner_model}",
  readonly=false,
  description="Quick reference plan: ${DESCRIPTION}"
)
```

```yaml
child_gate:
  id: "quick_planner_plan"
  role: "gpd-planner"
  return_profile: "planner"
  required_status: "completed"
  expected_artifacts:
    - "${QUICK_DIR}/${next_num}-PLAN.md"
  allowed_roots:
    - "${QUICK_DIR}"
  freshness_marker: "after $QUICK_PLANNER_HANDOFF_STARTED_AT"
  validators:
    - "readable artifact check"
    - "gpd validate plan-preflight <PLAN.md> when tool_requirements is non-empty"
  applicator: none
  failure_route: "retry planner | explicit main-context fallback with its own return | abort"
  status_route:
    checkpoint: "fresh planner continuation after user response"
    blocked: "retry planner, main-context planning, or abort"
    failed: "retry planner, main-context planning, or abort"
```

If the planner does not return a completed typed envelope naming `${QUICK_DIR}/${next_num}-PLAN.md`, treat any file on disk as recovery evidence only and route through the gate status.

**Step 5R: Execute reference-aware plan**

Set `QUICK_EXECUTOR_HANDOFF_STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")` immediately before spawning.

```
task(
  prompt="First, read {GPD_AGENTS_DIR}/gpd-executor.md for your role and instructions.

Execute quick task ${next_num}.

Plan: read `${QUICK_DIR}/${next_num}-PLAN.md`
Project state: read GPD/STATE.md
Project contract: {project_contract}
Project contract gate: {project_contract_gate}
Project contract load info: {project_contract_load_info}
Project contract validation: {project_contract_validation}

If the selected planner stage was `reference_context`, pass through the selected reference payload:
Contract intake: {contract_intake}
Effective reference intake: {effective_reference_intake}
Reference artifact files: {reference_artifact_files}
Literature review files: {literature_review_files}
Literature review count: {literature_review_count}
Research map reference files: {research_map_reference_files}
Research map reference count: {research_map_reference_count}
Manuscript proof review status: {derived_manuscript_proof_review_status}
<protocol_bundle_handoff>
<selected_protocol_bundle_ids>{selected_protocol_bundle_ids}</selected_protocol_bundle_ids>
<protocol_bundle_count>{protocol_bundle_count}</protocol_bundle_count>
<protocol_bundle_load_manifest>{protocol_bundle_load_manifest}</protocol_bundle_load_manifest>
<protocol_bundle_verifier_extensions>{protocol_bundle_verifier_extensions}</protocol_bundle_verifier_extensions>
</protocol_bundle_handoff>

<constraints>
- Execute all plan tasks and write `${QUICK_DIR}/${next_num}-SUMMARY.md`.
- Do not update ROADMAP.md.
- Read a reference artifact, literature-review file, research-map file, or protocol bundle source only when the selected plan names the specific handle and the task depends on body text.
- If proof-bearing work slipped through planning, STOP and return the reroute.
- Return the executor handoff with status and written files.
</constraints>
",
  subagent_type="gpd-executor",
  model="{executor_model}",
  readonly=false,
  description="Execute quick reference task: ${DESCRIPTION}"
)
```

```yaml
child_gate:
  id: "quick_executor_summary"
  role: "gpd-executor"
  return_profile: "executor"
  required_status: "completed"
  expected_artifacts:
    - "${QUICK_DIR}/${next_num}-SUMMARY.md"
  allowed_roots:
    - "${QUICK_DIR}"
  freshness_marker: "after $QUICK_EXECUTOR_HANDOFF_STARTED_AT"
  validators:
    - "readable summary artifact check"
  applicator:
    command: "gpd apply-return-updates \"${QUICK_DIR}/${next_num}-SUMMARY.md\""
    require_passed_true: true
  failure_route: "retry executor | explicit main-context fallback with its own return | abort"
  status_route:
    checkpoint: "fresh executor continuation after user response"
    blocked: "retry executor, main-context execution, or abort"
    failed: "retry executor, main-context execution, or abort"
```

Apply `quick_executor_summary`; the tuple and applicator decide completion.

```bash
APPLY_RETURN=$(gpd apply-return-updates "${QUICK_DIR}/${next_num}-SUMMARY.md")
if [ $? -ne 0 ]; then
  echo "ERROR: apply-return-updates failed: $APPLY_RETURN"
  # STOP; show structured errors.
fi

gpd state add-decision --phase "quick-${next_num}" --summary "Quick task ${next_num}: ${DESCRIPTION}" --rationale "Ad-hoc task completed outside planned phases"
gpd state update "Last Activity" "${date}"

PRE_CHECK=$(gpd pre-commit-check --files ${QUICK_DIR}/${next_num}-PLAN.md ${QUICK_DIR}/${next_num}-SUMMARY.md GPD/STATE.md 2>&1) || true
echo "$PRE_CHECK"
gpd commit "docs(quick-${next_num}): ${DESCRIPTION}" --files ${QUICK_DIR}/${next_num}-PLAN.md ${QUICK_DIR}/${next_num}-SUMMARY.md GPD/STATE.md
```

Report the summary path and final commit hash, then offer `gpd:quick` for the next task.

</process>
