<purpose>
Bootstrap `gpd:sync-state` with deterministic, fail-closed routing for
`STATE.md`, `state.json`, and `state.json.bak`. `state.json` is authoritative
for structured fields; `STATE.md` is the projection and only becomes a recovery
source when JSON is missing or unreadable.
</purpose>

<required_reading>
Read all files referenced by the invoking prompt's execution_context before starting.

Canonical reconciliation contract: later stages keep
`{GPD_INSTALL_DIR}/templates/state-json-schema.md`
conditional; load it only for manual schema-drift diagnosis or backend
validation failure context.
</required_reading>

<process>

<step name="inspect" priority="first">
Load bootstrap and use returned state-file fields as the routing authority:

```bash
SYNC_BOOTSTRAP_INIT=$(gpd --raw init sync-state --stage sync_bootstrap)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd sync-state bootstrap failed: $SYNC_BOOTSTRAP_INIT"
  # STOP; surface the error.
fi
export PROJECT_ROOT
PROJECT_ROOT=$(echo "$SYNC_BOOTSTRAP_INIT" | gpd json get .project_root)
```

Apply `SYNC_BOOTSTRAP_INIT.staged_loading.field_access_instruction` before
reading `SYNC_BOOTSTRAP_INIT`.

Use `SYNC_BOOTSTRAP_INIT.staged_loading.required_init_fields` from the payload.
Use `project_root` from the init payload as the only write/read root; do not use
the shell launch directory. `init_root_policy` and `project_reentry_guidance`
are authoritative: sync-state is current-workspace-only and must not inspect or repair a recent project from another folder. Do not re-probe `GPD/STATE.md`,
`GPD/state.json`, or `GPD/state.json.bak` by hand during routing.

If init reports `corrupt_state_bad_backup` / `unrecoverable_state_pair`, fail closed: stop in read-only diagnosis, writes none, no `state repair-sync`, backup promotion, or state rewrite. Offer only `gpd:health`, manual repair, and `gpd:export-logs`.

**If `state_md_exists` and `state_json_exists` are both false, and `state_json_backup_exists` is true:**

```
Backup-only state found. Display state_recovery_guidance, then stop.
```

Exit. Do not promote `GPD/state.json.bak` automatically.

**If `state_md_exists` and `state_json_exists` are both false:**

```
No state files found. Run gpd:new-project to initialize project state.
```

Exit.

**If exactly one of `state_md_exists` or `state_json_exists` is true:**

For the exactly-one-source branch, load `single_source_recovery` and then read only that stage's `staged_loading.eager_authorities` before running repair.

**If `state_md_exists` and `state_json_exists` are both true:** Continue to comparison.
</step>

</process>
