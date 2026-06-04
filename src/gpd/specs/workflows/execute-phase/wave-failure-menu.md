<purpose>
Render wave failure choices and route retry, skip, rollback, and stop decisions.
</purpose>

<stage_boundary>
This stage owns the user-visible failure menu after a child gate, spot-check, spawn, or plan-level execution failure. It does not accept child success, apply SUMMARY updates, dispatch proof critics, or perform bounded checkpoint continuation transport.
</stage_boundary>

<process>

<step name="refresh_wave_failure_menu_context">
Refresh only this stage before rendering retry, skip, rollback, or stop choices:

```bash
WAVE_FAILURE_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage wave_failure_menu)
if [ $? -ne 0 ] || [ -z "$WAVE_FAILURE_INIT" ]; then
  echo "ERROR: wave-failure menu stage refresh failed: $WAVE_FAILURE_INIT"
  exit 1
fi
```

Apply `WAVE_FAILURE_INIT.staged_loading.field_access_instruction` before reading `WAVE_FAILURE_INIT`.
</step>

<step name="wave_failure_menu">
Identify the failed plan and downstream impact from the phase dependency graph. Only inspect plans in later waves when computing dependent skips.

Render a stop envelope before presenting choices:

```yaml
stage_stop:
  workflow: execute-phase
  stage: wave_failure_menu
  status: blocked
  reason: wave_failure_choice_required
  checkpoint: none
  failed_plan_id: "{FAILED_PLAN_ID}"
  failed_wave: "{WAVE_NUM}"
  user_decision_needed: true
  next_runtime_command: "gpd:execute-phase {PHASE_NUMBER}"
  also_available:
    - "gpd:resume-work"
    - "gpd:suggest-next"
```

Then render the menu:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 GPD > WAVE {N} FAILURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Failed plan: {PLAN_ID} -- {plan name}
Reason: {failure description from child gate, spot-check, spawn error, or plan report}

Wave {N} Status
| Plan | Status |
| ---- | ------ |
| {plan-A} | Passed |
| {plan-B} | FAILED |
| {plan-C} | Passed |

Downstream Impact
Plans that depend on {FAILED_PLAN_ID}:
{dependent plans with wave numbers, or "None -- no downstream dependencies"}

Options:
1. Retry failed plan only
2. Skip failed plan and dependent plans
3. Rollback wave to checkpoint
4. Stop execution and preserve completed work
```

Decision routes:

- `Retry failed plan only`: retry once with the failed gate diagnostics and the accepted artifacts from sibling plans as read-only context. If the retry reaches another checkpoint, route to `checkpoint_resume`; if it fails again, re-render this menu with the new failure evidence.
- `Skip failed plan and dependent plans`: mark `FAILED_PLAN_ID` as skipped, auto-skip every later plan whose indexed dependencies include a skipped or failed plan, and carry `SKIPPED_PLANS` plus reasons into the recovery report.
- `Rollback wave to checkpoint`: revert to the wave checkpoint tag, commit the rollback with phase, wave, failed plan, failure reason, and checkpoint tag, then ask whether to retry the wave or stop.
- `Stop execution and preserve completed work`: stop the phase, keep accepted commits and artifacts, and proceed to recovery reporting.

During later waves, filter out any plan whose indexed dependencies intersect `SKIPPED_PLANS`; record `depends_on_{dep_id}` as the skip reason and continue with the next eligible plan.

Do not convert partial files, git commits, or child prose into a successful return here. Success can only be accepted by the owning child gate in `wave_return_checkpoint` or `proof_critic_dispatch`.
</step>

</process>
