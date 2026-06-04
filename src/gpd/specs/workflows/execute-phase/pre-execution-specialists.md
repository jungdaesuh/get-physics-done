<purpose>
Prepare explicit one-shot pre-execution specialist handoffs when classification requested them.
</purpose>

<stage_boundary>
This stage owns specialist routing only. It does not run the wave executor loop, aggregate results, or close the phase.
</stage_boundary>

<process>

<step name="prepare_pre_execution_specialists">
Load the specialist-routing stage only when a pre-wave specialist is actually needed.

When `PRE_EXECUTION_SPECIALISTS` is non-empty, refresh only this stage:

```bash
PRE_EXECUTION_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage pre_execution_specialists)
if [ $? -ne 0 ] || [ -z "$PRE_EXECUTION_INIT" ]; then
  echo "ERROR: pre-execution-specialists stage refresh failed: $PRE_EXECUTION_INIT"
  exit 1
fi
```

Apply `PRE_EXECUTION_INIT.staged_loading.field_access_instruction` before reading `PRE_EXECUTION_INIT`; this stage is available only for explicit one-shot specialist handoff sites.

Use this stage only at explicit one-shot specialist handoff sites. Do not recreate placeholder `task(...)` examples here, do not wait in place for user approval inside a child run, and do not treat a named specialist route as complete unless its later artifact gate passes.
</step>

</process>
