# General Relativity / Cosmology Planning Guide

Use for spacetime backgrounds, perturbations, numerical relativity, cosmological
evolution, and relativistic observables.

Dependency skeleton:

```
Convention and background -> gauge or formulation choice -> equations
-> source terms and initial data -> evolution or solution -> observable
extraction -> constraint, gauge, and known-limit checks
```

Decision points:

- Metric signature, curvature convention, and units.
- Gauge choice for perturbation theory.
- Formulation for numerical work: BSSN, generalized harmonic, Z4c, ADM, or
  covariant perturbation theory.

Planning requirements:

- Make gauge/formulation a first-wave decision before deriving or evolving.
- Include Hamiltonian/momentum constraints or gauge-invariant variables in the
  verification path.
- Add a Newtonian, post-Newtonian, weak-field, or known-background limit.

Common pitfalls:

- Gauge-mode contamination in extracted observables.
- Constraint growth mistaken for physics.
- Junk radiation from inconsistent initial data.
- Finite extraction radius or sign convention systematics.

Decisive artifacts:

- Locked convention and gauge/formulation note.
- Constraint or gauge-invariant verification output.
- Observable comparison against a trusted limit or benchmark.
