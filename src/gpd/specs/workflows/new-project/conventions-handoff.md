<purpose>
Establish notation conventions after the roadmap has been committed.
</purpose>

@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md

<stage_boundary>
This stage starts only after the staged roadmap commit is recorded. It owns the
notation-coordinator handoff, supervised no-write checkpoint boundary, auto
direct-write path, deterministic fallback, convention lock, commit, and
checkpoint. It must not revise requirements or roadmap structure.
</stage_boundary>

<bootstrap>
Run a fresh staged init before spawning the notation coordinator:

```bash
NOTATION_HANDOFF_STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
CONVENTIONS_INIT=$(gpd --raw init new-project --stage conventions_handoff)
if [ $? -ne 0 ]; then
  echo "ERROR: conventions init failed: $CONVENTIONS_INIT"
  exit 1
fi
```

Follow `CONVENTIONS_INIT.staged_loading.field_access_instruction`; `<INIT>` there means `CONVENTIONS_INIT`. Do not revise requirements or roadmap structure here.

Do not require a `notation_model` init field. Resolve the concrete local model
override inside this stage immediately before spawning:

```bash
NOTATION_MODEL=$(gpd resolve-model gpd-notation-coordinator)
```

If `NOTATION_MODEL` is empty or null, omit `model=` entirely in the spawn call.
Continue without commentary about the missing override; that empty result is the
normal "use the runtime default model" path. If it has a concrete value, include
`model="$NOTATION_MODEL"`.
</bootstrap>

<process>

## 8.5. Establish Conventions

Convention setup mode is driven by autonomy, not by whether intake used
`--auto`:

- `autonomy=supervised` uses `interactive` mode. The notation coordinator must
  return a checkpoint proposal before writing anything. The orchestrator
  presents it to the user, then a fresh continuation handoff performs the final
  write after confirmation or override.
- `autonomy=balanced` uses `auto` mode. Lock clear subfield defaults
  automatically and checkpoint only for genuine ambiguity or cross-subfield
  conflict.
- `autonomy=yolo` uses `auto` mode and accepts the returned conventions
  automatically.

Set `CONVENTION_MODE` before spawning:

- `interactive` only when `autonomy=supervised`
- `auto` for `autonomy=balanced` and `autonomy=yolo`

Display:

```text
GPD >>> ESTABLISHING CONVENTIONS
>>> Spawning notation coordinator...
```

Apply the canonical runtime delegation convention already loaded above.

Spawn `gpd-notation-coordinator`. Use the same prompt for both model paths; only
the spawn call arguments differ:

```text
If NOTATION_MODEL has a concrete value:
  task(prompt=NOTATION_PROMPT, subagent_type="gpd-notation-coordinator", model="$NOTATION_MODEL", readonly=false, description="Establish project conventions")

If NOTATION_MODEL is empty or null:
  task(prompt=NOTATION_PROMPT, subagent_type="gpd-notation-coordinator", readonly=false, description="Establish project conventions")
```

`NOTATION_PROMPT`:

```text
First, read {GPD_AGENTS_DIR}/gpd-notation-coordinator.md for your role and instructions.

<task>
Establish initial conventions for this research project.
</task>

<project_context>
Read these files:
- GPD/PROJECT.md - Project definition, physics subfield, theoretical framework
- GPD/ROADMAP.md - Phase structure (what conventions will be needed)
- GPD/REQUIREMENTS.md - Research requirements
- GPD/literature/SUMMARY.md - Literature survey (if exists)
</project_context>

<mode>
{CONVENTION_MODE}
Auto mode: Use subfield defaults, lock all, skip user confirmation unless a genuine ambiguity or conflict blocks completion.
Interactive mode: Return `status: checkpoint` with the suggested conventions, rationale, test values, and any conflicts. Do NOT write `GPD/CONVENTIONS.md` and do NOT call `gpd convention set` until the orchestrator collects the user's confirmation/override and spawns a fresh continuation handoff.
</mode>

<output>
If mode=`auto`:
1. Create: GPD/CONVENTIONS.md (full convention reference)
2. Lock conventions via: gpd convention set
3. Return `gpd_return.status: completed` with a convention summary

If mode=`interactive`:
1. Return a checkpoint proposal only
2. Include the suggested conventions, rationale, test values, and any conflicts
3. Leave file creation and `gpd convention set` for the continuation handoff after user confirmation
</output>
Use only when mode=`auto`.

<spawn_contract>
activation: mode == auto
write_scope:
  mode: scoped_write
  allowed_paths:
    - GPD/CONVENTIONS.md
expected_artifacts:
  - GPD/CONVENTIONS.md
shared_state_policy: direct
</spawn_contract>

<spawn_contract_interactive>
activation: mode == interactive
write_scope:
  mode: no_write
  allowed_paths: []
expected_artifacts: []
expected_return:
  status: checkpoint
shared_state_policy: none
</spawn_contract_interactive>
```

**Notation-coordinator child gate:**

```yaml
child_gate:
  id: "notation_conventions"
  role: "gpd-notation-coordinator"
  return_profile: "roadmapper"
  required_status: "completed"
  expected_artifacts:
    - "GPD/CONVENTIONS.md"
  allowed_roots:
    - "GPD"
  freshness_marker: "$NOTATION_HANDOFF_STARTED_AT"
  validators:
    - "gpd validate handoff-artifacts - --expected GPD/CONVENTIONS.md --allowed-root GPD --require-status completed --require-files-written --fresh-after \"$NOTATION_HANDOFF_STARTED_AT\""
    - "readable CONVENTIONS.md"
    - "convention lock commands succeed in the child-owned direct path"
  applicator:
    command: "child direct gpd convention set in auto/approved continuation"
    require_passed_true: false
  failure_route: "spawn one fresh gpd-notation-coordinator continuation when usable content exists | repair prompt once | fail closed | fresh continuation persists GPD/CONVENTIONS.md and convention lock | repair path once | fail closed; surface incomplete handoff and stop | ..."
```

No-write approval boundary: in `interactive` mode before user approval,
expected artifacts are `[]` and the first checkpoint proposal is supervised
success, not an error. Route `checkpoint` -> present conventions, collect
confirmation/overrides, then spawn one fresh `gpd-notation-coordinator`
continuation that writes `GPD/CONVENTIONS.md`, runs `gpd convention set`, and
returns `gpd_return.status: completed`; route `spawn_or_error` -> deterministic
convention fallback below.

If the notation-coordinator agent fails to spawn or returns an error, use this
deterministic fallback instead of hardcoded defaults:

1. Read `GPD/PROJECT.md` and extract any explicit unit-system or
   metric-signature choices already recorded there.
2. If either value is still missing, read
   `{GPD_INSTALL_DIR}/references/conventions/subfield-convention-defaults.md`,
   identify the project's physics subfield from `GPD/PROJECT.md`, and resolve
   the matching default convention pair from that table.
3. If either value is still unresolved, stop and ask the user. Do not hardcode
   `natural` or `mostly_minus`.
4. Create a minimal `GPD/CONVENTIONS.md` that records the resolved values and
   states that richer convention coverage is still pending.
5. Populate the convention lock with the same resolved values:

   ```bash
   gpd convention set units "$RESOLVED_UNITS"
   gpd convention set metric_signature "$RESOLVED_METRIC"
   ```

6. Note that full convention establishment was skipped. The user can run
   `gpd:validate-conventions`; the fallback lock must match the values written
   into `GPD/CONVENTIONS.md`.

If conventions are established, display the convention summary. Pre-check
`GPD/CONVENTIONS.md`, then commit it:

```bash
gpd commit "docs: establish notation conventions" --files GPD/CONVENTIONS.md
```

If the coordinator reports `CONVENTION CONFLICT`, display conflicts and ask the
user to resolve them before proceeding.

Checkpoint step 8.5 by recording the current UTC timestamp and description
`Conventions established and committed` in `GPD/init-progress.json`.

After the checkpoint, reload `completion`.
</process>
