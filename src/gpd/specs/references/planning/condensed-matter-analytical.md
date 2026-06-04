# Condensed Matter (Analytical) Planning Guide

Use for analytical many-body models, order parameters, mean-field theory,
response functions, collective modes, and phase diagrams.

Dependency skeleton:

```
Model Hamiltonian -> symmetry analysis -> order-parameter choice
-> mean-field or saddle-point construction -> self-consistency
-> fluctuations or response -> phase-boundary calculation -> benchmark checks
```

Decision points:

- Decoupling channel: particle-hole, particle-particle, exchange, or mixed.
- Order parameter and broken symmetry.
- Whether spin-orbit, disorder, interactions, or topology are in scope.

Planning requirements:

- Put the model definition and symmetry inventory before approximation work.
- Treat mean field as the parent result for fluctuation, RPA, or 1/N tasks.
- Add a validity or Ginzburg-criterion task when claiming a phase boundary.

Common pitfalls:

- Using mean-field exponents where fluctuations dominate.
- Neglecting Goldstone or gauge modes.
- Double-counting diagrams in self-consistent approximations.
- Mistaking a crossover for a phase transition.

Decisive artifacts:

- Locked Hamiltonian and convention ledger.
- Self-consistency equations or saddle-point conditions.
- Response, mode, or phase-boundary result with symmetry and limit checks.
