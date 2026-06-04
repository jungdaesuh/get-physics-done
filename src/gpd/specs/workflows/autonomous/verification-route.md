<purpose>
Route post-execution verification by delegating to `gpd:verify-work` and reading only canonical child status payloads.
</purpose>

<stage_scope>
Stage id: `verification_route`. This stage owns the autonomous decision after execute-phase returns completed. `verify-work` owns verifier preflight, active-session routing, target construction, proof policy, checks, report validation, and canonical verification status.
</stage_scope>

<routing_contract>
Autonomous mode is a runtime/provider-neutral orchestrator. Route on the `gpd:verify-work` child `gpd_return.status` and the verify-work `session_router` payload.

Do not inspect verification report prose, headings, score tables, or local status lines. Missing, malformed, stale, or unknown status is non-passing and stops at the owning child command route.
</routing_contract>

<process>

<step name="invoke_verify_work">
Unless `plan_execute_child_cycle` already returned a bounded checkpoint stop, invoke the runtime-installed `gpd:verify-work` child command with structured arguments `{phase: PHASE_NUM}`.
</step>

<step name="load_session_router_status">
After the child returns, normalize status from the child return envelope and the canonical verify-work session-router payload:

```bash
VERIFY_PAYLOAD=$(gpd --raw init verify-work "${PHASE_NUM}" --stage session_router)
VERIFY_STATUS=$(echo "$VERIFY_PAYLOAD" | gpd json get .verification_report_status --default "missing")
VERIFY_STATUS_PAYLOAD=$(echo "$VERIFY_PAYLOAD" | gpd json get .verification_report_status_payload --default '{}')
VERIFY_SCORE=$(echo "$VERIFY_STATUS_PAYLOAD" | gpd json get .score --default "")
```

Apply `VERIFY_PAYLOAD.staged_loading.field_access_instruction` before reading
`VERIFY_PAYLOAD`.

Use `verification_report_status_payload` for child-produced issue summaries and next-command hints. Never replace it with presentation text.
</step>

<step name="fail_closed_statuses">
If the child return is absent, malformed, ambiguous, or has an unknown `gpd_return.status`, stop through `blocked_recovery`.

If `VERIFY_STATUS` is `missing`, `missing_status`, `unparseable`, `unknown_status`, or any value not listed below, stop through `blocked_recovery` with primary `gpd:verify-work ${PHASE_NUM}`.

The stop is non-mutating: do not update ROADMAP, STATE, phase completion, convention records, or lifecycle artifacts.
</step>

<step name="route_verified_status">
Route only these canonical verification statuses:

| `verification_report_status` | Autonomous route |
| --- | --- |
| `passed` | Continue to `convention_lifecycle_closeout`. |
| `human_needed` | Ask whether the user will validate now or defer; a defer continues with a visible limitation, not a pass rewrite. |
| `expert_needed` | Ask whether to continue with the limitation or stop; stopping uses primary `gpd:verify-work ${PHASE_NUM}`. |
| `gaps_found` | Ask whether to run the one-attempt `gap_route`, continue with accepted gaps, or stop. |

For `human_needed`, `expert_needed`, and accepted `gaps_found`, carry the limitation forward in the stage state so lifecycle closeout can refuse to mark it as a clean pass unless the owning child status later becomes `passed`.
</step>

<stage_transition>
On `passed`, transition to `convention_lifecycle_closeout`.

On selected gap closure, transition to `gap_route` with `gap_retry_count` from stage state or child payload. If no retry count is present, initialize it to `0`.

On any fail-closed or user-stop route, transition to `blocked_recovery` and render exactly one primary next runtime command.
</stage_transition>

</process>

<success_criteria>
- [ ] Verification delegates to `gpd:verify-work`.
- [ ] Routing uses `gpd_return.status` plus verify-work `session_router` status.
- [ ] Missing, malformed, stale, prose-only, or unknown verification status is non-passing.
- [ ] Gaps can enter at most one automatic gap closure route.
- [ ] No roadmap, state, or lifecycle mutation occurs on non-passing verification.
- [ ] Routing stays runtime/provider-neutral.
</success_criteria>
