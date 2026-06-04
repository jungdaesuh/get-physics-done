<stage id="discuss_delegate">
<purpose>
Create missing phase context by delegating to the dedicated discussion workflow.
</purpose>

<load>
Load this stage:

```sh
DISCUSS_DELEGATE_INIT=$(gpd --raw init autonomous --stage discuss_delegate)
```

Apply `DISCUSS_DELEGATE_INIT.staged_loading.field_access_instruction` before
reading `DISCUSS_DELEGATE_INIT`. Refresh the phase operation state:

```sh
PHASE_STATE=$(gpd --raw init phase-op ${PHASE_NUM})
```
</load>

<route>
Inspect `has_context` from the structured phase state.

- If `has_context` is true, route to `plan_execute_child_cycle`.
- If `has_context` is false, invoke `gpd:discuss-phase` with structured arguments `{phase: PHASE_NUM, auto: true}`.

Equivalent CLI form:

```text
gpd:discuss-phase ${PHASE_NUM} --auto
```
</route>

<ownership>
Autonomous mode does not clone the discussion template or author the phase
context directly. After the child returns, reload phase state and route to
`plan_execute_child_cycle` only when context is present.
</ownership>
</stage>
