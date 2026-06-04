<purpose>
Set up each execution wave, create the rollback checkpoint, and route to the next narrow execute-phase stage.
</purpose>

<stage_boundary>
This stage owns staged init refresh, convention-lock preflight, checkpoint-before-work, and wave route selection. It does not construct executor prompts, spawn proof critics, validate child returns, apply return updates, surface completed artifacts, or present rollback menus.
</stage_boundary>

<process>

<step name="refresh_wave_dispatch_context">
Refresh the wave-dispatch stage immediately before any wave setup so dispatch sees only its setup context:

```bash
WAVE_DISPATCH_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage wave_dispatch)
if [ $? -ne 0 ] || [ -z "$WAVE_DISPATCH_INIT" ]; then
  echo "ERROR: wave-dispatch stage refresh failed: $WAVE_DISPATCH_INIT"
  exit 1
fi
```

Apply `WAVE_DISPATCH_INIT.staged_loading.field_access_instruction` before reading `WAVE_DISPATCH_INIT`.
</step>

<step name="lock_wave_conventions">
Before launching or routing a wave, verify convention consistency:

```bash
gpd convention check
```

- If conventions are unlocked for any field that parallel plans will use, lock them first via `gpd convention set`.
- Do not proceed with parallel execution if convention conflicts exist.
- Before parallel waves, compare every plan's metric signature, Fourier convention, unit system, and other `convention_lock` references against the locked values.
- If any plan differs from the locked values, stop before fanout and route to `wave_failure_menu` or user repair rather than dispatching inconsistent workers.
</step>

<step name="create_wave_checkpoint_before_work">
Create the wave-level checkpoint before any plan starts. This is the rollback authority gate for the wave.

No scripts, numerical computation, executor dispatch, proof critic dispatch, artifact writes, or success claims may happen before this helper returns `safe_to_execute_wave: true`. Do not run computation and then checkpoint afterward.

```bash
WAVE_CHECKPOINT_RESULT=$(gpd --raw phase checkpoint create --phase "${phase_number}" --wave "${WAVE_NUM}" --namespace phase)
if [ $? -ne 0 ]; then
  echo "$WAVE_CHECKPOINT_RESULT"
  exit 1
fi
```

Store the `tag` field from the helper result for wave-level recovery. If the helper refuses the project/git-root boundary, emit a stage stop and route to failure handling before spawning any work.
</step>

<step name="describe_wave_before_route">
Read each selected plan's `<objective>` and render the wave before any fanout:

```
---
## Wave {N}

**{Plan ID}: {Plan Name}**
{2-3 sentences: what this derives/computes/simulates, mathematical approach, why it matters for the overall research}

Route: {executor_dispatch | proof_critic_dispatch | wave_return_checkpoint | wave_failure_menu}
---
```

Avoid generic "executing plan" narration. Describe what the plan computes or derives and why it matters.
</step>

<step name="choose_wave_route">
Choose exactly one immediate route after the checkpoint and convention preflight:

- `executor_dispatch`: normal route for plans that still need execution. Pass the wave plan, checkpoint tag, proof-bearing plan IDs, first-result/pre-fanout flags, dense/supervised cadence flags, and any serialization decisions.
- `executor_dispatch` with `probe_then_fanout`: risky waves launch only to the first-result gate or bounded segment first. Downstream work stays locked until the first material result clears sanity, decisive-evidence, anchor, convention, and proof-redteam preconditions.
- `proof_critic_dispatch`: proof-bearing executor outputs exist and need independent proof red-team before wave acceptance.
- `wave_return_checkpoint`: executor/proof children have returned or checkpointed and need child-return acceptance, checkpoint routing, SUMMARY applicator handling, or inter-wave transition handling.
- `wave_failure_menu`: checkpoint creation, convention preflight, route selection, spawn setup, or explicit user choice blocks safe execution.

Route metadata for risky fanout must preserve:
- `checkpoint_reason: pre_fanout`
- `pre_fanout_review_pending: true`
- `downstream_locked: true`
- `last_result_label` or `last_artifact_path` once a first result exists
- proof-redteam status for proof-bearing plans
- skeptical re-questioning fields when the first result is anchor-thin
- tangent decision: `ignore | defer | branch_later | pursue_now`

Do not normalize a fanout-lock event into execution success. Gate clear and fanout unlock are separate transitions.
</step>

<step name="next_up">
Emit a compact route handoff. Keep raw staged-init mechanics out of the user-facing command.

```
stage_route:
  stage: wave_dispatch
  wave: "{WAVE_NUM}"
  checkpoint_tag: "{WAVE_CHECKPOINT_TAG}"
  next_stage: "executor_dispatch | proof_critic_dispatch | wave_return_checkpoint | wave_failure_menu"
  route_reason: "{one-line reason}"
  strict_wait: "{STRICT_WAIT}"
  never_interrupt_running_workers: "{NEVER_INTERRUPT_RUNNING_WORKERS}"
  never_auto_close_child_agents: "{NEVER_AUTO_CLOSE_CHILD_AGENTS}"
```

## > Next Up

Primary: `gpd:execute-phase {N}`

**Route:** continue through the routed execute-phase stage.
</step>

</process>
