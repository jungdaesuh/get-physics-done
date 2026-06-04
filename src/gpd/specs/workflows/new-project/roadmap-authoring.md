<purpose>
Create the full-mode research roadmap through the `gpd-roadmapper` handoff,
artifact gate, approval loop, commit, and checkpoint.
</purpose>

@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md

<stage_boundary>
This stage starts after `GPD/REQUIREMENTS.md` exists. It owns the roadmapper
handoff and the roadmap/state/requirements traceability update. It must not
author `GPD/CONVENTIONS.md`, must not spawn `gpd-notation-coordinator`, and
must not establish notation conventions.
</stage_boundary>

<bootstrap>
Run a fresh late-stage init immediately before the roadmapper handoff:

```bash
ROADMAPPER_HANDOFF_STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
ROADMAPPER_INIT=$(gpd --raw init new-project --stage roadmap_authoring)
if [ $? -ne 0 ]; then
  echo "ERROR: roadmap init failed: $ROADMAPPER_INIT"
  exit 1
fi
```

Follow `ROADMAPPER_INIT.staged_loading.field_access_instruction`; `<INIT>` there means `ROADMAPPER_INIT`. Convention authorities remain unavailable.

If `project_contract_gate.authoritative` is false,
`project_contract_load_info.status` starts with `blocked`, or
`project_contract_validation.valid` is false, stop and route back to the
approval/contract recovery path. Do not guess a roadmap from stale state.
</bootstrap>

<process>

## 8. Create Roadmap

Display:

```text
GPD >>> CREATING RESEARCH ROADMAP
>>> Spawning roadmapper...
```

Apply the canonical runtime delegation convention already loaded above.

```
task(prompt="First, read {GPD_AGENTS_DIR}/gpd-roadmapper.md for your role and instructions.

<planning_context>

**Read these files before proceeding:**
- `GPD/PROJECT.md` - Project definition and research question
- `GPD/REQUIREMENTS.md` - Derived requirements
- `GPD/literature/SUMMARY.md` - Literature survey (if exists)
- `GPD/config.json` - Project configuration
- `GPD/state.json` - Continuity state only; do not treat a bare read of `project_contract` there as authoritative

**Contract authority surfaces:**
- `project_contract` - approved scope payload
- `project_contract_gate` - whether the contract is authoritative
- `project_contract_load_info` - load / continuation status for the contract
- `project_contract_validation` - validation result for the contract

**Contract context:**
- `project_contract`: {project_contract}
- `project_contract_gate`: {project_contract_gate}
- `project_contract_load_info`: {project_contract_load_info}
- `project_contract_validation`: {project_contract_validation}

Project contract: {project_contract}
Project contract gate: {project_contract_gate}
Project contract load info: {project_contract_load_info}
Project contract validation: {project_contract_validation}

<shallow_mode>true</shallow_mode>

Shallow mode: produce Phase 1 fully detailed (Goal, Depends on, Requirements, Contract Coverage, 2-5 Success Criteria, placeholder plans) and Phases 2+ as compact stubs only: title, one-line Goal, objective IDs, compact contract/anchor/proxy labels, `**Plans:** 0 plans`, and a single `- [ ] TBD (run plan-phase N to break down)` entry. The researcher fleshes out detailed success criteria and task decomposition for each subsequent phase on demand via `gpd:plan-phase N`.

</planning_context>

<instructions>
Create research roadmap through the staged post-scope continuation handoff. Keep the handoff orchestration-only: do not reinterpret contract authority, do not widen scope, and do not invent an alternate roadmap path.
1. If `project_contract_gate.authoritative` is false, `project_contract_load_info.status` starts with `blocked`, or `project_contract_validation.valid` is false, return `gpd_return.status: checkpoint` rather than guessing.
2. Otherwise, derive the smallest decomposition that keeps decisive outputs, anchor handoffs, and verification legible. A tightly scoped project may have a single phase or a coarse early roadmap. Do NOT invent literature, numerics, or paper phases unless the requirements or contract demand them.
3. Map every requirement to exactly one phase.
4. For Phase 1, include explicit contract coverage in ROADMAP.md showing the decisive contract items, deliverables, anchor coverage, and forbidden proxies advanced by that phase. Phases 2+ are stubs under shallow_mode - they carry objective IDs and compact contract/anchor/proxy labels, but no detailed contract coverage narrative until the researcher runs `gpd:plan-phase N`.
5. Derive 2-5 success criteria for Phase 1 (concrete, verifiable results) that respect the decisive outputs, anchors, and forbidden proxies in the approved project contract. Phases 2+ omit success criteria in shallow mode.
6. Validate 100% requirement coverage. In shallow mode, surface contract-critical identity for all phases through objective IDs and compact contract/anchor/proxy labels, but require detailed per-phase coverage and success criteria only for Phase 1.
7. Write files immediately (ROADMAP.md, STATE.md, update REQUIREMENTS.md traceability) while preserving any existing `GPD/state.json` fields, especially `project_contract` and previously recorded open questions.
8. Return a typed `gpd_return` envelope with `status` and `files_written`, and use `gpd_return.files_written` to prove freshness; do not rely on runtime completion text alone.

Write files first, then return. This ensures artifacts persist even if context is lost.
</instructions>
<spawn_contract>
write_scope:
  mode: scoped_write
  allowed_paths:
    - GPD/ROADMAP.md
    - GPD/STATE.md
    - GPD/REQUIREMENTS.md
expected_artifacts:
  - GPD/ROADMAP.md
  - GPD/STATE.md
  - GPD/REQUIREMENTS.md
shared_state_policy: direct
</spawn_contract>
", subagent_type="gpd-roadmapper", model="{roadmapper_model}", readonly=false, description="Create research roadmap")
```

**Roadmapper child gate:**

```yaml
child_gate:
  id: "project_roadmapper"
  role: "gpd-roadmapper"
  return_profile: "roadmapper"
  required_status: "completed"
  expected_artifacts:
    - "GPD/ROADMAP.md"
    - "GPD/STATE.md"
    - "GPD/REQUIREMENTS.md"
  allowed_roots:
    - "GPD"
  freshness_marker: "$ROADMAPPER_HANDOFF_STARTED_AT"
  validators:
    - "gpd validate handoff-artifacts - --expected GPD/ROADMAP.md --expected GPD/STATE.md --expected GPD/REQUIREMENTS.md --allowed-root GPD --require-status completed --require-files-written --fresh-after \"$ROADMAPPER_HANDOFF_STARTED_AT\""
    - "readable ROADMAP.md / STATE.md / REQUIREMENTS.md"
    - "requirement coverage checks already in the roadmapper prompt"
  applicator:
    command: "shared_state_policy=direct for this legacy init handoff"
    require_passed_true: false
  failure_route: "retry once | repair prompt once | stop roadmap path | retry once; partial writes are diagnostics only | repair path once | fail closed | ..."
```

Run the child gate before displaying, approving, or committing the roadmap.
Route `checkpoint` through `references/orchestration/continuation-boundary.md`,
`blocked` after resolution through the same continuation boundary, and `failed`
to retry once then stop. Headings such as
`## ROADMAP CREATED` or `## ROADMAP BLOCKED` are not authority; the tuple and
shared gate are.

If `gpd_return.status: completed`, read the created `GPD/ROADMAP.md` after the
freshness proof passes and present the proposed roadmap inline with phase count,
requirement coverage, contract coverage, and Phase 1 success criteria.

If auto mode and `autonomy` is not `supervised`, skip the approval gate and
commit directly. Otherwise ask:

- "Approve" - Commit and continue
- "Adjust phases" - Tell me what to change
- "Review full file" - Show raw ROADMAP.md

If the user chooses `Adjust phases`, get notes and respawn the roadmapper with a
revision continuation:

```
task(prompt="First, read {GPD_AGENTS_DIR}/gpd-roadmapper.md for your role and instructions.

<revision>
User feedback on roadmap:
[user's notes]

Read `GPD/ROADMAP.md` for the current roadmap.

<shallow_mode>true</shallow_mode>

Shallow mode: keep Phase 1 fully detailed (Goal, Depends on, Requirements, Contract Coverage, 2-5 Success Criteria, placeholder plans) and Phases 2+ as compact stubs only (title + one-line Goal + objective IDs + compact contract/anchor/proxy labels + `**Plans:** 0 plans` + a single `- [ ] TBD (run plan-phase N to break down)` entry). Do not promote Phases 2+ to full detail during revision unless the user's feedback explicitly requests it.

Update the roadmap based on feedback. Edit files in place.
Return completed with changes made and updated roadmap artifacts in the typed return.
</revision>
", subagent_type="gpd-roadmapper", model="{roadmapper_model}", readonly=false, description="Revise roadmap")
```

If the revision roadmapper fails to spawn or returns an error, compare
`GPD/ROADMAP.md` with the pre-revision content. If the artifact changed, present
the revised roadmap. If it did not change, retry the revision agent once; if the
roadmap still does not update, stop and surface that the revision handoff
failed. Do not fork a second manual roadmap-editing path in the main context.

Loop until user approval, with a maximum of 3 revision iterations. After 3,
commit the current version with the user's notes recorded as open questions in
`ROADMAP.md` and note: "Roadmap committed after 3 revision rounds. Further
adjustments via `gpd:add-phase` or `gpd:remove-phase`."

If the user chooses `Review full file`, display raw `GPD/ROADMAP.md`, then
re-ask.

Pre-check `GPD/ROADMAP.md`, `GPD/STATE.md`, and `GPD/REQUIREMENTS.md`, then
commit:

```bash
gpd commit "docs: create research roadmap ([N] phases)" --files GPD/ROADMAP.md GPD/STATE.md GPD/REQUIREMENTS.md
```

Checkpoint step 8 by recording the current UTC timestamp and description
`ROADMAP.md created and committed` in `GPD/init-progress.json`.

After the checkpoint, reload `conventions_handoff`.
</process>
