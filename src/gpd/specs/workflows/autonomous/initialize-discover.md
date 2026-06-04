<stage id="initialize_discover">
Autonomous mode is an orchestrator, not a Markdown status parser. Load this
stage first:

```sh
AUTONOMOUS_INIT=$(gpd --raw init autonomous --stage initialize_discover)
```

Apply `AUTONOMOUS_INIT.staged_loading.field_access_instruction` before reading
`AUTONOMOUS_INIT`, then use the returned JSON and the raw helpers below as the
only phase-status authorities.

<discover>
If the user supplied `--from`, use it as `PHASE_NUM`; otherwise run
`gpd --raw roadmap analyze` and select the first incomplete phase. Load that
phase with `gpd --raw roadmap get-phase ${PHASE_NUM}` before any child command
starts. When the selected phase may already be complete, call
   `gpd --raw init verify-work ${PHASE_NUM}` and use
   `verification_report_status` from the JSON response.
</discover>

<delegation_surface>
Autonomous mode routes work to the runtime-installed child commands instead of
copying their local procedures:

- `gpd:discuss-phase`
- `gpd:plan-phase`
- `gpd:execute-phase`
- `gpd:verify-work`
- `gpd:write-paper`
- `gpd:validate-conventions`
- `gpd:audit-milestone`
- `gpd:complete-milestone`
</delegation_surface>

<next_route>
If no runnable phase remains, route to `convention_lifecycle_closeout`.
If `PHASE_NUM` is known, route to `phase_route`.
</next_route>
</stage>
