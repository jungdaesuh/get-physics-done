<trigger>
Use this workflow when:
- Starting or returning to an existing research project
- User says "continue", "what's next", "where were we", "resume"
- Any planning operation when `GPD/` already exists
</trigger>

<purpose>
Restore selected project context so "Where were we?" has an immediate answer.

@{GPD_INSTALL_DIR}/references/orchestration/resume-vocabulary.md
</purpose>

<required_reading>
Bootstrap loads only immediate resume vocabulary. Later staged payloads name
`{GPD_INSTALL_DIR}/references/orchestration/continuation-format.md`,
`{GPD_INSTALL_DIR}/references/orchestration/state-portability.md`, and
`{GPD_INSTALL_DIR}/templates/state-json-schema.md`; read them when entering those stages.
</required_reading>

<process>

Runtime label: Show `gpd:` as native labels; keep local CLI `gpd ...` unchanged.

<step name="initialize">
Load resume bootstrap. `gpd:resume-work` is the guided runtime path; `gpd resume` is the public local read-only summary; `gpd resume --recent` is the cross-project discovery surface; `gpd --raw resume` is raw local JSON:

```bash
INIT=$(gpd --raw init resume --stage resume_bootstrap)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $INIT"
  # STOP; surface the error.
fi
```

<field_access>
Apply `INIT.staged_loading.field_access_instruction` before reading `INIT`.
`active_resume_result` is route context only; stale bodies stay unavailable.
</field_access>

Parse JSON semantically:

- **Requested workspace availability:** `workspace_state_exists`, `workspace_roadmap_exists`, `workspace_project_exists`, `workspace_planning_exists`
- **Selected project availability:** `state_exists`, `state_json_backup_exists`, `roadmap_exists`, `project_exists`, `planning_exists`
- **Availability and contract authority:** `project_contract_gate` and peers are loaded by `STATE_RESTORE_INIT` before use
- **Canonical continuation and recovery authority:** `active_resume_kind`, `active_resume_pointer`, `active_bounded_segment`, `derived_execution_head`, `active_resume_result`, handoff-file fields, `resume_candidates`, and execution gate fields
- **Machine advisory state:** `machine_change_detected`, `machine_change_notice`, current/session hostname and platform

@{GPD_INSTALL_DIR}/references/orchestration/resume-vocabulary.md

The recent-project list is advisory and machine-local; once a workspace is
chosen, `gpd:resume-work` reloads that project's canonical state.

**If `project_reentry_requires_selection` is true or `project_reentry_mode="ambiguous-recent-projects"`:** Stop before new-project routing or reconstruction. Show the recent-project count; tell the user to run `gpd resume --recent`, open the chosen workspace, and rerun `gpd:resume-work`.

**If `project_root_auto_selected` is true or `project_root_source="recent_project"`:** Runtime started outside the selected project. Do not quick-resume or act from the unrelated workspace. On bare "continue" or "go", stop. Show `project_root`; require explicit confirmation or a reopened project folder.

`workspace_*` fields judge the user-requested workspace; selected-project
fields apply after re-entry resolution. Resolver order: `GPD/state.json` /
continuation, then `GPD/state.json.bak`, then `GPD/STATE.md`;
`.continue-here.md` and live snapshots are context, not sole authority.

**If `planning_exists` is false and no recent-project selection is required:** If recoverable state exists, repair first. Otherwise route to gpd:new-project and do not attempt STATE.md reconstruction.
**If `state_exists` is false but `roadmap_exists` or `project_exists` is true:** Offer to reconstruct STATE.md from the existing project artifacts.

If `active_resume_kind="bounded_segment"` and `active_bounded_segment` exists,
that is the primary bounded resume target. `derived_execution_head` is advisory context only unless canonical active-resume fields name a usable pointer; by
itself it is not a ranked bounded-segment resume candidate and does not justify
`active_resume_kind="bounded_segment"`. Keep recorded or missing handoff
artifacts visible through their handoff fields, not as a second resume system.
Pre-fanout and first-result gates remain live until their exact clear/unlock
evidence is present.
</step>

</process>
