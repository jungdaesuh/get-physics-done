<purpose>
Systematically identify and verify the relevant limiting cases for a physics
result or phase, producing either phase-scoped `LIMITING-CASES.md` or
standalone `GPD/analysis/limits-{slug}.md` rooted at the current workspace.
</purpose>

<core_principle>
Every new result must reduce to known results in appropriate limits. If it does
not, the new result is wrong or the known-result identification is wrong. The
workflow must decide that with explicit evidence, not by intuition.
</core_principle>

<references>
Use `references/results/result-lookup-policy.md` for canonical result lookup.
Use `{GPD_INSTALL_DIR}/references/analysis/physics-validation-recipes.md` when
executing domain limit catalogs, singular-limit protocols, numerical
limit-check recipes, and failure-diagnosis prompts.
</references>

<process>

## 0. Validate Context, Load Workspace State, and Resolve the Durable Target

Run centralized command-context preflight first:

```bash
CONTEXT=$(gpd --raw validate command-context limiting-cases "$ARGUMENTS")
if [ $? -ne 0 ]; then
  echo "$CONTEXT"
  # STOP; surface the error.
fi
```

Parse `project_exists`, `checks`, and `managed_output_root`, then classify one
target:

| Condition | Action |
| --- | --- |
| Empty input + current project | ask one focused question for phase number or file path |
| Empty input + no project | stop; centralized preflight should already reject standalone empty launch |
| No project + bare number like `3` or `4.1` | stop: standalone `gpd:limiting-cases` requires an explicit file path. Do not reinterpret a numeric token as a hidden phase selection. |
| Resolved file path | set `TARGET_KIND=file`, `TARGET_FILE=<resolved current-workspace path>` |
| Current project + bare phase number | set `TARGET_KIND=phase`, `PHASE_ARG=<number>` |
| Anything else | ask one focused clarification question |

Load workspace-bound state and conventions without project reentry:

```bash
INIT=$(gpd --raw init progress --include state,config --no-project-reentry)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $INIT"
  # STOP; surface the error.
fi
```

Parse `commit_docs`, `project_exists`, `state_exists`, conventions, active
approximations, validity ranges, and `intermediate_results`. If canonical
stored-result context is needed, follow that result lookup policy.

If `TARGET_KIND=phase`, resolve the phase inside the current workspace:

```bash
PHASE_INIT=$(gpd --raw init phase-op --include state,config "${PHASE_ARG}")
if [ $? -ne 0 ]; then
  echo "ERROR: limiting-cases phase resolution failed: $PHASE_INIT"
  # STOP; surface the error.
fi
```

Parse `phase_found`, `phase_dir`, `phase_number`, `phase_name`, and
`phase_slug`; stop if a requested phase is absent. Set target/output variables
before scanning physics:

| Target kind | Variables |
| --- | --- |
| phase | `TARGET_LABEL="phase ${phase_number}"`; `OUTPUT_PATH="${phase_dir}/LIMITING-CASES.md"` |
| file | stable ASCII `slug`; `TARGET_LABEL="${TARGET_FILE}"`; `OUTPUT_PATH="GPD/analysis/limits-{slug}.md"` rooted at the current workspace |

Only file mode creates `GPD/analysis`. Reuse the resolved `TARGET_KIND`, `TARGET_FILE`, `slug`, and `OUTPUT_PATH` variables consistently. Never replace them with placeholder prose paths. Never write standalone/current-workspace limiting-cases reports under `GPD/phases/**`.

For phase targets, honor contract-critical anchors before writing. If the
loaded state, plan, or intake names a benchmark, comparison target, prior
artifact, or must-read reference, inspect it before claiming verification. If
required evidence is missing, stale, malformed, or fails decisive comparison,
stop before writing `${OUTPUT_PATH}`, report the blocker, and route to
`gpd:plan-phase ${phase_number} --gaps`.

## 1. Identify the Result(s) to Check

Work from resolved target variables, not raw `$ARGUMENTS`.

- If `TARGET_KIND=phase`, enumerate concrete files under `${phase_dir}` first
  (`SUMMARY.md`, `VERIFICATION.md`, `RESEARCH.md`, and numbered artifacts).
- If `TARGET_KIND=file`, set `TARGET_FILES` to `${TARGET_FILE}`.

Scan target files for result expressions and equation labels:

```bash
for path in "${TARGET_FILES[@]}"; do
  grep -n "result\|final\|=.*\\\\frac\|=.*\\\\sqrt\|=.*\\\\sum\|=.*\\\\int\|E\s*=\|Z\s*=\|sigma\s*=\|Gamma\s*=" "$path" 2>/dev/null
  grep -n "\\\\label\|\\\\tag\|# Eq\." "$path" 2>/dev/null
done
```

For each result, record quantity, parameter dependence, physical system, and
source location.

## 2. Identify Applicable Limits

Select limits only when they apply to the result's parameters, physical system,
and independently known behavior. Start from:

- universal: free theory, classical, static, single-particle;
- thermodynamic/statistical: high/low temperature, thermodynamic, ideal/dilute;
- quantum: non-relativistic, semiclassical, weak/strong field, harmonic;
- field theory: tree/free field, low energy, large N, Abelian, regulator limits;
- condensed matter: continuum, atomic/single-site, mean-field, non-interacting;
- relativity/gravity: Newtonian, flat-spacetime, slow-motion, symmetry limits;
- spatial/geometric: dimension, long/short distance, infinite volume.

Ask the user only when the known limiting expression, convention, or benchmark
source is genuinely ambiguous.

## 3. Select and Record Limits

Create a selected-limits table:

```markdown
## Limiting Cases for {Result Name}

| # | Limit | Parameter | Known Result | Source |
|---|-------|-----------|--------------|--------|
```

Required selection checks:

- parameter appears in the result or controls its validity;
- known result source is identified;
- convention compatibility is checked;
- active project approximations make mandatory limits visible.

## 4. Verify Each Limit

Prefer analytical verification:

1. write the full expression;
2. take the limit or expansion explicitly;
3. simplify;
4. compare with the known result;
5. record exact difference if it fails.

Use numerical verification only when analytical comparison is intractable. A
valid numerical limit check approaches the limit systematically and reports the
ratio/error trend; one point is not decisive.

Classify each check as exact match, numerical match, correct leading order,
discrepancy, divergent, or cannot check.

Singular limits require explicit order-of-limits handling. Distributional
limits require test-function or moment comparisons. Load the analysis reference
for the compact protocol when those cases arise.

## 5. Diagnose Failures

For every failed limit, characterize whether the mismatch is a factor, sign,
power, functional form, divergence, convention error, or invalid known-result
selection. Then localize the earliest intermediate expression where the limit
first fails and route to `gpd:debug` only after concrete symbolic or numerical
limit evidence localizes the fault.

## 6. Generate Report

Write `${OUTPUT_PATH}` with:

- target and output path;
- results analyzed;
- limits selected and sources;
- verification evidence table;
- failed limits with discrepancy and likely cause;
- singular-limit notes where applicable;
- summary status and next action.

If `TARGET_KIND=phase`, `${OUTPUT_PATH}` is `${phase_dir}/LIMITING-CASES.md`.
If `TARGET_KIND=file`, `${OUTPUT_PATH}` is `GPD/analysis/limits-{slug}.md`
rooted at the current workspace.

## 7. Present Results and Route

If all pass, report confidence and the passed limit count. If failures exist,
list failures and suggest targeted debugging, dimensional analysis, or
derivation review at the localized expression.

## 8. Finalize Persistence Honestly

Do not run an unconditional standalone docs commit for this workflow.

- If `TARGET_KIND=phase`, `state_exists` is true, and `commit_docs` is enabled,
  you may include `${OUTPUT_PATH}` in the phase's normal documentation commit
  path after reviewing the diff.
- If the run is standalone/current-workspace file mode, skip the commit step entirely and report `${OUTPUT_PATH}` back to the user.
- Do not mutate `STATE.md` or `state.json` from standalone/current-workspace
  file mode.

Optional phase-backed commit flow:

```bash
PRE_CHECK=$(gpd pre-commit-check --files "${OUTPUT_PATH}" 2>&1) || true
echo "$PRE_CHECK"

gpd commit \
  "docs: limiting cases verification — ${phase_slug}" \
  --files "${OUTPUT_PATH}"
```

Only run the commit block when the report is phase-backed and the project is
already in its normal docs-commit path.

</process>

<output>
`${OUTPUT_PATH}` written with full verification results.
</output>

<success_criteria>
- [ ] Target classified through command-context preflight.
- [ ] Workspace state loaded with
  `gpd --raw init progress --include state,config --no-project-reentry`.
- [ ] `TARGET_KIND`, `TARGET_FILE`, `slug`, and `OUTPUT_PATH` reused
  consistently.
- [ ] All relevant results in the target identified.
- [ ] Applicable limits selected with known-result sources.
- [ ] Each limit verified analytically or numerically with trend evidence.
- [ ] Singular or distributional limits handled explicitly when present.
- [ ] Discrepancies characterized and localized.
- [ ] Report generated at `${OUTPUT_PATH}`.
- [ ] Standalone/current-workspace outputs stay under `GPD/analysis/` and skip
  state mutation and commits.
</success_criteria>
