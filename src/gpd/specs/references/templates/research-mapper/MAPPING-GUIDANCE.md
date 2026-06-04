# Research Mapper Filling Guidance

Load this reference when filling research-map templates, performing incremental
updates, assessing map quality, or falling back after a broken template install.

## Downstream Consumers

Research-map documents are operational references, not prose summaries.

- `gpd:plan-phase` uses FORMALISM.md, ARCHITECTURE.md, CONCERNS.md,
  STRUCTURE.md, VALIDATION.md, CONVENTIONS.md, and REFERENCES.md to decompose
  tasks, inherit conventions, and choose validation priorities.
- `gpd:execute-phase` uses paths, equation locators, validation patterns,
  structure notes, and concerns to continue the project without rediscovery.
- `gpd:research-phase` uses REFERENCES.md and FORMALISM.md to distinguish known
  anchors from unresolved investigation targets.

Every map should therefore include exact file paths in backticks, equation or
section locators when available, convention notes, and clear downstream action.

## How To Fill Templates

Read first, write second. Read all files relevant to a section before writing
that section. Synthesize rather than transcribe: identify the governing
equations, derivation dependencies, load-bearing approximations, and validation
evidence instead of listing every occurrence.

For FORMALISM.md, start from the action, Lagrangian, Hamiltonian, or defining
constraints and trace forward to equations of motion, conservation laws, and
observables. For CONCERNS.md, start from final results and trace backward to
assumptions, approximations, missing checks, or convention drift.

When a template asks for a section and the project does not contain evidence for
it, write `Not detected` or `Not applicable`; do not invent generic content.

## Focus Search Recipes

Use these as starting searches, then follow project-specific file references.

Theory focus:

- Find LaTeX, notebooks, data, and bibliography files.
- Search for Hamiltonian, Lagrangian, action, partition function, model,
  coupling, mass, parameter, symmetry, and conservation.
- Trace `input` and `include` relationships in LaTeX projects.

Computation focus:

- Search LaTeX structure and macro definitions.
- Search Python, Mathematica, and notebook entry points, solvers, imports,
  modules, data flow, and generated outputs.
- Record where new calculations, scripts, and data should be added.

Methodology focus:

- Search approximation, expansion, truncation, assumption, regime, tolerance,
  convergence, precision, benchmark, exact, known, TODO, CHECK, VERIFY, tests,
  and validation scripts.
- Connect every approximation to its parameter, validity regime, and first
  missing correction when detectable.

Status focus:

- Search TODO, FIXME, TBD, placeholder, incomplete, commented-out derivations,
  stubs, unchecked limits, empty citations, missing references, validity ranges,
  and breakdown statements.
- Use web lookup only for the status focus when comparing project coverage with
  current broader literature.

## Section Reasoning

FORMALISM.md Physical System:

1. Find defining model statements and the governing action, Lagrangian,
   Hamiltonian, or constraints.
2. Extract energy, length, time, and dimensionless scales.
3. List degrees of freedom and the files where they are defined.
4. Check whether a reader could reconstruct the model from the map.

FORMALISM.md Symmetries:

1. Search for symmetry, invariant, conserved, Noether, Ward, selection rule, and
   anomaly statements.
2. Mark each symmetry as exact or approximate and state what breaks it.
3. Record consequences: conserved currents, selection rules, gauge constraints,
   or anomaly coefficients.

CONVENTIONS.md Approximations:

1. For each approximation, identify the expansion parameter, its project value
   if available, and the first neglected correction.
2. Grade justification as Strong, Adequate, Weak, or Missing.
3. State what fails if the approximation breaks down.

VALIDATION.md Limiting Cases:

1. For each key result, identify expected limits such as free, classical,
   nonrelativistic, weak/strong coupling, high/low temperature, and system-size
   limits.
2. Search whether the project checks each limit.
3. Record unchecked but known limits as validation gaps.

CONCERNS.md:

1. Start from weak or missing approximations, unchecked load-bearing equations,
   missing validations, and convention drift.
2. Prioritize concerns by impact on the main result.
3. State the repair path or research phase needed.

## Equation Catalog

Every equation cataloged in FORMALISM.md should use stable IDs and include
dependency information:

```markdown
## Equation Catalog

| ID | Equation | Type | Location | Dimensions | Status | Depends On | Used By |
|----|----------|------|----------|------------|--------|------------|---------|
| EQ-001 | H = -J sum_<ij> s_i s_j - h sum_i s_i | Defining | `model.tex` (1.1) | energy | Postulated | - | EQ-002 |
```

Type values: Defining, Derived, Approximate, Numerical.

Status values: Postulated, Derived, Verified, Unchecked, DIMENSIONAL ISSUE.

Assign dimensions to every symbol, verify every term has consistent dimensions,
and mark dimensionless quantities explicitly. If a check fails, record the
failure in the equation table and flag it in CONCERNS.md.

## Worked Example

For a 2D Ising project, the defining Hamiltonian is the load-bearing equation.
Record it as the first equation, then trace derived quantities such as the
partition function, free energy, magnetization, and susceptibility to their
files and equation numbers. Mark the Hamiltonian as Postulated, derived
thermodynamic quantities as derived from it, and observables as depending on the
free energy or partition function.

Do not write only "the Ising Hamiltonian appears in the notes." Write the
specific file and locator, then record the dependency chain.

## Incremental Updates

When `GPD/research-map/*.md` already exists, update incrementally unless the
framework changed, more than half the project changed, the existing map is
corrupt, or the user requested a fresh map.

1. Read existing maps.
2. Compare each map's mtime and `Analysis Date` against referenced files.
3. Use git history when available to find changed non-GPD files since the last
   map edit.
4. Update only affected sections and preserve unchanged content.
5. Update `Analysis Date` and add a short revision note with the previous
   analysis date.

## Quality Self-Assessment

Before returning, score each written document:

- Coverage: COMPLETE, PARTIAL, or INCOMPLETE.
- Specificity: HIGH, MEDIUM, or LOW.
- Physics Accuracy: VERIFIED, PLAUSIBLE, or UNCERTAIN.
- Actionability: ACTIONABLE, PARTIALLY ACTIONABLE, or NOT ACTIONABLE.

Minimum gate: PARTIAL coverage, MEDIUM specificity, PLAUSIBLE physics accuracy,
and PARTIALLY ACTIONABLE downstream use. If a document misses any minimum,
annotate the document line in the canonical confirmation and add a short quality
warning.

Ask these checks before declaring completion:

- Could the planner create concrete tasks from this?
- Could the executor find every referenced file and equation?
- Did you distinguish findings from inferences?
- Did any section receive generic filler instead of project-specific content?

## Broken Template Fallback

If `{GPD_INSTALL_DIR}/references/templates/research-mapper/` is missing, do not
search alternate runtime-specific paths. Treat it as a broken install, use the
minimum structure below, and flag the deterministic missing path in the return
confirmation.

Minimum section structures:

- FORMALISM.md: Physical System, Fundamental Equations, Symmetries, Key Results,
  Open Derivations.
- REFERENCES.md: Active Anchor Registry, Benchmark Values, Prior Artifacts and
  Baselines, Open Questions in Literature.
- ARCHITECTURE.md: Computational Pipeline, Solver Stack, Performance
  Characteristics, Data Flow.
- STRUCTURE.md: Directory Layout, File Inventory, Entry Points, Where to Add New
  Work.
- CONVENTIONS.md: Unit System, Notation Table, Approximations Made, Convention
  Sources.
- VALIDATION.md: Limiting Cases, Numerical Benchmarks, Cross-Checks Performed,
  Gaps.
- CONCERNS.md: Unjustified Approximations, Missing Validations, Theoretical
  Gaps, Priority Rankings.
