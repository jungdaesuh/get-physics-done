# Planner Gap And Revision Policy

Use this reference for gap closure and checker-driven revision planning.

## Gap Closure Source Discovery

Use the init context `phase_dir` and inspect only relevant phase artifacts:

```bash
ls "$phase_dir"/*-VERIFICATION.md 2>/dev/null
grep -l "status: diagnosed" "$phase_dir"/*-REVIEW.md 2>/dev/null
```

Gap-closure plans keep `type: execute`; the repair marker is
`gap_closure: true`.

## Gap Closure Steps

1. Parse each gap: truth, reason, affected artifact, missing item, and failed
   check.
2. Load existing SUMMARYs only when needed to repair a specific gap.
3. Find the next plan number.
4. Group gaps by shared root cause and dependency order.
5. Create repair tasks that list the missing item, existing reference, failed
   check, and new passing check.
6. Write PLAN.md files with `type: execute` and `gap_closure: true`.

## Gap-Specific Contract Fields

```yaml
gap_closure: true
contract:
  schema_version: 1
  scope:
    question: "[Which failed verification or gap does this plan repair?]"
    in_scope: ["Repair the failed verification for the published benchmark comparison"]
  context_intake:
    must_include_prior_outputs: ["GPD/phases/XX-name/XX-NN-SUMMARY.md"]
    crucial_inputs: ["Exact failed verification and affected artifact"]
  claims:
    - id: "claim-gap-fix"
      statement: "[What repaired result must now hold]"
      claim_kind: other
      deliverables: ["deliv-gap-fix"]
      acceptance_tests: ["test-gap-fix"]
  deliverables:
    - id: "deliv-gap-fix"
      kind: "report"
      path: "GPD/phases/XX-name/XX-NN-SUMMARY.md"
      description: "[Artifact proving the repair]"
  acceptance_tests:
    - id: "test-gap-fix"
      subject: "claim-gap-fix"
      kind: "other"
      procedure: "[Re-run the failed check]"
      pass_condition: "[Exact verification condition that must now pass]"
      evidence_required: ["deliv-gap-fix"]
  forbidden_proxies:
    - id: "fp-gap-fix"
      subject: "claim-gap-fix"
      proxy: "[What would look fixed but would not count]"
      reason: "[Why that would still be false progress]"
  uncertainty_markers:
    weakest_anchors: ["[What still makes the repair fragile]"]
    disconfirming_observations: ["[What would show the fix did not actually hold]"]
```

## Gap Strategy

- Dimensional failure: trace mismatch backward through the derivation.
- Limit mismatch: re-derive the limit independently and compare.
- Sign or factor error: check a midpoint or test point, then narrow down.
- Convergence failure: try finer resolution before changing algorithms.
- Conservation, gauge, or symmetry issue: check each term independently.
- Convention mismatch: verify conventions at each boundary; do not change the
  project convention to fit the error.

Do not add new physics, expand scope, change conventions to fit the error, or
re-run phases that already passed.

## Revision From Checker Feedback

Triggered by `<revision_context>`. This is targeted update mode.

1. Load existing `GPD/phases/$PHASE-*/$PHASE-*-PLAN.md` files.
2. Parse checker issues by plan, dimension, severity, and fix hint.
3. Classify the revision:
   - Targeted fix: one known localized gap.
   - Diagnostic revision: two to four related gaps with unclear root cause.
   - Structural revision: framework-level issue; checkpoint before executing.
   - Supplementary calculation: existing work is correct but bounded work is
     needed.
4. Edit only flagged sections, preserving working parts.
5. Validate every updated plan and return a typed revision summary.

Do not rewrite whole plans for minor issues, add unnecessary tasks, break valid
dependencies, or change conventions mid-stream.

## Checker Feedback Examples

Use these examples to classify checker findings without bloating the base
planner prompt:

| Checker finding | Revision class | Plan response |
| --- | --- | --- |
| Missing dimensional check on one derived formula | Targeted fix | Add a verification task tied to the existing deliverable |
| Several sign errors with unclear source | Diagnostic revision | Add a root-cause task before changing formulas |
| Contract claim lacks any deliverable | Structural revision | Return checkpoint before reshaping the plan contract |
| Existing result is valid but needs one benchmark | Supplementary calculation | Add a bounded benchmark task and preserve prior work |
| Convention mismatch between imported reference and lock | Targeted or diagnostic | Convert the source formula; do not change project conventions to fit the error |

Return examples should stay typed and compact: list changed plans, issue IDs,
classification, files written, validation command, and next action. Do not
paste the full checker report back into `PLAN.md`.
