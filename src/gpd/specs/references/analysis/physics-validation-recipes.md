# Physics Analysis Validation Recipes

Compact, on-demand checks for medium analysis workflows. Load this reference
only when executing the corresponding check or writing the report; workflow
roots should keep only the decisive gates visible.

## Shared Validation Floor

- Resolve the target and output path before scanning content. Never infer
  phase-backed writes from recent-project state, prose, or a guessed phase.
- Read convention locks before algebra or numerics. Stop on convention drift.
- Prefer decisive evidence: explicit formulas, benchmark values, convergence
  series, conserved-quantity drift, finite structured data, or named artifacts.
- Use `references/results/result-lookup-policy.md` before rebuilding dependency
  trees by hand.
- Use `references/verification/verification-status-authority.md` for pass/gap
  vocabulary.

## Derivation Checks

- State assumptions, definitions, starting point, and validity domain first.
- Mark every convention with `ASSERT_CONVENTION` at the document header and at
  any step using a convention-sensitive operation.
- For each major step: name the operation, show enough algebra to verify it,
  check dimensions, check a simple limit, and check relevant symmetries.
- For approximations: name the neglected terms, required small or large
  parameter, expected leading correction, and where the approximation fails.
- For complicated algebra: evaluate both sides numerically at safe physical
  parameters and report relative difference.
- For proof-bearing derivations: keep the theorem inventory and proof-redteam
  artifact gate in the workflow root; this reference does not replace that
  fail-closed gate.

Common pitfall prompts: metric/Fourier sign, integration boundary term, free
index mismatch, Wick-rotation factor of `i`, measure/Jacobian factor,
symmetry-factor multiplicity, non-commuting limits, branch cut, and
distributional identity domain.

## Numerical Convergence Checks

- Benchmark first: exactly solvable special case, trusted published value, or
  analytical limit at high resolution.
- Conservation law: record conserved quantity, initial value, max drift, drift
  type, and pass/warn/fail status.
- Convergence: use at least three geometric refinement levels; five is
  preferred. Estimate observed order from Richardson ratios and compare with
  theoretical order.
- Multi-parameter studies: refine each numerical parameter independently while
  holding the others at their finest values; then check that combined
  refinement is order-independent.
- Stability: perturb initial data, compare precision or algorithm variants, and
  check residual/CFL/physicality conditions relevant to the method.
- Error budget: list discretization, truncation, statistical, floating-point,
  approximation, and model errors; identify the dominant error and whether it
  is reducible.

Pitfall prompts: oscillatory quadrature, stiffness, critical slowing down,
catastrophic cancellation, adaptive mesh artifacts, non-monotone convergence,
and hidden tolerance floors.

## Parameter Sweep Checks

- Keep method fixed across all points. If method/regime changes across the
  range, split the request into multiple sweeps and document the boundary.
- Record parameter name, scale, range, point count, observable, computation
  anchor, and total wave count before execution.
- Each point artifact records parameter value(s), observable, uncertainty,
  status, and notes; failed points remain in the aggregate with null results.
- Feature detection checks extrema, rapid-change regions, monotonicity,
  asymptotics, NaN/Inf values, non-physical values, and identical-output bugs.
- Adaptive refinement adds points only around justified high-derivative,
  high-curvature, sign-change, or failed-gap regions and rewrites the merged
  aggregate with provenance.

## Sensitivity Checks

- Compute `S_i = (partial f / partial p_i) * (p_i / f)` and uncertainty
  contribution `abs(df_dp) * delta_p` for every analyzed parameter.
- Choose analytical, numerical, or combined derivatives per parameter and
  record the reason.
- Reject finite-difference steps that leave the validity domain; vary step size
  if derivatives are unstable.
- Flag `|S| > 100`, sign changes, endpoint sensitivities differing by more
  than 50 percent, null directions, and paired cancellations.
- Approximation sensitivity compares current approximation against an exact,
  next-order, or more complete calculation where possible.

## Limiting-Case Checks

- Select only limits involving parameters in the result, the physical domain,
  and independently established known behavior.
- Prefer analytical limits. Numerical limits must approach the limiting
  parameter systematically and report ratio/error trends, not one point.
- Classify each check as exact match, numerical match, correct leading order,
  discrepancy, divergent, or cannot check.
- Singular limits require explicit order-of-limits handling. Distributional
  limits require test-function or moment comparisons instead of pointwise
  comparisons.
- Failure diagnosis starts with factor, sign, power, functional form, or
  divergence mismatch, then checks the earliest intermediate expression where
  the limit fails.

## Report Skeleton

Every report should include target, date, output path, checks performed,
decisive evidence table, gaps/failures, final status, and next action. Keep the
full tables in the artifact, not in the command wrapper.
