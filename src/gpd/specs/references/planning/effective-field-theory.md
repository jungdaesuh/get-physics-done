# Effective Field Theory Planning Guide

Use for scale separation, power counting, operator bases, matching, running,
and EFT predictions.

Dependency skeleton:

```
Scale hierarchy -> degrees of freedom -> power counting -> operator basis
-> matching -> running and mixing -> observable prediction
-> truncation and scheme uncertainty
```

Decision points:

- Which scales are separated and by how much.
- Power-counting scheme and expansion parameter.
- Matching order and scheme.

Planning requirements:

- Start with power counting. It determines which operators are required.
- Add an operator-completeness check at the working order.
- Include matching-scale, scheme, and truncation-uncertainty tasks whenever a
  numerical prediction is claimed.

Common pitfalls:

- Including operators beyond the order while missing required lower-order ones.
- Mixing incompatible power-counting schemes.
- Ignoring operator mixing under RG.
- Reporting central values without truncation uncertainty.

Decisive artifacts:

- Scale and degree-of-freedom ledger.
- Operator basis with power-counting labels.
- Prediction with running, matching, and truncation-error evidence.
