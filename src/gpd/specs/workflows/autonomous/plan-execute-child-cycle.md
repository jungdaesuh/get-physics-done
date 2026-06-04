<purpose>
Plan and execute the current phase by delegating to the public child commands while preserving lifecycle gates and bounded-checkpoint stops.
</purpose>

<stage_scope>
Stage id: `plan_execute_child_cycle`. This stage owns only the autonomous handoff from context-ready phase work to `gpd:plan-phase` and `gpd:execute-phase`.

It does not author plans, inspect plan semantics, dispatch executors, aggregate summaries, verify scientific results, close verification gaps, run convention checks, or close the phase. Those responsibilities stay with the owning child commands.
</stage_scope>

<routing_contract>
Autonomous mode is a runtime/provider-neutral orchestrator. Invoke runtime-installed child commands with structured arguments and route on child `gpd_return` envelopes or canonical init/status payloads.

Do not route on report headings, prose marker strings, or local `status:` scans. Missing, malformed, or unknown child status is non-passing and routes to `blocked_recovery`.
</routing_contract>

<process>

<step name="refresh_stage">
Refresh the current phase payload before reading stage fields:

```bash
AUTONOMOUS_PLAN_EXECUTE_INIT=$(gpd --raw init autonomous "${PHASE_NUM}" --stage plan_execute_child_cycle)
```

Apply `AUTONOMOUS_PLAN_EXECUTE_INIT.staged_loading.field_access_instruction` before reading it. If staged init is unavailable, use the `phase_route` payload; do not scan.
</step>

<step name="plan_lifecycle_gate">
Before invoking the planner, keep the lifecycle authority blocker:

```bash
PHASE_CONTRACT_GATE=$(gpd --raw validate lifecycle-contract-gate plan-phase "${PHASE_NUM}")
```

If the gate exits nonzero, stop before child work and render `blocked_recovery` with primary `gpd:plan-phase ${PHASE_NUM}` after the surfaced state repair. Do not relabel this as missing plan authority.
</step>

<step name="plan_child_command">
Invoke the runtime-installed `gpd:plan-phase` child command with structured arguments `{phase: PHASE_NUM}`.

After return, accept planning only from a completed child return plus canonical phase payload evidence that plans exist:

```bash
PHASE_STATE=$(gpd --raw init phase-op "${PHASE_NUM}")
HAS_PLANS=$(echo "$PHASE_STATE" | gpd json get .has_plans --default false)
```

If the child return is absent, checkpointed, blocked, failed, or `has_plans` is false, stop through `blocked_recovery` with primary `gpd:plan-phase ${PHASE_NUM}`. Do not proceed to execution on old plans alone.
</step>

<step name="execute_lifecycle_gate">
Before invoking execute-phase, run the execution lifecycle gate:

```bash
EXECUTE_CONTRACT_GATE=$(gpd --raw validate lifecycle-contract-gate execute-phase "${PHASE_NUM}")
```

If the gate exits nonzero, stop before workspace scripts, numerical computations, task dispatches, subagents, artifact writes, or result claims. Route to the repair command surfaced by the gate; otherwise primary `gpd:execute-phase ${PHASE_NUM}` after repair.
</step>

<step name="execute_child_command">
Invoke the runtime-installed `gpd:execute-phase` child command with structured arguments `{phase: PHASE_NUM}`.

`gpd:execute-phase` owns its normal phase transition / closeout path. Autonomous mode must not duplicate closeout, run phase completion helpers, or transition the same successful phase.
</step>

<step name="bounded_checkpoint_stop">
If the invoking prompt, resume state, or `gpd:execute-phase` result says this autonomous invocation is bounded to one authorized segment/checkpoint, stop immediately when the checkpoint is reached.

Checkpoint reached means execute-phase returned `checkpoint`, returned a bounded-stop payload, or produced the expected execution checkpoint artifact while verification remains absent or pending. Do not run redundant read-only probing after that evidence is known.

At this stop, do not invoke verification, convention checks, milestone audit, completion, or another phase. Primary is `gpd:resume-work` for resume continuations, otherwise `gpd:verify-work ${PHASE_NUM}`.

```yaml
stage_stop: {workflow: autonomous, stage: plan_execute_child_cycle, status: checkpoint, reason: bounded_execution_checkpoint, checkpoint: bounded_execution, user_decision_needed: false, next_runtime_command: "gpd:resume-work", also_available: ["gpd:verify-work ${PHASE_NUM}", "gpd:suggest-next"]}
```

## > Next Up

Primary: `gpd:resume-work`

Also: `gpd:verify-work ${PHASE_NUM}`, `gpd:suggest-next`
</step>

<stage_transition>
When execute-phase returns completed and no bounded stop is active, continue to `verification_route`. Pass only the phase number, the structured child return, and the refreshed phase payload. Do not carry child transcript memory as authority.
</stage_transition>

</process>

<success_criteria>
- [ ] Plan and execute work delegated to runtime-installed child commands.
- [ ] Lifecycle gates run before planning and execution.
- [ ] Execution-side work never starts after a failed lifecycle gate.
- [ ] Execute-phase owns normal transition and phase closeout.
- [ ] Bounded checkpoints stop before verification, convention validation, lifecycle, or next-phase routing.
- [ ] Routing stays runtime/provider-neutral and never depends on report prose.
</success_criteria>
