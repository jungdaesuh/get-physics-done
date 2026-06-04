<purpose>
Determine which input parameters most strongly affect an output quantity or
uncertainty budget, then recommend which inputs deserve more effort.
</purpose>

<core_principle>
Sensitivity analysis turns an error bar into an actionable map. It identifies
which dependencies dominate uncertainty, which directions are stiff or null,
and where approximations or validity boundaries make the result fragile.
</core_principle>

<references>
Use `{GPD_INSTALL_DIR}/references/analysis/physics-validation-recipes.md` when
executing derivative, endpoint, approximation, divergence, and report-table
recipes. Use `references/results/result-lookup-policy.md` for canonical result
and dependency lookup.
</references>

<process>

<step name="initialize" priority="first">
Load workspace-bound supporting context first. Sensitivity analysis may use
project data when it exists in the invoking workspace, but it must not silently
reenter a different recent project.

```bash
INIT=$(gpd --raw init progress --include state,config --no-project-reentry)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $INIT"
  # STOP; surface the error.
fi
```

Parse `executor_model`, `commit_docs`, `parallelization`, `project_exists`,
`state_exists`, and `roadmap_exists`.

- If `state_exists=true`: extract conventions, active approximations,
  `convention_lock`, parameter definitions, and `intermediate_results`; use
  `GPD/analysis/PARAMETERS.md` as the parameter registry when present.
- If `state_exists=false`: require explicit parameter declarations from the
  user; standalone outputs stay under `GPD/analysis/` and do not mutate
  `STATE.md` or `state.json`.

Resolve authoritative phase-backed persistence only after the target quantity is
known. If the target resolves to a canonical stored result with phase metadata,
or the user explicitly anchors the run to a current-workspace phase, load phase
context explicitly:

```bash
PHASE_INIT=$(gpd --raw init phase-op --include state,config "{phase_number}")
if [ $? -ne 0 ]; then
  echo "ERROR: phase initialization failed: $PHASE_INIT"
  # STOP; surface the error.
fi
```

Use that follow-up phase init only when the phase number is authoritative. If no
authoritative phase context exists, keep `phase_found=false` and treat the run
as analysis-only persistence under `GPD/analysis/`.
</step>

<step name="define_scope">
Identify the target quantity and the parameters to analyze.

For canonical target lookup, use `gpd result search`; once a canonical
`result_id` is known, use `gpd result show "{result_id}"` before
`gpd result deps "{result_id}"` for the recorded upstream dependency chain.
Keep `gpd query search` for SUMMARY/frontmatter lookup.

Use `--target` directly when supplied. Otherwise inspect current-workspace
state, phase summaries, or explicit user context. If canonical target metadata
resolves authoritative phase context, record `phase_found`, `phase_dir`,
`phase_number`, and `phase_slug` before choosing persistence. Never recover phase-backed persistence from `${PHASE_ARG:-}`, recent-project state, or a guessed current phase.

Record:

```markdown
## Sensitivity Target

**Output quantity:** f = {description}
**Expression:** f(p_1, p_2, ..., p_N) = {form if known}
**Nominal value:** f_0 = {current best value}
**Location:** {file:line or phase}

## Parameters

| # | Parameter | Symbol | Nominal Value | Uncertainty | Source |
| --- | --- | --- | --- | --- | --- |
```

If `--params` is supplied, restrict analysis to those parameters. Otherwise
catalog physical parameters, numerical controls, approximation controls, and
measured inputs that the target actually depends on.
</step>

<step name="choose_method">
Select method per parameter:

| Method | Use when | Evidence |
| --- | --- | --- |
| analytical | closed-form dependency exists | compute `partial f / partial p_i` from the derivation chain |
| numerical | dependency is through code or pipeline | central finite difference with `f_plus`, `f_minus`, and domain check |
| combined | dependencies differ by parameter | table listing method per parameter |

Default to combined when `--method` is omitted. Reject finite-difference steps
that leave the validity domain; vary step size if derivatives are unstable.
</step>

<step name="compute_sensitivity">
For each parameter compute:

```text
S_i = (partial f / partial p_i) * (p_i / f)
delta_f_i = abs(df_dp) * delta_p
```

Record `df_dp`, `S_i`, `delta_f_i`, uncertainty share, and endpoint
sensitivity. Flag:

- endpoint sensitivity changes greater than 50 percent;
- `|S| > 100`;
- sign changes;
- oscillatory or unstable finite differences;
- regulator or approximation sensitivity masquerading as parameter sensitivity.
</step>

<step name="rank_parameters">
Rank by `abs(df_dp * delta_p)` and cumulative uncertainty share. Identify stiff
directions, null directions, paired cancellations, and the highest-impact
follow-up measurement or computation.
</step>

<step name="approximation_sensitivity">
Analyze active approximations from project state or explicit standalone inputs:
controlling parameter, current value, validity boundary, next-order or
better-model comparison, estimated systematic error, and whether that systematic
dominates the target uncertainty.
</step>

<step name="generate_output">
Write `SENSITIVITY-REPORT.md` with target, parameter ranking, method table,
sensitivity details, parameter-space structure, approximation sensitivity,
uncertainty budget, recommendations, and summary.

Save to:

- if phase-scoped: `${phase_dir}/SENSITIVITY-REPORT.md`;
- otherwise: `GPD/analysis/sensitivity-{slug}.md`.

Resolve `REPORT_PATH` only after the target quantity and any authoritative
phase metadata are known:

- If authoritative phase-backed context exists: `REPORT_PATH="${phase_dir}/SENSITIVITY-REPORT.md"`
- Otherwise: `REPORT_PATH="GPD/analysis/sensitivity-{slug}.md"`

Create `GPD/analysis/` only for the standalone/current-workspace branch:

```bash
mkdir -p GPD/analysis
```

Never write standalone/current-workspace sensitivity reports under `GPD/phases/**`.

Update state only when both `state_exists` and `phase_found` are true:

```bash
gpd uncertainty add "{target quantity}" \
  --value "{nominal_value}" \
  --uncertainty "{total_uncertainty}" --phase "{phase_number}" --method "sensitivity-analysis"
```

Run `gpd uncertainty add` for the target and significant parameter-derived
contributions. If no phase-scoped project context exists, skip all `gpd uncertainty add` calls. The run ends after writing
`GPD/analysis/sensitivity-{slug}.md` in the invoking workspace and presenting
the results directly.
</step>

<step name="commit_and_present">
Commit phase-scoped sensitivity artifacts only when both `state_exists` and
`phase_found` are true:

```bash
PRE_CHECK=$(gpd pre-commit-check --files "${REPORT_PATH}" GPD/STATE.md 2>&1) || true
echo "$PRE_CHECK"

gpd commit \
  "data(phase-${phase_number}): sensitivity analysis - ${TARGET_QUANTITY}" \
  --files "${REPORT_PATH}" GPD/STATE.md
```

If `commit_docs` is disabled, expect the CLI commit bridge to skip cleanly. Do not run an unconditional standalone docs commit for this workflow. If the run is not phase-scoped, do not run `gpd pre-commit-check` or `gpd commit`. Leave
`GPD/analysis/sensitivity-{slug}.md` in the working tree and present the
findings directly.

Present target value, total uncertainty, dominant parameter, top contributors,
warnings, output files, and next commands for error propagation, parameter
sweep, or numerical convergence.
</step>

</process>

<failure_handling>
- Divergent sensitivity: flag critical point, resonance, or ill-conditioned
  formulation and recommend reformulation or non-perturbative treatment.
- Missing parameter: ask for value and uncertainty; do not guess.
- Unstable finite difference: change step, prefer analytical derivative, or
  mark parameter as special treatment required.
- All-zero sensitivities: verify dependency chain and perturbation scale before
  reporting.
</failure_handling>

<success_criteria>
- [ ] Current-workspace supporting context loaded via
  `gpd --raw init progress --include state,config --no-project-reentry`.
- [ ] `gpd --raw init phase-op` used only when authoritative phase context exists.
- [ ] `gpd result search`, `gpd result show "{result_id}"`, and
  `gpd result deps "{result_id}"` used for canonical target/dependency lookup
  when applicable.
- [ ] Target quantity and relevant parameters cataloged with nominal values and
  uncertainties.
- [ ] Analytical, numerical, or combined method chosen per parameter.
- [ ] Dimensionless sensitivity, endpoint sensitivity, and uncertainty
  contribution computed for each parameter.
- [ ] Divergent, stiff, null, or cancelling directions flagged.
- [ ] Approximation systematics included.
- [ ] `SENSITIVITY-REPORT.md` generated at the resolved path.
- [ ] `propagated_uncertainties` updated via `gpd uncertainty add` only when
  `state_exists=true` and `phase_found=true`.
- [ ] Phase-scoped artifacts committed via `gpd commit`; standalone or
  analysis-only runs present results directly without `STATE.md` or `state.json`
  mutations.
</success_criteria>
