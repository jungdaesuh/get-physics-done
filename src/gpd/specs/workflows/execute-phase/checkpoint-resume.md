<purpose>
Handle checkpoint presentation, continuation prompt generation, and bounded execution resume transport.
</purpose>

<stage_boundary>
This stage owns bounded continuation and resume transport after a child returned `gpd_return.status: checkpoint`. Do not reuse wave-dispatch fields blindly, accept SUMMARY returns, run child gates, apply completed-work updates, choose retry/skip/rollback/stop paths, aggregate results, or perform closeout here.
</stage_boundary>

<process>

<step name="checkpoint_handling">
Plans with `interactive: true` require user interaction.

```bash
CHECKPOINT_RESUME_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage checkpoint_resume)
if [ $? -ne 0 ] || [ -z "$CHECKPOINT_RESUME_INIT" ]; then
  echo "ERROR: checkpoint_resume init failed: $CHECKPOINT_RESUME_INIT"
  exit 1
fi
```

Apply `CHECKPOINT_RESUME_INIT.staged_loading.field_access_instruction` before reading `CHECKPOINT_RESUME_INIT`; do not reuse wave-dispatch fields here.

**Flow:**

1. Receive a checkpoint return from the wave-return child gate. Identify `CHECKPOINT_RETURN_FILE`, the child report containing the checkpoint envelope.
2. Confirm the return includes completed tasks, current blocker, awaited item, and checkpoint intent or bounded execution segment; first-result/pre-fanout pauses add gate flags, skeptical re-questioning fields, and `downstream_locked`.
3. Write the parent-owned continuation prompt to `CHECKPOINT_RESUME_FILE` (`.continue-here.md` under the phase directory unless init gives a stricter project-relative handoff path). Then run `gpd --raw apply-return-updates "${CHECKPOINT_RETURN_FILE}" --checkpoint-resume-file "${CHECKPOINT_RESUME_FILE}"`; do not accept it as completed work. Applicator rejection stops here with its JSON; do not show `gpd:resume-work` until the durable state write passes.
4. **Present to user:** populate the stop envelope, then render the canonical block.

   ```yaml
   stage_stop:
     workflow: execute-phase
     stage: checkpoint_resume
     status: checkpoint
     reason: checkpoint_plan_pause
     checkpoint: "{checkpoint_type}"
     user_decision_needed: true
     next_runtime_command: "gpd:resume-work"
     also_available:
       - "gpd:execute-phase {PHASE_NUMBER}"
       - "gpd:suggest-next"
   ```

   ```
   ## Checkpoint: [Type]

   **Plan:** 03-03 Perturbation Expansion
   **Progress:** 2/3 tasks complete

   [Checkpoint Details from agent return]
   [Awaiting section from agent return]

   ## > Next Up

   Primary: `gpd:resume-work`

   **Also available:**
   - `gpd:execute-phase {PHASE_NUMBER}` -- retry this phase workflow
   - `gpd:suggest-next` -- confirm the next action

   <sub>Start a fresh context window, then run the primary command above.</sub>
   ```

5. User responds: "approved"/"done" | issue description | decision selection
6. **Spawn continuation agent (NOT resume).** Load the `continuation_prompt_rendering` conditional authority pack only when rendering `{GPD_INSTALL_DIR}/templates/continuation-prompt.md`; load `machine_change_or_resume_transport_repair` only for machine-change or resume-transport repair.
   - `{completed_tasks_table}`: From checkpoint return
   - `{resume_task_number}` + `{resume_task_name}`: Current task
   - `{user_response}`: What user provided
   - `{resume_instructions}`: Based on checkpoint type (see template for type-specific instructions)
   - `{execution_segment}`: The returned bounded-segment state, including checkpoint cause, current cursor, resume preconditions, downstream-lock status, and any skeptical re-questioning fields that must survive into the continuation
   - `{selected_protocol_bundle_ids}` / `{protocol_bundle_load_manifest}`: From checkpoint_resume init JSON
   - `{protocol_bundle_verifier_extensions}`: From checkpoint_resume init JSON as the verifier-extension checklist surface
7. Continuation agent verifies previous commits, continues from resume point
8. Repeat until plan completes or user stops

**Why fresh agent, not resume:** Resume relies on internal serialization that breaks with parallel tool calls. Fresh agents with explicit state are more reliable.

**Checkpoints in parallel waves:** Agent pauses and returns while other parallel agents may complete. Present checkpoint, spawn continuation, wait for all before next wave.
</step>

</process>
