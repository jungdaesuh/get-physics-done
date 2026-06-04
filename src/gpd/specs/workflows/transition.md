<required_reading>

This is a conditional compatibility authority. Normal `execute-phase` closeout
uses its closeout stage first; load this file only when a local phase transition
needs extra project-evolution or next-up guidance.

Read current project artifacts only as needed:

1. `GPD/STATE.md`
2. `GPD/PROJECT.md`
3. `GPD/ROADMAP.md`
4. Current phase plan files (`PLAN.md` and `*-PLAN.md`)
5. Current phase summary files (`SUMMARY.md` and `*-SUMMARY.md`)

</required_reading>

<purpose>

Mark the current research phase complete and advance to the next phase without
forking lifecycle authority.

The installed runtime command surface is the public surface. Phase completion is
gated by verification/readiness: run the read-only closeout helper before any
mutation, then run `gpd phase complete` only when that helper says mutation is
allowed.

</purpose>

<authority_boundary>

- `gpd --raw phase closeout-readiness "${phase_number}" --require-verification`
  is the read-only authority for closeout readiness, plan/summary pairing,
  verification status, proof-redteam blockers, active bounded segments,
  checkpoint cleanup eligibility, and concrete next-up commands.
- `gpd phase complete "${phase_number}"` is the mutation authority for ROADMAP,
  STATE, state.json, progress-table, current-phase advancement, and checkpoint
  shelf sync. It rechecks lifecycle readiness before mutating.
- Do not hand-edit lifecycle fields or duplicate helper-owned cleanup. Use
  `gpd state update-progress`, `gpd state update`, and `gpd state patch` only for
  remaining structured fields outside the helper-owned transition.
- Use `gpd state add-decision` for additional project decisions; keep decision
  records structured instead of editing state tables ad hoc.

</authority_boundary>

<process>

<step name="resolve_phase_context" priority="first">

Use the phase number supplied by the caller or by the closeout stage. If no
phase is supplied, ask for the exact phase number before proceeding.

Optional compatibility context:

```bash
ROADMAP=$(gpd --raw roadmap analyze)
```

The readiness helper owns authoritative artifact counts. The legacy artifact
shape remains supported for human inspection only:

```bash
ls "${PHASE_DIR}"/PLAN.md "${PHASE_DIR}"/*-PLAN.md 2>/dev/null | sort
ls "${PHASE_DIR}"/SUMMARY.md "${PHASE_DIR}"/*-SUMMARY.md 2>/dev/null | sort
```

Count standalone and numbered PLAN files as one inventory. Count standalone and
numbered SUMMARY files as one inventory. The standalone and numbered SUMMARY files share the same helper-owned pairing semantics. Counting standalone `PLAN.md` / `SUMMARY.md` alongside numbered `*-PLAN.md` / `*-SUMMARY.md` artifacts
is helper-owned; do not let a model-local count override the readiness payload.

</step>

<step name="readiness_gate">

Run the read-only readiness gate:

```bash
READINESS=$(gpd --raw phase closeout-readiness "${phase_number}" --require-verification)
```

Use the JSON result, especially:

- `ready`
- `mutation_allowed`
- `phase`
- `phase_dir`
- `plan_count`
- `summary_count`
- `all_plans_complete`
- `incomplete_plans`
- `verification_status`
- `verification_routing_status`
- `proof_redteam_required`
- `proof_redteam_ready`
- `active_bounded_segment`
- `closeout_command`
- `cleanup_command`
- `next_up`
- `blockers`
- `warnings`

If the command exits nonzero or `ready` is false, do not mutate lifecycle state.
Present the blockers and route to the helper-provided `next_up` projection.
Use `lifecycle_next_up.rendered_markdown` or `next_up.rendered_markdown` and the
matching stage-stop fields when present. If route fields are absent, surface the
helper JSON rather than inventing a runtime command.

**Incomplete-plan safety rail**

Skipping incomplete plans is destructive. Always ask regardless of mode:

```
Phase [X] has incomplete plans:
- [plan or summary from readiness.incomplete_plans]

Safety rail: skipping plans requires confirmation.

Options:
1. Continue current phase
2. Stop and discuss a scope change
3. Review what remains
```

Do not fabricate missing summaries to satisfy closeout. If the researcher wants
to abandon work, stop and route through the appropriate planning/scope command
so the lifecycle helper can remain fail-closed.

</step>

<step name="perform_safe_transition">

When readiness reports `ready: true` and `mutation_allowed: true`, run the
completion helper exactly once:

```bash
TRANSITION=$(gpd phase complete "${phase_number}")
```

If it fails, stop. Do not continue to project evolution, commits, cleanup, or
next-phase planning while lifecycle state may be inconsistent.

Use the result fields:

- `completed_phase`
- `phase_name`
- `plans_executed`
- `all_plans_complete`
- `next_phase`
- `next_phase_name`
- `is_last_phase`
- `roadmap_updated`
- `state_updated`

The helper owns the ROADMAP/STATE transition. It marks the phase complete,
updates final plan counts, advances the state position, detects last-phase
milestone state, and syncs state.json/state markdown through the canonical
lifecycle path.

If the readiness payload included a `cleanup_command`, run that helper after the
transition succeeds. If no cleanup command is provided, preserve checkpoint tags
and recovery artifacts. Do not delete continuation or recovery files manually.

</step>

<step name="project_evolution">

Use the helper result and the current phase summaries to make only research
content updates that remain outside lifecycle mutation.

Read phase evidence from `phase_dir` in the readiness payload:

```bash
cat ${PHASE_DIR}/SUMMARY.md ${PHASE_DIR}/*-SUMMARY.md 2>/dev/null
cat ${PHASE_DIR}/CONTEXT.md ${PHASE_DIR}/*-CONTEXT.md 2>/dev/null
```

Review `GPD/PROJECT.md` for:

- answered or invalidated research questions;
- new active questions discovered during the phase;
- decisions that deserve structured records;
- changed constraints, approximations, parameter regimes, or target outputs;
- current-focus wording that should reflect the next phase.

Keep the review compact. Add decisions through `gpd state add-decision` when the
state surface needs them. Use `gpd state update-progress` after helper-owned
completion if the rendered progress field needs refresh, and use `gpd state
update` / `gpd state patch` for any remaining structured fields that feed the
rendered state surface.

</step>

<step name="parallel_reconciliation">

Only use this branch when the project actually has parallel phase work or the
closeout result/warnings indicate reconciliation is needed.

```bash
ROADMAP=$(gpd --raw roadmap analyze)
```

Combine roadmap dependency data with the loaded summaries. Resolve only concrete
conflicts:

- convention conflicts that would make downstream work ambiguous;
- result conflicts that change a claim or parameter value;
- file conflicts in shared project artifacts.

Record accepted reconciliation decisions through `gpd state add-decision`.
Leave unresolved scientific disagreement as a blocker or next-phase task; do not
hide it in the transition.

</step>

<step name="commit_and_next_up">

Run pre-commit validation or project-specific tests for the files actually
changed. Commit only the transition/project-evolution changes that occurred in
this workflow.

After the local transition and any project-evolution work, refresh the
code-owned lifecycle route:

```bash
POST_TRANSITION_ROUTE=$(gpd --raw phase closeout-readiness "${phase_number}" --require-verification || true)
```

The helper may exit nonzero after the phase is already closed. Treat that as
displayable only when it returns parseable route JSON. Emit
`lifecycle_next_up.rendered_markdown` or `next_up.rendered_markdown` plus the
matching `stage_stop` projection. Do not choose the next phase, milestone audit,
milestone archive, or new-milestone command in this prompt.

</step>

</process>

<output>

Report:

```markdown
## Phase {X}: {Phase Name} Complete

Closed with `gpd phase complete {X}` after read-only closeout readiness passed.

Completed:
- Plans executed: {plans_executed}
- Verification status: {verification_status}
- Roadmap updated: {roadmap_updated}
- State updated: {state_updated}
- Project evolution: {brief summary or "none"}

{rendered next-up block from the refreshed lifecycle route payload}
```

</output>

<checklist>

- [ ] Closeout readiness passed before mutation
- [ ] `gpd phase complete` ran successfully, or no mutation occurred
- [ ] Verification/readiness blockers were not bypassed
- [ ] Incomplete-plan destructive rail was shown if summaries were incomplete
- [ ] ROADMAP/state lifecycle fields were left to the helper
- [ ] Structured state updates used `gpd state` commands when needed
- [ ] PROJECT.md research evolution was evidence-backed
- [ ] Next command uses `## > Next Up`

</checklist>
