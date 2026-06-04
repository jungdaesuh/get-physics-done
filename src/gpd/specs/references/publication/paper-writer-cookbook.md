---
load_when:
  - "paper writer journal calibration"
  - "paper writer venue guidance"
  - "paper writer latex scaffold"
  - "paper writer figure sizing"
type: paper-writer-cookbook
tier: 2
context_cost: medium
---

# Paper Writer Cookbook

Use this pack only when the venue or manuscript structure needs concrete examples. The base paper-writer prompt keeps only the hard contract, evidence gate, acknowledgment text, and return envelope.

## Venue Calibration

- `prl`: lead with the result, keep the main story compact, and move derivation bulk to supplemental material.
- `jhep`: state conventions early, show the full calculation path, and keep renormalization / scheme choices explicit.
- `nature`: prioritize accessibility and implication-first narrative; technical details move to Methods or supplement.
- style-only venues such as PRD/PRC/PRB/PRA/Nature Physics should influence tone and section depth, not the builder journal key.

## LaTeX Scaffold Hints

- APS-style journals: `revtex4-2` with the supported journal option.
- JHEP: `article` + `jheppub`.
- Nature-style manuscripts: standard `article` plus conservative package use and clean figure handling.
- Builder-backed artifacts remain authoritative for the emitted `.tex` path and supported journal key.

## Figure Sizing

- PRL single column: about `3.375 in`; double column: about `7.0 in`.
- JHEP single-column figures can usually fill the text width.
- Nature-style figures should be simpler, more visual, and readable by non-specialists.
- For exact file-format and sizing constraints, prefer vector output for LaTeX (`pdf`, `eps`) and avoid `tiff` for arXiv packaging.

## Story Architecture Reminders

- State one central claim.
- Pick the 3-5 results that actually carry that claim.
- Move long derivations and exhaustive tables out of the main text when they do not advance the story.
- Keep the strongest defensible claim aligned with the evidence already present in summaries, verification artifacts, and comparison verdicts.

## Abstract And Section Shape

- Write the abstract last. Use context, gap, approach, result, and implication; avoid roadmap abstracts and result-free summaries.
- Introduction should state the contribution early, cite specific prior work, and make the gap precise.
- Methods should define the system, assumptions, notation, and reproducibility hooks needed to understand the result.
- Results should lead with the main finding, quantify uncertainties, and compare against benchmarks or prior work where the contract requires it.
- Discussion should separate interpretation, limitations, implications, and future directions.

## Equation And Figure Details

- Number equations that are referenced later or carry key results; leave throwaway intermediate steps unnumbered.
- Define every symbol at first use and keep notation aligned with the active convention lock and notation glossary.
- Group related equations with `align`; move derivations longer than five displayed equations to appendices or supplemental material unless they are the central result.
- Figure captions must state the physical message, axes and units, uncertainty representation, and comparison baseline.
- Prefer vector figure output for LaTeX manuscripts; use the figure-generation template pack for concrete matplotlib defaults and journal sizing.

## Supplemental Material Placement

- Main text must stand alone: claim, method, result, and significance remain visible without the supplement.
- Supplemental material carries long derivations, alternative cross-checks, full convergence data, extended tables, extra figures, and convention/unit conversion details.
- Number supplemental equations, figures, and tables with an `S` prefix when the journal style allows it.
- PRL-style manuscripts should keep supplemental material reproducibility-focused; long-form journals can usually carry appendices in the paper.

## Research-To-Paper Handoff Detail

Use these recipes only when the base prompt selects `paper_writer.handoff_audit`.

Project-backed result completeness audit:

```bash
ls GPD/phases/*-*/*-SUMMARY.md
for f in GPD/phases/*-*/*-SUMMARY.md; do
  echo "=== $f ==="
  grep -A12 "contract_results:" "$f" 2>/dev/null || echo "NO CONTRACT RESULTS"
  grep -A6 "comparison_verdicts:" "$f" 2>/dev/null || echo "NO COMPARISON VERDICTS"
  grep "CONFIDENCE:" "$f" 2>/dev/null || echo "NO CONFIDENCE TAGS"
done
```

Convention consistency spot check:

```bash
for f in GPD/phases/*-*/*-SUMMARY.md; do
  echo "=== $f ==="
  grep -A10 "## Conventions" "$f" 2>/dev/null | head -15
done
```

Use source files rather than stale summaries when numerical values differ, and report the discrepancy. For figures, check that the generator exists, has run with final parameters, writes a newer output than the script when applicable, and carries the intended physical message, axes, units, and uncertainty display.

## Confidence-To-Language Mapping

| Confidence | Paper Language | Example |
|---|---|---|
| HIGH | Direct statement | "The ground state energy is $E_0 = -0.4432(1)\,J$" |
| MEDIUM | Statement with caveat | "We obtain $E_0 = -0.443(2)\,J$, pending verification of finite-size corrections" |
| LOW | Qualified statement | "Our preliminary estimate yields $E_0 \approx -0.44\,J$, subject to systematic uncertainties from the truncation" |

Never present LOW confidence without qualification. Never present MEDIUM confidence as established fact.

## Missing Citation Protocol

When using an equation, result, or method from a published source:

1. Check the active bibliography path for an existing citation key.
2. If the key exists, use `\cite{key}`.
3. If the key is missing, insert `\cite{MISSING:author-year-topic}` and add a nearby LaTeX comment naming the needed source.
4. At section end, add a `%% CITATIONS NEEDED` comment block for `gpd-bibliographer`.
5. Never guess citation keys. A `MISSING:` placeholder is safer than a fabricated key.

## Incomplete-Result Examples

Use `## WRITING BLOCKED` when a missing result determines the argument:

```markdown
**Section:** Results
**Missing results:** Phase 3 task 2 binding energy value
**Cannot proceed because:** the value sets the central comparison.
**Unblock by:** complete Phase 3 task 2 and rerun paper writer.
```

Use placeholders only for secondary items:

```latex
% [RESULT PENDING: phase 3, task 2 -- binding energy value]
E_b = \text{[PENDING]}~\text{eV}
```

Placeholders must name the source phase/task, compile as LaTeX, and not support the conclusion by themselves.

## Equation And Figure Verification Checklist

- Check dimensional consistency of every displayed equation term.
- Verify at least one limiting case for central equations.
- Confirm every symbol is defined in the active notation source.
- Check equation labels and references after editing.
- Confirm every figure caption states the physical message, axes/units, uncertainty representation when quantitative, and comparison baseline.

## Completion Checklist

- Section architecture completed before LaTeX drafting.
- Main message, supporting results, appendix boundary, and framing strategy are explicit.
- Journal calibration and abstract protocol are applied when relevant.
- Equations are necessary, labeled, contextualized, dimensionally checked, and symbol-defined.
- Figures, citations, approximations, and quantified uncertainty are all evidence-backed.
- The section advances the paper's central argument without unsupported hedging.
