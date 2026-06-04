---
load_when:
  - "peer review panel stages"
  - "reviewer rubric"
  - "journal fit"
type: peer-review-panel-playbook
tier: 3
context_cost: medium
---

# Peer Review Panel Playbook

This playbook is reviewer guidance for Stage 1 through Stage 5 of the staged
peer-review panel. It complements the compact machine contract in
`references/publication/peer-review-panel.md`; it does not define artifact schemas,
write scopes, or Stage 6 final-adjudication authority.

## Core Principle

Peer review is not one pass. It is a sequence of skeptical checks with fresh
context:

1. Read the manuscript end-to-end and identify what it actually claims.
2. Compare those claims with the literature and the paper's novelty framing.
3. Check mathematical correctness and internal consistency.
4. Check whether physical assumptions and interpretations are reasonable.
5. Check whether the result is interesting enough for the claimed venue.
6. Let Stage 6 adjudicate from persisted evidence.

No stage silently substitutes for another. A mathematically coherent paper can
still deserve major revision or rejection if its physical story is weak, its
novelty collapses against prior work, or its significance is overstated.

## Stage Rubrics

### Stage 1. Manuscript Read

Agent: `gpd-review-reader`

Read the whole manuscript once. Extract the main claim, supporting subclaims,
and the paper's logic. Flag narrative jumps, overclaims, missing evidence, and
places where the conclusions outrun the body.

The reader should be conservative about claim identity: preserve exact
manuscript wording when possible, record locations, and distinguish claims of
mathematical truth from claims of physical interpretation, novelty, generality,
and significance.

### Stage 2. Literature Context

Agent: `gpd-review-literature`

Evaluate novelty and prior-work positioning using the manuscript, bibliography,
bibliography audit, bib files, comparison artifacts, and targeted search when
positioning is uncertain. Identify missing foundational work, unacknowledged
overlap, inflated novelty claims, and places where the manuscript's framing is
weaker than the actual technical contribution.

Do not accept "we are not aware of prior work" as evidence. Ask what a
competent specialist referee would expect to see cited or compared.

### Stage 3. Mathematical Soundness

Agent: `gpd-review-math`

Check key equations, derivation integrity, theorem-to-proof alignment,
self-consistency, limiting cases, sign conventions, assumptions, and verification
coverage. If the validator requires theorem-bearing Stage 1 claims to be
reviewed, do not sample only a subset: every theorem-bearing Stage 1 claim must
be reviewed and proof-audited.

Keep the math stage focused on the manuscript's internal technical claims. When
the separate proof critique is active, do not duplicate it; instead record how
the math-stage evidence aligns with the proof-redteam result.

### Auxiliary Proof Critique

Agent: `gpd-check-proof`

When theorem-bearing claims are present, run a separate adversarial proof
critique instead of overloading the math stage. Audit theorem-to-proof alignment
claim by claim: named parameters, stated hypotheses, quantifiers/domains, and
conclusion clauses. Try to break the proof by forcing narrower-case,
dropped-parameter, or hidden-assumption failures into the open before final
adjudication.

Favorable recommendations require same-round proof-redteam clearance. A
Stage 3 `proof_audits[]` entry is supporting evidence, not clearance by itself.

### Stage 4. Physical Soundness

Agent: `gpd-review-physics`

Check regime of validity, physical assumptions, interpretation, connection
between math and physics, and whether claimed physical conclusions are actually
supported. Be especially skeptical of formal analogies presented as physical
evidence, parameter regimes that are never justified, and interpretations that
require assumptions not present in the derivation.

A mathematically respectable manuscript can still fail this stage if the
physical story is unsupported or overstated.

### Stage 5. Significance And Venue Fit

Agent: `gpd-review-significance`

Judge interestingness, scientific value, and venue fit after seeing the reading,
literature, and physics outputs. Separate "technically correct" from "worth the
claimed venue." Be willing to conclude that the paper is mathematically
respectable but scientifically weak.

Venue fit is not a style preference. It asks whether the result clears the
audience, novelty, and significance bar the manuscript is claiming.

## Recommendation Guardrails

Stage 1-5 reviewers do not issue the final recommendation, but their
`recommendation_ceiling` should constrain Stage 6.

### `accept`

Use an `accept` ceiling only when there are no unresolved blockers, no major
concerns in the stage's domain, claims are proportionate to evidence, and the
venue-fit bar is met.

For theorem-bearing work, central theorem claims must have complete proof-audit
coverage and no theorem-to-proof alignment gaps before any stage suggests an
`accept` ceiling.

### `minor_revision`

Use a `minor_revision` ceiling only when the core contribution is sound,
novelty/significance are at least adequate for the target venue, and remaining
issues are local clarifications, citation additions, wording fixes, or
presentation polish.

Minor revision is not allowed when the paper's central physical story is
unsupported, when a theorem statement outruns what its proof establishes, or
when title, abstract, or conclusions materially overclaim.

### `major_revision`

Use a `major_revision` ceiling when the core result may survive but the paper
needs substantial reframing, new checks, stronger literature comparison, narrower
claims, or repaired theorem/proof coverage. This is the normal ceiling for
fixable but material weaknesses.

### `reject`

Use a `reject` ceiling when the main claim depends on unsupported physical
reasoning, a central theorem-bearing claim is not proved as stated and cannot be
honestly narrowed, novelty collapses against prior work, or the work is too thin
for the claimed venue.

Reject is not reserved for algebraic failure. A physically unconvincing or
scientifically minor paper can deserve rejection even when equations are
internally consistent.

## Claim Discipline

Every reviewer should ask:

- Does the title promise more than the paper delivers?
- Does the abstract imply physical consequences not established in the body?
- Do the conclusions convert formal analogy into physical evidence without
  justification?
- Does the manuscript use suggestive language such as "connection",
  "implication", "relevance", or "prediction" without adequate support?

Treat claim inflation as publication-relevant, not stylistic. Unsupported
central physical-interpretation or significance claims are never compatible with
a soft-positive assessment.

## Journal Calibration

Use official venue expectations as hard calibration input.

### PRL-style standard

APS describes PRL as publishing results with significant new advances and broad
interest across physics. A paper that is merely technically competent inside a
narrow corner of the field should not receive a soft-positive recommendation for
PRL.

### JHEP-style standard

JHEP seeks significant new material of high scientific quality and broad
interest within high-energy physics. Incremental or physically thin manuscripts
should not be waved through as minor revisions just because formal manipulations
are consistent.

### General reviewer standard

Reviewer guidance from major publishers commonly emphasizes originality,
significance, and whether conclusions are supported by results. Check all three
explicitly.

## Anti-Rubber-Stamp Checks

Before completing a stage artifact, verify that each finding names the affected
claims, evidence, severity, support status, and required action. Avoid generic
statements such as "needs more discussion" without specifying what claim is
unsupported and what evidence would fix it.

Do not let clean prose hide missing evidence. If the manuscript sounds plausible
but the actual support chain is thin, record the gap as a substantive finding.
