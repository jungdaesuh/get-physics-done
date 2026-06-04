<purpose>
Conduct a systematic physics literature review: foundational works, methods,
key results, disputes, open questions, and where new work can contribute.
Produce LITERATURE-REVIEW.md for planning and paper writing.

Also emit `GPD/literature/{slug}-CITATION-SOURCES.json` with strict
`CitationSource` objects keyed by stable `reference_id` values. Include
`bibtex_key` only when already known and verified; audit-only verification fields
belong in `GPD/literature/{slug}-CITATION-AUDIT.md`.

Called from gpd:literature-review command.

This workflow owns staged init, scope fixing, deferred reference-artifact
loading, and artifact gates. Do not frontload reference artifacts before scope is
fixed.

Keep all durable review artifacts rooted under `GPD/literature/` in the current workspace. In project-backed mode, that is the resolved project root's `GPD/literature/`; in standalone mode, it is `./GPD/literature/` in the invoking workspace.
</purpose>

<core_principle>
A physics literature review is not a bibliography. It maps who computed what, with which methods and assumptions, what results agree or conflict, what is open, and where new work can contribute.
</core_principle>

<source_hierarchy>
Authoritative sources before general search: textbooks/monographs, review
articles, seminal papers, recent arXiv, conference proceedings, then web_search
only as a last resort for discussions, code, or benchmarks.

</source_hierarchy>

<process>

<step name="load_context" priority="first">
Load staged context:

```bash
load_literature_review_stage() {
  local stage_name="$1"
  shift
  local init_payload=""

  init_payload=$(gpd --raw init literature-review "$@" --stage "$stage_name" 2>/dev/null)
  if [ $? -ne 0 ] || [ -z "$init_payload" ]; then
    echo "ERROR: staged gpd initialization failed for stage '${stage_name}': ${init_payload}"
    return 1
  fi

  printf '%s' "$init_payload"
  return 0
}

BOOTSTRAP_INIT=$(load_literature_review_stage review_bootstrap "$ARGUMENTS")
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $BOOTSTRAP_INIT"
  # STOP; surface the error.
fi
```

Apply `BOOTSTRAP_INIT.staged_loading.field_access_instruction` before reading `BOOTSTRAP_INIT`.
`{GPD_INSTALL_DIR}/references/orchestration/contract-authority-gate.md`

Topic gate:
- If `topic` is empty, do not invent or auto-derive it from project state,
  active references, or deferred artifacts.
- Project-backed mode: ask one focused question to lock topic before broadening
  search or loading scoped reference artifacts.
- Standalone mode: stop; centralized preflight should already require explicit
  topic input.

Do not use `reference_artifact_files` or `reference_artifacts_content` yet. Keep them deferred until scope is fixed so reference artifacts cannot broaden the topic before the user has chosen it.

Mode behavior:
- `research_mode=explore`: broad field, citation network, open questions.
- `research_mode=exploit`: direct relevance, key results, methods.
- `research_mode=balanced` (default): standard depth and default anchor/contract coverage.
- `research_mode=adaptive`: start medium-depth, expand on critical gaps.
- `autonomy=supervised`: pause after each review round for scope/direction.
- `autonomy=balanced`: complete automatically except ambiguity, contradiction, or recommendation changes.
- `autonomy=yolo`: complete without pausing, but never drop contract-critical anchors or user-mandated references.

Context gate: if `state_exists` is true, use `convention_lock`, active topic,
phase context, and contract-critical references from `active_reference_context`.
If false, proceed only from explicit topic input. Treat
`effective_reference_intake` as the carry-forward ledger for anchors, prior
outputs, baselines, user-mandated context, and unresolved gaps. Apply the shared
contract gate: `project_contract` is authoritative only when
`project_contract_gate.authoritative` is true; otherwise keep diagnostics visible
without promoting them to approved review truth.
</step>

<step name="scope_review">
The review topic must already be explicit or newly clarified; project existence
alone does not satisfy subject selection.

Fix scope before search: topic/focus, depth (`quick|standard|comprehensive`),
time range, purpose, include/exclude boundaries, and seed anchors from
`project_contract`, `contract_intake`, `effective_reference_intake`, and
`active_reference_context`. Track contract-critical anchors in a compact registry
with a `| Must Surface |` column and roles such as `benchmark`, `definition`,
`method`, or `must_consider`.
  </step>

</process>
