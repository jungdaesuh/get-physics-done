<purpose>
Detect incomplete work, present recovery status, select the next action, and update continuation only after a route is known.
</purpose>

<first_route>
First rank canonical `resume_candidates` and active bounded/handoff/interrupted
handles; PLAN-without-SUMMARY scans are fallback diagnostics, not candidate
invention.
</first_route>

<process>

<step name="check_incomplete_work">
Load resume-routing before deciding what work is incomplete or resumable:

```bash
RESUME_ROUTING_INIT=$(gpd --raw init resume --stage resume_routing)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd resume-routing initialization failed: $RESUME_ROUTING_INIT"
  # STOP; surface the error.
fi
```

<field_access>
Apply `RESUME_ROUTING_INIT.staged_loading.field_access_instruction` before reading `RESUME_ROUTING_INIT`. Pick one route from candidates/handles before body reads.
</field_access>

**Bounded execution segment detection:** If `active_resume_kind` is `bounded_segment`, `execution_resumable` is true, and `active_resume_pointer` is present, treat that bounded continuation as the primary resume target. The runtime ranks three recovery families into `resume_candidates`: a resumable live execution snapshot, a recorded handoff, and an interrupted-agent marker. If the live snapshot lacks a portable usable resume file, keep it visible only as advisory context. Do NOT invent additional candidates from plan files without summaries, auto-checkpoints, or other ad hoc checkpoints.

Reason-scoped clears still matter on resume: a `first_result` clear does not retire `pre_fanout` or skeptical fields, and a `fanout unlock` does not clear the review gate by itself.

When resuming from `first_result` or skeptical state, ask one concrete question first: "What decisive evidence is still owed before downstream work is trustworthy?" Do not resume fanout based only on proxy-looking success or "seems on track" prose.

After canonical candidates are ranked, use a PLAN-without-SUMMARY check only as
a lower-priority fallback when no higher-priority blocker or resume target is
active.

**If PLAN without SUMMARY exists:**

- Execution was started but not completed
- Flag: "Found incomplete plan execution"

**If interrupted agent found and no newer bounded execution segment exists:**

- Subagent was spawned but session ended before completion
- Read agent-history.json for task details
- Flag: "Found interrupted agent"
  </step>

<step name="present_status">
Present the resume status as exactly three visible lanes. Use the detailed
routing payload to fill the lanes, but do not render a separate candidate
table, recovery ladder, or live-snapshot section unless the user explicitly asks
for diagnostics.

```
Resume Summary
Read-only local recovery snapshot for this workspace.

Selected project
  [project_root or "No project selected"; include workspace_root only when it differs]
  [if auto-selected recent project: "auto-selected recent project; reopen or confirm before writes"]

Primary resume target
  [bounded segment with active_resume_pointer, OR recorded handoff, OR interrupted-agent marker, OR missing handoff repair target, OR advisory live snapshot]
  [include active_resume_result if present]
  [include candidate family only as a compact note: bounded_segment, continuity_handoff, interrupted_agent]

Blocker / next command
  [blocking repair or selection gate, otherwise one next command]
```

Lane rules:

- `active_resume_kind="bounded_segment"` with `active_resume_pointer` outranks
  any advisory `derived_execution_head`, even if the live snapshot is newer.
- `derived_execution_head` is advisory unless the canonical active resume fields
  identify a bounded segment with a usable pointer.
- `missing_continuity_handoff_file` is a repair blocker, not a local recovery
  target.
- `project_root_auto_selected=true` or `project_root_source="recent_project"`
  disables quick resume; show the selected project path and require explicit
  confirmation or reopening the folder before any write-capable continuation.
- Contract/state repair, convention mismatches, machine-change notices,
  pending todos, and carried concerns belong in the blocker lane unless they are
  only supporting context for the primary target.

</step>

<step name="determine_next_action">
Based on project state, determine the most logical next action:

**If partial/recoverable state or `project_contract_gate.repair_required` needs repair:**
-> Contract repair required: surface the blocked contract or state-integrity issue before planning or execution.
-> Stop before planning, mutation, execution, reconstruction, or continuation update; writes none; next `gpd:sync-state`
-> Choices exactly: `gpd:sync-state`, `gpd:health`, `gpd:resume-work` after repair; exclude `gpd:progress` and `gpd:new-project`
-> This gate overrides quick-resume auto-execution; show only repair choices.

**If `project_contract_gate.authoritative` is false:**
-> Primary: Repair the blocked contract or state-integrity issue before planning or execution
-> Option: Inspect the blocked contract context and supporting diagnostics without resuming downstream work

**If `active_resume_kind="bounded_segment"` and `active_bounded_segment` exists:**
-> Primary: Continue the bounded execution segment using its current cursor, checkpoint cause, downstream-lock state, and resume preconditions
-> If `checkpoint_reason=first_result`, `checkpoint_reason=pre_fanout`, or skeptical re-questioning is required: treat the next action as a review/replan decision whenever decisive evidence is still missing, not a routine execution resume
-> Do not resume downstream fanout until the gate has an explicit clear/override outcome and, for `pre_fanout`, the matching fanout-unlock transition
-> Option: Review another ranked resume candidate from `resume_candidates`

**If `derived_execution_head` exists and `execution_resumable` is false:**
-> Primary: Treat the live snapshot as advisory continuity context only and prefer a valid recorded handoff or repair action
-> Option: Inspect the live gate state without claiming the bounded segment is directly resumable

**If interrupted agent exists:**
-> Primary: Recreate the interrupted work as a fresh handoff built from the interrupted-agent record, or continue the canonical bounded segment when one exists
-> Option: Start fresh (abandon agent work)

**If `continuity_handoff_file` exists and `execution_resumable` is false and no interrupted agent exists:**
-> Primary: Continue from the recorded handoff in the current workspace
-> Option: Inspect any advisory live execution context without claiming a bounded segment is active

**If `missing_continuity_handoff_file` exists and no interrupted agent exists:**
-> Primary: Repair or recreate the recorded handoff artifact before treating it as a resumable local target
-> Option: Inspect advisory live execution context or other recorded recovery state without claiming a bounded segment is active

**If incomplete plan (PLAN without SUMMARY) and no higher-priority blocker is active:**
-> Primary: Complete the incomplete plan
-> Option: Abandon and move on

**If phase in progress, all plans complete:**
-> Primary: Transition to next phase
-> Option: Review completed work

**If phase ready to plan:**
-> Check if CONTEXT.md exists for this phase:

- If CONTEXT.md missing:
  -> Primary: Discuss phase vision (how user imagines the physics working out)
  -> Secondary: Plan directly (skip context gathering)
- If CONTEXT.md exists:
  -> Primary: Plan the phase
  -> Option: Review roadmap

**If phase ready to execute:**
-> Primary: Execute next plan
-> Option: Review the plan first
</step>

<step name="offer_options">
Present contextual options based on project state:

**If partial/recoverable state or `project_contract_gate.repair_required` needs repair:** keep writes none and show only `gpd:sync-state`, `gpd:health`, `gpd:resume-work` after repair.

```
What would you like to do?

[Primary action based on state - e.g.:]
1. Resume interrupted agent [if interrupted agent found]
   OR
1. Execute phase (gpd:execute-phase {phase})
   OR
1. Discuss Phase 3 context (gpd:discuss-phase 3) [if CONTEXT.md missing]
   OR
1. Plan Phase 3 (gpd:plan-phase 3) [if CONTEXT.md exists or discuss option declined]

[Secondary options:]
2. Review current phase status
3. Check pending todos ([N] pending)
4. Review brief alignment
5. Something else
```

**Note:** When offering phase planning, check for CONTEXT.md existence first:

```bash
ls GPD/phases/${current_phase_slug}/*-CONTEXT.md 2>/dev/null
```

If missing, suggest discuss-phase before plan. If exists, offer plan directly.

Wait for user selection.
</step>

<step name="route_to_workflow">
Based on user selection, route to appropriate workflow:

- **Execute plan** -> Show the exact next command after clearing:

  ```
  ---

  ## > Next Up

  **{phase}-{plan}: [Plan Name]** -- [objective from PLAN.md]

  Primary: `gpd:execute-phase {phase}`
  Secondary runtime: `gpd:suggest-next`

  <sub>Start a fresh context window, then run `gpd:execute-phase {phase}`</sub>

  ---
  ```

- **Plan phase** -> Show the exact next command after clearing:

  ```
  ---

  ## > Next Up

  **Phase [N]: [Name]** -- [Goal from ROADMAP.md]

  Primary: `gpd:plan-phase [phase-number]`
  Secondary runtime: `gpd:discuss-phase [N]`
  Secondary runtime: `gpd:research-phase [N]`

  <sub>Start a fresh context window, then run `gpd:plan-phase [phase-number]`</sub>

  ---
  ```

- **Transition** -> `{GPD_INSTALL_DIR}/workflows/transition.md`
- **Check todos** -> Read GPD/todos/pending/, present summary
- **Review alignment** -> Read PROJECT.md, compare to current state
- **Something else** -> Ask what they need
  </step>

<step name="update_continuation">
Refresh canonical continuation only after the selected route, phase, and handoff file are known. Do not write a generic resume marker just because this workflow was opened.

Template only - do not run as-is:

```text
gpd state record-session \
  --stopped-at "<actual selected route and phase>" \
  --resume-file "<actual project-relative handoff path>"

gpd state record-session \
  --stopped-at "<actual selected route; pointer intentionally cleared>" \
  --resume-file none
```

Use the second form only when the selected route intentionally clears the pointer. Never copy placeholder phase numbers, prose, or file paths into state.
STATE.md should render the authoritative continuation update.
</step>

</process>

<reconstruction>
If STATE.md is missing but other artifacts exist and `planning_exists` is true:

"STATE.md missing. Reconstructing from artifacts..."

1. Read PROJECT.md -> Extract "What This Is" and Core Research Question
2. Read ROADMAP.md -> Determine phases, find current position
3. Scan \*-SUMMARY.md files -> Extract decisions, concerns
4. Count pending todos in GPD/todos/pending/
5. Check current execution snapshot -> Session continuity

Reconstruct and write STATE.md, then proceed normally.

If `planning_exists` is false:
- If recoverable state exists, repair recoverable state first, then run reconstruction.
- If state is not recoverable, skip reconstruction and route to `gpd:new-project`.

This handles cases where:

- Project predates STATE.md introduction
- File was accidentally deleted
- Cloning repo without full GPD/ state
  </reconstruction>

<quick_resume>
If user says "continue" or "go":

- If `project_root_auto_selected` is true or `project_root_source="recent_project"`, quick resume is disabled; show the project path, require explicit confirmation or reopened folder, and do not continue automatically.
- If partial/recoverable state or `project_contract_gate.repair_required` needs repair, quick resume must not auto-execute; show only repair choices.
- Load state silently
- Determine primary action
- Execute immediately without presenting options

"Continuing from [state]... [action]"
</quick_resume>

<success_criteria>
Resume is complete when:

- [ ] STATE.md loaded or reconstructed
- [ ] DERIVATION-STATE.md read, cap-checked, cross-referenced with state.json, and summarized when present
- [ ] Gaps, incomplete work, and restored research context surfaced
- [ ] Clear status and contextual next actions presented
- [ ] User knows where the project stands
- [ ] Session continuity updated
</success_criteria>
