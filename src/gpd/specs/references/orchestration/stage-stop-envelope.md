# Stage Stop Envelope

Compact model-facing convention for deciding what a stop, checkpoint, blocked
return, failed return, or completion renders as the final `## > Next Up` block.
The envelope is not user-facing by itself. The code-owned `NextCommand`
taxonomy and `render_next_up_block(...)` renderer own public next-up rendering;
the envelope is the runtime-only projection of that typed decision.

```yaml
stage_stop:
  workflow: execute-phase
  stage: wave_dispatch
  status: checkpoint
  reason: first_result_review
  checkpoint: first_result
  user_decision_needed: true
  next_runtime_command: gpd:resume-work
  also_available:
    - gpd:execute-phase {phase_number}
    - gpd:suggest-next
```

## Field Rules

- `workflow`: public workflow id, such as `execute-phase`, `verify-work`, or
  `plan-phase`.
- `stage`: manifest stage id, such as `wave_dispatch`, `closeout`, or
  `gap_repair`.
- `status`: one of `checkpoint`, `blocked`, `completed`, or `failed`.
- `reason`: compact snake_case reason for `checkpoint`, `blocked`, and
  `failed` stops.
- `checkpoint`: compact checkpoint class, or `none`.
- `user_decision_needed`: boolean. True only when the next run depends on user
  input.
- `next_runtime_command`: exactly one public `gpd:` runtime command projected
  from the rendered primary runtime command or from the `After this completes`
  route after a readiness-gated local transition. Shell commands, `gpd --raw
  init`, and `gpd --raw stage field-access` stay out of this field.
- `also_available`: optional secondary public `gpd:` runtime commands projected
  from secondary runtime `NextCommand` entries. These are alternatives, not
  competing primaries; keep shell commands, file-display commands, local
  transitions, local helpers, local finalizers, raw staged reload mechanics, and
  structural local helpers out.

If no domain-specific route is clear, set `next_runtime_command` to
`gpd:suggest-next`.

## Owner Labels

Use the `NextCommand` owner labels when a stop surface also mentions non-runtime
commands:

- `runtime`: public runtime commands rendered from `next_runtime_command` or
  `also_available`.
- `local_transition`: local state transitions such as
  `gpd phase complete N`. These can be the primary only for readiness-gated
  local transition surfaces, not for blocked/checkpoint runtime stops.
- `local_helper`: secondary local helper work such as helper-owned checkpoint
  cleanup. This is a non-runtime stage-stop owner; keep it out of
  `next_runtime_command` and `also_available`.
- `local_finalizer`: secondary local finalizer commands that produce or apply a
  concrete artifact. This is a non-runtime stage-stop owner; keep it out of
  `next_runtime_command` and `also_available`.
- `display_only`: explanatory paths or examples that are not commands to run.

Blocked, checkpoint, failed, and post-completion runtime stops keep
`next_runtime_command` as the primary runtime route. A ready local transition
may render `Primary local transition: ...`, but the next runtime command after
that transition must be rendered separately under `**After this completes:**`.
Do not use `**After this completes:**` after a runtime primary; repair retry
routes belong under `Secondary runtime:` or a display-only note.

## Render Rule

Every user-facing stop renders through `render_next_up_block(...)` into this
command-line shape:

```markdown
## > Next Up

Primary: `gpd:resume-work`
Secondary runtime: `gpd:execute-phase {phase_number}`
Secondary runtime: `gpd:suggest-next`
```

A rendered runtime `## > Next Up` block contains exactly one `Primary:` line,
and that line contains a public `gpd:` command. A readiness-gated local
transition block instead contains exactly one `Primary local transition:` line
plus `**After this completes:**`. Put secondary commands only under
renderer-owned secondary labels such as `Secondary runtime:`, `Secondary local
helper:`, or `Secondary local finalizer:`.

Report paths and other display-only entries are not commands. Render them under
a label such as `**Report:**` or `**Display only:**`, never in
`stage_stop.also_available`.

For readiness-gated local transitions, the one primary line may use the owner
label:

```markdown
## > Next Up

Primary local transition: `gpd phase complete N`

**After this completes:** `gpd:plan-phase N+1`
Secondary local helper: `gpd --raw phase checkpoint cleanup --phase N --namespace phase --policy successful-closeout`
```

## Raw-Init Boundary

Raw staged reload mechanics belong only in runtime and agent-authority loading
instructions.

- Allowed: shell snippets and stage-loading instructions before closeout render
  logic, such as `gpd --raw init ... --stage ...`.
- Allowed: field inventory instructions such as
  `gpd --raw stage field-access ...`.
- Not user-facing: rendered `## > Next Up` blocks, checkpoint text intended as final
  user output, or closeout snippets that ask the user to run raw staged-init or
  field-access commands.

## Route Examples

| Stop class | `status` | `checkpoint` | `next_runtime_command` |
| --- | --- | --- | --- |
| Resumable checkpoint | `checkpoint` | `first_result` | `gpd:resume-work` |
| Blocked contract gate | `blocked` | `none` | `gpd:sync-state` |
| New project setup gate | `blocked` | `none` | `gpd:new-project` |
| Verification gaps | `blocked` | `verification_gap` | `gpd:plan-phase N --gaps` |
| Successful next phase with context | `completed` | `none` | `gpd:plan-phase N` |
| Successful next phase without context | `completed` | `none` | `gpd:discuss-phase N` |
| Milestone ready for audit | `completed` | `none` | `gpd:audit-milestone` |
| Milestone audit passed | `completed` | `none` | `gpd:complete-milestone` |
| Failed stop with no clear route | `failed` | `none` | `gpd:suggest-next` |
