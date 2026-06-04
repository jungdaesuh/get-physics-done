# Executor Numerical Protocol

Load this reference for `<phase_class>numerical</phase_class>`, `<context_hint>code-heavy</context_hint>`, simulations, numerical computation, data analysis, code implementation, `verify="numerical"`, or selected bundles with numerical execution guides.

This module is an executor-specific routing shim. It does not replace the canonical numerical references:

- `{GPD_INSTALL_DIR}/references/protocols/numerical-computation.md`
- `{GPD_INSTALL_DIR}/references/protocols/symbolic-to-numerical.md`
- `{GPD_INSTALL_DIR}/references/protocols/reproducibility.md`
- `{GPD_INSTALL_DIR}/references/verification/core/verification-numerical.md`
- `{GPD_INSTALL_DIR}/references/execution/executor-tool-preflight.md`

Load the heavy verification reference only when a numerical value is load-bearing, contract-backed, surprising, publication-bound, or failed a compact check.

## Minimum Numerical Record

Before computational work, record:

- random seed or deterministic-mode setting;
- code entrypoint and exact command;
- library/package versions;
- compiler/interpreter version;
- hardware or accelerator details when relevant;
- data provenance and input parameter file;
- output artifact paths.

For every numerical result, include:

- convergence at more than one resolution, tolerance, timestep, sample size, or basis size;
- benchmark, known-answer, conservation-law, or analytic-limit comparison;
- error bar, residual, confidence interval, or convergence measure;
- reproducibility command;
- explicit note if the benchmark came from unverified model memory or training data.

Never silently replace `NaN` or `Inf`, ignore numerical exceptions, skip failed computations, or proceed with placeholder values.

## Failure Triage

| Symptom | Likely cause | Executor action |
|---|---|---|
| `NaN` or `Inf` | Division by zero, log branch, overflow, sign error | Trace the operation, add guards, compare intermediate values to derivation, and apply self-critique before retry. |
| Wrong value with no crash | Translation bug or convention mismatch | Load symbolic-to-numerical protocol, unit-test subexpressions, and compare hand-calculated checkpoints. |
| Divergence or poor convergence | Inadequate resolution, bad regulator, invalid approximation | Apply Deviation Rule 2 remedies; after 3 distinct failed attempts, escalate to Rule 5. |
| Hang or no progress | Infinite loop, stalled solver, unreachable tolerance | Add timeout/residual logging, reduce problem size, and check convergence criteria. |
| Memory error or OOM | Grid/basis too large or leak | Reduce size, use sparse/out-of-core methods, and check allocations. |
| Inconsistent runs | Race condition, uninitialized memory, floating-point nondeterminism | Set seeds, deterministic algorithms, `-O0` comparison when compiled, and repeat. |
| Missing package/license/GPU | Environment gate | Stop current task and use `{GPD_INSTALL_DIR}/references/execution/executor-tool-preflight.md`. |

## Convergence Report Skeleton

```markdown
### Numerical Verification: {quantity}

- Command: `{command}`
- Seed/version/hardware: {metadata}
- Resolutions or tolerances: {list}
- Values: {table or artifact path}
- Estimated error: {method and value}
- Benchmark or analytic limit: {source/value/check}
- Failure attempts: {0/1/2/3 with remedies}
- Reproducibility artifact: {script/notebook/data path}
- Verdict: pass | inconclusive | failed
```

## Benchmark Values

Before using a numerical benchmark value as ground truth:

1. Mark it `[UNVERIFIED - training data]` unless it comes from an already verified file, bibliographer output, verifier output, or cited source in the workspace.
2. Record claimed source, exact value, units, uncertainty, and convention.
3. Prefer authoritative sources for downstream verification: PDG for particle physics, NIST CODATA for constants, DLMF for special functions, and explicit review articles.
4. Reduce confidence by one level for any result that depends on an unverified benchmark.

## Selected Guards

When selected protocol bundles provide numerical `execution_guides` or guard assets, load only those selected paths. If selected assets do not cover the method, load `{GPD_INSTALL_DIR}/references/execution/guards/README.md` and then one matching guard file. Do not load the full guard catalog by default.
