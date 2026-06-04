# Planner Proof-Bearing Plan Checklist

Use this reference only when drafting proof-bearing PLAN contracts. The
canonical schema remains `phase-prompt.md` -> `plan-contract-schema.md` ->
`contract-proof-obligation-rules.md`.

## Required Cues

- Use an explicit non-`other` `claim_kind`, such as `claim_kind: theorem`.
- Make parameters auditable, for example `parameters -> symbol "q"`.
- Give hypotheses stable IDs, for example `hypotheses -> hyp-gauge`.
- Name conclusion clauses, for example `conclusion_clauses ->
  concl-transverse`.
- Name proof deliverables, for example `proof_deliverables:
  ["deliv-proof-vac-pol"]`.
- Keep reference anchors concrete with `must_surface: true`, non-empty
  `applies_to`, and `required_actions: ["read", "compare", "cite"]` when the
  plan depends on external grounding.

## Acceptance Tests

- Include proof-specific acceptance tests for logical completeness,
  hypothesis use, conclusion coverage, counterexample checks, and boundary
  cases.
- Include a sibling `*-PROOF-REDTEAM.md` audit path when proof-redteam review is
  required by the workflow or contract.
- Do not treat generic manuscript `claim` prose as equivalent to planner
  contract proof semantics.
