# Research Synthesis Guidance

Load this reference when contradiction resolution, cross-validation, iterative
refinement, or detailed SUMMARY.md closeout needs more detail than the base
research-synthesizer prompt carries.

## Notation Reconciliation

Catalog symbols, operators, index conventions, units, sign conventions, and
renormalization schemes across all source files. For collisions, record the
source convention, unified convention, conversion rule, and whether the
difference is only convention, a formulation change, or a real disagreement.

Common collisions include sigma, J, hbar conventions, metric signature, Fourier
signs, summation conventions, scheme choices, and anomaly normalization factors.

## Contradiction Resolution

Use this sequence for each conflict:

1. Identify the exact claims and whether they concern the same quantity in the
   same regime.
2. Check convention, unit, approximation-regime, numerical-definition, and
   methodological differences.
3. Weight evidence by proximity to the project regime, source reliability,
   recency, independent validation, and benchmark agreement.
4. Resolve by stating which claim applies and why, or mark the contradiction
   unresolved and create a research-program response.

For high-confidence conflicts, do not average claims and do not select the most
common claim by count. Prefer, in order: controlled expansion; method valid in
the project's regime; result with more independent consistency checks;
non-perturbative numerics when expansion parameters are order one; agreement
with relevant experiment; otherwise hypothesis branches without premature
choice.

Unresolved contradictions belong in the Research Flags section and in the
machine-readable `contradictions_unresolved` list.

For a concrete worked example, load
`{GPD_INSTALL_DIR}/references/examples/contradiction-resolution-example.md`.

## Confidence Weighting

HIGH confidence:

- Multiple independent confirmations.
- Established theoretical results with textbook or review-level derivations.
- Peer-reviewed numerical benchmarks or experimental constraints.
- Findings consistent across the relevant research files.

MEDIUM confidence:

- Single authoritative source.
- Standard method with known limitations.
- Theoretical prediction without independent numerical verification.
- Minor inconsistencies across two or three files.

LOW confidence:

- Unreviewed preprint, single source, extrapolation beyond validated regime,
  known method limitation, or unresolved contradiction.

Do not base roadmap recommendations primarily on LOW confidence findings unless
no better source exists; when that happens, flag the validation phase needed.

## Input Extraction

METHODS.md: extract methods, rationale, domain of applicability, tool versions,
accuracy/cost tradeoffs, and validation strategy.

PRIOR-WORK.md: extract established results, exact solutions, experimental
constraints, consensus, conflicts, and results that may be superseded.

COMPUTATIONAL.md: extract algorithms, convergence properties, software,
resource estimates, data flow, parallelization, and benchmark strategy.

PITFALLS.md: extract critical pitfalls, numerical instabilities, finite-size or
discretization artifacts, gauge or infrared issues, approximation failures, and
phase-specific warnings.

## Approximation And Cross-Validation

For each approximation or method, record validity regime, breakdown signatures,
whether it is controlled, complementary methods, and cost scaling. Identify
parameter regimes with no reliable method.

Build a project-specific cross-validation matrix. Each entry states where a row
method can be checked against a column method, exact result, benchmark, or
experiment. Highlight methods with no useful cross-validation.

## Critical Claim Verification

Verify the most roadmap-driving claims before writing SUMMARY.md. Prioritize
phase blockers, phase-ordering dependencies, benchmark values, method
recommendations, consensus claims, and cited arXiv claims.

Record verification results in SUMMARY.md:

```markdown
### Critical Claim Verification

| # | Claim | Source | Verification | Result |
|---|-------|--------|--------------|--------|
| 1 | [claim] | METHODS.md | [query or file check] | CONFIRMED / CONTRADICTED / UNVERIFIED |
```

## Iterative Refinement

Re-synthesize when research files, literature review findings, or phase
execution evidence change conclusions. Use incremental updates for one localized
input change. Use full re-synthesis for first synthesis, two or more changed
inputs, substantial rewrites, or notation changes.

For incremental updates, read current SUMMARY.md and changed files, update only
affected sections, check new or resolved contradictions, preserve
cross-references, update confidence and roadmap impact, and append a compact
revision-history row.

Skip re-synthesis for cosmetic edits, non-load-bearing detail, or values still
within stated uncertainty.

## Expanded Closeout Skeleton

When a human-readable closeout is useful in addition to the YAML return, keep it
brief and do not paste the full SUMMARY.md:

```markdown
## SYNTHESIS COMPLETE

**Files synthesized:** METHODS.md, PRIOR-WORK.md, COMPUTATIONAL.md, PITFALLS.md
**Output:** GPD/literature/SUMMARY.md
**Unified notation:** [N] symbols, [M] conflicts resolved.
**Roadmap implications:** [N] suggested phases.
**Confidence:** Overall [HIGH/MEDIUM/LOW]; [critical gaps].
**Next:** Ready for `gpd:roadmap`.
```

Blocked closeout:

```markdown
## Synthesis Blocked

**Blocked by:** [issue]
**Missing files:** [list]
**Inconsistencies:** [list]
**Awaiting:** [needed input]
```
