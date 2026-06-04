---
load_when:
  - "checker return envelope"
  - "partial approval"
  - "revision loop"
  - "persistent blocker escalation"
  - "checker worked examples"
tier: 2
context_cost: medium
---

# Plan Checker Return Protocol And Examples

Use this reference when formatting checker findings, applying dependency-aware partial approval, or escalating persistent blocker rounds. The orchestrator routes on the structured `gpd_return` envelope; markdown headings and tables are presentation only.

## Persistent Blocker Escalation

If blocker-level issues persist after 3 revision rounds, return `gpd_return.status: blocked` with a structured escalation report. Do not simply repeat the same feedback; diagnose why the planner failed to resolve the blockers and present concrete user options.

### Escalation Rules

1. After round 3, always escalate; do not silently attempt a 4th round.
2. Include the full revision history so the user sees what was tried.
3. Classify each blocker pattern as stuck, oscillating, or late-emerging.
4. Present override, guidance, restructure, and abort options without pre-selecting one.
5. If the user chooses an override, ensure the orchestrator records which checks were waived.
6. If the user gives guidance, feed it to the planner as a locked decision.

## Scope Exceeded (most common miss)

**Plan 01 analysis:**

```
Tasks: 5
Key equations: ~35
  - Hubbard Hamiltonian construction
  - Mean-field decoupling (3 channels)
  - Self-consistency equations
  - Free energy functional
  - Phase boundary conditions
  - Finite-temperature generalization
  - Landau expansion near T_c
  - Order parameter susceptibility
  - Specific heat calculation
  - Numerical solution + convergence
```

5 tasks exceeds 2-3 target, scope covers ground state through finite-T thermodynamics, mean-field + fluctuations in one plan -> quality degradation risk.

```yaml
issue:
  dimension: scope_sanity
  severity: blocker
  description: "Plan 01 has 5 tasks covering Hamiltonian, mean-field, thermodynamics, phase diagram, AND fluctuation corrections"
  plan: "01"
  metrics:
    tasks: 5
    estimated_equations: 35
    estimated_context: "~85%"
  fix_hint: "Split into: 01 (Hamiltonian + mean-field ground state), 02 (finite-T + phase diagram), 03 (fluctuation corrections)"
```

## Approximation Validity Failure

**Plan uses harmonic approximation for anharmonic potential:**

```
Research question: Thermal expansion coefficient of crystal
Method: Harmonic phonon calculation
Problem: Harmonic approximation gives zero thermal expansion by symmetry
```

```yaml
issue:
  dimension: approximation_validity
  severity: blocker
  description: "Harmonic phonon calculation cannot produce thermal expansion -- anharmonic terms (at minimum cubic) are required by symmetry"
  plan: "04-02"
  task: 3
  fix_hint: "Include quasi-harmonic approximation (volume-dependent frequencies) or perturbative anharmonic corrections (3rd/4th order force constants)"
```

## Missing Validation (subtle)

**Plan derives new Green's function but only checks one limit:**

```
Result: Retarded Green's function G^R(omega, k)
Validation planned: Check G^R -> free-particle propagator as interaction -> 0
Missing: No check of spectral sum rule, no Kramers-Kronig consistency, no check of known strong-coupling limit
```

```yaml
issue:
  dimension: validation_strategy
  severity: warning
  description: "Green's function validated only in weak-coupling limit; missing spectral sum rule and Kramers-Kronig consistency check"
  plan: "04-01"
  task: 4
  fix_hint: "Add validation: (1) integral of spectral function = 1, (2) Im[G^R] and Re[G^R] satisfy Kramers-Kronig, (3) check strong-coupling limit if known"
```

## Issue Format

```yaml
issue:
  plan: "04-01" # Which plan (null if phase-level)
  dimension: "approximation_validity" # Which dimension failed
  severity: "blocker" # blocker | warning | info
  description: "..."
  task: 2 # Task number if applicable
  fix_hint: "..."
```

## Severity Levels

**blocker** - Must fix before execution

- Missing research requirement coverage
- Missing required task fields (formulation, method, validation, deliverable)
- Invalid approximation for stated regime
- Computationally infeasible approach without alternative
- Circular dependencies
- Scope > 5 tasks per plan
- Plan contradicts known physics (violates conservation law, symmetry, etc.)

**warning** - Should fix, execution may work

- Scope 4 tasks (borderline)
- Method-focused claims instead of physics-focused outcomes
- Incomplete validation (some checks present, key ones missing)
- Minor notation inconsistency
- Missing literature reference for standard result
- No failure mode identification for risky step
- Missing path from computation to interpretable result

**info** - Suggestions for improvement

- Could split for better parallelization
- Could improve validation specificity
- Alternative method might be more efficient
- Additional limiting case could strengthen result
- Notation could be standardized across tasks

Return all issues as a structured `issues:` YAML list (see dimension examples for format).

## Machine-Readable Return Envelope

Headings above are presentation only. Route on `gpd_return.status`, the approved/blocked plan lists, and `issues`.

```yaml
gpd_return:
  status: completed
  files_written: []
  issues: []
  next_actions:
    - "gpd:execute-phase 04"
  approved_plans:
    - "04-01"
    - "04-02"
  blocked_plans: []
  dimensions_checked:
    - "dependencies"
    - "contract coverage"
  revision_round: 1
  revision_guidance: "Plans are approved; execute the approved set."
```

When contract-gate failures or escalation diagnoses matter, represent them in the `issues` list and the markdown report above instead of inventing nested `gpd_return` payloads.

Use `agent-infrastructure.md` as the return skeleton/profile reference for status vocabulary and base fields.

## Partial Approval Protocol

When a phase has multiple plans, some may pass while others have blockers. Rather than blocking the entire phase, use partial approval to let passing plans proceed.

**Decision logic:**

```
For each plan in phase:
  if plan has 0 blockers → APPROVED
  if plan has blockers but they don't affect other plans → REVISION_NEEDED (this plan only)
  if plan has blockers that affect downstream plans → BLOCKED (this plan + dependents)
```

**Dependency-aware partial approval:** A plan can only be approved if ALL plans it depends on are also approved. If Plan 02 depends on Plan 01 and Plan 01 has blockers, Plan 02 is blocked regardless of its own status.

**Return format for partial approval:**

```markdown
## PARTIAL APPROVAL

Approved: {approved_plans}
Blocked/revision-needed: {blocked_plans}
Reason: summarize blockers and dependency causes from `issues`.
```

**Rules:**

1. Only approve plans whose entire dependency chain is also approved
2. Any plan failing the contract gate (missing decisive outputs, anchors, acceptance tests, forbidden-proxy handling, or disconfirming path) is NOT approvable and blocks its dependents
3. Wave 1 plans (no dependencies) are always independently assessable
4. If ALL plans in a wave have blockers, no partial approval is possible — return standard ISSUES FOUND
5. Approved plans proceed to execution while blocked plans go back to the planner
6. After revision, re-check ONLY the revised plans and their dependents — do not re-check already-approved plans unless their inputs changed
7. The orchestrator handles the split: it sends approved plans to the executor and revision feedback to the planner simultaneously

**When NOT to use partial approval:**

- All plans share a common blocker (e.g., notation inconsistency across all plans) — fix globally first
- The phase has only 1-2 plans — standard pass/fail is clearer
- Blockers in one plan expose likely issues in others (e.g., if Plan 01's approximation is invalid, Plans 02-04 building on it are suspect)
