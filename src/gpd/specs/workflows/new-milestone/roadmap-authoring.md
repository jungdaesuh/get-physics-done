<purpose>
Create the milestone roadmap through the roadmapper handoff and final artifact gate.
</purpose>

<first_decision>
First read `GPD/MILESTONES.md` for the next phase number, then run the fresh
roadmap-authoring init before spawning the one-shot roadmapper.
</first_decision>

<process>

## 9. Create Roadmap

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 GPD >>> CREATING RESEARCH ROADMAP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

>>> Spawning roadmapper...
```

**Starting phase number:** Read `GPD/MILESTONES.md` for the last phase number
and continue from there.

**Roadmap handoff staging:** run a fresh late-stage init immediately before the roadmapper handoff and treat it as the source of truth for roadmap assembly.

```bash
ROADMAPPER_INIT=$(gpd --raw init new-milestone --stage roadmap_authoring)
if [ $? -ne 0 ]; then
  echo "ERROR: roadmap init failed: $ROADMAPPER_INIT"
  exit 1
fi
```

Apply `ROADMAPPER_INIT.staged_loading.field_access_instruction` as the field policy for the fresh roadmap payload.

Use bootstrap init for milestone identity and contract gating. Use this
late-stage init for the final handoff; do not reuse earlier survey/objective
inputs.

Apply the canonical runtime delegation convention already loaded above. Spawn the
roadmapper with `gpd-roadmapper.md`, the current milestone identity, approved
objectives, project contract/gate status, effective reference intake,
`reference_artifact_files`, prior-output handles, and these local requirements:
start phases at `[N]`, map every objective exactly once, surface contract
coverage and unresolved context gaps, write `GPD/ROADMAP.md` and
`GPD/REQUIREMENTS.md` immediately, return typed `gpd_return`, and never edit
shared state directly.
For each phase, include explicit contract coverage in `ROADMAP.md`.

```
task(
  prompt="First, read {GPD_AGENTS_DIR}/gpd-roadmapper.md.\n\n<contract_context>\nProject contract gate: {project_contract_gate}\nProject contract load info: {project_contract_load_info}\nProject contract validation: {project_contract_validation}\nContract intake: {contract_intake}\nEffective reference intake: {effective_reference_intake}\nReference artifact file handles: {reference_artifact_files}\n</contract_context>\n\n<shallow_mode>false</shallow_mode>\n\nUse the milestone handoff above plus the task-local spawn_contract below; write GPD/ROADMAP.md and GPD/REQUIREMENTS.md immediately. Do not write STATE.md directly. Return the roadmapper gpd_return profile.",
  subagent_type="gpd-roadmapper",
  model="{roadmapper_model}",
  readonly=false,
  description="Create research roadmap"
)
```

Use the approved project contract only when `project_contract_gate.authoritative` is true.

Add this contract inside the spawned roadmapper prompt when adapting it:

```markdown
<spawn_contract>
write_scope:
  mode: scoped_write
  allowed_paths:
    - GPD/ROADMAP.md
    - GPD/REQUIREMENTS.md
expected_artifacts:
  - GPD/ROADMAP.md
  - GPD/REQUIREMENTS.md
shared_state_policy: return_only
</spawn_contract>
```

This roadmapper contract is task-local. Do not widen the write scope or reuse it outside this handoff. The roadmapper does not own shared state; apply any accepted STATE.md updates in the main workflow with `gpd state` commands only after the roadmap artifacts pass the freshness gate.

**Roadmapper child gate:**

```yaml
child_gate:
  id: "milestone_roadmapper"
  role: "gpd-roadmapper"
  return_profile: "roadmapper"
  required_status: "completed"
  expected_artifacts:
    - "GPD/ROADMAP.md"
    - "GPD/REQUIREMENTS.md"
  allowed_roots:
    - "GPD"
  freshness_marker: "after $MILESTONE_ROADMAPPER_HANDOFF_STARTED_AT"
  validators:
    - "gpd validate handoff-artifacts - --expected GPD/ROADMAP.md --expected GPD/REQUIREMENTS.md --allowed-root GPD --require-status completed --require-files-written --fresh-after \"$MILESTONE_ROADMAPPER_HANDOFF_STARTED_AT\""
    - "readable ROADMAP.md / REQUIREMENTS.md"
  applicator:
    command: "main workflow applies accepted state changes with gpd state patch / gpd state add-decision after the artifact gate"
    require_passed_true: false
  failure_route: "ask retry or stop | repair prompt once | stop roadmapper path | request fresh continuation | repair path once | fail closed | ..."
```

Route `checkpoint` through `references/orchestration/continuation-boundary.md`,
`blocked` after resolution through the same boundary, and `failed` to ask retry
or stop; Next Up primary
`gpd:new-milestone [milestone name]`, also `gpd:suggest-next`. Only after the
artifact gate passes, apply accepted state changes in the main workflow with
`gpd state patch` / `gpd state add-decision`; a direct roadmapper edit to
`GPD/STATE.md` is not success proof.

**If `gpd_return.status: completed`:** Read ROADMAP.md only after fresh file
proof passes, then present a compact roadmap summary:

```
## Proposed Research Roadmap

**[N] phases** | **[X] objectives mapped** | Contract coverage surfaced

| # | Phase | Goal | Objectives | Contract Coverage | Success Criteria |
|---|-------|------|------------|-------------------|------------------|
| [N] | [Name] | [Goal] | [REQ-IDs] | [claims / anchors] | [count] |
```

**Ask for approval** via ask_user:

- "Approve" — Commit and continue
- "Adjust phases" — Tell me what to change
- "Review full file" — Show raw ROADMAP.md

**If "Adjust":** Get notes, then respawn the roadmapper with a fresh revision
continuation: read `gpd-roadmapper.md`, `GPD/ROADMAP.md`, and
`GPD/REQUIREMENTS.md`; apply the user's notes in place; return typed
`gpd_return` and updated roadmap artifacts.

  **If the revision roadmapper agent fails to spawn or returns an error:** Treat the revision as incomplete. Do not compare old file contents as proof of success. Ask whether to retry the same continuation once or stop. If retrying, use a fresh continuation handoff that includes the current roadmap, requirements, and user notes.

- Present revised roadmap
- Loop until user approves (**maximum 3 revision iterations** - after 3, commit the current version with user's notes recorded as open questions in ROADMAP.md, and note: "Roadmap committed after 3 revision rounds. Further adjustments via `gpd:add-phase` or `gpd:remove-phase`.")

**If "Review full file":** Display raw `cat GPD/ROADMAP.md`, then re-ask.

**Commit roadmap** (after approval or auto mode):

```bash
PRE_CHECK=$(gpd pre-commit-check --files GPD/ROADMAP.md GPD/STATE.md GPD/REQUIREMENTS.md 2>&1) || true
echo "$PRE_CHECK"

gpd commit "docs: create milestone v[X.Y] roadmap ([N] phases)" --files GPD/ROADMAP.md GPD/STATE.md GPD/REQUIREMENTS.md
```

## 10. Done

```
Milestone initialized: v[X.Y] [Name]
Artifacts: GPD/PROJECT.md, GPD/literature/, GPD/REQUIREMENTS.md, GPD/ROADMAP.md
[N] phases | [X] objectives | Ready to investigate

## > Next Up

**Phase [N]: [Phase Name]** — [Goal]

`gpd:discuss-phase [N]`

<sub>Start a fresh context window, then run `gpd:discuss-phase [N]`.</sub>

---

Also available: `gpd:plan-phase [N]`, `gpd:suggest-next`
```
</process>

<success_criteria>

- [ ] PROJECT.md updated with Current Milestone section
- [ ] Objectives gathered and scoped per category
- [ ] REQUIREMENTS.md created with REQ-IDs
- [ ] gpd-roadmapper spawned with staged continuation context
- [ ] Roadmap files written immediately (not draft)
- [ ] User feedback incorporated (if any)
- [ ] ROADMAP.md phases continue from previous milestone
- [ ] User knows next step: `gpd:discuss-phase [N]`

**Atomic commits:** Each phase commits its artifacts immediately.
</success_criteria>
