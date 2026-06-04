# Numerical PDE/ODE Planning Guide

Use for discretized ODE/PDE systems, solvers, stability analysis, convergence,
and production evolution.

Dependency skeleton:

```
Equation and invariants -> discretization choice -> stability analysis
-> exact or manufactured benchmark -> convergence study -> production solve
-> post-processing -> extrapolation and error budget
```

Decision points:

- Spatial discretization: finite difference, finite volume, finite element,
  spectral, discontinuous Galerkin, or particle method.
- Time integration: explicit, implicit, symplectic, adaptive, or stiff solver.
- Refinement target: boundaries, shocks, singularities, turbulence, or long-time
  phase accuracy.

Planning requirements:

- Put stability and convergence before production.
- Require at least three resolutions when claiming convergence order.
- Add conservation, monotonicity, positivity, or symplectic checks when the
  physical system requires them.

Common pitfalls:

- CFL violations or hidden stiffness.
- Non-symplectic integrators causing secular energy drift.
- Boundary layers or shocks under-resolved.
- Measured convergence order inconsistent with the scheme.

Decisive artifacts:

- Benchmark or manufactured-solution test.
- Convergence table with measured order.
- Production result with error budget and resolution metadata.
