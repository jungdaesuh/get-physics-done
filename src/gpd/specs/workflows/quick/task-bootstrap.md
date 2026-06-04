<purpose>
Execute small ad-hoc physics tasks with GPD guarantees while skipping optional agents. Quick mode loads staged quick init, routes through the canonical planner handoff, writes under `GPD/quick/`, and records structured completion. Allowed tasks: derivation, dimensional/OOM check, limit, DOI. Not allowed: theorem-style, publication-grade, referee-response, claim-adjudication, or `proof_obligation` closure.
</purpose>

<required_reading>
Read all files referenced by the invoking prompt's execution_context before starting.
</required_reading>

<quick_authorities>
@{GPD_INSTALL_DIR}/references/quick/quick-mode-boundary.md
@{GPD_INSTALL_DIR}/references/quick/quick-durability-minimum.md
@{GPD_INSTALL_DIR}/references/quick/quick-reroute-rules.md
</quick_authorities>

<process>
**1. Intake**

Ask ONE inline freeform question (NOT ask_user):

```text
What quick task do you want to do? Examples:
  - Quick derivation of the equation of motion from the Lagrangian
  - Dimensional check on the cross-section formula in eq. (3.14)
  - Order-of-magnitude estimate for the tunneling rate
  - Verify the non-relativistic limiting case of the dispersion relation
  - Look up the DOI for a specific bibliography item
```

Store response as `$DESCRIPTION`.
If empty, re-prompt: "Please provide a task description."

---

**2. Bootstrap**

```bash
TASK_BOOTSTRAP_INIT=$(gpd --raw init quick "$DESCRIPTION" --stage task_bootstrap)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $TASK_BOOTSTRAP_INIT"
  # STOP; surface the error.
fi
INIT="$TASK_BOOTSTRAP_INIT"
```

Follow `TASK_BOOTSTRAP_INIT.staged_loading.field_access_instruction`; `<INIT>` there means `TASK_BOOTSTRAP_INIT`.

Bootstrap gates:
- If `project_exists` is false or `planning_exists` is false: STOP; Quick mode requires `GPD/PROJECT.md` plus `GPD/`. Run `gpd:new-project` first.
- Quick tasks can run mid-phase and do NOT require ROADMAP.md. They still require an initialized project workspace with `GPD/PROJECT.md` and the `GPD/` directory.
- Inherit `project_contract` only when `project_contract_gate.authoritative` is true. Do not bypass required anchors, baselines, or forbidden-proxy constraints because the task is small.
- Apply `quick-reroute-rules.md`. If the description or inherited contract indicates theorem-style, proof-bearing, publication-grade, referee-response, manuscript proof-review, claim-adjudication, or `proof_obligation` work, STOP instead of using quick mode. A "quick sketch", "light proof", or "just the main idea" does not override this gate.

Reroute explicitly to:
- `gpd:plan-phase <phase>` for planned phase work.
- `gpd:derive-equation "<goal>"` for a derivation/proof draft.
- `gpd:verify-work <phase>` only after a canonical proof-redteam artifact exists.

Mode behavior:
- `autonomy=supervised` (default): Pause after the plan for user approval before execution.
- `autonomy=balanced`: Execute without pausing unless the quick task reveals a real decision point.
- `autonomy=yolo`: Execute and commit without pausing.

Before the planner handoff, reload `task_authoring` for the default small-task path, or `reference_context` only when quick boundary rules require active project anchors, existing reference artifacts, literature/research-map files, protocol/reference context, or targeted source lookup. Treat the selected staged init payload's `staged_loading` block as the handoff shape.

---

**3. Create task directory**

Use `task_dir` from init JSON (for example, `GPD/quick/NNN-slug/`):

```bash
QUICK_DIR="${task_dir}"
mkdir -p "$QUICK_DIR"
```

Report to user:

```
Creating quick task ${next_num}: ${DESCRIPTION}
Directory: ${QUICK_DIR}
```

---

<stage_boundary>
First-stage authority for `gpd:quick`: task intake, bootstrap init, reroute gates, and quick directory creation only. Do not load `workflows/quick.md` or downstream authoring while this stage is active.
</stage_boundary>

<stage_handoff>
After Step 3 creates `${QUICK_DIR}`, choose the next stage using the quick boundary rules:

- `task_authoring` for the default small-task path.
- `reference_context` only for targeted source lookup or tasks that need active project anchors, existing reference artifacts, literature/research-map files, or protocol/reference context.

Reload with `gpd --raw init quick "$DESCRIPTION" --stage task_authoring` or `gpd --raw init quick "$DESCRIPTION" --stage reference_context`; the selected stage owns subsequent authority loading. Do not continue from bootstrap memory into planner or executor handoffs.
</stage_handoff>

</process>
