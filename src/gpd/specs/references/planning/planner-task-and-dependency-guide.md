# Planner Task And Dependency Guide

Use this reference when task shape, sizing, dependency categories, or examples
matter more than the compact base prompt.

## Task Anatomy

Every task has four required fields:

- `<files>`: exact file paths created or modified.
- `<action>`: specific research instructions, including what to avoid and why.
- `<verify>`: how to prove completion using physics consistency.
- `<done>`: measurable success criteria.

Keep wording concrete enough for another executor to run without clarification,
especially around conventions, normalization, sign choices, approximations, and
validation thresholds.

## Task Types

| Type | Use For | Autonomy |
| --- | --- | --- |
| `auto` | Everything the assistant can do independently | Checkpoint-free |
| `checkpoint:human-verify` | Physical intuition checks, plot inspection, interpretation checks | Pauses for researcher |
| `checkpoint:decision` | Approach, approximation, convention, or scope choices | Pauses for researcher |
| `checkpoint:human-action` | Truly unavoidable manual setup, credential, license, or cluster actions | Pauses for researcher |

Automation-first rule: if the assistant can derive, code, compute, plot, or
test it, the assistant must do it. Checkpoints verify after automation; they do
not replace automation.

## Sizing

Each task usually targets 15-60 minutes of agent execution time.

- Under 15 minutes: combine with related work.
- 15-60 minutes: right size.
- Over 60 minutes: split.

Split when the task crosses physical regimes, touches more than a few files,
needs multiple distinct techniques, or mixes discovery with implementation.
Combine when one output is immediately the next input, both tasks touch the
same file, and neither task is meaningful alone.

## Physics Task Categories

| Category | Examples | Typical verification |
| --- | --- | --- |
| Derivation | equation of motion, Green's function, Ward identity | dimensions, known limits, symmetry |
| Proof | unitarity, no-go theorem, Goldstone theorem | logical completeness, counterexample check |
| Algorithm | Monte Carlo update, FFT solver, RG integrator | convergence, analytical benchmark |
| Simulation | Ising model, N-body dynamics, lattice gauge theory | conservation, thermalization, finite-size scaling |
| Analysis | correlation extraction, phase diagram mapping | error bars, chi-squared, systematic uncertainty |
| Validation | limiting cases, known results, cross-checks | exact match or convergence |
| Write-up | derivation narrative, methods, result summary | completeness, notation consistency, reproducibility |

## Dependency Graph Detail

For each task, record `needs`, `creates`, and `has_checkpoint`.

| Dependency type | Description | Example |
| --- | --- | --- |
| Mathematical prerequisite | Need result X to derive Y | free propagator before self-energy |
| Computational foundation | Need framework before simulations | integrator before time evolution |
| Logical prerequisite | Need special case before general case | 1D solution before 3D |
| Data dependency | Need output before analysis | MC data before finite-size scaling |
| Notational dependency | Need conventions before calculation | metric choice before Lagrangian |
| Validation dependency | Need benchmark before trusting code | harmonic oscillator test before anharmonic |

Wave assignment: no dependencies -> Wave 1; depends only on Wave 1 -> Wave 2;
shared file conflict -> same plan or sequential waves. Convention
establishment is always Wave 1.

## TDD And External Resources

If you can write the assertion before the implementation, use a dedicated TDD
plan and load `{GPD_INSTALL_DIR}/references/planning/planner-tdd.md`.

If the task needs credentials, licenses, cluster access, or other human-only
setup, record that in `researcher_setup`. If a specialized tool is a hard
execution prerequisite, declare it in `tool_requirements`.
