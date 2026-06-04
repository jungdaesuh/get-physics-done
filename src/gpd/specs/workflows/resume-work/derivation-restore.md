<purpose>
Restore derivation history, continuity anchors, and convention status without mutating derivation state.
</purpose>

<process>

<step name="restore_persistent_state">
Load derivation-restore before reconstructing derivation history:

```bash
DERIVATION_RESTORE_INIT=$(gpd --raw init resume --stage derivation_restore)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd derivation-restore initialization failed: $DERIVATION_RESTORE_INIT"
  # STOP; surface the error.
fi
```

<field_access>
Apply `DERIVATION_RESTORE_INIT.staged_loading.field_access_instruction` before reading `DERIVATION_RESTORE_INIT`. Read selected bodies only for continuity recovery.
</field_access>

**Read cumulative derivation history from `GPD/DERIVATION-STATE.md`:**

This reconstructs accumulated derivation history and prevents lossy context resets.

```bash
# Check if persistent derivation state exists
if [ -f GPD/DERIVATION-STATE.md ]; then
  echo "=== DERIVATION-STATE.md found ==="
  cat GPD/DERIVATION-STATE.md
else
  echo "No DERIVATION-STATE.md found (first session or pre-persistence project)"
fi
```

**If DERIVATION-STATE.md exists:**

### Check Session Cap (Last 5 Sessions)

During read-only restoration, count session blocks and warn if over cap. Do not prune, rewrite, replace, or otherwise modify `GPD/DERIVATION-STATE.md` from `gpd:resume-work`.

```bash
SESSION_COUNT=$(grep -c "^## Session:" GPD/DERIVATION-STATE.md 2>/dev/null || echo 0)

if [ "$SESSION_COUNT" -gt 5 ]; then
  echo "WARNING: DERIVATION-STATE.md has ${SESSION_COUNT} session blocks (recommended cap: 5)."
  echo "Read and summarize the file as-is; do not prune, rewrite, or replace it during resume restoration."
  echo "After restoration, suggest the pause-work runtime command or an explicit maintenance pass if the researcher wants capping."
fi
```

This is a report-only check. Mutating cap enforcement belongs to explicit write/maintenance workflows.

1. **Read the full file** to reconstruct the complete equation/convention/result history across all sessions. If the latest handoff or session continuity metadata already carries a canonical `last_result_id`, prefer that value as the rerun anchor before rediscovering the target from prose or older summaries.
2. **Cross-reference against state.json intermediate_results** to find any gaps:
   - Are there result IDs in DERIVATION-STATE.md that are missing from state.json? (suggests state.json was reset or corrupted)
   - Are there intermediate_results in state.json that are NOT in DERIVATION-STATE.md? (suggests a session did not properly pause)
   - Does the newest handoff/session record expose a `last_result_id` that should be reused on rerun instead of searching again? If so, surface it as the preferred continuity anchor.
3. **Count and summarize** what was restored:
   - Total equations established across all sessions
   - Total conventions locked in
   - Total intermediate results recorded
   - Total approximations catalogued
4. **Present the restoration summary:**

```
>> Persistent derivation state restored:
   - Equations: [X] established across [N] sessions
   - Conventions: [Y] locked (metric: [sig], Fourier: [conv], ...)
   - Intermediate results: [Z] recorded (IDs: [list])
   - Approximations: [W] catalogued
   [If gaps found:]
   >> WARNING: [description of gaps found between DERIVATION-STATE.md and state.json]
```

**If DERIVATION-STATE.md does NOT exist:**

- This is either the first session or a project that predates the persistence mechanism.
- If state.json has intermediate_results, offer to bootstrap DERIVATION-STATE.md from them.
- Flag: "No persistent derivation history (will be created on next pause)"

</step>

<step name="verify_conventions">
**Convention verification** — after days away, convention drift is the most common source of silent errors when resuming:

```bash
CONV_CHECK=$(gpd --raw convention check 2>/dev/null)
if [ $? -ne 0 ]; then
  echo "WARNING: Convention verification failed — conventions may have drifted since last session"
  echo "$CONV_CHECK"
fi
```

If convention check fails, flag in the status presentation (step present_status) so the user sees it before resuming work. Convention mismatches between locked conventions and CONVENTIONS.md should be resolved before any new derivations.
</step>

</process>
