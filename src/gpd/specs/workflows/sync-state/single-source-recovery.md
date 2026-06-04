<purpose>
Regenerate the missing state mirror from the backend-selected surviving source.
</purpose>

<process>

<step name="single_source_recovery">
**If exactly one of `state_md_exists` or `state_json_exists` is true:**

Load single-source recovery for the diagnostic context, but do not choose the
recovery source in the prompt. The backend repair command is the source-selection
authority; it uses the recovery-aware state loader, including recovered backup
sources and integrity issues.

```bash
SINGLE_SOURCE_RECOVERY_INIT=$(gpd --raw init sync-state --stage single_source_recovery)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd sync-state recovery init failed: $SINGLE_SOURCE_RECOVERY_INIT"
  exit 1
fi
```

Apply `SINGLE_SOURCE_RECOVERY_INIT.staged_loading.field_access_instruction`
before reading `SINGLE_SOURCE_RECOVERY_INIT`.

Use `SINGLE_SOURCE_RECOVERY_INIT.staged_loading.required_init_fields` from the
payload.
These fields are compact status and loader fields only. Do not request raw
`STATE.md`, `state.json`, or `state.json.bak` bodies, and do not load the state
JSON schema before repair; the backend repair command owns source selection and
state reconstruction.

Repair the dual-write pair through the tested backend path:

```bash
SYNC_STATE_REPAIR=$(gpd --raw --cwd "$PROJECT_ROOT" state repair-sync)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd sync-state repair failed: $SYNC_STATE_REPAIR"
  exit 1
fi
```

Report `source_used`, `integrity_issues`, and `validation_status` from
`SYNC_STATE_REPAIR`, then stop. Do not prompt for a merge decision and do not
run raw JSON or markdown parsing from the prompt.

If the backend repair completes but validation reports schema-specific failures,
select the `backend_validation_failed_needs_schema_context` conditional
authority for diagnosis only. Do not use schema context to edit either state
file by hand.

</step>

</process>
