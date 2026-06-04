---
load_when:
  - "dimension detail"
  - "ambiguous blocker classification"
  - "deep/full plan-check profile"
  - "compact D0-D16 index needs examples"
  - "unfamiliar dimension"
tier: 1
context_cost: large
---

# Plan Checker Dimension Catalog

Detailed D0-D16 criteria for `gpd-plan-checker`. The compact D0-D16 index in
the agent prompt stays mandatory; load this catalog only when that index flags
ambiguity, blocker classification needs examples, the profile is deep/full, or a
plan touches an unfamiliar dimension.

## Dimension 0: Contract Gate

**Question:** Do these plans carry the approved contract into execution without allowing false progress?

**Authority order:** `plan frontmatter contract` -> `verification_context project_contract`. Treat `effective_reference_intake` and `active_reference_context` only as readable projections of those anchors, never as substitute authority.
Treat stable knowledge docs surfaced through the shared reference context as reviewed background syntheses only. They may refine assumptions or method choice when they agree with stronger sources, but they do not override `convention_lock`, `project_contract`, the PLAN `contract`, `contract_results`, `comparison_verdicts`, proof-review artifacts, or direct benchmark/result evidence.

Reject with `blocker` if any of the following is true:

- No decisive claim or deliverable tied to the phase goal is covered by the plan set.
- A plan advances no decisive claim or deliverable and only reports infrastructure, setup, or qualitative proxy progress.
- A decisive claim or deliverable lacks at least one acceptance test or explicit executable check.
- A contract-critical anchor (`must_surface`, `must_read_refs`, user-critical prior output, or known baseline) is absent from the plan context or comparison path.
- A forbidden proxy is used as the only success condition.
- A risky plan has no disconfirming observation, stop condition, or reframe trigger.
- Selected protocol bundle guidance is absent where the phase clearly depends on it for estimator discipline, decisive artifacts, or verification coverage.

Treat a plan as risky if it relies on approximations, novel inference, weak anchors, or non-empty `uncertainty_markers`.

**Stable blocker dimensions for this gate:**

- `contract_decisive_output`
- `contract_acceptance_test`
- `contract_anchor_coverage`
- `proxy_only_success_path`
- `contract_disconfirming_path`
- `protocol_bundle_coverage`

## Dimension 1: Research Question Coverage

**Question:** Does every component of the research question have task(s) addressing it?

**Process:**

1. Extract phase goal from ROADMAP.md
2. Decompose goal into requirements (what must be true for the question to be answered)
3. For each requirement, find covering task(s)
4. Flag requirements with no coverage

**Red flags:**

- Requirement has zero tasks addressing it
- Multiple requirements share one vague task ("solve the model" for ground state, excitations, and thermodynamics)
- Requirement partially covered (forward scattering derived but backward scattering omitted)
- Observable claimed but no task connects theory to measurable quantity
- Research question requires comparison with experiment but no data analysis task exists

## Dimension 2: Task Completeness

**Question:** Does every task have Formulation + Method + Validation + Deliverable?

**Process:**

1. Parse each `<task>` element in PLAN.md
2. Check for required fields based on task type
3. Flag incomplete tasks

**Required by task type:**
| Type | Formulation | Method | Validation | Deliverable |
|------|-------------|--------|------------|-------------|
| `analytical` | Equations/setup | Derivation steps | Limiting cases + consistency checks | Expressions/results |
| `computational` | Model specification | Algorithm + parameters | Convergence tests + benchmarks | Data/plots/tables |
| `literature` | Search scope | Sources + criteria | Cross-referencing | Summary + key results |
| `checkpoint:*` | N/A | N/A | N/A | N/A |

**Red flags:**

- Missing `<validation>` -- can't confirm correctness of result
- Missing `<deliverable>` -- no concrete output specification
- Vague `<method>` -- "solve the Schrodinger equation" instead of specific approach (perturbation theory to 2nd order, exact diagonalization for N<=12, etc.)
- Empty `<formulation>` -- starting point undefined
- No error estimation strategy for numerical work
- No specification of units or conventions

## Dimension 3: Mathematical Prerequisite Completeness

**Question:** Are all mathematical tools and prerequisites available for the planned approach?

**Process:**

1. For each analytical task, identify required mathematical machinery
2. Verify prerequisites are either assumed known or have preceding tasks
3. Check that notation and conventions are defined before use
4. Verify that special functions, identities, or theorems cited are applicable

**Red flags:**

- Task assumes a result that is itself non-trivial and unplanned (e.g., "using the Ward identity" without deriving or citing it)
- Integral or sum claimed convergent without justification
- Regularization/renormalization needed but no scheme specified
- Coordinate system or gauge choice absent when result depends on it
- Tensor notation or index conventions used inconsistently across tasks
- Symmetry assumptions stated but not verified for the specific model

## Dimension 4: Approximation Validity

**Question:** Are all approximations and assumptions appropriate for the physical regime of interest?

**Process:**

1. Catalog all approximations used across tasks (perturbative, semiclassical, mean-field, adiabatic, etc.)
2. For each approximation, verify the validity conditions are stated
3. Check that the parameter regime in the research question satisfies those conditions
4. Verify that corrections or breakdown signatures are mentioned

**MANDATORY COMPUTATION:** For EVERY approximation in the plan, COMPUTE the numerical value of the expansion parameter in the regime being studied. If the plan says "weak coupling g << 1" and studies g = 0.5, compute O(g^2) ≈ 0.25 and assess whether 25% corrections constitute "small." This computation, not just the validity statement, IS the check. A plan that states "perturbation theory is valid" without computing the expansion parameter's numerical value in the target regime FAILS this dimension.

**Red flags:**

- Perturbation theory applied without specifying the small parameter or its numerical value
- Mean-field approximation used near a critical point without justification
- Non-relativistic approximation used for energies approaching rest mass
- WKB/semiclassical approximation used where quantum number is small
- Born approximation for strong coupling
- Linearization of inherently nonlinear dynamics without estimating nonlinear corrections
- Multiple approximations compounded without tracking cumulative error

## Dimension 5: Computational Feasibility

**Question:** Will the computational approach actually work within resource constraints?

**Process:**

1. For each computational task, estimate scaling (time, memory)
2. Verify convergence criteria are specified
3. Check that numerical precision requirements are stated
4. Assess stability of proposed algorithms for the problem at hand

**Red flags:**

- Exact diagonalization planned for Hilbert space dimension > 10^6 without sparse methods
- Monte Carlo simulation without specified equilibration/sampling strategy
- PDE solver without mesh convergence study
- Floating-point sensitive calculation without precision analysis (cancellation, condition number)
- Algorithm complexity exceeds available resources (O(N!) for N > 20, etc.)
- No error bars or uncertainty quantification for stochastic methods
- Iterative method without convergence criterion or maximum iteration count
- Parallelization assumed but not specified in the plan

**Scaling reference (order-of-magnitude):**
| Method | Feasible Scale | Warning Scale | Blocker Scale |
|--------|---------------|---------------|---------------|
| Exact diag. | dim < 10^4 | dim ~ 10^5 | dim > 10^6 |
| Dense linear algebra | N < 10^4 | N ~ 10^4 | N > 10^5 |
| Sparse linear algebra | nnz < 10^7 | nnz ~ 10^8 | nnz > 10^9 |
| MC sampling | 10^4-10^6 samples | 10^7 samples | 10^8+ without justification |
| DFT (plane-wave) | < 100 atoms | 100-500 atoms | > 500 atoms (need linear-scaling) |

## Dimension 6: Validation Strategy Adequacy

**Question:** Is the plan for checking correctness sufficient to trust the results?

**Process:**

1. Catalog all validation checks across tasks
2. Map checks against standard physics validation hierarchy
3. Flag missing validation layers

**Validation hierarchy (most to least fundamental):**

1. **Dimensional analysis** -- do all expressions have correct units?
2. **Symmetry checks** -- does the result respect the symmetries of the problem?
3. **Limiting cases** -- does the result reduce to known results in appropriate limits?
4. **Conservation laws** -- are conserved quantities actually conserved?
5. **Sum rules / identities** -- are exact constraints satisfied?
6. **Numerical cross-checks** -- do independent methods agree?
7. **Comparison with literature** -- do results match published values?
8. **Comparison with experiment** -- does theory match data?

**Red flags:**

- No limiting cases checked (every physical result should have at least one known limit)
- Numerical results presented without convergence study
- Analytical result not checked numerically in any regime
- Symmetry of solution not verified against symmetry of Hamiltonian/Lagrangian
- Conservation law violated (energy, momentum, charge, probability)
- No comparison with any prior work
- Error bars absent from numerical results

**Verifier confidence interaction:** The verifier caps confidence at MEDIUM when code execution is unavailable, and defers convergence (5.9) and statistical rigor (5.12) checks entirely. If the plan's validation strategy relies SOLELY on numerical verification (convergence tests, Monte Carlo error bars, numerical cross-checks) with no analytical fallback:

- If Dimension 16 (environment validation) confirms computational tools are available: no issue
- If Dimension 16 flags limited or uncertain computational capability: escalate from info to warning
- In all cases, plans should include at least one analytical cross-check (limiting case, dimensional analysis, or symmetry argument) as a verification anchor that works even without code execution

## Dimension 7: Anomaly and Topological Awareness

**Question:** If the research involves quantum field theories, many-body systems, or topological phases, are anomalies and topological properties properly accounted for?

**Process:**

1. Check whether the system has classical symmetries that could be anomalous
2. Verify that anomaly matching is planned between UV and IR descriptions
3. For topological systems, check that topological invariants are computed and verified to be integers
4. For gauge theories, verify anomaly cancellation is checked

**Red flags:**

- Chiral symmetry used in a quantum calculation with no mention of ABJ anomaly
- Effective field theory matching without anomaly matching ('t Hooft conditions)
- Topological phase studied without computing topological invariant (Chern number, Berry phase, Z_2 index)
- Gauge theory with chiral fermions and no anomaly cancellation check
- Theta terms or Chern-Simons terms ignored when they could contribute
- Bulk-boundary correspondence not checked in topological systems

## Dimension 8: Result Wiring and Coherence

**Question:** Are results connected to form a complete answer, not just derived in isolation?

**Process:**

1. Identify deliverables across all tasks
2. Check that downstream tasks reference upstream results correctly
3. Verify that final deliverable synthesizes intermediate results
4. Check for consistent notation, conventions, and units across tasks

**Red flags:**

- Intermediate result derived but never used in subsequent tasks
- Two tasks derive the same quantity with different methods but no comparison task
- Final result depends on intermediate that has no producing task
- Notation inconsistent between tasks (k vs q for wavevector, different sign conventions)
- Units differ between connected tasks (natural units in one, SI in another) without conversion
- Parameter values assumed differently across tasks

**What to check:**

```
Hamiltonian -> Equations of motion: Does action mention variation/commutator?
Partition function -> Thermodynamics: Does action mention differentiation?
Scattering amplitude -> Cross section: Does action mention squaring and phase space?
Band structure -> DOS: Does action mention integration/tetrahedron method?
Symmetry analysis -> Selection rules: Does action mention matrix elements?
```

## Dimension 9: Dependency Correctness

**Question:** Are plan dependencies valid and acyclic?

**Process:**

1. Parse `depends_on` from each plan frontmatter
2. Build dependency graph
3. Check for cycles, missing references, future references

**Red flags:**

- Plan references non-existent plan (`depends_on: ["99"]` when 99 doesn't exist)
- Circular dependency (A -> B -> A)
- Future reference (plan 01 referencing plan 03's output)
- Wave assignment inconsistent with dependencies
- Analytical result needed by computational task but scheduled in parallel

**Dependency rules:**

- `depends_on: []` = Wave 1 (can run parallel)
- `depends_on: ["01"]` = Wave 2 minimum (must wait for 01)
- Wave number = max(deps) + 1

**Physics-specific dependency patterns to verify:**

```
Literature review -> Problem formulation (must know prior art first)
Symmetry analysis -> Hamiltonian construction (symmetry constrains form)
Analytical derivation -> Numerical implementation (code implements equations)
Convergence tests -> Production runs (parameters must be validated first)
Raw computation -> Post-processing/analysis (data must exist first)
```

## Dimension 10: Scope Sanity

**Question:** Will plans complete within context budget?

**Process:**

1. Count tasks per plan
2. Estimate complexity of each task (lines of derivation, compute time, etc.)
3. Check against thresholds

**Thresholds:**
| Metric | Target | Warning | Blocker |
|--------|--------|---------|---------|
| Tasks/plan | 2-3 | 4 | 5+ |
| Equations/task | 5-15 | 20 | 30+ |
| Files/plan | 5-8 | 10 | 15+ |
| Total context | ~50% | ~70% | 80%+ |

**Red flags:**

- Plan with 5+ tasks (quality degrades)
- Single task attempting full derivation of complex result (e.g., all of renormalization group in one task)
- Computational task with no intermediate checkpoints
- Literature review spanning more than 3 subfields in one task
- Ambitious scope without fallback strategy (what if the integral doesn't converge analytically?)

## Dimension 11: Contract Completeness And Artifact Derivation

**Question:** Does the plan contract trace back to the research question and block false progress?

**Process:**

1. Check each plan has `contract` in frontmatter
2. Verify the contract contains claims, deliverables, references, acceptance tests, forbidden proxies, and uncertainty markers
3. Verify claims are physically meaningful (not implementation details)
4. Verify deliverables and acceptance tests support the claims
5. Verify anchor references are present where the plan depends on benchmarks, prior outputs, or user-mandated refs
6. Verify there is an explicit disconfirming path and at least one forbidden proxy guarding against false progress

**Red flags:**

- Missing `contract` entirely
- Missing claims, deliverables, references, acceptance tests, forbidden proxies, or uncertainty markers
- Claims are method-focused ("scipy installed", "matrix diagonalized") not physics-focused ("ground state energy converged to 0.1% accuracy", "phase boundary determined for 0 < T < T_c")
- Deliverables or tests don't map to claims
- Missing disconfirming observation or weakest anchor
- No anchor reference despite benchmark- or literature-dependent work
- Proxy-only plans where the plan would produce activity without decisive evidence
- No clear path from artifacts to a publishable figure, table, or equation

## Dimension 12: Literature Awareness

**Question:** Is the plan aware of relevant prior work to avoid rediscovery and ensure correctness?

**Process:**

1. Identify the key physical quantities and methods in the plan
2. Check whether known exact results, standard approximations, or established techniques are referenced
3. Verify the plan doesn't propose solving a problem that has a known closed-form solution
4. Check that the novelty claim (if any) is supported

**Red flags:**

- Plan derives a result that is textbook material without citing it (Landau levels, Debye model, BCS gap equation)
- Numerical approach used for a problem with a known analytical solution
- No references to prior work in the same system/regime
- Method chosen is known to fail for this class of problems (in published literature) but plan doesn't address this
- Claim of novelty for a known result

**Independent verification:** Use external literature lookup to verify at least one key literature claim per plan. Do not rely solely on grepping project files. If the plan claims "the Onsager solution provides an exact benchmark," search to confirm this claim.

## Dimension 13: Path to Publication

**Question:** Is there a clear trajectory from the planned work to a communicable, publishable result?

**Process:**

1. Identify the main results the plan aims to produce
2. Check that figures, tables, or key equations are specified as deliverables
3. Verify that context and framing tasks exist (introduction, motivation, comparison)
4. Check that the narrative arc is coherent: question -> method -> result -> implication

**Red flags:**

- Computation produces raw data but no analysis or visualization task
- Analytical result derived but physical interpretation absent
- No comparison with competing approaches or experimental data
- Results are technically correct but not framed to answer a meaningful question
- Missing uncertainty quantification that would be required for publication
- No task addresses "so what?" -- the significance of the result

## Dimension 14: Failure Mode Identification

**Question:** Does the plan identify what can go wrong and have contingency strategies?

**Process:**

1. For each task, identify potential failure modes
2. Check whether the plan acknowledges these risks
3. Verify fallback strategies exist for critical paths

**Common physics failure modes:**

- Perturbation series diverges or is asymptotic
- Numerical instability (stiff ODEs, ill-conditioned matrices, sign problem)
- Integral doesn't converge (UV/IR divergences)
- Saddle-point approximation has multiple saddles with comparable contributions
- Phase transition is first-order when mean-field predicted second-order
- Symmetry breaking pattern differs from assumption
- Finite-size effects dominate and don't extrapolate cleanly
- Monte Carlo sampling gets trapped in metastable states
- Analytical continuation from imaginary time is ill-posed

**Red flags:**

- No mention of what happens if the primary approach fails
- Numerical work without convergence criteria (how do you know it failed?)
- Perturbative calculation without estimate of higher-order corrections
- Single computational method with no cross-check

## Dimension 15: Context Compliance (if CONTEXT.md exists)

**Question:** Do plans honor researcher decisions from gpd:discuss-phase?

**Only check if CONTEXT.md was provided in the verification context.**

**Process:**

1. Parse CONTEXT.md sections: Decisions, Agent's Discretion, Deferred Ideas
2. For each locked Decision, find implementing task(s)
3. Verify no tasks implement Deferred Ideas (scope creep)
4. Verify Discretion areas are handled (planner's choice is valid)

**Red flags:**

- Locked decision has no implementing task
- Task contradicts a locked decision (e.g., researcher said "use tight-binding model", plan uses DFT)
- Task implements something from Deferred Ideas
- Plan ignores researcher's stated preference for method, approximation, or scope

## Dimension 16: Computational Environment Validation

**Question:** Does the plan assume tools, libraries, or infrastructure that may not be available to the executor?

**Process:**

1. Scan all tasks for references to specific software, libraries, hardware, or services
2. Classify each dependency as: standard (Python stdlib, numpy, scipy, sympy, matplotlib), common (well-known pip packages), specialized (licensed software, compiled codes, specific hardware)
3. For specialized dependencies, check whether the plan provides an alternative or installation path
4. Flag assumptions about hardware (GPU, cluster, large RAM) without justification

**Dependency tiers:**

| Tier | Examples | Action |
|------|----------|--------|
| **Standard** | Python, numpy, scipy, sympy, matplotlib, mpmath | No flag needed |
| **Common** | networkx, pandas, h5py, numba, cython | Info: verify available |
| **Specialized** | Mathematica, MATLAB, Maple, Cadabra, FORM | Warning: needs alternative or confirmed availability |
| **Licensed/Compiled** | VASP, Gaussian, ABINIT, COMSOL, Ansys | Blocker: must confirm license + access or provide open alternative |
| **Hardware** | GPU (CUDA), HPC cluster, >64 GB RAM, MPI | Warning: must justify necessity and confirm availability |
| **External services** | Cloud computing, API access, database servers | Blocker: must confirm access and cost |

**Red flags:**

- Plan says "use Mathematica to solve..." without confirming Mathematica is available
- Computational task requires GPU but no GPU availability is established
- Plan assumes MPI parallelism or cluster scheduler (SLURM, PBS) without confirming access
- Task uses a compiled Fortran/C code that requires specific build environment
- Library version dependency not specified (e.g., "use JAX" without noting CPU vs GPU backend)
- Plan assumes internet access for downloading data or packages during execution
- Code requires specific OS features (Linux-only system calls, Windows COM objects)

**Key principle:** The executor agent runs in a computational environment with Python, standard scientific packages, and file I/O. Plans should not assume anything beyond this without explicit justification. When specialized tools are genuinely needed, the plan must declare them in `tool_requirements`, keep `researcher_setup` for human-only credentials/setup, and then either (a) confirm availability, (b) provide installation instructions as a permission-gated prerequisite task, or (c) offer a fallback using standard tools.

## Benchmark Contract Anchor Example

**Checker anchor example:** Keep one concrete benchmark contract visible when it matters:

- `schema_version: 1`
- `in_scope: ["Recover the benchmark value within tolerance"]`
- `GPD/phases/00-baseline/00-01-SUMMARY.md`
- `GPD/phases/00-baseline/00-01-SUMMARY.md#gauge-unit-and-notation-conventions`
- `GPD/phases/00-baseline/00-01-SUMMARY.md#gauge-and-tensor-convention`
- `GPD/phases/01-vacuum-polarization/01-01-SUMMARY.md`
- `claim_kind: theorem`
- `parameters:`
- `- symbol: k`
- `domain_or_type: "dimensionless"`
- `aliases: [kappa]`
- `required_in_proof: true`
- `hypotheses:`
- `- id: hyp-normalization`
- `text: "Reference normalization and tolerance convention match Ref-01"`
- `symbols: [k]`
- `category: assumption`
- `conclusion_clauses:`
- `- id: concl-benchmark`
- `text: "Benchmark agreement stays within tolerance at every approved sample"`
- `proof_deliverables: [deliv-proof-main]`

context_intake:
  must_read_refs: [ref-main]
  must_include_prior_outputs: ["GPD/phases/00-baseline/00-01-SUMMARY.md"]
  user_asserted_anchors: ["GPD/phases/00-baseline/00-01-SUMMARY.md#gauge-unit-and-notation-conventions"]

references:
  - id: ref-main
    why_it_matters: "Provides the benchmark value and comparison convention."
    required_actions: [read, compare, cite]

acceptance_tests:
  - id: test-main
    procedure: "Compare the computed value against the benchmark anchor within tolerance."
