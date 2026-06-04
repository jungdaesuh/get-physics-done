# Cross-Domain Projects Planning Guide

Use when the phase combines a physics domain with a distinct method domain or
when results cross subfield convention boundaries.

Core principle:

One domain supplies the physics claim and therefore the decisive verification
criteria. Another domain may supply the method and therefore the task order.
Make that split explicit before planning work.

Planning requirements:

1. Create an early convention-bridge task when outputs from one domain become
   inputs to another.
2. State metric, unit, Fourier, field-normalization, temperature, and coupling
   conversions at every boundary where they matter.
3. Add spot checks on both sides of the bridge: the physics-domain limit and
   the method-domain consistency check.
4. Assign verification to the right domain. Do not use a method-domain check as
   a substitute for the physics-domain decisive evidence.

Common convention conflicts:

- Metric signature between particle-physics and relativity conventions.
- Unit systems between natural units, geometric units, SI, CGS, or atomic units.
- Fourier normalization between lattice, condensed-matter, and continuum QFT
  expressions.
- Relativistic versus non-relativistic state normalization.
- Temperature as energy units versus Kelvin.
- Coupling constants such as alpha, e, g, or atomic-unit conventions.

Decisive artifacts:

- Conversion table consumed by later tasks.
- Boundary spot-check calculation.
- Verification task that confirms the transported result still satisfies the
  destination-domain contract claim.
