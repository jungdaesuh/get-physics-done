# Roadmap Methodology Reference

Late-load this reference only when a roadmap needs a worked decomposition
example, a reminder of the full physics success taxonomy, or help resolving a
nontrivial phase split. The roadmapper prompt carries the always-on contract;
this file carries optional method detail.

## Objective-Driven Decomposition

Roadmaps are for one physicist working with GPD. They should organize physics
progress, not academic administration.

Never add phases for committees, grants, routine status reports, collaboration
management, or conference preparation unless the user explicitly made those
deliverables part of the project. Literature work is usually an input to a
research phase, not a standalone deliverable.

Derive phase boundaries from the objectives and approved contract:

1. Group objectives by natural intellectual milestone.
2. Check dependencies between groups.
3. Merge groups when the contract only supports a narrow first milestone.
4. Split groups only when each split has an independent verifiable closure.
5. Assign every objective to exactly one primary phase.

Good phase boundaries include a complete derivation, a self-consistent
formalism, validated numerical results, or a physically interpretable
prediction. Weak boundaries include arbitrary technique layers, partial
derivations with no closure, or equal-sized buckets of objectives.

## Goal-Backward Criteria

For each fully detailed phase, ask what must be true about the physics when the
phase ends. Convert that answer into 2-5 outcomes that can be checked by
inspecting equations, running a computation, comparing to a benchmark, or
testing a limit.

Examples of outcome framing:

- "The effective theory is derived and its regime of validity is bounded" is a
  phase goal; "integrate out heavy fields" is a task.
- "Predictions are obtained with controlled uncertainty" is a phase goal; "run
  simulations" is a task.

Cross-check every criterion:

- If no objective supports it, either add or repair an objective, mark the
  criterion out of scope, or expose the gap for user decision.
- If a mapped objective supports no criterion, move it, defer it explicitly, or
  rewrite the criteria so the objective has visible closure.

## Dependency DAG

Phases form a directed acyclic graph. For each phase, record prerequisites,
enabled downstream phases, parallelizable waves, and the critical path.
Dependencies should come from physics requirements, not from the order in which
the prompt happens to list objectives.

Common dependencies:

- Formalism normally precedes calculation.
- Calculation or algorithm design normally precedes numerics.
- Validation depends on the result being validated.
- Phenomenology depends on computed observables.
- Paper writing depends on the completed results it summarizes.

## Risk And Backtracking

Research roadmaps must expect dead ends. A perturbative expansion may diverge,
a symmetry argument may fail, an ansatz may become inconsistent, or a numerical
method may not converge.

Each phase should name the top risk, probability, impact, mitigation, and
backtracking trigger. High-impact risks need a fallback method or a clear
checkpoint before the project builds on unstable results.

## Physics Success Checks

Choose checks relevant to the phase. Do not force every check onto every phase.

Mathematical consistency:

- Dimensional correctness of every term.
- Index, sign, normalization, and convention consistency.
- Symmetry, covariance, conservation, causality, positivity, and unitarity
  where applicable.
- No unregulated divergences in final physical predictions.

Limits and benchmarks:

- Known special cases and textbook results.
- Nonrelativistic, weak-coupling, classical, single-particle, low-energy, or
  large/small parameter limits when relevant.
- Agreement with published analytical, numerical, or experimental benchmarks
  within stated uncertainty.

Numerical validation:

- Convergence with resolution, order, sample size, or truncation.
- Stability under step size, cutoff, seed, basis, or gauge choices.
- Error bars or systematic uncertainty estimates.
- Expected computational scaling.

Physical plausibility:

- Correct sign, units, scale, and asymptotic behavior.
- Compatibility with thermodynamics or other established physical constraints.
- Discrepancies with prior work are identified rather than hidden.

## Shallow Mode

Under `shallow_mode=true`, only Phase 1 gets full success criteria. Later
phases remain compact stubs, but each stub must preserve identity:

- objective IDs;
- decisive contract items and deliverables;
- required anchors, baselines, and user-critical prior outputs;
- known forbidden proxies;
- load-bearing stop or rethink triggers.

Do not replace those identities with generic labels. Detailed criteria and task
decomposition are created later by `gpd:plan-phase N`.
