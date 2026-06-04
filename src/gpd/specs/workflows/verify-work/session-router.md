<purpose>
Thin `gpd-verifier` session router: preflight and routing only. The verifier owns targets, proof policy, verdicts, and status.
</purpose>
<stage_scope>
Stage id: `session_router`. Owns argument normalization, active-session routing, review preflight, contract/lifecycle gates, and canonical phase artifact discovery. Do not load proof-redteam, verifier handoff, report schema, or gap-repair authorities here.
</stage_scope>
<process>

<step name="check_type_selection">
Normalize args before init: the first non-flag token is the optional phase; flags may appear anywhere.

```bash
PHASE_ARG=""
VERIFY_FLAGS=()
for token in $ARGUMENTS; do
  case "$token" in
    --*) VERIFY_FLAGS+=("$token") ;;
    *) [ -z "$PHASE_ARG" ] && PHASE_ARG="$token" ;;
  esac
done
VERIFY_FLAG_TEXT="${VERIFY_FLAGS[*]}"
[ -n "$VERIFY_FLAG_TEXT" ] || VERIFY_FLAG_TEXT="--all"
```

Flags narrow optional checks only; proof gates, verifier ownership, and fail-closed routing do not change.
</step>

<step name="initialize" priority="first">
Load session-router first; load later stages only where used.

```bash
SESSION_ROUTER_INIT=$(gpd --raw init verify-work "${PHASE_ARG}" --stage session_router)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $SESSION_ROUTER_INIT"
  # STOP; surface the error.
fi
```

<field_access>
Apply `SESSION_ROUTER_INIT.staged_loading.field_access_instruction` before
reading `SESSION_ROUTER_INIT`. Do not assume reference ledgers, protocol
bundles, or report schemas are loaded here; verifier/gap authorities are
stage-local.
</field_access>

```bash
export PROJECT_ROOT PHASE_DIR_ABS
PROJECT_ROOT=$(echo "$SESSION_ROUTER_INIT" | gpd json get .project_root)
PHASE_DIR_ABS=$(echo "$SESSION_ROUTER_INIT" | gpd json get .phase_dir_abs --default "")
```

**If no phase was provided:**

Read `active_verification_sessions` from `SESSION_ROUTER_INIT`. It comes from the canonical verification-status reader, is capped to five sessions, and replaces shell loops over `GPD/phases`.

Active sessions are payload entries with `session_status` of `validating` or `diagnosed`. Route on each entry's canonical `status` / `routing_status` and keep `session_status` conversational only; never let `session_status` overwrite `status`.

No-phase routing is choice-only:

- active sessions present: ask the user to choose one numbered session or provide a phase number; do not delegate yet;
- no active sessions present: ask for a phase and show the runtime route `gpd:verify-work <phase>`;
- never render `gpd verify phase` or bare `gpd-verify-work` as the visible verification workflow action.

If active sessions exist, display a compact numbered list and ask for a number or phase.

Wait for user response; load phase-only stages only after `PHASE_ARG` is set. If none exist, stop with the envelope below:

```yaml
stage_stop: {workflow: verify-work, stage: session_router, status: blocked, reason: verification_phase_needed, checkpoint: none, user_decision_needed: true, next_runtime_command: "gpd:verify-work <phase>", also_available: ["gpd:suggest-next"]}
```

## > Next Up
Primary: `gpd:verify-work <phase>`
Secondary runtime: `gpd:suggest-next`

## Phase Argument Errors

**If non-empty `${PHASE_ARG}` is not found:**

```
ERROR: Phase not found: ${PHASE_ARG}

Available phases:
$(gpd phase list)

Usage: gpd:verify-work <phase>
```

Exit.

Run the centralized review preflight before continuing:

```bash
if [ -n "${PHASE_ARG}" ]; then
  REVIEW_PREFLIGHT=$(gpd validate review-preflight verify-work "${PHASE_ARG}" --strict)
else
  REVIEW_PREFLIGHT=$(gpd validate review-preflight verify-work --strict)
fi
if [ $? -ne 0 ]; then
  echo "$REVIEW_PREFLIGHT"
  exit 1
fi
```

If review preflight exits nonzero, stop and show its blocking issues before any delegation.

`contract_gate_stop:` workflow=verify-work; stage=session_router; status=blocked; checkpoint=contract_gate; trigger=blocked load | invalid validation | non-authoritative gate; primary=gpd:sync-state|gpd:new-project; rerun=gpd:verify-work ${PHASE_ARG}; secondary=gpd:suggest-next.

If contract load is blocked, validation is invalid, or `project_contract_gate.authoritative` is not true, STOP before delegation, show the surfaced gate/load/validation errors, and use one concrete `contract_gate_stop` envelope:

```yaml
stage_stop: {workflow: verify-work, stage: session_router, status: blocked, reason: contract_gate_repair_required, checkpoint: contract_gate, user_decision_needed: true, next_runtime_command: "gpd:sync-state", also_available: ["gpd:verify-work ${PHASE_ARG}", "gpd:suggest-next"]}
```

Use `gpd:new-project` as `next_runtime_command` only when the surfaced gate says no project exists.

## > Next Up
Primary: `gpd:sync-state`
Secondary runtime: `gpd:verify-work ${PHASE_ARG}`
Secondary runtime: `gpd:suggest-next`

## Continue Routing

Run the executable lifecycle authority gate before proof repair, inventory building, contract checks, or verifier delegation:

```bash
LIFECYCLE_CONTRACT_GATE=$(gpd --raw validate lifecycle-contract-gate verify-work "${PHASE_ARG}")
if [ $? -ne 0 ]; then
  echo "$LIFECYCLE_CONTRACT_GATE"
  exit 1
fi
```

Use canonical artifact discovery helpers during bootstrap. `verification_report_status_payload` is fail-closed; `missing`, `missing_status`, `unparseable`, or `unknown_status` means pending verification, never pass.

```bash
PHASE_INFO=$(gpd --raw roadmap get-phase "${PHASE_ARG}")
```

Use `phase_dir_abs` for shell/file IO. Read PLAN.md files in `${PHASE_DIR_ABS}/` with `file_read`.
</step>

<stage_transition>
After `PHASE_ARG` is set and session-router preflight succeeds, load the next active authority with:

```bash
PHASE_BOOTSTRAP_INIT=$(gpd --raw init verify-work "${PHASE_ARG}" --stage phase_bootstrap)
```

Apply `PHASE_BOOTSTRAP_INIT.staged_loading.field_access_instruction` before
reading `PHASE_BOOTSTRAP_INIT`.

Do not load inventory, interactive-validation, gap-repair, verification-report schema, or planner/checker authorities in this stage.
</stage_transition>

</process>
