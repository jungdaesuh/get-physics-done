<purpose>
Construct and fan out executor child tasks for the selected wave.
</purpose>

<stage_boundary>
This stage owns only `gpd-executor` task construction and fanout. It does not create the wave checkpoint, spawn proof critics, validate child returns, apply return updates, surface completed artifacts, or close child agents from parent inference.
</stage_boundary>

<process>

<stage_policy>
`workflows/execute-plan.md` is a child-readable workflow path inside executor prompts, not parent eager authority for this stage. The parent carries route metadata, not the full plan-local execution workflow.

Executor children must receive enough context to execute rigorously, write their SUMMARY, and return structured state updates. They must not write `GPD/STATE.md` directly; durable return application belongs to the return/checkpoint stage.
</stage_policy>

<step name="refresh_executor_dispatch_context">
Refresh the executor-dispatch stage immediately before constructing executor tasks:

```bash
EXECUTOR_DISPATCH_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage executor_dispatch)
if [ $? -ne 0 ] || [ -z "$EXECUTOR_DISPATCH_INIT" ]; then
  echo "ERROR: executor-dispatch stage refresh failed: $EXECUTOR_DISPATCH_INIT"
  exit 1
fi
```

Apply `EXECUTOR_DISPATCH_INIT.staged_loading.field_access_instruction` before reading `EXECUTOR_DISPATCH_INIT`.
</step>

<step name="pre_fanout_guard">
Require the `wave_dispatch` route record and a wave checkpoint tag before any executor task is constructed. If no checkpoint tag exists, STOP before work and route back to `wave_dispatch`; do not create a checkpoint after computation.

Within a wave: parallel if `PARALLELIZATION=true` AND `FORCE_SEQUENTIAL=false`, sequential otherwise. Honor serialization decisions from wave planning and convention preflight.

Read `review_cadence`, `research_mode`, `strict_wait`, `never_interrupt_running_workers`, and `never_auto_close_child_agents` from the staged payload/config:
- `strict_wait=true` disables unattended-minute cutoffs entirely.
- `never_interrupt_running_workers=true` means parent checkpoint/review timing waits for natural child completion unless the child itself checkpoints or fails.
- `never_auto_close_child_agents=true` forbids synthesizing child completion from files, commits, partial output, or parent confidence.
- `review_cadence=dense` and `autonomy=supervised` require the first-result/pre-fanout gates selected by wave planning; they still checkpoint at task/gate boundaries, not algebraic micro-steps.
</step>

<step name="dispatch_executor_tasks">
Pass paths only. Executors read files themselves with fresh context; parent setup does not preload child workflow authority.

Canonical runtime delegation convention for every `task()` block in this workflow:
@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md
The shared note owns runtime-neutral task construction and handoff conventions. This stage only fills the executor-specific payload and enforces handoff gates.

```
EXECUTOR_HANDOFF_STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
task(
  subagent_type="gpd-executor",
  model="{executor_model}",
  readonly=false,
  prompt="First, read {GPD_AGENTS_DIR}/gpd-executor.md for your role and instructions.

    <objective>
    Execute plan {plan_number} of phase {phase_number}-{phase_name}.
    Commit each task atomically. Create SUMMARY.md.
    Return state updates (position, decisions, metrics) in your response -- do NOT write STATE.md directly.
    </objective>

    <context_hint>{EXECUTOR_CONTEXT_HINT}</context_hint>
    <wave_checkpoint_tag>{WAVE_CHECKPOINT_TAG}</wave_checkpoint_tag>
    <phase_class>{PHASE_CLASSES}</phase_class>
    <research_mode>{RESEARCH_MODE}</research_mode>
    <selected_protocol_bundle_ids>{selected_protocol_bundle_ids}</selected_protocol_bundle_ids>
    <protocol_bundle_load_manifest>{protocol_bundle_load_manifest}</protocol_bundle_load_manifest>
    <protocol_bundle_context>{protocol_bundle_context}</protocol_bundle_context>
    <protocol_bundle_verifier_extensions>{protocol_bundle_verifier_extensions}</protocol_bundle_verifier_extensions>
    <selected_task_overlay_ids>{selected_task_overlay_ids}</selected_task_overlay_ids>
    <task_overlay_load_manifest>{task_overlay_load_manifest}</task_overlay_load_manifest>
    <task_overlay_policy_summary>{task_overlay_policy_summary}</task_overlay_policy_summary>
    <review_cadence>{REVIEW_CADENCE}</review_cadence>
    <strict_wait>{STRICT_WAIT}</strict_wait>
    <never_interrupt_running_workers>{NEVER_INTERRUPT_RUNNING_WORKERS}</never_interrupt_running_workers>
    <never_auto_close_child_agents>{NEVER_AUTO_CLOSE_CHILD_AGENTS}</never_auto_close_child_agents>
    <max_unattended_minutes_per_plan>{MAX_UNATTENDED_MINUTES_PER_PLAN}</max_unattended_minutes_per_plan>
    <max_unattended_minutes_per_wave>{MAX_UNATTENDED_MINUTES_PER_WAVE}</max_unattended_minutes_per_wave>
    <segment_task_cap>{SEGMENT_TASK_CAP}</segment_task_cap>
    <first_result_gate>{FIRST_RESULT_GATE_REQUIRED}</first_result_gate>
    <pre_fanout_review>{PRE_FANOUT_REVIEW_REQUIRED}</pre_fanout_review>
    <checkpoint_before_downstream>{CHECKPOINT_BEFORE_DOWNSTREAM}</checkpoint_before_downstream>
    <bounded_execution>{true}</bounded_execution>

    <proof_redteam_gate>
    If this plan is proof-bearing, leave the proof artifact, theorem inventory, and enough context for `gpd-check-proof`.
    Do NOT self-certify the sibling `{plan_id}-PROOF-REDTEAM.md` artifact when a fresh `gpd-check-proof` subagent is available.
    If any named parameter, hypothesis, or quantifier is missing, surface the gap and do NOT claim the theorem is established. Do not bypass this gate because the algebra looks clean, one limit works, or verification is disabled elsewhere.
    </proof_redteam_gate>

    <tangent_control>
    Proposal-first: classify unexpected non-blocking alternatives as `ignore`, `defer`, `branch_later`, or `pursue_now`; do not silently pursue optional tangents.
    `pursue_now` requires explicit user request or approved scope. If `research_mode=exploit`, suppress optional tangents unless requested.
    </tangent_control>

    <files_to_read>
    Read these files at execution start using the file_read tool:
    - Workflow: {GPD_INSTALL_DIR}/workflows/execute-plan.md
    - Summary template: {GPD_INSTALL_DIR}/templates/summary.md
    - Checkpoint policy path: {GPD_INSTALL_DIR}/references/orchestration/checkpoints.md
    - Validation path: {GPD_INSTALL_DIR}/references/verification/core/verification-core.md plus any domain-specific verification file named by the plan
    - Task overlays: read only selected task overlay `portable_path` entries listed in `task_overlay_load_manifest.overlays` where `body_loaded` is `false`; do not read or assume unselected overlays
    - Plan: {phase_dir}/{plan_file}
    - State: GPD/STATE.md
    - Config: GPD/config.json (if exists)
    </files_to_read>

    <success_criteria>
    - [ ] Tasks executed rigorously and committed individually
    - [ ] Dimensional consistency and specified limiting cases checked
    - [ ] Proof-bearing plans leave context for `gpd-check-proof` and do not self-certify proof-redteam status
    - [ ] SUMMARY.md created in plan directory
    - [ ] State updates returned (NOT written to STATE.md directly)
    </success_criteria>
  ",
  description="Execute phase {phase_number} plan {plan_id}"
)
```

For risky fanout, launch each selected plan only to its first-result gate or bounded segment first. Collect the child checkpoint/return through the downstream return stage before unlocking later fanout. Do not spawn downstream work when the first result is proxy-only, convention-thin, proof-open, or skeptical re-questioning remains unresolved.
</step>

<step name="route_after_fanout">
After executor tasks are launched, do not accept completion in this stage.

Route by observed child state:
- `wave_return_checkpoint` for `completed`, `checkpoint`, malformed, stale, or incomplete executor returns that need child-return handling.
- `proof_critic_dispatch` when proof-bearing executor outputs are present and need independent red-team before acceptance.
- `wave_failure_menu` when a spawn failure, route conflict, or user choice blocks safe continuation.

## > Next Up

Primary: `gpd:execute-phase {N}`

**Route:** continue through `wave_return_checkpoint`, `proof_critic_dispatch`, or `wave_failure_menu` according to child state.
</step>

</process>
