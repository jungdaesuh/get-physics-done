# QFT Perturbative Calculation Planning Guide

Use for amplitudes, cross sections, loop calculations, renormalization, and
perturbative observables.

Dependency skeleton:

```
Convention lock -> Lagrangian and Feynman rules -> diagram enumeration
-> algebra reduction -> master integral evaluation -> UV/IR treatment
-> physical observable -> Ward identity, unitarity, and known-limit checks
```

Decision points:

- Regularization scheme, because it affects every divergent expression.
- Renormalization scheme, because only scheme-aware observables compare cleanly.
- Diagram organization: individual diagrams, gauge-invariant classes, color
  ordering, or spinor-helicity representation.

Planning requirements:

- Enumerate diagrams before integration. Missing one graph invalidates Ward
  identity and counterterm checks.
- Add an independent count or automated cross-check for diagram completeness.
- Keep coupling, metric, Fourier, field-normalization, and state-normalization
  conventions in the first executable task.

Common pitfalls:

- Missing symmetry factors or fermion-loop signs.
- Incomplete counterterm set.
- Mixing coupling normalizations across sources.
- Treating virtual IR divergences without the matching real contribution.

Decisive artifacts:

- Diagram inventory with order, topology, and symmetry factor.
- Renormalized expression in the locked scheme.
- Observable-level comparison against a known limit, Ward identity, or benchmark.
