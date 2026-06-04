<purpose>
Bootstrap phase lookup, contract gates, plan preflight, and branch setup.
</purpose>

<stage_boundary>
First-stage authority only: arguments, bootstrap init, lifecycle gates, plan preflight, and branch setup. Do not load downstream authorities.
</stage_boundary>

<process>

<step name="normalize_arguments" priority="first">
Normalize phase and flags before any init call. The first non-flag positional token is the phase; flags may appear before or after it.

```bash
PHASE_ARG=""
EXECUTE_FLAGS=()
for token in $ARGUMENTS; do
  case "$token" in
    --*) EXECUTE_FLAGS+=("$token") ;;
    *) [ -z "$PHASE_ARG" ] && PHASE_ARG="$token" ;;
  esac
done
GAPS_ONLY=false
for flag in "${EXECUTE_FLAGS[@]}"; do
  [ "$flag" = "--gaps-only" ] && GAPS_ONLY=true
done

if [ -z "$PHASE_ARG" ]; then
  echo "ERROR: missing phase. Usage: execute-phase <phase-number> [--gaps-only]"
  exit 1
fi
```
</step>

<step name="initialize" priority="first">
Load only the bootstrap stage.

```bash
INIT_STDERR=$(mktemp)
BOOTSTRAP_INIT=$(gpd --raw init execute-phase "${PHASE_ARG}" --stage phase_bootstrap 2>"$INIT_STDERR")
INIT_STATUS=$?
if [ "$INIT_STATUS" -ne 0 ] || [ -z "$BOOTSTRAP_INIT" ]; then
  echo "ERROR: gpd initialization failed: execute-phase bootstrap (exit ${INIT_STATUS})."
  [ -n "$BOOTSTRAP_INIT" ] && echo "stdout: $BOOTSTRAP_INIT"
  [ -s "$INIT_STDERR" ] && echo "stderr: $(cat "$INIT_STDERR")"
  rm -f "$INIT_STDERR"
  exit 1
fi
rm -f "$INIT_STDERR"
```

Apply `BOOTSTRAP_INIT.staged_loading.field_access_instruction` before reading `BOOTSTRAP_INIT`.

Bind `phase_dir` and `phase_number` from `BOOTSTRAP_INIT` before snippets; default phase number to `PHASE_ARG`.

Init blockers: `phase_found=false` => phase directory not found; `plan_count=0` => no plans found; `state_exists=false` with `GPD/` => offer reconstruct or continue.

`contract_gate_stop:` workflow=execute-phase; stage=phase_bootstrap; status=blocked; checkpoint=contract_gate; trigger=blocked load | invalid validation | non-authoritative gate; primary=gpd:sync-state|gpd:new-project; rerun=gpd:execute-phase ${PHASE_ARG}; secondary=gpd:suggest-next.

For blocked contract load, invalid contract validation, or non-authoritative `project_contract_gate`, STOP, show the gate/load/validation errors, and use `contract_gate_stop`.

Run the lifecycle authority gate before branch, plan, wave, contract, alignment, or delegation work:

```bash
LIFECYCLE_CONTRACT_GATE=$(gpd --raw validate lifecycle-contract-gate execute-phase "${PHASE_ARG}")
if [ $? -ne 0 ]; then
  echo "$LIFECYCLE_CONTRACT_GATE"
  exit 1
fi
```

Later stages surface reference/protocol handles. Before branch handling, scripts, dispatches, writes, or claims, selected `PLAN.md` files must pass preflight.
</step>

<step name="validate_selected_plans_before_execution" priority="first">
Validate selected plans before execution-side work. On failure, do not run scripts, computations, dispatches, subagents, writes, branch creation, or result claims.
```bash
SELECTED_PLAN_FILES=()
for plan in "$phase_dir"/*-PLAN.md; do
  [ -e "$plan" ] || continue
  if [ "$GAPS_ONLY" = true ]; then
    GAP_CLOSURE=$(gpd frontmatter get "$plan" --field gap_closure 2>/dev/null || echo false)
    [ "$GAP_CLOSURE" = "true" ] || continue
  fi
  SELECTED_PLAN_FILES+=("$plan")
done
if [ ${#SELECTED_PLAN_FILES[@]} -eq 0 ]; then
  echo "ERROR: no executable PLAN.md files found for phase ${PHASE_ARG}. Revise or recreate the missing/invalid plan, then rerun execute-phase for ${PHASE_ARG}."
  exit 1
fi
PLAN_GATE_FAILED=false
for plan in "${SELECTED_PLAN_FILES[@]}"; do
  gpd validate plan-contract "$plan" || PLAN_GATE_FAILED=true
  if ! gpd verify plan "$plan"; then
    PLAN_GATE_FAILED=true
  fi
  PLAN_PREFLIGHT=$(gpd --raw validate plan-preflight "$plan") || {
    echo "ERROR: plan preflight failed for $(basename "$plan")"
    echo "$PLAN_PREFLIGHT"
    PLAN_GATE_FAILED=true
  }
  gpd verify references "$plan" || PLAN_GATE_FAILED=true
done
gpd phase validate-waves "$phase_number" || PLAN_GATE_FAILED=true
if [ "$PLAN_GATE_FAILED" = true ]; then
  echo "Plan validation/preflight failed before execution; no workspace scripts, numerical computations, task dispatches, subagents, artifact writes, or result claims were authorized."
  echo "Next: revise or recreate the invalid PLAN.md, then rerun execute-phase for ${PHASE_ARG}."
  exit 1
fi
```
Repair invalid plans with `gpd:plan-phase {N}`, then rerun `gpd:execute-phase {N}`.
</step>

<step name="handle_branching">
Check `branching_strategy` from init:

`none`: continue on current branch. `per-phase` or `per-milestone`: use precomputed `branch_name`:

```bash
git checkout -b "$BRANCH_NAME" 2>/dev/null || git checkout "$BRANCH_NAME"
```

Subsequent commits go to this branch; the user handles merging.
</step>

</process>
