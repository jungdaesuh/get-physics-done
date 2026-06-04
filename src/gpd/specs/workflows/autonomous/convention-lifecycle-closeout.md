<purpose>
Run post-verification convention validation, re-read roadmap state, and route milestone lifecycle through child commands.
</purpose>

<stage_scope>
Stage id: `convention_lifecycle_closeout`. This stage owns late autonomous routing after verification has passed or a user has explicitly accepted a limitation.

It does not decide scientific verification status, parse audit markdown, implement convention logic, or complete a milestone directly. The owning child commands provide those statuses.
</stage_scope>

<routing_contract>
Use runtime-installed child commands and structured payloads. Do not route on report headings, audit prose, local status lines, or archive-file guesses.

Before any milestone audit or completion, re-check that every completed phase needed for closeout has a fresh canonical verification status of `passed` unless the user-facing route is explicitly a limitation stop. Missing, stale, malformed, non-passing, or unknown verification blocks lifecycle.
</routing_contract>

<process>

<step name="convention_validation">
If the project has `GPD/CONVENTIONS.md`, invoke the runtime-installed `gpd:validate-conventions` child command with structured arguments `{phase: PHASE_NUM}`.

Route on the child `gpd_return.status` or child-provided structured validation result:

- `completed` / `passed`: continue;
- `issues_found` / `blocked` / `failed` / malformed / missing: ask whether drift is intentional or stop with primary `gpd:validate-conventions ${PHASE_NUM}`.

If conventions are absent, skip this gate without creating a substitute convention artifact.
</step>

<step name="roadmap_reread">
After convention routing, re-read roadmap state through the roadmap helper:

```bash
ROADMAP_PAYLOAD=$(gpd --raw roadmap analyze)
```

Re-filter incomplete phases from the structured payload, preserving the original `--from` bound. If another phase remains, return a stage stop that routes to `phase_route` for that phase; do not jump directly into plan or execute from stale local state.
</step>

<step name="verification_closeout_guard">
If no incomplete phases remain, validate lifecycle readiness through verify-work session-router payloads before audit:

```bash
VERIFY_PAYLOAD=$(gpd --raw init verify-work "${COMPLETE_PHASE}" --stage session_router)
VERIFY_STATUS=$(echo "$VERIFY_PAYLOAD" | gpd json get .verification_report_status --default "missing")
```

Apply `VERIFY_PAYLOAD.staged_loading.field_access_instruction` before reading
`VERIFY_PAYLOAD`.

Every completed phase must report `passed` before milestone audit or completion. If any phase reports `missing`, `missing_status`, `unparseable`, `unknown_status`, `gaps_found`, `human_needed`, `expert_needed`, or any other non-passing value, stop with primary `gpd:verify-work ${COMPLETE_PHASE}`.
</step>

<step name="audit_child_route">
Invoke the runtime-installed `gpd:audit-milestone` child command with structured arguments `{}`.

Route on the child `gpd_return.status` and any structured audit payload returned by the command:

- `passed`: continue to completion;
- `gaps_found`: invoke or offer `gpd:plan-milestone-gaps` with structured arguments `{}`, then return to phase discovery;
- `issues_found`, `tech_debt`, `blocked`, `failed`, malformed, or missing: stop through `blocked_recovery` with primary `gpd:audit-milestone`.

Audit markdown is not a routing source.
</step>

<step name="complete_child_route">
Invoke the runtime-installed `gpd:complete-milestone` child command with structured arguments `{milestone_version: milestone_version}`.

Route on the child `gpd_return.status` or child-provided completion payload:

- `completed`: render final autonomous completion;
- `checkpoint`, `blocked`, `failed`, malformed, or missing: stop through `blocked_recovery` with the child-provided primary next command, otherwise primary `gpd:complete-milestone`.

Do not run archive verification as a local substitute for the completion child status.
</step>

<stage_transition>
For more phases, transition to `phase_route` with the next phase number from the fresh roadmap payload.

For audit gaps that create new roadmap phases, transition to `initialize_discover` or `phase_route` after the child command returns completed.

For completed milestone lifecycle, emit a final `stage_stop` with `status: completed`, `next_runtime_command: "gpd:new-milestone"`, and no raw staged-init commands in `## > Next Up`.
</stage_transition>

</process>

<success_criteria>
- [ ] Convention validation delegates to `gpd:validate-conventions`.
- [ ] Roadmap is re-read after each phase before routing onward.
- [ ] Stale, missing, malformed, or non-passing verification blocks lifecycle.
- [ ] Milestone audit delegates to `gpd:audit-milestone`.
- [ ] Audit gaps route through `gpd:plan-milestone-gaps`.
- [ ] Milestone completion delegates to `gpd:complete-milestone`.
- [ ] Audit and completion routing never depends on markdown prose.
- [ ] Routing stays runtime/provider-neutral.
</success_criteria>
