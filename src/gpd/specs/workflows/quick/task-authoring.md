<purpose>
Own the default quick-task authoring, executor handoff, child-return application, state update, and final commit after quick bootstrap selects `task_authoring`.
</purpose>

<stage_boundary>
This authority starts only after `task_bootstrap` has created the quick-task directory and selected the staged authoring payload. Do not read `workflows/quick.md`; it is only a staged-file index.
</stage_boundary>

<quick_authorities>
@{GPD_INSTALL_DIR}/references/quick/quick-mode-boundary.md
@{GPD_INSTALL_DIR}/references/quick/quick-durability-minimum.md
@{GPD_INSTALL_DIR}/references/quick/quick-reroute-rules.md
</quick_authorities>

<process>
**Step 4: Spawn planner (quick mode)**

This authority is for self-contained small tasks: local calculations, dimensional checks, unit conversions, one-file numerical spot-checks, formatting, and similar work. If the task needs targeted source lookup, active project anchors, reference artifacts, literature/research-map files, or protocol/reference context, leave this authority and reload `reference_context`.

```bash
TASK_AUTHORING_INIT=$(gpd --raw init quick "$DESCRIPTION" --stage task_authoring)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd quick task-authoring init failed: $TASK_AUTHORING_INIT"
  # STOP; surface the error.
fi
INIT="$TASK_AUTHORING_INIT"
```

Follow `TASK_AUTHORING_INIT.staged_loading.field_access_instruction`; `<INIT>` there means `TASK_AUTHORING_INIT`. Do not choose `reference_context` just because `project_contract_gate` exists; contract-gate fields are already present in the default payload.

Spawn gpd-planner with the quick-mode context:

@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md

> Apply the canonical runtime delegation convention already loaded above.

Set `QUICK_PLANNER_HANDOFF_STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")` immediately before spawning.

```
task(
  prompt="First, read {GPD_AGENTS_DIR}/gpd-planner.md for your role and instructions.

<planning_context>

**Mode:** quick
**Directory:** ${QUICK_DIR}
**Description:** ${DESCRIPTION}

**Project State:**
Read the file at GPD/STATE.md

**Project Exists:** {project_exists}

**Project Contract:** {project_contract}
**Project Contract Gate:** {project_contract_gate}
**Project Contract Load Info:** {project_contract_load_info}
**Project Contract Validation:** {project_contract_validation}

**Default Reference Runtime:** not loaded for `task_authoring`.

</planning_context>

<constraints>
- Create a SINGLE plan with 1-3 focused tasks
- Quick tasks should be atomic and self-contained
- No literature review phase, no checker phase
- Use the `staged_loading` fields from `TASK_AUTHORING_INIT` as the source of truth for the handoff instead of inventing a separate quick-only contract
- Do not invent reference-runtime, protocol, literature/research-map, proof-review, or publication context that is not present in the active staged payload.
- If `project_contract_load_info.status` starts with `blocked` or `project_contract_validation.valid` is false, return checkpoint instead of drafting a plan from guessed scope.
- If the task is theorem-style or proof-bearing, return checkpoint and tell the user quick mode is blocked pending the full proof-redteam workflow.
- Proof-obligation command block: theorem-style, lemma/corollary/proposition, or explicit `proof_obligation` work must route to the full proof-redteam workflow.
- ProjectContract `claim_kind: claim` is not proof-bearing by itself. A generic manuscript or task "claim" is not enough by itself. Require theorem/proof/formal metadata before routing generic manuscript claims through proof-redteam.
- Target ~30% context usage (simple, focused)
</constraints>

<output>
Write plan to: ${QUICK_DIR}/${next_num}-PLAN.md
Return the planner handoff; completed output is `${QUICK_DIR}/${next_num}-PLAN.md` and it must appear in `files_written`. Use checkpoint when user input or a contract block prevents drafting.
</output>
",
  subagent_type="gpd-planner",
  model="{planner_model}",
  readonly=false,
  description="Quick plan: ${DESCRIPTION}"
)
```

Run this `child_gate`; shared gate and continuation rules live in `references/orchestration/child-artifact-gate.md` and `references/orchestration/continuation-boundary.md`.

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

Tuple summary: role=`gpd-planner`; expected=`${QUICK_DIR}/${next_num}-PLAN.md`.

**If the planner agent fails to spawn or returns an error:** Keep the handoff incomplete under the gate above. A plan file at `${QUICK_DIR}/${next_num}-PLAN.md` is recovery evidence only; require `quick_planner_plan` to pass, or run explicit main-context fallback with its own return. Offer: 1) Retry planner, 2) Create the plan in the main context, 3) Abort.

After planner returns:

1. Apply `quick_planner_plan`: completed passes only through the tuple.
2. For checkpoint, use `status_route` plus `references/orchestration/continuation-boundary.md`.
3. For blocked or failed, offer retry, main-context planning, or abort.
4. Extract plan count (typically 1 for quick tasks).
5. Report: "Plan created: ${QUICK_DIR}/${next_num}-PLAN.md"

If `quick_planner_plan` fails, error: "Planner failed to create ${next_num}-PLAN.md"

If the plan declares specialized `tool_requirements`, run `gpd validate plan-preflight <PLAN.md>` before spawning the executor:

```bash
PLAN_TOOL_REQUIREMENTS=$(gpd frontmatter get "${QUICK_DIR}/${next_num}-PLAN.md" --field tool_requirements 2>/dev/null || true)
if [ -n "$PLAN_TOOL_REQUIREMENTS" ]; then
  PLAN_PREFLIGHT=$(gpd --raw validate plan-preflight "${QUICK_DIR}/${next_num}-PLAN.md")
  if [ $? -ne 0 ]; then
    echo "ERROR: plan-preflight failed: $PLAN_PREFLIGHT"
    # STOP; surface the error.
  fi
fi
```

---

**Step 5: Spawn executor**

Spawn gpd-executor with plan reference:
Apply the canonical runtime delegation convention already loaded above.

Set `QUICK_EXECUTOR_HANDOFF_STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")` immediately before spawning.

```
task(
  prompt="First, read {GPD_AGENTS_DIR}/gpd-executor.md for your role and instructions.

Execute quick task ${next_num}.

Plan: Read the file at ${QUICK_DIR}/${next_num}-PLAN.md
Project state: Read the file at GPD/STATE.md
Project contract: {project_contract}
Project contract gate: {project_contract_gate}
Project contract load info: {project_contract_load_info}
Project contract validation: {project_contract_validation}

Reference runtime: not loaded for default `task_authoring`.

<constraints>
- Execute all tasks in the plan
- Commit each task atomically
- Create summary at: ${QUICK_DIR}/${next_num}-SUMMARY.md
- Do NOT update ROADMAP.md (quick tasks are separate from planned phases)
- Do not invent reference artifacts or publication/proof-review context in the default `task_authoring` path.
- If proof-bearing work slipped through planning, STOP and return the reroute instead of executing. Quick mode must not produce a proof result without the mandatory proof-redteam gate.
- Return the executor handoff; local completed output is `${QUICK_DIR}/${next_num}-SUMMARY.md`.
</constraints>
",
  subagent_type="gpd-executor",
  model="{executor_model}",
  readonly=false,
  description="Execute: ${DESCRIPTION}"
)
```

Run this `child_gate`; shared gate and continuation rules live in `references/orchestration/child-artifact-gate.md` and `references/orchestration/continuation-boundary.md`.

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

Tuple summary: role=`gpd-executor`; expected=`${QUICK_DIR}/${next_num}-SUMMARY.md`.

**If the executor agent fails to spawn or returns an error:** Check `git log --oneline -3` only for partial evidence. Commits or files do not prove success without the local child artifact gate above. Offer: 1) Retry executor, 2) Execute in explicit main-context fallback with its own return, 3) Abort.

After executor returns:

1. Verify summary exists at `${QUICK_DIR}/${next_num}-SUMMARY.md`
2. Extract commit hash from executor output
3. Report completion status

> **Handoff verification:** Apply the executor child artifact gate before success; git commits are partial evidence only.

If summary not found, error: "Executor failed to create ${next_num}-SUMMARY.md"

Note: For quick tasks producing multiple plans (rare), spawn executors in parallel waves per execute-phase patterns.

---

**Step 6: Apply child-return effects**

Treat the executor summary as the canonical child-return artifact. Before any direct quick-task state updates, validate and apply its durable subset through the shared command path:

```bash
APPLY_RETURN=$(gpd apply-return-updates "${QUICK_DIR}/${next_num}-SUMMARY.md")
if [ $? -ne 0 ]; then
  echo "ERROR: apply-return-updates failed: $APPLY_RETURN"
  # STOP — show the structured errors and do not proceed.
fi
```

Apply `quick_executor_summary`; the tuple and applicator decide completion, and non-completed statuses route through `status_route`.

Only proceed to the quick-task completion record after `apply-return-updates` succeeds and the summary file still exists on disk.

**Step 7: Update project state**

Update project state with quick task completion record using gpd commands (ensures STATE.md + state.json stay in sync):

**7a. Record quick task completion as a decision:**

```bash
gpd state add-decision --phase "quick-${next_num}" --summary "Quick task ${next_num}: ${DESCRIPTION}" --rationale "Ad-hoc task completed outside planned phases"
```

**7b. Update last activity:**

```bash
gpd state update "Last Activity" "${date}"
```

Treat the durable record for a quick task as:

- the decision entry written above via `gpd state add-decision`
- the updated `Last Activity` field via `gpd state update`
- the artifacts in `${QUICK_DIR}` (`${next_num}-PLAN.md`, `${next_num}-SUMMARY.md`, and any committed outputs)

If you want a human-facing index, put it in `GPD/quick/README.md` or in the quick-task summary.

---

**Step 8: Final commit and completion**

Stage and commit quick task artifacts:

```bash
PRE_CHECK=$(gpd pre-commit-check --files ${QUICK_DIR}/${next_num}-PLAN.md ${QUICK_DIR}/${next_num}-SUMMARY.md GPD/STATE.md 2>&1) || true
echo "$PRE_CHECK"

gpd commit "docs(quick-${next_num}): ${DESCRIPTION}" --files ${QUICK_DIR}/${next_num}-PLAN.md ${QUICK_DIR}/${next_num}-SUMMARY.md GPD/STATE.md
```

Get final commit hash:

```bash
commit_hash=$(git rev-parse --short HEAD)
```

Display completion output:

```
---

GPD > QUICK TASK COMPLETE

Quick Task ${next_num}: ${DESCRIPTION}

Summary: ${QUICK_DIR}/${next_num}-SUMMARY.md
Commit: ${commit_hash}

---

Ready for next task: gpd:quick
```

</process>

<success_criteria>

- [ ] `GPD/` directory exists
- [ ] User provides task description
- [ ] Slug generated (lowercase, hyphens, max 40 chars)
- [ ] Next number calculated (001, 002, 003...)
- [ ] Directory created at `GPD/quick/NNN-slug/`
- [ ] `${next_num}-PLAN.md` created by planner
- [ ] `${next_num}-SUMMARY.md` created by executor
- [ ] Structured state updated via `gpd state` commands
- [ ] Artifacts committed
</success_criteria>
