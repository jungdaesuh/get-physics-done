<purpose>
Render fail-closed autonomous stops and bounded user recovery choices without duplicating child workflow internals.
</purpose>

<stage_scope>
Stage id: `blocked_recovery`. This stage owns shared autonomous stop rendering, retry bounds, skip/stop choices, and `stage_stop` / `## > Next Up` output.

It does not repair child artifacts, rewrite child status, mutate roadmap/state directly, or continue closed child sessions.
</stage_scope>

<routing_contract>
Prefer the primary next command supplied by the owning child payload. If none is present, choose the public command that owns the failed stage:

- context missing: `gpd:discuss-phase ${PHASE_NUM}`
- planning blocked: `gpd:plan-phase ${PHASE_NUM}`
- execution blocked: `gpd:execute-phase ${PHASE_NUM}`
- bounded checkpoint: `gpd:resume-work`
- verification blocked: `gpd:verify-work ${PHASE_NUM}`
- convention blocked: `gpd:validate-conventions ${PHASE_NUM}`
- audit blocked: `gpd:audit-milestone`
- milestone completion blocked: `gpd:complete-milestone`

Never expose raw staged-init, field-access, helper-only, or diagnostic commands as the primary user continuation.
</routing_contract>

<process>

<step name="classify_stop">
Classify the stop from structured fields:

- owning command;
- phase number, if any;
- `gpd_return.status`;
- canonical status payload;
- child-provided next command;
- retry counters.

Do not classify from report prose or transcript memory.
</step>

<step name="offer_recovery">
When user input is useful, present at most three choices:

1. Fix and retry the owning command.
2. Skip this phase and continue to `phase_route`.
3. Stop autonomous mode.

Track retry count per phase and failed stage. After three retries for the same phase/stage, remove the retry option and offer only skip or stop.

Skip is a user decision route, not an automatic success claim. It must be recorded by the owning lifecycle surface or surfaced as a limitation before continuing.
</step>

<step name="render_stage_stop">
Render exactly one primary next runtime command:

```yaml
stage_stop:
  workflow: autonomous
  stage: blocked_recovery
  status: blocked
  reason: "{structured reason}"
  checkpoint: none
  user_decision_needed: true
  next_runtime_command: "gpd:{primary-command}"
  also_available:
    - "gpd:suggest-next"
```

Then render:

```markdown
## > Next Up

Primary: `gpd:{primary-command}`

**Also available:**
- `gpd:suggest-next` -- confirm the next action
```

Replace `{primary-command}` with the selected public runtime command. The
`## > Next Up` block must contain exactly one `Primary:` line and no raw
staged-init commands.
</step>

</process>

<success_criteria>
- [ ] Failures stop at the child command that owns repair.
- [ ] Retry, skip, and stop choices are bounded and explicit.
- [ ] Stops expose exactly one primary public next command.
- [ ] Raw staged-init and helper-only commands stay out of user-facing Next Up output.
- [ ] No child transcript memory is treated as authority.
- [ ] Routing stays runtime/provider-neutral.
</success_criteria>
