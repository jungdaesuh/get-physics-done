<purpose>
Compatibility index for the staged `write-paper` workflow.
</purpose>

<stage_authorities>
The active authority is selected by `write-paper-stage-manifest.json`.
Do not load this index as a stage authority.

- `paper_bootstrap` -> `workflows/write-paper/paper-bootstrap.md`: lane and
  manuscript preflight. Read summary artifacts (`SUMMARY.md` and `*-SUMMARY.md`)
  from `GPD/phases/*/*SUMMARY.md` when digests are insufficient.
- `outline_and_scaffold` -> `workflows/write-paper/outline-scaffold.md`:
  journal key, outline, `${PAPER_DIR}/PAPER-CONFIG.json`, scaffold.
- `figure_and_section_authoring` -> `workflows/write-paper/authoring.md`:
  figure tracker, section writers, child artifact gates.
- `consistency_and_references` -> `workflows/write-paper/consistency-references.md`:
  notation, bibliography audit, reproducibility manifest.
- `publication_review` -> `workflows/write-paper/publication-review-finalization.md`:
  review routing, finalization, revision/response path. Deferred response
  routing uses `{GPD_INSTALL_DIR}/references/publication/publication-response-writer-handoff.md`
  and `templates/paper/author-response.md`; review-round artifact handling stays
  with `references/publication/publication-review-round-artifacts.md`.
</stage_authorities>

<stage_loading_rule>
The public command includes only `workflows/write-paper/paper-bootstrap.md`;
later stage loading is manifest-owned, and each active payload supplies
`staged_loading.field_access_instruction`.
Keep downstream authoring, bibliography, critique, referee, review-panel, and
response-routing authorities lazy until their matching stage.
</stage_loading_rule>
