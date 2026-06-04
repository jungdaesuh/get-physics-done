# Condensed Matter (Numerical) Planning Guide

Use for ED, DMRG, QMC, DMFT, tensor-network, and many-body production
computations.

Dependency skeleton:

```
Model definition -> benchmark reproduction -> convergence study
-> production sweep -> finite-size or bond-dimension scaling
-> extrapolation -> error budget and decisive figure/table
```

Decision points:

- Method choice and known failure mode: sign problem, entanglement growth,
  bath discretization, or finite-size ceiling.
- System size, geometry, and boundary conditions.
- Observable definitions and normalization.

Planning requirements:

- Plan benchmark reproduction before production.
- Reserve explicit work for convergence, autocorrelation, or discarded-weight
  accounting depending on method.
- Keep raw data and metadata as deliverables when claims depend on sweeps.

Common pitfalls:

- QMC sign problem away from controlled regimes.
- DMRG bond dimension too small for two-dimensional or long-time behavior.
- ED extrapolation from too few sizes.
- Production runs launched before thermalization or convergence is proven.

Decisive artifacts:

- Benchmark comparison table.
- Convergence or finite-size scaling plot.
- Reproducible dataset with parameters, seeds, and analysis script.
