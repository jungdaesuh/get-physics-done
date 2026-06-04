<purpose>
Execute a systematic one- or two-parameter sweep, keep methodology fixed across
points, aggregate structured data, and report physics features without
inventing phase-local outputs.
</purpose>

<core_principle>
A sweep delivers a data table. Each point changes only the selected parameter
value(s); any change in method, approximation, solver, or validity regime is a
separate sweep and must be documented explicitly.
</core_principle>

<references>
Use `{GPD_INSTALL_DIR}/references/analysis/physics-validation-recipes.md` for
feature-detection, failed-point, adaptive-refinement, and report-table recipes.
Use `references/orchestration/child-artifact-gate.md` for child-return artifact
acceptance and `references/orchestration/continuation-boundary.md` if a wave
must stop at a fresh continuation boundary.
</references>

<process>

<step name="initialize" priority="first">
Load current-workspace context with a workspace-locked bootstrap:

```bash
INIT=$(gpd --raw init progress --include state,roadmap,config --no-project-reentry)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $INIT"
  # STOP; surface the error.
fi
```

Parse `executor_model`, `commit_docs`, `autonomy`, `research_mode`,
`parallelization`, `project_exists`, `state_exists`, and `roadmap_exists`.

Run centralized command-context preflight before continuing:

```bash
CONTEXT=$(gpd --raw validate command-context parameter-sweep "$ARGUMENTS")
if [ $? -ne 0 ]; then
  echo "$CONTEXT"
  exit 1
fi
```

If `state_exists=true`, read conventions, unit system, active approximations,
and prior results. If `state_exists=false`, require one explicit computation
anchor plus explicit `--param` and `--range` inputs; all GPD-authored outputs
remain under `GPD/sweeps/` rooted at the invoking workspace.

Resolve authoritative phase context only after the computation anchor is known:

```bash
PHASE_INIT=$(gpd --raw init phase-op --include state,config "{phase_number}")
if [ $? -ne 0 ]; then
  echo "ERROR: phase initialization failed: $PHASE_INIT"
  # STOP; surface the error.
fi
```

Use that follow-up init only when the phase number is authoritative. Parse
`phase_found`, `phase_dir`, `phase_number`, and `phase_slug`; otherwise keep
`phase_found=false` and stay current-workspace scoped. Do not invent `GPD/phases/XX-sweep`.
</step>

<step name="define_sweep_parameters">
Resolve:

| Field | Source |
| --- | --- |
| Parameter name(s) | `--param` or one focused prompt |
| Range and scale | `--range`, `--log`, or one focused prompt |
| Observable | argument/context or one focused prompt |
| Computation anchor | phase plan, file, notebook/script, or explicit description |
| Adaptive mode | `--adaptive` |

Generate linear values with `np.linspace(...)`, logarithmic values with
`np.logspace(...)`, and 2D values as the cartesian product. Show a compact plan:
parameter name(s), range(s), grid size, point count, observable, adaptive flag,
and estimated wave count.

Approval policy:

- `autonomy=supervised` (default): ask before generating plans.
- `autonomy=balanced`: pause only for more than 100 grid points, high context
  pressure, or material scope/method changes; only then pause for user approval.
- `autonomy=yolo`: continue unless a hard gate fails.

If `autonomy=supervised`, show this plan and ask for confirmation before generating plans.

Derive durable paths:

```bash
SWEEP_SLUG="{slug derived from parameter names and observable}"
if [ "${phase_found}" = "true" ]; then
  SWEEP_PHASE_DIR="${phase_dir}"
  SWEEP_PHASE_KEY="${phase_number}-${phase_slug}"
  SWEEP_DOC_DIR="${SWEEP_PHASE_DIR}"
  SWEEP_ROOT="GPD/sweeps/${SWEEP_PHASE_KEY}/${SWEEP_SLUG}"
else
  SWEEP_PHASE_DIR=""
  SWEEP_PHASE_KEY=""
  SWEEP_DOC_DIR="GPD/sweeps/${SWEEP_SLUG}"
  SWEEP_ROOT="GPD/sweeps/${SWEEP_SLUG}"
fi
SWEEP_RESULTS_DIR="${SWEEP_ROOT}/results"
mkdir -p "${SWEEP_DOC_DIR}" "${SWEEP_RESULTS_DIR}"
```

Durable machine-readable data always lives under `${SWEEP_ROOT}`. Phase-backed
runs may put plan/SUMMARY docs in `${SWEEP_PHASE_DIR}`; standalone runs keep all
sweep docs and datasets under `${SWEEP_ROOT}`. Do not write durable sweep datasets to `artifacts/`.
</step>

<step name="generate_sweep_plans">
For each point, write `${SWEEP_DOC_DIR}/sweep-{PADDED_INDEX}-PLAN.md`.

Required plan content:

- frontmatter with `wave`, `interactive: false`, `depends_on: []`,
  `sweep_index`, parameter name/value fields, and `files_modified` containing
  `${SWEEP_DOC_DIR}/sweep-{PADDED_INDEX}-SUMMARY.md` plus
  `${SWEEP_RESULTS_DIR}/point-{PADDED_INDEX}.json`;
- `context_intake:` with `must_read_refs: [ref-sweep-anchor]`;
- scope, claim, deliverable, test, and false-progress entries for the configured
  observable at the configured point;
- tasks to set parameters, verify regime, run the identical computation
  template, write point JSON, and write point SUMMARY.

Hard stop: do not generate a plan that changes methodology across points.

Assign independent points to waves. If there are more than 10 points, batch
waves at 5-8 plans each and display a compact wave table.
</step>

<step name="execute_sweep">
Execute each wave with `gpd-executor` children. For phase-backed runs, create a
checkpoint tag before the wave; standalone/current-workspace runs skip tags.

Spawn each point with the compact payload below.
@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md

```
task(
  subagent_type="gpd-executor",
  model="{executor_model}",
  readonly=false,
  prompt="First, read {GPD_AGENTS_DIR}/gpd-executor.md for your role and instructions.
Execute ${SWEEP_DOC_DIR}/sweep-{PADDED_INDEX}-PLAN.md.
Write result to ${SWEEP_RESULTS_DIR}/point-{PADDED_INDEX}.json.
Create ${SWEEP_DOC_DIR}/sweep-{PADDED_INDEX}-SUMMARY.md.
Return state updates in your response -- do NOT write STATE.md directly.

<spawn_contract>
write_scope:
  mode: scoped_write
  allowed_paths:
    - ${SWEEP_RESULTS_DIR}/point-{PADDED_INDEX}.json
    - ${SWEEP_DOC_DIR}/sweep-{PADDED_INDEX}-SUMMARY.md
expected_artifacts:
  - ${SWEEP_RESULTS_DIR}/point-{PADDED_INDEX}.json
  - ${SWEEP_DOC_DIR}/sweep-{PADDED_INDEX}-SUMMARY.md
shared_state_policy: return_only
</spawn_contract>

Read at execution start: {GPD_INSTALL_DIR}/workflows/execute-plan.md, {GPD_INSTALL_DIR}/templates/summary.md, ${SWEEP_DOC_DIR}/sweep-{PADDED_INDEX}-PLAN.md, GPD/STATE.md only when state_exists=true, and GPD/config.json if it exists.

Success checks: parameter set; identical methodology used; result JSON written; uncertainty estimated if applicable; SUMMARY.md created; State updates returned (NOT written to STATE.md directly) only when authoritative phase-backed persistence is actually in scope.",
  description="Sweep point {PADDED_INDEX}"
)
```

For each child return, apply the local child gate tuple using
`references/orchestration/child-artifact-gate.md`: expected artifacts are the
point JSON and point SUMMARY, allowed roots are `${SWEEP_RESULTS_DIR}` and
`${SWEEP_DOC_DIR}`, freshness is after spawn, validators require readable JSON,
finite observable values for completed points, and valid SUMMARY. Route
`checkpoint` through `references/orchestration/continuation-boundary.md`.

Individual point failures become `"status": "agent_failed"` or a specific
failed status in that point JSON; continue remaining points and report failures
in the wave summary.
</step>

<step name="collect_results">
Aggregate every `${SWEEP_RESULTS_DIR}/point-*.json` into
`${SWEEP_ROOT}/sweep-results.json`. Preserve failed points with null observable
values and status/reason fields.

Write `${SWEEP_DOC_DIR}/SWEEP-SUMMARY.md` with:

- metadata: parameter names, ranges, scale, observable, total/completed/failed
  points, timestamp, adaptive flag;
- data table or 2D matrix;
- feature summary: extrema, rapid changes, crossovers, monotonicity,
  asymptotic behavior, failed points, and non-physical/NaN/Inf values;
- data-file list for aggregate and point JSON outputs.
</step>

<step name="adaptive_refinement">
Only run when `--adaptive` is set. Analyze the aggregate data for large
first/second derivatives, sign changes, failed gaps between successful points,
or visibly undersampled regions. Present a compact refinement table and one
`[Y/n/e]` decision. **Edit branch:** if the user chooses edit, revise the region
list once, re-present the updated `[Y/n/e]` prompt once, and then continue only
after approval. Do not treat the edit text itself as approval.

Generate refinement plans with the same plan and executor contract, continue
wave numbering, merge new point data into `${SWEEP_ROOT}/sweep-results.json`,
sort by parameter value, update metadata, and regenerate `SWEEP-SUMMARY.md`.
</step>

<step name="commit_and_present">
Apply project state updates and commits only when authoritative phase-backed
persistence is actually in scope.

- If `phase_found` is true and executor plans returned state updates, apply
  them through `gpd apply-return-updates` before touching `GPD/STATE.md`.
- If `phase_found` is false, do not mutate `STATE.md` or `state.json`, do not
  tag a checkpoint, and do not run a standalone docs commit.
- Include `GPD/STATE.md` in commit/pre-commit file lists only if the state
  bridge changed it.

```bash
if [ "${phase_found}" = "true" ] && [ "${commit_docs}" = "true" ]; then
  PRE_CHECK=$(gpd pre-commit-check --files "${SWEEP_ROOT}/sweep-results.json" "${SWEEP_DOC_DIR}/SWEEP-SUMMARY.md" "${SWEEP_RESULTS_DIR}" 2>&1) || true
  echo "$PRE_CHECK"

  gpd commit \
    "data(phase-${phase_number}): parameter sweep - ${OBSERVABLE} vs ${PARAM_NAME}" \
    --files "${SWEEP_ROOT}/sweep-results.json" "${SWEEP_DOC_DIR}/SWEEP-SUMMARY.md" "${SWEEP_RESULTS_DIR}"
fi
```

Present observable, range, completed count, key features, output files, and next
commands for visualization, adaptive refinement, numerical convergence, or
branching a follow-up hypothesis.
</step>

</process>

<failure_handling>
- Single point fails: record failed status and continue.
- Entire wave fails: use the wave failure route and offer retry, skip, or stop.
- Method breaks in part of the range: document validity boundary and split the
  sweep.
- Identical values, NaN/Inf, or non-physical values: flag prominently and
  exclude from feature claims unless physically justified.
</failure_handling>

<success_criteria>
- [ ] Sweep parameters, observable, scale, and computation anchor resolved.
- [ ] Plans generated with `context_intake:` and `must_read_refs: [ref-sweep-anchor]`.
- [ ] Executor child gate applied for point JSON and SUMMARY artifacts.
- [ ] Results aggregated into `sweep-results.json`.
- [ ] `SWEEP-SUMMARY.md` reports data, features, failures, and output files.
- [ ] Adaptive refinement executed and merged when requested.
- [ ] Phase-backed runs apply returned state updates only through the canonical bridge.
- [ ] Standalone/current-workspace runs stop after writing GPD-owned sweep artifacts under `GPD/sweeps/`.
</success_criteria>
