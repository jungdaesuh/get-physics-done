<purpose>
Restore state authority, contract visibility, and blocked-contract routing before downstream resume decisions.
</purpose>

<process>

<step name="load_state">
Load state-restore before using contract, reference, or readable state fields:

```bash
STATE_RESTORE_INIT=$(gpd --raw init resume --stage state_restore)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd state-restore initialization failed: $STATE_RESTORE_INIT"
  # STOP; surface the error.
fi
```

<field_access>
Apply `STATE_RESTORE_INIT.staged_loading.field_access_instruction` before reading `STATE_RESTORE_INIT`. Use handles/integrity first; route stale or blocked state to repair.
</field_access>

**machine_change_detection:** Compare the current hostname/platform with `state.json.continuation.machine.hostname` and `state.json.continuation.machine.platform`. If they differ, display the non-blocking machine-change notice from INIT and recommend rerunning the installer so runtime-local config stays current.

**canonical handoff path:** `gpd:pause-work` records a canonical phase handoff in `GPD/phases/.../.continue-here.md` and stores the durable pointer in `state.json.continuation.handoff`. That handoff file is temporary, not the authoritative store for project position or resume ranking. If a handoff file is missing but state authority is intact, report the missing artifact rather than treating the whole project as lost. Use `gpd resume --recent` first when you need to rediscover the project.

Read and parse STATE.md, then PROJECT.md:

```bash
cat GPD/STATE.md
cat GPD/PROJECT.md
```

**From STATE.md extract:**

- **Project Reference**: Core research question and current focus
- **Current Position**: Phase X of Y, Plan A of B, Status
- **Progress**: Visual progress bar
- **Recent Decisions**: Key decisions affecting current work (method choices, convention selections, approximation schemes)
- **Pending Todos**: Ideas captured during sessions
- **Blockers/Concerns**: Issues carried forward (divergences, instabilities, missing data)
- **Session Continuity**: Last session timestamp, stopped-at continuation point, resume file pointer, previous hostname/platform, and any machine-change notice

**From PROJECT.md extract:**

- **What This Is**: Current accurate description of the research
- **Research Questions**: Primary and secondary questions being investigated
- **Requirements:** Validated, Active, Out of Scope
- **Key Decisions**: Full decision log with outcomes (conventions, methods, approximations)
- **Constraints**: Hard limits on the research (computational resources, time, available data)

**Machine-readable carry-forward context from INIT JSON:**

- `project_contract` is the authoritative structured scoping and anchor contract only when `project_contract_gate.authoritative` is true.
- `project_contract_load_info` and `project_contract_validation` remain visible gate inputs and diagnostics; they explain why the gate is blocked, but they are not the authority themselves.
- `effective_reference_intake` is the authoritative carry-forward ledger for must-read refs, prior outputs, baselines, user anchors, and context gaps.
- `active_reference_context` and `reference_artifacts_content` are readability aids for that ledger, not substitutes for it.
- Do not reconstruct contract-critical anchors only from `STATE.md` / `PROJECT.md` prose when INIT already provided the structured ledger, and do not use reconstruction to override a missing planning workspace.
- If the current readable `state.json` carries a malformed `project_contract`, surface that primary-state block. Do not silently promote `state.json.bak` as the current authoritative contract while the live state file is still readable.
- If `project_contract_gate.authoritative` is false, present that contract as visible-but-blocked and route the next action to contract repair before planning or execution.

</step>

</process>
