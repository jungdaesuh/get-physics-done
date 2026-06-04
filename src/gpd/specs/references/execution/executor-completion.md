# Executor Completion Protocols

Load this reference after all tasks complete, before creating the canonical `{phase}-{plan}-SUMMARY.md`, final self-check, typed return, and completion commit.

## Summary Creation

After all tasks complete, create `{phase}-{plan}-SUMMARY.md` at `${phase_dir}/`.

**Use template:** templates/summary.md

**Frontmatter:** phase, plan, depth, physics-area, tags, dependency graph (requires/provides/affects), methods (analytical/numerical/computational), key-files (created/modified), decisions, metrics (duration, completed date).

**Canonical ledger schema to load before writing SUMMARY frontmatter:**

@{GPD_INSTALL_DIR}/templates/contract-results-schema.md

Before treating contract-backed output as complete, run:

```bash
gpd validate summary-contract GPD/phases/XX-name/{phase}-{plan}-SUMMARY.md
```

**Verification contract:** For contract-backed work, the SUMMARY.md frontmatter MUST declare `plan_contract_ref`, `contract_results`, and any decisive `comparison_verdicts` so the verifier can test results without re-reading the full derivation. `plan_contract_ref` must end with the exact `#/contract` fragment. `contract_results` must cover every declared claim, deliverable, acceptance test, reference, and forbidden proxy ID from the PLAN contract. Use only real contract IDs in both ledgers. If a decisive comparison remains open, keep the parent target incomplete and emit `verdict: inconclusive` or `verdict: tension` instead of omitting the verdict. Every decisive numerical result needs concrete evidence. Every equation that matters downstream needs a spot-check or limiting-case anchor. The contract-backed example below keeps `uncertainty_markers` explicit and non-empty to match the canonical schema.
For `contract_results.references`, keep the action ledger internally consistent: `completed` requires non-empty `completed_actions`, `missing` requires non-empty `missing_actions`, `not_applicable` leaves both empty, and the two lists must not overlap.
Even singleton values must stay YAML lists in strict contract-backed ledgers: use `linked_ids: [claim-id]`, `completed_actions: [read]`, and `weakest_anchors: [anchor-1]`, never scalar strings.
Every `comparison_verdicts` entry must declare `subject_role` explicitly. If the decisive external anchor came from the literature or another artifact, include `reference_id`; if the reference itself is the comparison subject, use `subject_kind: reference`.
Treat decisive comparisons as required whenever the PLAN contract includes `benchmark` or `cross_method` acceptance tests, whenever a benchmark/compare-driven reference anchors the subject, or whenever execution actually performed a decisive comparison.

```yaml
plan_contract_ref: "GPD/phases/XX-name/{phase}-{plan}-PLAN.md#/contract"
contract_results:
  claims:
    claim-main:
      status: passed
      summary: "[what was actually established]"
      linked_ids: [deliv-main, test-main, ref-main]
      evidence:
        - verifier: gpd-executor
          method: benchmark reproduction
          confidence: high
          claim_id: claim-main
          deliverable_id: deliv-main
          acceptance_test_id: test-main
          reference_id: ref-main
          evidence_path: "GPD/phases/XX-name/{phase}-VERIFICATION.md"
  deliverables:
    deliv-main:
      status: passed
      path: "paper/figures/benchmark.pdf"
      summary: "[artifact produced and why it matters]"
      linked_ids: [claim-main, test-main]
  acceptance_tests:
    test-main:
      status: passed
      summary: "[executed decisive check and outcome]"
      linked_ids: [claim-main, deliv-main, ref-main]
  references:
    ref-main:
      status: completed
      completed_actions: [read, compare, cite]
      missing_actions: []
      summary: "[how the anchor was surfaced]"
  forbidden_proxies:
    fp-main:
      status: rejected
      notes: "[why this tempting proxy did not count as success]"
  uncertainty_markers:
    weakest_anchors: ["finite-term mass matching"]
    unvalidated_assumptions: ["general-gauge-independence"]
    competing_explanations: ["on-shell vs MS-bar finite-part conventions"]
    disconfirming_observations: ["no independent gauge-parameter scan"]
comparison_verdicts:
  - subject_id: "claim-main"
    subject_kind: "claim"
    subject_role: "decisive"
    reference_id: "ref-main"
    comparison_kind: "benchmark"
    metric: "relative_error"
    threshold: "<= 0.01"
    verdict: "pass"
    recommended_action: "[what to do next if this later regresses]"
    notes: "[How the benchmark was checked]"
```

**Title:** `# Phase [X] Plan [Y]: [Name] Summary`

**One-liner must be substantive and physics-specific:**

- Good: "Derived optical theorem from S-matrix unitarity; verified in Born and eikonal limits"
- Good: "Converged ground state energy of 2D Hubbard model at half-filling using DMRG (bond dimension 512)"
- Good: "Generated phase diagram of XY model via Monte Carlo; identified KT transition at T_c = 0.893(5)"
- Bad: "Scattering calculation completed"
- Bad: "Numerical results obtained"

**Conventions section:**

```markdown
## Conventions Used

| Convention | Choice                 | Inherited from | Notes                    |
| ---------- | ---------------------- | -------------- | ------------------------ |
| Units      | natural (hbar = c = 1) | Phase 01       |                          |
| Metric     | (+,-,-,-)              | Phase 01       | k^2 = m^2 on shell       |
| Fourier    | e^{-ikx} forward       | Phase 01       | 2pi in dk measure        |
| Gauge      | Feynman (xi=1)         | This plan      | Verified xi-independence |
```

**Key results section:**

```markdown
## Key Results

### Analytical Results

- [Equation/relation]: [brief description] (verified by [method])

### Numerical Results

| Quantity | Value | Units | Method | Uncertainty |
| -------- | ----- | ----- | ------ | ----------- |

### Figures Produced

| Figure | File | Description |
| ------ | ---- | ----------- |
```

**Deviation documentation:**

```markdown
## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Convergence] Lanczos solver required increased basis size**

- **Found during:** Task 4
- **Issue:** Default Krylov subspace dimension (50) insufficient for degenerate spectrum
- **Fix:** Increased to 200 with block Lanczos; added convergence monitoring
- **Files modified:** scripts/diagonalize.py
- **Checkpoint:** [hash]
- **Impact on results:** None --- final results unchanged, computation 3x slower

**2. [Rule 3 - Approximation] Born approximation invalid below 10 MeV**

- **Found during:** Task 6
- **Issue:** Partial wave expansion shows Born series diverges for l=0 below 10 MeV
- **Fix:** Switched to exact partial-wave summation for E < 50 MeV
- **Files modified:** scripts/cross_section.py, derivations/partial_waves.tex
- **Checkpoint:** [hash]
- **Impact on results:** Low-energy cross sections now correct; required additional figure
```

Or: "None --- plan executed exactly as written."

**Approximations and limitations section:**

```markdown
## Approximations and Limitations

- [Approximation used]: valid for [regime], breaks down when [condition], error estimate [O(...)]
- [Limitation]: [what was not computed/verified and why]
- [Known issue]: [any open question or unresolved discrepancy]
```

**Environment gates section** (if any occurred): Document which task, what was needed, outcome.

## Final Self-Check

After writing SUMMARY.md, verify claims before proceeding to typed return or completion commit.

1. Check created files exist:

```bash
[ -f "path/to/file" ] && echo "FOUND: path/to/file" || echo "MISSING: path/to/file"
```

2. Check task checkpoint commits exist:

```bash
git log --oneline | grep -q "{hash}" && echo "FOUND: {hash}" || echo "MISSING: {hash}"
```

3. Verify numerical results are reproducible by rerunning the key command and comparing with the SUMMARY.md value.

4. Verify LaTeX compiles when applicable:

```bash
cd documents/ && latexmk -pdf -interaction=nonstopmode "${MANUSCRIPT_TEX}" 2>&1 | tail -5
```

5. Verify figures are newer than their generating scripts when applicable.

6. Verify convention consistency across all created or modified outputs.

7. Apply selected bundle final checks: load the selected verification-domain docs, `protocol_bundle_verifier_extensions`, and matching `execution_guides` from `<protocol_bundle_context>`. If no selected bundle covers the final result domain, load `{GPD_INSTALL_DIR}/references/execution/guards/final-verification-guards.md` on demand and apply only matching rows.

Minimum final checks:

- Contract-backed anchors and first-result gates outrank every bundle or guard asset.
- Analytical results need dimension, convention, sign/factor, limiting-case, and symmetry checks.
- Numerical results need convergence, benchmark or known-answer comparison, uncertainty/error bars, and reproducibility commands.
- Claims that use a proxy must explicitly state why the proxy is forbidden, inadequate, decisive, or unresolved under the contract.
- If no domain or selected guard matches, skip topic-specific rows and rely on generic execution flow plus contract-backed anchors and checks.

Append `## Self-Check: PASSED` or `## Self-Check: FAILED` to SUMMARY.md with missing items listed.

For contract-backed plans, also confirm:

- every decisive claim ID has a `contract_results.claims` entry;
- every deliverable has produced, partial, or failed status and a path when applicable;
- every acceptance test has an explicit outcome plus evidence or notes;
- every must-surface reference has completed or missing required actions recorded;
- every forbidden proxy is rejected, violated, or unresolved;
- profiles and autonomy modes do NOT relax contract-result emission.

Do not proceed to typed return or completion commit if the self-check fails.

## Closeout Success Checklist

Use this checklist after the inline executor prompt says plan execution is done:

- Conventions were loaded and verified before the first task.
- All tasks were executed, or the run paused at a checkpoint with enough state
  for a fresh continuation.
- Each completed task was checkpointed with the proper format.
- Derivation work tracked signs and conventions, with self-critique checkpoints
  every 3-4 derivation steps.
- Method-specific modules were loaded only when the task entered that method
  family.
- Numerical work recorded reproducibility metadata, convergence evidence,
  benchmark or analytic-limit checks, and uncertainty.
- Automatic escalation counters were tracked.
- All deviations have a deviation-rule classification.
- Environment gates were handled and documented as gated flow.
- Research log and state-tracking files were maintained during execution.
- Every derived equation and computed value was verified at the required depth.
- SUMMARY.md has substantive physics content, conventions, confidence tags, and
  contract ledgers when the plan is contract-backed.
- Shared-state updates were returned through `gpd_return` by default; direct
  shared-state writes happened only when explicitly delegated.
- Context pressure honored the 50% forced checkpoint and ORANGE/RED stops.
- Stuck points were documented honestly; no plausible-but-wrong results were
  produced.
- Selected or on-demand post-step guards were applied after major steps, and
  guard failures were mapped to deviation rules.

## State Updates

Before recording completion, verify that no live first-result, skeptical, or pre-fanout gate remains in the bounded execution state. A pre-fanout review is not retired until both the matching gate clear and the matching fanout unlock have been recorded.

After SUMMARY.md, apply durable child-return state effects through the canonical applicator:

```bash
gpd apply-return-updates "${SUMMARY_FILE}"
```

The canonical applicator owns plan advance, progress recompute, metric recording, decisions, blockers, and session cleanup for spawned-agent completion. Do not duplicate those effects with direct `gpd state ...` commands in the completion path.

**gpd CLI error handling:**

The applicator command can fail. Handle errors explicitly and keep durable state changes inside the return envelope:

```bash
# CORRECT - check exit code and handle applicator failure
if ! gpd apply-return-updates "${SUMMARY_FILE}"; then
  echo "ERROR: apply-return-updates failed. Keep shared-state repair in the return envelope."
  # Capture stderr, inspect the SUMMARY/return envelope, and retry once only
  # with a corrected fenced gpd_return block if the failure is repairable.
fi

# WRONG — ignoring exit codes
gpd apply-return-updates "${SUMMARY_FILE}"  # might silently fail
```

**Common gpd CLI failure modes:**

| Failure | Cause | Fix |
|---------|-------|-----|
| `ENOENT` | SUMMARY, returned artifact, or project state file missing | Verify the referenced SUMMARY/artifact path; do not hand-edit shared state |
| `Parse error` | Malformed SUMMARY frontmatter or fenced `gpd_return` YAML | Fix the SUMMARY/return envelope and retry once if repairable |
| `No phase/plan found` | Return phase/plan does not match the roadmap/state contract | Correct the return envelope or escalate to the orchestrator |
| Non-zero exit with no output | Python crash or missing dependency | Check `python --version`, verify gpd CLI path |

**Recovery protocol:** If a gpd CLI command fails twice, do not patch `STATE.md` or `state.json` manually. Capture the failing command and stderr in the return envelope or plan SUMMARY, run `gpd state validate` if the failure looks state-related, and escalate to `gpd:sync-state` or the orchestrator instead of editing shared state files directly.

**Decisions from SUMMARY.md:** Put executor-owned decisions in SUMMARY frontmatter and/or `gpd_return.decisions`. The canonical applicator records accepted decisions; do not add them with direct `gpd state ...` commands in the spawned-agent completion path.

**For blockers found during execution:** Put blocker entries in `gpd_return.blockers` and set the typed return status/next action accordingly. The canonical applicator records accepted blockers; if the applicator rejects them, stop with the applicator failure instead of patching shared state.


## Completion Format

```markdown
## PLAN COMPLETE

**Plan:** {phase}-{plan}
**Tasks:** {completed}/{total}
**SUMMARY:** {path to SUMMARY.md}
**LOG:** {path to LOG.md}

**Conventions Used:**

- Units: {unit system}
- Metric: {signature}
- Gauge: {gauge choice, if applicable}

**Key Results:**

- {equation/value}: {brief description}
- {equation/value}: {brief description}

**Checkpoints:**

- {hash}: {message}
- {hash}: {message}

**Artifacts produced:**

- {N} equations derived
- {N} numerical results computed
- {N} figures generated
- {N} code modules implemented

**Verification Summary:**

- {N} dimensional analyses passed
- {N} limiting cases checked
- {N} convergence tests passed
- {N} conservation laws verified

**Duration:** {time}

---

### Structured Return Envelope

```yaml
gpd_return:
  status: completed
  files_written:
    - "derivations/hamiltonian.tex"
    - "scripts/compute_spectrum.py"
    - "GPD/phases/XX-name/{phase}-{plan}-SUMMARY.md"
  issues:
    - "Lanczos solver required increased basis size (auto-fixed: Rule 2)"
  next_actions:
    - "gpd:execute-phase {phase}"
    - "gpd:show-phase {phase}"
  phase: "{phase}"
  plan: "{plan}"
  tasks_completed: 4
  tasks_total: 4
  duration_seconds: 3600
  conventions_used:
    units: "natural"
    metric: "(+,-,-,-)"
    gauge: "Feynman"
  checkpoint_hashes:
    - hash: "abc1234"
      message: "derive(02-01): optical theorem from unitarity"
```

Append this YAML block after the markdown completion format. It enables machine-readable parsing by the orchestrator.
```

If the workflow expects a spawned-agent handoff, the same `gpd_return` object may also carry these top-level keys:

```yaml
gpd_return:
  status: checkpoint
  files_written: ["GPD/phases/XX-name/{phase}-{plan}-SUMMARY.md"]
  issues:
    - "{blocker text}"
  next_actions:
    - "Resolve {blocker text} before continuing downstream execution."
  state_updates:
    advance_plan: true
    update_progress: true
    record_metric:
      phase: "{phase}"
      plan: "{plan}"
      duration: NNN
      tasks: N
      files: N
  contract_updates:
    claim_id:
      status: "updated"
  decisions:
    - summary: "{decision summary}"
      phase: "{phase}"
  blockers:
    - text: "{blocker text}"
  continuation_update:
    handoff:
      stopped_at: "Completed ${PHASE}-${PLAN}-PLAN.md"
      resume_file: null
      last_result_id: null
    bounded_segment: null
```

`gpd apply-return-updates` records handoff timestamp/provenance; omit `recorded_at` and `recorded_by` from child returns.

Include ALL checkpoints (previous + new if continuation agent).

## Final Commit

```bash
gpd commit "docs({phase}-{plan}): complete [plan-name] research plan" --files ${phase_dir}/{phase}-{plan}-SUMMARY.md ${phase_dir}/{phase}-{plan}-LOG.md ${phase_dir}/{phase}-{plan}-STATE-TRACKING.md
```

Separate from per-task checkpoints --- captures execution metadata only. The default spawned executor completion commit excludes `GPD/STATE.md`; durable shared-state effects flow through `gpd_return` and `gpd apply-return-updates`. If a workflow explicitly delegates shared-state ownership, follow that workflow's separate state-write and commit instructions.
