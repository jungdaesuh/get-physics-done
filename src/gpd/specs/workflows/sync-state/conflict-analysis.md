<purpose>
Compare mirrored state fields when a human-readable drift report is needed, and
classify reconciliation deterministically without mutating state files.
</purpose>

<process>

<step name="compare">
Load conflict analysis and compare the returned state representations:

```bash
CONFLICT_ANALYSIS_INIT=$(gpd --raw init sync-state --stage conflict_analysis)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd sync-state conflict-analysis init failed: $CONFLICT_ANALYSIS_INIT"
  exit 1
fi
```

Apply `CONFLICT_ANALYSIS_INIT.staged_loading.field_access_instruction` before
reading `CONFLICT_ANALYSIS_INIT`.

Use `CONFLICT_ANALYSIS_INIT.staged_loading.required_init_fields` from the
payload. Do not re-read the mirrored files by hand for comparison.
This is the only non-bootstrap sync stage that may receive raw state bodies for
a read-only drift report. Do not load the state JSON schema unless
`manual_schema_drift_analysis` is explicitly selected.

**Parse STATE.md into comparable fields:**
- Current Phase (number and name)
- Current Plan
- Status
- Last Activity
- Core research question
- Current focus
- Decisions list
- Blockers list
- Session info (last date, stopped at, resume file)

**Parse state.json fields:**
- `position.current_phase`, `position.current_phase_name`
- `position.current_plan`
- `position.status`
- `position.last_activity`
- `project_reference.core_research_question`
- `project_reference.current_focus`
- `decisions[]`
- `blockers[]`
- `session.last_date`, `session.stopped_at`
- `convention_lock` (JSON-only field)
- `intermediate_results` (JSON-only field)
- `approximations` (JSON-only field)
- `propagated_uncertainties` (JSON-only field)
</step>

<step name="classify">
1. If `state.json` is unreadable, invalid JSON, or missing required structured data, use the markdown recovery path and stop treating the pair as a bidirectional merge problem.
2. If `state.json` parses successfully, treat it as the structured source of truth for all mirrored fields.
3. If `STATE.md` contains schema-backed edits that disagree with `state.json` while both files parse, report the drift, but do not invent a field-by-field merge. Regenerate `STATE.md` from `state.json`.
4. Preserve JSON-only fields from `state.json` on every sync path.

state.json is authoritative for structured fields, and STATE.md is regenerated as the markdown projection of that authority.

This workflow is intentionally fail-closed: no recency heuristics, no user prompt, and no silent promotion of markdown-only edits into structured state when `state.json` is still readable.
Do not move or delete files from the prompt.
Do not write reconciled state from this stage; the backend repair path in
`reconcile_and_validate` owns mutation.
</step>

</process>
