<purpose>
Run the rapid cross-phase consistency checker after verification passes and before closeout readiness can transition state.
</purpose>

<stage_boundary>
This stage owns rapid consistency checker spawn, consistency artifact validation, malformed checker output handling, convention-repair routing, and fail-closed stops. It does not verify physics, repair conventions inline, or close the phase.
</stage_boundary>

<process>

<step name="load_consistency_stage">
Refresh only this stage before reading consistency-check fields:

```bash
CONSISTENCY_CHECK_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage consistency_check)
if [ $? -ne 0 ] || [ -z "$CONSISTENCY_CHECK_INIT" ]; then
  echo "ERROR: consistency-check stage refresh failed: $CONSISTENCY_CHECK_INIT"
  exit 1
fi
```

Apply `CONSISTENCY_CHECK_INIT.staged_loading.field_access_instruction` before reading `CONSISTENCY_CHECK_INIT`.
</step>

<step name="spawn_rapid_checker">
Resolve the checker model and set a freshness marker immediately before spawning:

```bash
CONSISTENCY_MODEL=$(gpd resolve-model gpd-consistency-checker)
CONSISTENCY_HANDOFF_STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
```

Spawn a single rapid checker:

```
task(
  subagent_type="gpd-consistency-checker",
  model="{consistency_model}",
  readonly=false,
  prompt="First, read {GPD_AGENTS_DIR}/gpd-consistency-checker.md for your role and instructions.

<mode>rapid</mode>
<phase>{PHASE_NUMBER}</phase>

Check phase {PHASE_NUMBER} results against the conventions ledger and accumulated project state.
Use CONSISTENCY_CHECK_INIT fields first: convention_lock, derived_convention_lock, SUMMARY frontmatter convention fields, state_load_source, and state_integrity_issues.
Use `gpd convention list` and file_read GPD/STATE.md / GPD/state.json only if the payload is missing or inconsistent.

<spawn_contract>
write_scope:
  mode: scoped_write
  allowed_paths:
    - "{phase_dir}/CONSISTENCY-CHECK.md"
expected_artifacts:
  - "{phase_dir}/CONSISTENCY-CHECK.md"
shared_state_policy: return_only
</spawn_contract>

Return exactly one typed gpd_return envelope, include files_written, and keep that envelope in the child response. Write {phase_dir}/CONSISTENCY-CHECK.md as a fresh report artifact. The runtime return is canonical: the report is accepted only when the runtime return names it in files_written and the child_gate freshness check passes. Do not embed or duplicate gpd_return inside the report artifact.",
  description="Rapid consistency check for Phase {PHASE_NUMBER}"
)
```
</step>

<step name="checker_return_status_route">
After the single rapid checker returns, read the runtime `gpd_return.status` first and route before schema repair or report-acceptance details.

- `completed`: accept only if the child_gate passes; continue to `consistency_child_gate` to run that gate.
- `checkpoint`: stop, surface the checkpoint payload, and route to `gpd:resume-work`.
- `blocked`: stop and route to `gpd:validate-conventions`.
- `failed`: stop and route to `gpd:validate-conventions`.

If the checker fails to spawn, returns an error, omits `gpd_return.status`, omits `files_written`, writes no readable `CONSISTENCY-CHECK.md`, or returns malformed output, treat the consistency check as blocked. Do not infer success from prose headings or untyped routing. Do not hand-author or paste a synthetic `gpd_return` into the checker artifact from the parent stage. Do not load report-contract repair templates unless the completed-return gate reports a repairable report schema issue.
</step>

<step name="consistency_child_gate">
Run the local child_gate only for checker returns triaged as `completed`. Shared acceptance semantics live in `references/orchestration/child-artifact-gate.md`; checkpoint transport lives in `references/orchestration/continuation-boundary.md`.

```yaml
child_gate:
  id: "rapid_consistency_check"
  profile: "execute.consistency_report.v1"
  artifact:
    path: "{phase_dir}/CONSISTENCY-CHECK.md"
  allowed_root: "{phase_dir}"
  freshness_marker: "$CONSISTENCY_HANDOFF_STARTED_AT"
```

The profile-expanded gate owns `CONSISTENCY-CHECK.md` acceptance through the shared child-artifact gate. A consistency-check artifact missing result is a gate failure.
</step>

<step name="completed_consistency_route">
After `rapid_consistency_check` passes, surface checker issues as warnings and continue to `closeout`. The report artifact must not embed or duplicate a `gpd_return`; the runtime return is canonical.
</step>

<step name="convention_repair_route">
Convention repair is out-of-line. Do not spawn `gpd-notation-coordinator` from execute-phase, do not route on checker-local prose markers, and do not accept a stale convention document as proof of repair.

For every consistency-check stop, populate `stage_stop` before rendering. Do not print raw staged-init or field-access commands in `## > Next Up`; those remain runtime mechanics.

| Stop | `stage_stop.status` | `reason` | `checkpoint` | `next_runtime_command` | `also_available` |
| --- | --- | --- | --- | --- | --- |
| checker spawn/error | `blocked` | `consistency_checker_unavailable` | `consistency_check` | `gpd:validate-conventions` | `gpd:resume-work`; `gpd:execute-phase {PHASE_NUMBER}`; `gpd:suggest-next` |
| checker checkpoint | `checkpoint` | `consistency_checker_checkpoint` | `consistency_check` | `gpd:resume-work` | `gpd:validate-conventions`; `gpd:suggest-next` |
| checker blocked | `blocked` | `consistency_checker_blocked` | `consistency_check` | `gpd:validate-conventions` | `gpd:resume-work`; `gpd:suggest-next` |
| checker failed | `failed` | `consistency_checker_failed` | `consistency_check` | `gpd:validate-conventions` | `gpd:resume-work`; `gpd:suggest-next` |
| malformed output | `blocked` | `consistency_checker_malformed_output` | `consistency_check` | `gpd:validate-conventions` | `gpd:verify-work {PHASE_NUMBER}`; `gpd:suggest-next` |

## > Next Up

Primary: `{stage_stop.next_runtime_command}`

**Also available:**
- `{secondary command}` -- route-specific recovery
- `gpd:suggest-next` -- confirm the next action

<sub>Start a fresh context window, then run the primary command above.</sub>
</step>

</process>
