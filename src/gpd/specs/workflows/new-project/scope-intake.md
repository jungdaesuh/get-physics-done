<purpose>
Own the first staged `new-project` boundary: read-only startup checks, recovery
and existing-work routing, and one narrow physics scope question.
</purpose>

<stage_boundary>
This is the only first-stage authority. Do not read `workflows/new-project.md`
or any downstream authoring/template/setup authority while this stage is active.

Stage 1 does not delegate. It decides whether the workspace is safe to scope and
captures the user's initial scope/anchor input.
</stage_boundary>

<bootstrap>
Run the staged init before any user interaction:

```bash
SCOPE_INIT=$(gpd --raw init new-project --stage scope_intake)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $SCOPE_INIT"
  # STOP; surface the error.
fi
```

Follow `SCOPE_INIT.staged_loading.field_access_instruction`; `<INIT>` there means `SCOPE_INIT`. No model fields or downstream bodies are available.

Setup is read-only. Do not initialize git, create `GPD/`, write state, or
write/delete `GPD/init-progress.json`.
</bootstrap>

<recovery_routing>
Use the structured setup fields from `SCOPE_INIT`; do not manually parse
`GPD/init-progress.json`.

- If `init_progress_status="corrupt_init_progress"` or `init_progress_corrupt=true`,
  stop and ask the user to inspect, move, or delete `GPD/init-progress.json`.
- If `init_progress_status="interrupted_init_progress"` and
  `init_progress_valid=true`, offer resume versus start fresh. Delete
  `GPD/init-progress.json` only after an explicit start-fresh choice.
- If no valid init-progress checkpoint exists and `project_exists=true`, stop and
  route to `gpd:progress`.
- If no valid init-progress checkpoint exists and `recoverable_project_exists=true`
  but `project_exists=false`, stop and route to `gpd:resume-work` or
  `gpd:sync-state`.
</recovery_routing>

<existing_work_routing>
If `needs_research_map=true`, ask one routing question:

- header: "Existing Research"
- question: "I detected existing research artifacts in this directory. Would you like to map the existing work first?"
- options:
  - "Map existing work first" -- Run `gpd:map-research` to understand current research state (Recommended)
  - "Skip mapping" -- Proceed with fresh project scoping

If the user chooses mapping, stop after telling them to run `gpd:map-research`
and then return to `gpd:new-project`.

If `project_contract`, `project_contract_load_info`, or
`project_contract_validation` are visible in `SCOPE_INIT`, preserve that state
while deciding whether this is fresh work or a continuation. Do not treat a
visible-but-blocked contract as approved scope.
</existing_work_routing>

<scope_intake>
After recovery and existing-work routing are clear, ask exactly one inline
freeform question first:

"Describe your research project in one pass: what is the core physics target,
what output, claim, or deliverable would count as success, what anchor,
reference, prior output, or baseline must stay visible (or say the anchor is
unknown), what existing work should be carried forward, and what would make you
rethink the approach?"

Wait for the response. Extract only:

core target; first deliverable or decisive success signal; named anchor,
reference, prior output, baseline, or unknown-anchor gap; existing work to carry
forward; first investigation chunk if named; rethink, stop, or review triggers.

If one of those fields is missing and blocks a coherent scoping contract, ask one
narrow repair question for the missing item. Do not ask broad post-scope setup
questions in this stage.
</scope_intake>

<handoff>
When the narrow intake is complete, reload with
`gpd --raw init new-project --stage scope_approval` before drafting, approving,
validating, or persisting a scoping contract.
</handoff>
