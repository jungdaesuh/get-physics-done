<purpose>
Start a new research milestone cycle for an existing project. This bootstrap
loads milestone identity, mode, and contract-gate state, then hands off to the
survey/objectives stage before any research, objective drafting, or roadmapping.
</purpose>

<required_reading>

Read all files referenced by the invoking prompt's execution_context before starting.

</required_reading>

<process>

## 1. Bootstrap and Load Context

```bash
INIT=$(gpd --raw init new-milestone --stage milestone_bootstrap)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $INIT"
  exit 1
fi
```

Apply `INIT.staged_loading.field_access_instruction` before reading the bootstrap payload.

**Mode-aware behavior:** supervised pauses before roadmap generation; balanced
runs unless scope is ambiguous or conflicts; yolo skips optional survey but not
contract coverage or anchor visibility. `research_mode` controls survey breadth:
explore broadens, exploit narrows, balanced uses standard depth, adaptive starts
broad unless prior decisive evidence supports narrowing.

Run centralized context preflight before continuing:

```bash
CONTEXT=$(gpd --raw validate command-context new-milestone "$ARGUMENTS")
if [ $? -ne 0 ]; then
  echo "$CONTEXT"
  exit 1
fi
```

`{GPD_INSTALL_DIR}/references/orchestration/contract-authority-gate.md`

Apply the shared contract authority gate: `project_contract` is authoritative
milestone scope only when `project_contract_gate.authoritative` is true, with
`project_contract_load_info` and `project_contract_validation` kept visible as
gate inputs.

Treat init as staged: use this bootstrap init for milestone identity and contract gate state only; run survey/objectives init before milestone scoping; run a fresh late-stage init immediately before roadmapping.

**If `roadmap_exists` is true:** Note that this milestone will replace
`GPD/ROADMAP.md`.

Load only the planning files needed for routing:

- Read PROJECT.md (existing project, answered questions, decisions)
- Read MILESTONES.md (if exists — may not exist for first milestone)
- Read STATE.md (if `state_exists` — pending items, blockers)
- Check for MILESTONE-CONTEXT.md (from milestone discussion)
- Continue applying the contract authority gate while gathering goals, determining milestone version, and reviewing roadmap coverage.
- If `project_contract_gate.authoritative` is false, checkpoint with the user and repair the stored contract before using it for milestone scope.


<stage_handoff>
When bootstrap routing is complete, reload `survey_objectives` with:

```bash
SURVEY_INIT=$(gpd --raw init new-milestone --stage survey_objectives)
```

Then apply `SURVEY_INIT.staged_loading.field_access_instruction` before gathering goals, reading scoped reference artifacts, running optional scouts, or drafting objectives.
</stage_handoff>

</process>
