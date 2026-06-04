# Statistical Mechanics Planning Guide

Use for partition functions, thermodynamics, phase transitions, universality,
and critical behavior.

Dependency skeleton:

```
Ensemble choice -> partition function or simulation measure -> free energy
-> thermodynamic derivatives -> transition diagnosis -> scaling analysis
-> benchmark, exact-limit, or transfer-matrix check
```

Decision points:

- Ensemble and fixed quantities.
- First-order versus continuous transition strategy.
- Scaling variables and finite-size protocol near criticality.

Planning requirements:

- State which variables fluctuate and which are fixed before deriving response
  or fluctuation formulae.
- Add analytical and numerical cross-checks in parallel only when both are in
  scope and share a decisive observable.
- For simulations, require thermalization, autocorrelation, and effective sample
  size handling before production interpretation.

Common pitfalls:

- Confusing crossovers with transitions.
- Using the wrong scaling variable near a multicritical point.
- Missing first-order transitions in too-small systems.
- Dropping the identical-particle Gibbs factor.

Decisive artifacts:

- Ensemble declaration tied to observables.
- Critical or thermodynamic result with finite-size or limit accounting.
- Benchmark or exact-solution comparison for the decisive claim.
