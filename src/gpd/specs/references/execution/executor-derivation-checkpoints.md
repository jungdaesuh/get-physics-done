# Executor Derivation Checkpoints

Load this reference when the active task is derivation-heavy, formalism-heavy, proof-adjacent, ODE/PDE solving, perturbative, cancellation-sensitive, or uses nontrivial mathematical identities.

The base executor prompt owns the always-visible trigger: after every 3-4 derivation steps, run sign, factor, convention, and dimension checks. This module owns the detailed checkpoint forms and error-specific annotations.

## Cancellation Detection

When a computed result is very small compared to individual terms contributing to it:

1. Compute the cancellation ratio: `ratio = |final_result| / max(|individual_terms|)`.
2. If `ratio < 10^{-4}`, treat the result as likely cancellation enforced by a symmetry or identity.
3. Stop and identify the mechanism: Ward identity, conservation law, selection rule, Bose symmetry, Furry's theorem, gauge invariance, or another symmetry/identity.
4. If a symmetry explanation exists, document it as a cross-check.
5. If no symmetry explanation exists, suspect a sign error and re-derive the large terms independently.
6. Record the mechanism in the derivation log and SUMMARY.md, for example: terms cancel to `O(10^{-6})` due to a Ward identity.

## Identity Claims

When using a mathematical identity, tag it close to the step that uses it:

```latex
% IDENTITY_CLAIM: \int_0^\infty x^{s-1}/(e^x+1) dx = (1-2^{1-s}) \Gamma(s) \zeta(s)
% IDENTITY_SOURCE: Gradshteyn-Ryzhik 3.411.3 | derived | training_data
% IDENTITY_VERIFIED: s=2 (LHS=0.8225, RHS=0.8225), s=3 (...), s=0.5 (...)
```

Rules:

- `IDENTITY_SOURCE: citation`: cite the source.
- `IDENTITY_SOURCE: derived`: show the derivation or the reduction to a cited identity.
- `IDENTITY_SOURCE: training_data`: verify numerically at 3 or more test points before use.
- If any verification point fails, do not use the identity. Apply Deviation Rule 3, document the failed tests, and switch to a derived or cited route.

## Boundary Conditions

When solving an ODE or PDE, explicitly declare and verify boundary conditions:

```latex
% BOUNDARY_CONDITIONS: Dirichlet at x=0 (psi(0)=0), Dirichlet at x=L (psi(L)=0)
% ODE_ORDER: 2
% BC_COUNT: 2 (matches ODE order)
% BC_VERIFIED: psi(0) = A sin(0) = 0, psi(L) = A sin(n pi L/L) = 0
```

Rules:

- `BC_COUNT` must equal `ODE_ORDER` for a well-posed boundary-value problem unless the mismatch is explicitly justified.
- Verify each boundary condition in the final solution.
- For PDEs, count spatial and temporal conditions separately.
- If conditions are missing, apply Deviation Rule 4. If the proposed solution violates declared conditions, apply Deviation Rule 5.

## Expansion Order

For perturbative or asymptotic calculations, declare the order before manipulating terms:

```latex
% EXPANSION_ORDER: O(alpha_s^2) in MS-bar scheme
% TERMS_AT_ORDER: tree-level + 1-loop (2 diagrams) + 2-loop (7 diagrams)
% COMPLETENESS: all 2-loop topologies enumerated (vertex, self-energy, box)
```

Rules:

- Count diagrams or terms at each retained order.
- Verify no topology or source term is missing by systematic enumeration.
- Cross-check term counts against known results when available.
- If missing terms appear, apply Deviation Rule 4. If the expansion fails to converge, apply Deviation Rule 3 and escalate after repeated attempts.

## Checkpoint Form

Use this compact form in derivation logs:

```markdown
### SELF-CRITIQUE CHECKPOINT step N

- Sign check: expected sign changes: __; actual: __
- Factor check: factors introduced/removed: __
- Convention check: convention lock fields used: __
- Dimension check: expression dimension: __; expected: __
- Guard tags used: IDENTITY_CLAIM / BOUNDARY_CONDITIONS / EXPANSION_ORDER / none
- Result: pass | re-derived | blocked
```

## Success Checklist

- Every 3-4 derivation steps has a visible sign, factor, convention, and dimension check.
- Failed checks stop downstream work until re-derived.
- Nontrivial identities are cited, derived, or numerically verified at 3 or more points.
- ODE/PDE solutions declare and verify boundary conditions.
- Perturbative results declare the expansion order and term completeness.
- Cancellation-sensitive results record a cancellation ratio and mechanism.
- If the worked-example style is needed, load `{GPD_INSTALL_DIR}/references/execution/executor-worked-example.md` after this module.
