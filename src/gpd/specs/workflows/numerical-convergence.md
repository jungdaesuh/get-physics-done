<purpose>
Validate numerical physics results through benchmark checks, conservation or
invariant checks, convergence studies, stability tests, and an honest error
budget.
</purpose>

<core_principle>
A numerical result without convergence and error evidence is only a number.
Validation must show that the result is independent of numerical artifacts to
the stated precision and that known physics is recovered before new claims are
trusted.
</core_principle>

<references>
Load `{GPD_INSTALL_DIR}/references/analysis/physics-validation-recipes.md` only
when executing detailed benchmark, conservation, convergence, stability, or
error-budget recipes.
Use `references/verification/verification-status-authority.md` for pass/gap
vocabulary.
</references>

<process>

<step name="load_context" priority="first">
Load project state and conventions before validation. Keep this workflow rooted
in the invoking workspace; numerical convergence can use project context when it
exists there, but it must not silently reenter a different recent project.

```bash
INIT=$(gpd --raw init progress --include state,config --no-project-reentry)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $INIT"
  # STOP; surface the error.
fi
```

Parse `state_exists`, `project_exists`, `commit_docs`, conventions, active
approximations, validity ranges, and `intermediate_results`. Use
`gpd result search` for canonical prior-result lookup; once a canonical
`result_id` is known, use `gpd result show "{result_id}"` before reading
supporting artifacts. Keep `gpd query search` for SUMMARY/frontmatter lookup.

When the target is an authoritative current-workspace phase or stored result
with phase metadata, load phase context explicitly:

```bash
PHASE_INIT=$(gpd --raw init phase-op --include state,config "{phase_number}")
if [ $? -ne 0 ]; then
  echo "ERROR: phase initialization failed: $PHASE_INIT"
  # STOP; surface the error.
fi
```

If a bare phase number is not owned by the current workspace, stop and ask for a
file target or correct project. Do not invent phase-local outputs.
</step>

<step name="resolve_target">
**Resolve the validation target and durable output path from the current workspace**

Use the command wrapper's centralized command-context preflight plus `$ARGUMENTS` to classify the target honestly before scanning physics content.

- Empty input + project: ask one focused question for phase number or file path.
- Empty input + no project: stop; the wrapper should already reject it.
- Bare number: phase-backed only when `gpd --raw init phase-op` resolves it in
  the current workspace; otherwise require an explicit file target and do not invent `phase_dir` or `phase_slug` from ambient workspace state.
- File path: derive stable ASCII `slug` and treat it as standalone/current-workspace file mode.

Set the durable output path only after classification:

| Target kind | Output |
| --- | --- |
| authoritative phase | `OUTPUT_PATH="${phase_dir}/NUMERICAL-VALIDATION.md"` |
| standalone/current-workspace file | `OUTPUT_PATH="GPD/analysis/numerical-{slug}.md"` |

Create `GPD/analysis/` only for the standalone/current-workspace branch:

```bash
mkdir -p GPD/analysis
```

Never write standalone/current-workspace numerical validation reports under `GPD/phases/**`.
</step>

<step name="identify_computations">
Catalog each numerical computation in the target:

| Property | Required record |
| --- | --- |
| Observable | physical quantity being computed |
| Method | algorithm, scheme, solver, estimator, or pipeline |
| Numerical controls | grid, timestep, basis, cutoff, tolerance, sample count |
| Expected convergence | order/scaling or reason unknown |
| Benchmarks | analytical, published, or known-limit values |
| Invariants | conservation laws, constraints, residuals, symmetries |
| Cost | time/memory scaling when relevant |

Classify method family: ODE/PDE, eigenvalue, Monte Carlo, optimization,
quadrature, linear algebra, simulation, or other. That classification selects
which detailed recipes to load from the analysis reference.
</step>

<step name="benchmark_validation">
Benchmark before convergence claims. For each benchmark, name the exact special
case, reference value, high-resolution run configuration, absolute/relative
error, tolerance, and status.

If any benchmark fails, stop and debug before interpreting convergence: wrong
high-resolution physics cannot be repaired by grid refinement.
</step>

<step name="conservation_check">
Verify conserved quantities, residual identities, or constraints required by
the physics. Record initial value, maximum drift or residual, growth type
(bounded/linear/exponential), and status. For systems without conservation
laws, record the relevant invariant or why none applies.
</step>

<step name="convergence_testing">
Design the convergence study before running it:

- use at least three geometric refinement levels; five is preferred;
- vary each numerical control independently while holding others at their
  finest tested values;
- compare observed order to expected order;
- use Richardson extrapolation or successive-difference error when justified;
- check multi-parameter order independence before declaring convergence.

Grade each observable:

| Grade | Meaning |
| --- | --- |
| A | last refinements below tolerance and order matches theory |
| B | clear trend, final change within 10x tolerance |
| C | converging but not yet within tolerance |
| D | slow/fluctuating convergence; method suspect |
| F | non-monotone, oscillating, divergent, or wrong limit |

Use the analysis reference for detailed pitfall prompts including stiffness,
oscillatory integrals, critical slowing down, cancellation, adaptive meshes,
and hidden tolerance floors.
</step>

<step name="stability_analysis">
Test sensitivity to small perturbations, precision, and algorithm variants. For
time-stepping, check CFL/physicality/energy-boundedness as applicable. For
iterative algorithms, check residual decrease and expected convergence rate.
Large perturbation amplification, precision disagreement, or algorithm
disagreement must be reported as a gap or blocker.
</step>

<step name="error_estimation">
Construct an error budget for each computed quantity:

| Error source | How estimated | Reducible? |
| --- | --- | --- |
| discretization | convergence/Richardson | yes |
| truncation | cutoff/basis variation | yes |
| statistical | bootstrap/jackknife/autocorrelation | yes |
| floating-point | precision comparison | limited |
| approximation | next-order or better-model comparison | method-dependent |
| model | comparison to a more complete model | research question |

State total error rule, dominant source, and whether more refinement is worth
the cost.
</step>

<step name="generate_report">
Write `${OUTPUT_PATH}` with:

- target and artifact path;
- computation catalog;
- benchmark table;
- conservation/invariant table;
- convergence tables with observed order and grade;
- stability analysis;
- error budget;
- overall validation status and recommended next action.

Save the report to `${OUTPUT_PATH}`. Standalone/current-workspace file-target
runs end after writing the report; do not mutate `STATE.md` or `state.json`.
Do not run an unconditional standalone docs commit for this workflow.

Commit phase-scoped reports only when both `state_exists` and `phase_found` are
true:

```bash
PRE_CHECK=$(gpd pre-commit-check --files "${OUTPUT_PATH}" 2>&1) || true
echo "$PRE_CHECK"

gpd commit \
  "docs: numerical convergence validation — ${phase_slug}" \
  --files "${OUTPUT_PATH}"
```

If `commit_docs` is disabled, expect the CLI commit bridge to skip cleanly. If the run is not phase-scoped, do not run `gpd pre-commit-check` or `gpd commit`.
Leave `GPD/analysis/numerical-{slug}.md` in the working tree and present the
findings directly.
</step>

</process>

<success_criteria>
- [ ] Current-workspace context loaded via
  `gpd --raw init progress --include state,config --no-project-reentry`.
- [ ] `gpd --raw init phase-op` used only when authoritative phase context exists.
- [ ] Numerical computations identified and classified.
- [ ] Benchmarks tested against known results before convergence claims.
- [ ] Conservation laws or invariants checked with quantitative drift/residuals.
- [ ] Convergence tested with geometric refinement sequences and observed order.
- [ ] Stability tested across perturbation, precision, and algorithm variants.
- [ ] Complete error budget and dominant error source recorded.
- [ ] Report generated at the resolved output path.
- [ ] Standalone/current-workspace runs stop after writing
  `GPD/analysis/numerical-{slug}.md` without state mutation or standalone commit.
</success_criteria>
