<purpose>
Run at most one autonomous gap-closure attempt, then re-enter verification routing with fresh canonical status.
</purpose>

<stage_scope>
Stage id: `gap_route`. This stage owns only the optional autonomous gap retry after `verification_route` reports canonical `gaps_found`.

`plan-phase`, `execute-phase`, and `verify-work` own gap planning, gap-only execution, verifier policy, and verification report status. Autonomous owns the retry bound and fail-closed routing.
</stage_scope>

<routing_contract>
Track the retry bound in stage state or a child payload field named `gap_retry_count`. Do not infer retry history from conversation prose or report text.

Do not route on report headings, presentation summaries, or local status lines. Missing or unroutable child status stops through `blocked_recovery`.
</routing_contract>

<process>

<step name="retry_bound">
Before doing any work, read `gap_retry_count`.

If `gap_retry_count >= 1`, stop. Render a `stage_stop` with primary `gpd:plan-phase ${PHASE_NUM} --gaps` and secondary `gpd:verify-work ${PHASE_NUM}`. Do not start another autonomous gap attempt.

If no retry has happened, set `gap_retry_count` to `1` for this route before invoking children so a checkpoint/resume cannot repeat the attempt silently.
</step>

<step name="plan_gap_child">
Invoke the runtime-installed `gpd:plan-phase` child command with structured arguments `{phase: PHASE_NUM, mode: "gaps"}`.

After return, refresh phase state:

```bash
PHASE_STATE=$(gpd --raw init phase-op "${PHASE_NUM}")
HAS_PLANS=$(echo "$PHASE_STATE" | gpd json get .has_plans --default false)
```

If the child return is not completed or `has_plans` is false, stop through `blocked_recovery` with primary `gpd:plan-phase ${PHASE_NUM} --gaps`.
</step>

<step name="execute_gap_child">
Invoke the runtime-installed `gpd:execute-phase` child command with structured arguments `{phase: PHASE_NUM, mode: "gaps_only"}`.

If execute-phase returns `checkpoint` or a bounded-stop payload, stop immediately with primary `gpd:resume-work` or the child-provided next command. Do not invoke verification, convention validation, lifecycle, or next-phase routing from a bounded stop.
</step>

<step name="fresh_verify_child">
After gap-only execution returns completed, invoke the runtime-installed `gpd:verify-work` child command with structured arguments `{phase: PHASE_NUM}`.

Reload canonical status through verify-work session-router:

```bash
VERIFY_PAYLOAD=$(gpd --raw init verify-work "${PHASE_NUM}" --stage session_router)
VERIFY_STATUS=$(echo "$VERIFY_PAYLOAD" | gpd json get .verification_report_status --default "missing")
```

Apply `VERIFY_PAYLOAD.staged_loading.field_access_instruction` before reading
`VERIFY_PAYLOAD`.

Do not reuse an earlier verification payload. Do not read report prose to decide whether the gap closed.
</step>

<stage_transition>
If fresh `VERIFY_STATUS` is `passed`, continue to `convention_lifecycle_closeout`.

If fresh `VERIFY_STATUS` is still `gaps_found`, stop or ask the user to accept the remaining limitation; do not start another automatic retry. Primary next command: `gpd:plan-phase ${PHASE_NUM} --gaps`.

For missing, malformed, or unknown status, transition to `blocked_recovery` with primary `gpd:verify-work ${PHASE_NUM}`.
</stage_transition>

</process>

<success_criteria>
- [ ] Gap closure is limited to one automatic retry.
- [ ] Gap planning delegates to `gpd:plan-phase` in gaps mode.
- [ ] Gap execution delegates to `gpd:execute-phase` in gaps-only mode.
- [ ] Fresh verification delegates to `gpd:verify-work`.
- [ ] Bounded gap execution stops before verification or lifecycle.
- [ ] Retry tracking does not rely on prose memory.
</success_criteria>
