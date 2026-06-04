# Continuation Format

Continuation output is presentation layer only. Route authority comes from the
code-owned stage-stop envelope, lifecycle route, recovery advice, or typed
suggestion payload; this file must not choose lifecycle routes itself.

## Rendering Contract

Use `stage-stop-envelope.md` for the public stop shape. When a workflow receives
a typed route payload, emit its renderer-owned `## > Next Up` markdown and the
matching `stage_stop.next_runtime_command` / `stage_stop.also_available`
projection.

If a payload has typed `NextCommand` fields but no rendered next-up markdown,
render the same owner labels used by `render_next_up_block`:

- `Primary:`
- `Primary local transition:`
- `**After this completes:**`
- `Secondary runtime:`
- `Secondary local helper:`
- `Secondary local finalizer:`

Do not expose raw init, field-access, readiness, cleanup, shell-control,
structural verification, or local helper commands as public runtime next
commands.

## Stop And Checkpoint Rules

Every completion, checkpoint, blocked return, failed return, retry gate, or stop
that expects later action must end with a concrete route from the owning payload.
Do not end on labels such as "ready", "continue", "retry", "review", or "stop
here" unless the same final section gives the exact command or artifact action.

Start a fresh context window only when the next command and project rediscovery path are explicit.
Fresh context reset means a fresh context reset of the runtime window, not project recovery. Before
reopening the runtime, use your normal terminal to rediscover the workspace when
needed: `gpd resume` for the current recovery snapshot, or
`gpd resume --recent` to find the workspace first. do not treat the fresh context reset as project recovery.

Use these route families only as payload expectations, not prompt-owned branch
logic:

- persisted handoff/checkpoint: runtime resume route, usually `gpd:resume-work`;
- same workflow retried after user edits: the original runtime command, such as
  `gpd:new-project --minimal @file.md`;
- lifecycle phase planning/execution/verification/closeout: lifecycle or
  `gpd --raw suggest` route payload;
- convention or recovery blockers: recovery-advice route payload;
- no clear primary route: `gpd:suggest-next`.

If the owning payload is missing or unparseable, surface the payload/error and
stop instead of inventing a route.

## Pulling Context

Context labels are descriptive only; they cannot override the typed command.

For phases, extract the name and goal from `ROADMAP.md`:

```markdown
### Phase 2: Linear Response

**Goal:** Compute susceptibilities and response functions in RPA
```

Display context can become `Phase 2: Linear Response -- Compute
susceptibilities and response functions in RPA`.

For plans, prefer `PLAN.md` frontmatter/body fields already surfaced by the
runtime. If only the plan body is available, use the `<objective>` block as a
one-line description:

```xml
<objective>
Compute one-loop self-energy with RPA-screened interaction.

Purpose: Obtain quasiparticle lifetime and effective mass renormalization.
</objective>
```

## Anti-Patterns

- Command-only continuation with no context label.
- Fresh-context text without an exact next command from the owning route.
- "Other options" language instead of renderer-owned secondary labels.
- Fenced code blocks for public runtime commands; use inline command labels in
  renderer-owned lines.
