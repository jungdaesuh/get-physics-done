<purpose>
Run citation verification and enforce typed child-return gates for the review artifacts.
</purpose>

<process>

<step name="verify_citations">
**Phase 8: Citation Verification**

Spawn the bibliographer agent to verify all citations collected during the review. The bibliographer has the hallucination detection protocol, INSPIRE/ADS/arXiv search capability, and BibTeX management expertise needed for citation verification.

```bash
REVIEW_HANDOFF_INIT=$(load_literature_review_stage review_handoff "${topic:-$ARGUMENTS}")
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $REVIEW_HANDOFF_INIT"
  exit 1
fi
```

Apply `REVIEW_HANDOFF_INIT.staged_loading.field_access_instruction` before reading `REVIEW_HANDOFF_INIT`.
Reference artifacts may be hydrated here, while active reference and protocol prose remain handle-first through `active_references`, `reference_artifact_files`, and `protocol_bundle_load_manifest`.

Resolve bibliographer model:

```bash
BIBLIO_MODEL=$(gpd resolve-model gpd-bibliographer)
```
@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md

```
task(
  subagent_type="gpd-bibliographer",
  model="{biblio_model}",
  readonly=false,
  prompt="First, read {GPD_AGENTS_DIR}/gpd-bibliographer.md for your role and instructions.\\n\\nVerify all citations in the literature review.\\n\\nMode: Audit bibliography\\n\\nReview file: GPD/literature/{slug}-REVIEW.md\\n\\nFor every reference listed in the Full Reference List and cited in the body:\\n1. Run the hallucination detection protocol (Steps 1-5) against INSPIRE, ADS, arXiv\\n2. Cross-check metadata (title, authors, year, journal, identifiers)\\n3. Flag any hallucinated or inaccurate citations\\n4. Correct metadata errors where possible\\n\\nWrite results to GPD/literature/{slug}-CITATION-AUDIT.md\\n\\nReturn through the typed handoff. Local audit artifact: GPD/literature/{slug}-CITATION-AUDIT.md; completed must name it in files_written. Use checkpoint only when researcher input is required to continue."
)
```

<spawn_contract>
write_scope:
  mode: scoped_write
  allowed_paths:
    - GPD/literature/{slug}-CITATION-AUDIT.md
expected_artifacts:
  - GPD/literature/{slug}-CITATION-AUDIT.md
shared_state_policy: return_only
</spawn_contract>

**If the bibliographer agent fails to spawn or returns an error:** Treat the review as blocked until citation audit completes. Offer: 1) Retry citation audit, 2) Abort, 3) Return to the user with the review incomplete.

**If the bibliographer completed with issues recorded in the audit report:**

- Read the audit report
- Fix or remove hallucinated citations from the review document
- Update corrected metadata in the reference list
- Refresh `GPD/literature/{slug}-CITATION-SOURCES.json` so the sidecar stays aligned with the corrected review and reference keys.
- Re-run or refresh `GPD/literature/{slug}-CITATION-AUDIT.md` if citation fixes changed the review or sidecar.
- Note unresolvable citations in the return summary

**If the bibliographer reports completed:** apply the citation-audit artifact
gate for `GPD/literature/{slug}-CITATION-AUDIT.md` before continuing.
  </step>

</process>
