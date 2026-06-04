<stage id="phase_route">
<purpose>
Choose the correct workflow for `PHASE_NUM` after roadmap discovery.
</purpose>

<load>
Load the current phase:

```sh
PHASE_ROUTE_INIT=$(gpd --raw init autonomous --stage phase_route)
```

Apply `PHASE_ROUTE_INIT.staged_loading.field_access_instruction` before reading
`PHASE_ROUTE_INIT`. Also load `gpd --raw roadmap get-phase ${PHASE_NUM}`. Then
refresh phase state with:

```sh
PHASE_STATE=$(gpd --raw init phase-op ${PHASE_NUM})
```
</load>

<routing>
Use the phase title, roadmap entry, and structured phase-state fields.

- For pure paper-writing phases, Use gpd:write-paper by invoking
  `gpd:write-paper` with structured arguments `{phase: PHASE_NUM}`.
- For phases with a derivation/computation indicator, Use normal discuss->plan->execute routing.
- If the phase lacks context, route to `discuss_delegate`.
- If context exists, route to `plan_execute_child_cycle`.
</routing>

<ownership>
This stage decides the route only. It does not write context files, run plan or
execution children, or inspect report prose.
</ownership>
</stage>
