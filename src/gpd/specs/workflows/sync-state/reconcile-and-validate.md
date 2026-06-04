<purpose>
Apply the selected repair path, validate the state pair, report the result, and keep commit optional.
</purpose>

<process>

<step name="reconcile">
Load reconcile/validate immediately before writing either state file:

```bash
RECONCILE_INIT=$(gpd --raw init sync-state --stage reconcile_and_validate)
if [ $? -ne 0 ]; then echo "ERROR: gpd sync-state reconcile init failed: $RECONCILE_INIT"; exit 1; fi
```

Apply `RECONCILE_INIT.staged_loading.field_access_instruction` before reading it.
Use `RECONCILE_INIT.staged_loading.required_init_fields` as reconciliation inputs.
These are compact existence/recovery/loader fields. Do not inspect raw state bodies; backend repair owns source/mutation.

Run the backend reconciliation command. It chooses the recovery source from the
loader result, prefers valid backup state over malformed markdown, rejects
malformed markdown-only recovery, preserves JSON-only fields, and writes the
dual state pair atomically.

```bash
SYNC_STATE_REPAIR=$(gpd --raw --cwd "$PROJECT_ROOT" state repair-sync)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd sync-state repair failed: $SYNC_STATE_REPAIR"
  exit 1
fi
```

**Verify sync result:**

```bash
gpd --raw --cwd "$PROJECT_ROOT" state validate
```

If validation fails, report the validation issues and stop. Do not commit a partially reconciled pair.
If schema-specific failure context is needed after backend validation fails,
select the `backend_validation_failed_needs_schema_context` conditional
authority for diagnosis only. Do not patch `GPD/STATE.md`, `GPD/state.json`, or
`GPD/state.json.bak` by hand.
</step>

<step name="report">
**Report what happened:**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 GPD > STATE SYNCHRONIZED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Source used:** {state.json | STATE.md recovery}
**Structured fields authoritative:** state.json
**Markdown projection:** regenerated from the authoritative source
**Validation status:** {healthy / warning / degraded}

If they diverged, report changed mirrored fields and note JSON-only fields were preserved.
```
</step>

<step name="optional_commit">
**Only if the operator explicitly asks to commit the reconciled state:**

```bash
PRE_CHECK=$(gpd --cwd "$PROJECT_ROOT" pre-commit-check --files GPD/STATE.md GPD/state.json 2>&1) || true
echo "$PRE_CHECK"

gpd --cwd "$PROJECT_ROOT" commit \
  "fix: reconcile STATE.md and state.json divergence" \
  --files GPD/STATE.md GPD/state.json
```
</step>

</process>

<failure_handling>

- **STATE.md corrupt:** The backend repair path regenerates markdown from valid structured state. If primary JSON is missing or corrupt, it prefers a valid `state.json.bak` before considering markdown. Malformed markdown-only recovery fails closed.
- **state.json corrupt (invalid JSON):** The backend repair path uses the recovery-aware state loader and valid backup when available; if backup is also unusable, use the fail-closed bad-backup branch.
- **Both files exist but disagree:** Treat the mismatch as a reportable drift, not a bidirectional merge request. Use `state.json` for structured fields and regenerate `STATE.md` from it unless `state.json` is unreadable.
- **Regeneration fails validation:** Stop and report the blocking issues. Do not stage or commit the pair.

</failure_handling>

<success_criteria>

- [ ] Both state files checked for existence
- [ ] Missing file regenerated from the other when applicable
- [ ] Backend repair selected the source and wrote the dual state pair
- [ ] Raw state bodies were not inspected in the prompt
- [ ] JSON-only fields preserved by backend sync
- [ ] Validation rerun after regeneration
- [ ] Divergences reported without ad hoc merge heuristics
- [ ] Optional commit kept separate from the core reconcile/validate/report path

</success_criteria>
