# Executor Tool Preflight And Environment Gates

Load this reference when a PLAN has `tool_requirements`, a task requires a specialized executable/package/license/GPU/cluster resource, a notebook or compiled build must run, or execution hits an environment/tool failure.

## Required Preflight

Before substantive execution of a real `PLAN.md`, run:

```bash
gpd validate plan-preflight <PLAN.md path>
```

Rules:

- A missing `required: true` specialized tool is blocking.
- A declared fallback does not override a blocking `required: true` requirement.
- Automatic fallbacks are allowed only for non-blocking preferred tools when scientific intent is preserved.
- `researcher_setup` is for human credentials or manual setup, not a machine-checkable tool contract.
- Canonical tool keys are runtime-agnostic capability labels. For Mathematica / Wolfram Language capability, use `wolfram`.

## Environment Gates

Computational environment errors during execution are gates, not physics failures.

Indicators include: module not found, license expired, CUDA out of memory, MPI initialization failed, Mathematica kernel unavailable, LaTeX package not found, compiler not found, library version mismatch, insufficient disk space, and queue timeout.

Protocol:

1. Recognize the environment gate.
2. Stop the current task.
3. Return `checkpoint:human-action` using the executor checkpoint return format.
4. Provide exact setup steps, including install commands, environment variables, license actions, or queue/GPU requirements.
5. Provide one verification command.
6. Document environment gates in SUMMARY.md as normal gated flow, not as physics deviations.

## External Tool Failure Table

| Symptom | Likely cause | Action |
|---|---|---|
| `NaN` or `Inf` in output | Division by zero, log of negative, overflow | Check inputs, trace the producing operation, and consider sign or absolute-value errors. |
| Segfault or core dump | Out-of-bounds array, null pointer, stack overflow | Reduce problem size; check dimensions; for Fortran use bounds checks when available. |
| `ImportError` or `ModuleNotFoundError` | Library not installed in current environment | Try the project-approved install path; if unavailable, checkpoint as an environment gate. |
| Wrong numerical result | Derivation-to-code translation bug | Load symbolic-to-numerical protocol and compare intermediate values to hand calculations. |
| Hang or no output | Infinite loop, deadlock, excessive runtime | Set timeout, print residuals, and verify convergence criteria are reachable. |
| OOM or memory error | Problem too large or leak | Reduce grid/basis size, use sparse/out-of-core methods, and inspect allocation growth. |
| Inconsistent results across runs | Race, uninitialized memory, nondeterminism | Set seeds, force deterministic algorithms, and compare unoptimized compiled runs when relevant. |

Triage order:

1. Missing tool, wrong version, license, queue, or GPU issue: environment gate.
2. Sign, convention, unit, or translation issue: self-critique plus Deviation Rules 1-4.
3. Divergence, poor convergence, or overflow: Deviation Rule 2.
4. Three failed fix attempts for the same issue: Deviation Rule 5.

## Artifact Execution Details

- LaTeX: compile with project tooling such as `latexmk` or `pdflatex`; stage source and figures, not transient `.aux`, `.log`, `.synctex`, object, or cache files.
- Mathematica/Wolfram: execute `.wl` with `wolframscript` when possible; export notebook-critical results to reproducible scripts.
- Python notebooks/scripts: execute notebooks with `jupyter nbconvert --execute` or `papermill` when available; run scripts in the project environment and capture command, stdout/stderr, and return code.
- Compiled numerical code: build with the project toolchain, run known-answer cases first, and record compiler flags.
- Data files: validate schema/shape, provenance, generating command, parameters, and size; do not stage large binary data without explicit approval.
- Figures: regenerate from scripts, verify labels/units/legends, and stage both figure and generating code when appropriate.

For broader tool choice guidance, load `{GPD_INSTALL_DIR}/references/tooling/tool-integration.md`.
