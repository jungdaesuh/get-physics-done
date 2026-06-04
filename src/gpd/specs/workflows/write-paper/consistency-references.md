<purpose>
Own internal consistency, notation/cross-reference checks, placeholder gates,
bibliography verification, bibliography audit refresh, and reproducibility
manifest generation.
</purpose>

<stage_boundary>
This is the first write-paper stage allowed to run the bibliography audit child
gate. It does not run the embedded peer-review panel or referee adjudication.
</stage_boundary>

<init>
Load the staged consistency/reference payload before notation checks,
bibliography verification, or reproducibility manifest work:

```bash
if [ -n "${ARGUMENTS:-}" ]; then CONSISTENCY_INIT=$(gpd --raw init write-paper --stage consistency_and_references -- "$ARGUMENTS"); else CONSISTENCY_INIT=$(gpd --raw init write-paper --stage consistency_and_references); fi
if [ $? -ne 0 ]; then echo "ERROR: write-paper consistency/reference init failed: $CONSISTENCY_INIT"; fi
INIT="$CONSISTENCY_INIT"
```

Apply `CONSISTENCY_INIT.staged_loading.field_access_instruction` before reading `CONSISTENCY_INIT`.

```bash
WRITE_PAPER_ARGUMENTS=$(echo "$INIT" | gpd json get .write_paper_argument_input --default "")
PAPER_DIR=$(echo "$INIT" | gpd json get .publication_bootstrap_root --default "")
PAPER_DIR="${PAPER_DIR:-$(echo "$INIT" | gpd json get .manuscript_root --default "")}"
MANUSCRIPT_ENTRYPOINT=$(echo "$INIT" | gpd json get .manuscript_entrypoint --default "")
MANUSCRIPT_BASENAME="${MANUSCRIPT_ENTRYPOINT##*/}"
AUTONOMY=$(echo "$INIT" | gpd json get .autonomy --default balanced)
RESEARCH_MODE=$(echo "$INIT" | gpd json get .research_mode --default balanced)
```

This stage receives manuscript paths, citation-source context, reference artifact
handles, protocol load manifests, and manuscript reference/proof status. It does
not receive selected reference bodies, planning document bodies, or rendered
protocol/reference context. Read a specific citation-source, bibliography,
reference, planning, or bundle file only when a consistency finding depends on
its body.
</init>

<consistency_check>
Canonical schema for `${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json`:
`{GPD_INSTALL_DIR}/templates/paper/bibliography-audit-schema.md`.

After manuscript, bibliography, citation-command, or citation-source writes,
treat the old bibliography audit as stale until `gpd paper-build`
refreshes/proves `${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json` current. Do not enter
strict review or report `citation_state: verified` on a pre-edit audit.

Run these checks:

- notation audit: one symbol table, one definition per symbol, one symbol per
  quantity, consistent index conventions
- cross-reference audit: every `\ref{}` and `\cite{}` resolves, every referenced
  equation/figure exists, section ordering is current
- physics consistency: Abstract/Results/Conclusions agree on values, assumptions,
  approximations, units, and scope
- narrative flow: introduction poses the question, results answer it, discussion
  interprets it, conclusions introduce no new results
</consistency_check>

<placeholder_gate>
Scan all manuscript `.tex` files for `RESULT PENDING` markers and placeholder
value tokens before reference verification.

If `PENDING_COUNT > 0`:

```text
ERROR: ${PENDING_COUNT} unresolved RESULT PENDING marker(s) found.
A paper with placeholder values is not submission-ready.

HALTING -- do NOT proceed to verify_references until all markers are resolved.
```

Do not proceed to `verify_references` until all placeholders are resolved.
</placeholder_gate>

<notation_audit>
If `GPD/NOTATION_GLOSSARY.md` exists, cross-reference extracted manuscript
symbols against it. If it does not exist, skip glossary cross-reference and state
that the consistency checks compared the paper against itself.
</notation_audit>

<verify_references>
Resolve the bibliographer model override before spawning the bibliography audit.
Apply the canonical runtime delegation convention already loaded above.

```
task(
  subagent_type="gpd-bibliographer",
  model="{biblio_model}",
  readonly=false,
  prompt="First, read {GPD_AGENTS_DIR}/gpd-bibliographer.md for your role and instructions.\n\n<autonomy_mode>{AUTONOMY}</autonomy_mode>\n<research_mode>{RESEARCH_MODE}</research_mode>

Verify all references in the paper and audit citation completeness.

Mode: Audit bibliography + Audit manuscript

Paper directory: ${PAPER_DIR}/
Bibliography: `{ACTIVE_BIBLIOGRAPHY_PATH}` (the resolved active bibliography for this manuscript)
Citation sources: `GPD/literature/*-CITATION-SOURCES.json` when literature-review has already assembled a machine-readable citation list for the current topic
Manuscript tree: all `.tex` files under `${PAPER_DIR}` recursively, rooted at the manifest-resolved manuscript directory
Target journal: {target_journal}

Tasks:
1. Verify every entry in the active bibliography file against authoritative databases (INSPIRE, ADS, arXiv)
2. Check all \cite{} keys in .tex files resolve to bibliography entries
3. Detect orphaned bibliography entries
4. Scan for uncited named results, theorems, or methods that should have citations
5. Verify BibTeX formatting matches {target_journal} requirements
6. Check arXiv preprints for published versions
7. Preserve `GPD/literature/*-CITATION-SOURCES.json` as the source artifact that seeded the bibliography

Write audit report to ${PAPER_DIR}/CITATION-AUDIT.md

Return a typed `gpd_return` envelope for the `write_paper_bibliographer` child_gate. Always list `${PAPER_DIR}/CITATION-AUDIT.md` and `GPD/references-status.json` in `gpd_return.files_written`; list `{ACTIVE_BIBLIOGRAPHY_PATH}` only when the bibliography file changed. The active bibliography file must exist on disk before the bibliography pass is accepted."
)
```

Bibliographer child gate:

```yaml
child_gate:
  id: "write_paper_bibliographer"
  role: "gpd-bibliographer"
  return_profile: "bibliographer"
  required_status: "completed"
  expected_artifacts:
    - "${PAPER_DIR}/CITATION-AUDIT.md"
    - "GPD/references-status.json"
    - "{ACTIVE_BIBLIOGRAPHY_PATH} only when changed"
    - "${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json after paper-build refresh"
  allowed_roots:
    - "${PAPER_DIR}"
    - "GPD"
  freshness_marker: "after $BIBLIO_HANDOFF_STARTED_AT"
  validators:
    - "gpd validate handoff-artifacts for child-written audit, status, and changed bibliography paths"
    - "gpd paper-build refresh emits ${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json"
    - "bibliography_audit_clean before strict review"
  applicator: "none"
  failure_route: "stage-recovery-gate -> retry bibliographer | main-context audit | stop unverified"
```

Do not mark bibliography verification complete or proceed to strict review,
reproducibility-manifest generation, or final review until this tuple passes.
Older audit files are recovery evidence only.
If the bibliographer completed with issues recorded in the audit report or
`GPD/references-status.json`, keep the paper blocked on citation repair. If the
bibliographer completed cleanly with no remaining citation issues, continue only
after `gpd paper-build` refreshes the bibliography audit.

Run strict reproducibility-manifest validation before strict review. If validation fails, do not enter review until the manifest is repaired.

If bibliography or citation set changes were made, rerun `gpd paper-build` so
`${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json` and the derived reference bridge are
regenerated before strict review. Confirm `${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json`
exists after the refresh before proceeding to reproducibility or strict review.
Prefer the `reference_id -> bibtex_key` bridge emitted by `gpd paper-build` over
reconstructing manuscript keys from prose or source order.
</verify_references>

<reproducibility_manifest>
Before strict review, create or refresh the reproducibility manifest the
publication review contract expects.

Canonical schema for `${PAPER_DIR}/reproducibility-manifest.json`:
`{GPD_INSTALL_DIR}/templates/paper/reproducibility-manifest.md`.

Minimum required inputs:

- `${PAPER_DIR}/ARTIFACT-MANIFEST.json`
- `${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json` produced by the latest
  `gpd paper-build`
- `${PAPER_DIR}/FIGURE_TRACKER.md`
- contract-backed summary-artifact / `VERIFICATION.md` evidence for decisive
  claims, figures, and comparisons

Validate `${PAPER_DIR}/reproducibility-manifest.json` before entering strict
review. Stop on a missing or non-review-ready manifest.
</reproducibility_manifest>

<handoff>
When notation, placeholder, reference, bibliography-audit, and reproducibility
gates pass, reload:

```bash
if [ -n "$WRITE_PAPER_ARGUMENTS" ]; then PUBLICATION_REVIEW_INIT=$(gpd --raw init write-paper --stage publication_review -- "$WRITE_PAPER_ARGUMENTS"); else PUBLICATION_REVIEW_INIT=$(gpd --raw init write-paper --stage publication_review); fi
```
</handoff>
