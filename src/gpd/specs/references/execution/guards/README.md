# Executor Guard Assets

Use these files only when the active task or selected protocol bundle needs
them. They are execution guards, not tutorials.

## Loading Rule

1. Prefer `execution_guides` listed in the selected protocol bundle context.
2. Load one guard file at a time. Do not load this whole directory by default.
3. If no selected guard fits, use `core-computation-guards.md` for method
   families and `domain-post-step-guards.md` for domain quick checks.
4. For completion checks outside a selected bundle, use
   `final-verification-guards.md`.

## Generic Fallbacks

- `core-computation-guards.md` - compact method checks for common computation
  types.
- `domain-post-step-guards.md` - compact domain checks for major intermediate
  results.
- `final-verification-guards.md` - compact final checks before SUMMARY.md.

## Curated Bundle Guards

- `stat-mech-simulation.md`
- `lattice-gauge-monte-carlo.md`
- `tensor-network-dynamics.md`
- `numerical-relativity.md`
- `cosmological-perturbation-cmb.md`
- `fluid-mhd-dynamics.md`
- `density-functional-electronic-structure.md`

If none of these matches, stay with the executor base prompt, contract-backed
anchors, selected verifier extensions, and the on-demand executor index.
