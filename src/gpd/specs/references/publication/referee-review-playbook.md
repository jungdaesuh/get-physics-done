---
load_when:
  - "referee adjudication"
  - "journal review"
  - "publication review"
  - "review rubric"
  - "revision round"
type: referee-review-playbook
tier: 2
context_cost: medium
---

# Referee Review Playbook

Use this pack when the referee needs the detailed rubric, response strategy, or revision-round guidance. Keep the base referee prompt lean and load this only when the review task needs more than the compact decision contract.

## Compact Adjudication Rule

Start from the manuscript itself. Check claim-evidence proportionality, theorem-to-proof alignment, literature context, and venue fit. If the strongest defensible claim is narrower than the abstract or conclusion, that is a real publication problem.

## Rubric Summary

Judge the paper on these dimensions:

- novelty
- correctness
- clarity
- completeness
- significance
- reproducibility
- literature context
- presentation quality
- technical soundness
- publishability

For each dimension, ask whether the manuscript states a claim, supports it with evidence, and keeps the claim scope proportionate to that evidence.

## Recommendation Floors

- `minor_revision` only for local clarity, citation, or presentation fixes.
- `major_revision` when the physics may survive but the interpretation, significance, or theorem alignment needs narrowing or repair.
- `reject` when the central claim is unsupported, the novelty collapses, or the venue fit is fundamentally weak.

## Revision-Round Guidance

When author responses exist, re-check only the changed content first. Treat new content with the same physical and theorem-proof checks as the original. If a fix introduces a new inconsistency, report that explicitly instead of assuming the revision is globally better.

## Response Strategy

When the journal matters, tune the response style to the venue:

- PRL and Nature-style outlets need strong significance and tight scope.
- PRD/PRB/JHEP-style outlets can tolerate more technical detail, but not unsupported claims.
- Multi-round responses should keep the action items finite and clearly prioritized.

## Report Hygiene

Keep the report concise and machine-readable:

- issue IDs must stay stable across markdown and JSON outputs
- blocking issues should be explicit
- strengths should be acknowledged
- report prose should not duplicate long rubric text

## Initial Review Execution Detail

Use this only when `gpd-referee` selects the playbook for a full review.

1. Read the review target first: title, abstract, introduction, results, conclusion, and the supplied primary review surface. When the workflow supplies nearby manuscript section files, use them as companions; when the target is standalone `.txt`, `.csv`, or `.tsv`, or extracted text from `.pdf`, `.docx`, `.xlsx`, or `.xlsm`, treat that artifact as the primary review surface.
2. Extract claims from the manuscript before consulting project-internal summaries.
3. Read key derivation files, numerical code, and results only as evidence sources.
4. Read `ROADMAP.md`, `SUMMARY.md`, and `VERIFICATION.md` only after the manuscript-first claim map exists.
5. Read `STATE.md` for conventions and notation after the claim map is stable.

Optional search recipes:

```bash
find GPD -name "*.md" -not -path "./.git/*" 2>/dev/null | sort
find . -name "*.tex" 2>/dev/null | sort
find . -name "*.py" -path "*/derivations/*" -o -name "*.py" -path "*/numerics/*" 2>/dev/null | sort
```

## Claim And Physics Audit Detail

For each manuscript section, extract main results, novelty claims, comparison claims, generality claims, and significance claims. Central physical-interpretation or significance claims that are unsupported cap the recommendation at `major_revision`, and they cap it at `reject` when central to the paper's main pitch or repeated in the abstract/conclusion.

When theorem-bearing claims are present, use the theorem-to-proof audit from the base prompt. If a theorem statement names a parameter like `r_0` and the proof never uses it, mark `alignment_status` as `misaligned`; do not treat that as algebraic polish.

Evaluate dimensions in this order when context is tight:

1. correctness
2. completeness
3. technical soundness
4. novelty
5. significance
6. literature context
7. reproducibility
8. clarity
9. presentation quality
10. publishability

For key results, check dimensional analysis, limiting cases, symmetries, conservation laws, error analysis, approximation validity, convergence evidence, literature comparison, and reproducibility hooks. Focus on main results first.

## Steelman Rejection Check

Before recommending `accept` or `minor_revision`, write the three strongest reasons a skeptical editor or referee would reject the paper. Attempt to defeat each reason using manuscript evidence only. Any surviving reason becomes a blocking issue.

## Referee Report Template

Use this structure when the base referee prompt asks for the full Markdown skeleton.

````markdown
---
reviewed: YYYY-MM-DDTHH:MM:SSZ
scope: full_project | milestone_N | phase_XX | manuscript
target_journal: PRL | PRD | PRB | JHEP | Nature | other | unspecified
recommendation: accept | minor_revision | major_revision | reject
confidence: high | medium | low
major_issues: N
minor_issues: N
---

# Referee Report

## Summary

State the main result, the strongest evidence, the key strengths, and the publication-blocking weaknesses.

## Panel Evidence

| Stage | Artifact | Assessment | Key blockers or concerns |
| ----- | -------- | ---------- | ------------------------ |
| Read | path | strong/adequate/weak/insufficient | summary |
| Literature | path or not provided | assessment | summary |
| Math | path or not provided | assessment | summary |
| Physics | path or not provided | assessment | summary |
| Significance | path or not provided | assessment | summary |

## Recommendation

Give `accept`, `minor_revision`, `major_revision`, or `reject`, and justify it from novelty, physical support, theorem-proof alignment, and venue fit.

## Evaluation

### Strengths

List concrete strengths with manuscript evidence.

### Major Issues

For each publication-blocking issue, include dimension, severity, location, description, impact, suggested fix, quoted or paraphrased challenged claim, and missing evidence.

### Minor Issues

List fixable issues that do not affect the central conclusions.

### Suggestions

List optional improvements that would strengthen the work.

## Detailed Evaluation

Assess all 10 dimensions: novelty, correctness, clarity, completeness, significance, reproducibility, literature context, presentation quality, technical soundness, and publishability.

## Physics Checklist

Cover dimensional analysis, limiting cases, symmetries, conservation laws, error bars, approximations, convergence, literature comparisons, and reproducibility.

## Actionable Items

```yaml
actionable_items:
  - id: "REF-001"
    finding: "[brief description]"
    severity: "critical | major | minor | suggestion"
    specific_file: "[file path that needs changing]"
    specific_change: "[exactly what needs to be done]"
    estimated_effort: "trivial | small | medium | large"
    blocks_publication: true/false
```

## Confidence Self-Assessment

For each dimension, record HIGH/MEDIUM/LOW confidence and flag LOW dimensions for expert review.
````

## CONSISTENCY-REPORT.md Template

Use `${selected_publication_root}/CONSISTENCY-REPORT.md` only as a diagnostic sidecar for contradictions or convention mismatches discovered during adjudication. It never authorizes repairing, rewriting, or replacing `CLAIMS{round_suffix}.json`, `STAGE-*.json`, or `PROOF-REDTEAM{round_suffix}.md`.

Recommended sections:

- Cross-phase convention consistency: metric, Fourier, units, gauge, regularization, and project lock alignment.
- Equation numbering consistency: unresolved, duplicated, or ambiguous references.
- Notation consistency: same symbol, same meaning, and explicit redefinitions.
- Result dependency validation: values consumed by later phases match produced values.

## Anti-Pattern Examples

Avoid these review failure modes:

- Rubber stamp: acceptance with no equations, limits, convergence, or claim-evidence checks.
- Missing obvious holes: skipping dimensional analysis, limiting cases, convergence, or uncertainty because the prose looks polished.
- Surface-level critique: saying "there are sign issues" without naming the equation, convention, propagation path, and publication impact.
- Preferred-method critique: demanding a different method when the existing method is appropriate; instead, ask for the missing validation that would justify the current method.
- Confusing opacity with error: if a derivation is unreadable, say which step cannot be verified and what intermediate statement would make it checkable.
- Ignoring strengths: report real strengths, then identify blockers.
- Vague significance judgment: explain what the paper adds beyond specific prior work and what threshold the target venue requires.

## Revision Report Template

Use this for round `N >= 2` when a complete paired response package exists.

````markdown
---
reviewed: YYYY-MM-DDTHH:MM:SSZ
scope: revision_review
round: N
previous_report: REFEREE-REPORT{-RN-1}.md
recommendation: accept | minor_revision | major_revision | reject
confidence: high | medium | low
issues_resolved: N
issues_partially_resolved: N
issues_unresolved: N
new_issues: N
---

# Referee Report - Round {N}

## Summary of Revision Assessment

State how well the response addressed the previous concerns and whether new issues were introduced.

## Recommendation

Give the recommendation. For round 3, state that this is the final review round.

## Issue Resolution Tracker

| ID | Original Issue | Severity | Author Response | Status | Notes |
| -- | -------------- | -------- | --------------- | ------ | ----- |
| REF-001 | brief description | major | response summary | resolved/partially-resolved/unresolved | what remains |

## Detailed Resolution Assessment

Group resolved, partially resolved, unresolved, and new issues. For each claimed fix, locate the changed manuscript content and verify it independently.

## Remaining Actionable Items

```yaml
actionable_items:
  - id: "REF-R{N}-001"
    finding: "[description]"
    severity: "critical | major | minor | suggestion"
    from_round: N
    specific_file: "[file path]"
    specific_change: "[what needs to be done]"
    estimated_effort: "trivial | small | medium | large"
    blocks_publication: true/false
```
````

## Revision Review Success Criteria

- Previous `REFEREE-REPORT` loaded and all issue IDs extracted.
- `AUTHOR-RESPONSE` and `REFEREE_RESPONSE` parsed point-by-point for the same round.
- Every previous issue assessed as `resolved`, `partially-resolved`, `unresolved`, or `new-issue`.
- Resolution assessments backed by independent verification, not only author claims.
- New or modified content checked for dimensional consistency, limiting cases, numerical evidence, and notation consistency.
- Unchanged satisfactory dimensions left alone unless the revision touched them.
- Round `N+1` markdown and LaTeX reports written with stable issue IDs and a resolution tracker.
- Actionable items include `from_round` for remaining or new issues.
- Round 3 states: "This is the final review round. My recommendation is [X] based on the following assessment of the revision history."
