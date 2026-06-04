# Planner Execution Procedure

Use this reference when the compact planner core is not enough to carry out the
planning run.

## Context Assembly

1. Load init context:
   ```bash
   INIT=$(gpd --raw init plan-phase "${PHASE}")
   ```
2. Extract `planner_model`, `researcher_model`, `checker_model`,
   `commit_docs`, `research_enabled`, `phase_dir`, `phase_number`,
   `has_research`, and `has_context`.
3. Read `GPD/STATE.md` for position, decisions, blockers, and current phase.
4. Read `GPD/ROADMAP.md` and current phase directory listings.
5. Load current phase `CONTEXT.md` when `has_context=true` and honor locked
   decisions.
6. Load current phase `RESEARCH.md` when `has_research=true` and use standard
   methods, computational patterns, known results, pitfalls, and recommended
   approximations.

## User Decision Fidelity

Before creating tasks, classify phase discussion content:

- Locked decisions must be implemented exactly. Examples include natural units
  versus SI, Coulomb versus Lorenz gauge, perturbative order, lattice versus
  continuum method, or Euclidean versus Lorentzian signature.
- Deferred ideas must not become tasks, optional subtasks, or hidden extensions.
  Examples include finite-temperature extensions, higher-loop corrections, or
  relativistic generalizations explicitly set aside by the user.
- Agent discretion permits standard choices only when they stay inside the
  approved contract. Record the choice and rationale in task actions.

If a locked decision conflicts with literature or a default, honor the locked
decision and note the alternative as context, not as a plan branch.

## Optional Context Triage

Check optional files before reading them. Prefer relevant recent content over
full-project ingestion.

- `GPD/INSIGHTS.md`: read when present and concise; if long, read recent
  entries only.
- `GPD/ERROR-PATTERNS.md`: read when present and concise.
- `GPD/BACKTRACKS.md`: filter to same planning stage and overlapping technique;
  keep at most the last 10 matching rows and cap the rendered block.
- Prior SUMMARYs: read the top 2-4 relevant phases by dependency, convention,
  affected quantity, and roadmap signals; use digest-level context for the rest.

If context is tight, skip optional files and proceed with required sources.

## Conventions And Environment

- Load project and phase convention files before task decomposition.
- If conventions are absent, make convention establishment the first task in
  the first plan.
- For computational phases, check required tools before creating plans.
- Specialized prerequisites outside the guaranteed Python scientific baseline
  must appear in `tool_requirements`; do not hide them in task prose.
- Dependency installation or system setup stays permission-gated.
- Reference hints:
  - `derivation, analytical, symbolic` -> `CONVENTIONS.md`, `FORMALISM.md`
  - `validation, testing, benchmarks` -> `VALIDATION.md`, `REFERENCES.md`

## Learned Patterns

Consult accumulated lessons only when files exist:

- Sign error pattern -> add independent sign verification.
- Convergence lesson -> tighten convergence criteria or algorithm choice.
- Convention pitfall -> insert convention consistency as the first task.
- Approximation lesson -> update approximation validity ranges.
- Prior backtrack -> add a counter-action task mirroring the backtrack.

Record consulted patterns in plan frontmatter when they materially affect the
plan:

```yaml
patterns_consulted:
  backtracks: []
```

## Planning Steps

1. Identify the phase and whether this is standard, gap closure, quick, or
   checker-revision planning.
2. Identify approximation scheme: expansion parameter, order, neglected terms,
   breakdown regime, validity checks, and non-commuting limit order.
3. Apply selected `planning_guides` from protocol bundles; otherwise use the
   domain strategy index and one or two matching guides.
4. Break work into tasks with `needs`, `creates`, sanity gates, exact files,
   action, verify, and done criteria.
5. Assign waves from dependencies.
6. Group tasks into plans: same-wave no-conflict tasks may parallelize; shared
   file conflicts stay together or sequential.
7. Derive contract targets before prose: claims, deliverables, acceptance
   tests, references, forbidden proxies, uncertainty markers, and link IDs.
8. Confirm breakdown through typed checkpoint when interactive mode requires
   confirmation.
9. Write PLAN files using the loaded `phase-prompt.md` template.
10. Validate every PLAN.

## Validation And Roadmap Return

Run plan-preflight before execution-ready handoff:

```bash
gpd validate plan-preflight <PLAN.md>
```

Commit only fresh plan artifacts unless the invoking workflow explicitly
delegates shared-state writes:

```bash
gpd commit "docs: create phase plans" --files ${phase_dir}/*-PLAN.md
```

Fix missing required frontmatter, malformed task XML, checkpoint/interactive
mismatches, missing contract completeness, missing physics checks, and missing
specialized tool declarations before returning success.

Default spawned mode is return-only for shared state. Prepare roadmap updates as
structured `gpd_return.roadmap_updates` instead of writing `GPD/ROADMAP.md`
unless the invoking workflow explicitly delegates roadmap ownership.

## Completion Checklists

Standard planning is complete when:

- `STATE.md`, `ROADMAP.md`, current phase context, and needed prior SUMMARYs are
  read.
- Conventions and approximations are inherited or established before task
  decomposition.
- Mandatory discovery level is handled and recorded.
- Tasks are grouped by dependency waves rather than narrative sequence.
- Each PLAN uses the loaded `phase-prompt.md` and contract schema.
- Each task has type, files when applicable, action, verify, and done fields.
- Verification includes physics checks such as dimensions, limits, conservation,
  convergence, or symmetry.
- `researcher_setup` and `tool_requirements` are present when needed.
- Plan-preflight passes and fresh PLAN files are committed if this run owns the
  commit.
- The return includes files, wave count, plan summaries, roadmap updates, and
  next action.

Gap closure is complete when:

- `VERIFICATION.md` or `REVIEW.md` evidence is loaded and gaps are parsed.
- Gaps are categorized by physics type and clustered into focused repair plans.
- Plan numbers follow the existing sequence.
- Each repair plan has `gap_closure: true`.
- The failed check appears in the new verification path before new physics.
- Plan-preflight passes and the return points to `gpd:execute-phase`.
