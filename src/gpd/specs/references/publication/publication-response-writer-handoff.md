---
load_when:
  - "publication response drafting"
  - "publication response handoff"
  - "author response"
  - "referee response"
type: publication-response-writer-handoff
tier: 2
context_cost: low
---

# Publication Response Writer Handoff

Canonical workflow-facing handoff and completion reference for spawned response-writing work.

Use this pack when a workflow or agent spawns `gpd-paper-writer` to draft a response artifact pair or revise manuscript text in response to a referee report.

## Canonical Sources

- `{GPD_INSTALL_DIR}/templates/paper/author-response.md`
- `{GPD_INSTALL_DIR}/templates/paper/referee-response.md`
- `{GPD_INSTALL_DIR}/references/publication/publication-response-artifacts.md`
- `{GPD_INSTALL_DIR}/references/publication/stage-recovery-gate.md`

## Rules

- Apply the publication stage-recovery gate for one-shot writer lifecycle, checkpoint continuation, retry freshness, and stale-output rejection.
- For `status: checkpoint`, use that gate; the response pair remains incomplete.
- `status: completed` is provisional until the expected response files exist on disk and are named in fresh typed `gpd_return.files_written`.
- Successful response-round completion requires both `${selected_publication_root}/AUTHOR-RESPONSE{round_suffix}.md` and `${selected_review_root}/REFEREE_RESPONSE{round_suffix}.md`; default project subjects resolve those to `GPD/AUTHOR-RESPONSE{round_suffix}.md` and `GPD/review/REFEREE_RESPONSE{round_suffix}.md`.
- For explicit manuscript subjects, both files must carry response frontmatter with `round` and `manuscript_path` matching the active review round; stale same-round files without a binding do not complete the handoff.
- Do not treat prose-only status messages as proof of completion.
- Keep the hard gate visible at the spawn site, but do not duplicate the full response prose there when this reference is loaded.

## Response Pair Detail

Use workflow-supplied paths as authority: report, ledger, decision, author response, referee response, selected roots, and round suffix. `referee_report_path` owns `REF-*` IDs; ledger/decision artifacts calibrate blocking status, recommendation floor, and counts.

`author_response_path` is the internal tracker; `referee_response_path` is the synchronized journal-facing sibling. Keep IDs, classifications, status labels, blocking-item coverage, and new-calculation tracking aligned. Use `fixed` only after the manuscript edit exists; keep `needs-calculation` explicit when work remains.

If the workflow requests a short editor letter in addition to `referee_response_path`, the letter may compress tone and wording, but it does not replace the full paired response contract.
