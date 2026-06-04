<purpose>
Create executable PLAN.md files for a phase. First-stage work is only phase
lookup, contract-gate validation, lifecycle gate, dirty-worktree safety, early
conflict stops, and routing to the next staged authority.
</purpose>

<stage_boundary>
Do not load downstream plan-phase authorities here. Research, planner authoring,
checker review, revision templates, and runtime delegation details belong to
later manifest stages.
</stage_boundary>

<process>

## 1. Initialize

```bash
BOOTSTRAP_INIT=$(gpd --raw init plan-phase "$PHASE" --stage phase_bootstrap)
if [ $? -ne 0 ]; then
  echo "ERROR: gpd initialization failed: $BOOTSTRAP_INIT"
  exit 1
fi
```

Apply `BOOTSTRAP_INIT.staged_loading.field_access_instruction` before reading `BOOTSTRAP_INIT`. Use shell aliases only for scalar bindings that truly need them (`--alias ALIAS=field`); do not reuse shell variables parsed from an older stage.

```bash
REQUESTED_PHASE="${PHASE}"
INIT="${BOOTSTRAP_INIT}"
# For this scalar binding, the helper-owned shape is:
# gpd --raw stage field-access plan-phase --stage phase_bootstrap --style shell --payload-var INIT --alias PHASE=phase_number
PHASE=$(echo "$INIT" | gpd json get .phase_number --default "${REQUESTED_PHASE}")
```

## 1.1 Select Phase Target

<event name="phase_target_selected">
Extract phase number and flags (`--research`, `--skip-research`, `--gaps`,
`--skip-verify`, `--light`, `--inline-discuss`). If no phase number was given,
use bootstrap's `phase_number`; if bootstrap cannot infer one, ask for an
explicit phase before running downstream gates. If `phase_found` is false,
validate ROADMAP.md and stop with `Error: Phase {PHASE} not found in ROADMAP.md.`
when invalid.

Present the selected target before the gate wall: `phase_number`, `phase_name`,
`phase_dir`, and whether the target was found. This is a read-only selection
event; do not create `PHASE_DIR`, spawn agents, render planner/checker prompts,
or write files here.
</event>

Mode summary: supervised pauses for user review, balanced pauses only for real
checker or planning judgment issues, yolo proceeds after hard gates. Research
mode controls breadth only: explore broadens; exploit mode suppresses optional
tangents unless the user explicitly requests `gpd:branch-hypothesis`; do not
auto-create git-backed branches from `git.branching_strategy` alone. Balanced
uses standard depth, and adaptive starts broad until decisive evidence or an
explicit approach lock justifies narrowing. All modes still require contract
completeness, decisive outputs, required anchors, forbidden-proxy handling, and
disconfirming paths before execution starts.

**Dirty worktree safety gate:** before phase directory creation, handoffs,
fingerprints, alignment, or write-capable reloads, inspect only the project
worktree. If it is dirty, halt before planning, show dirty paths, and offer
`git status --short`, `gpd commit`, or an explicitly approved project-local cleanup path.
`plan-phase` never stashes, resets, cleans, overwrites, or hides user work.

**If `planning_exists` is false:** Error -- run `gpd:new-project` first.

`contract_gate_stop:` ref=contract-authority-gate#blocked-lifecycle-stop-phrase; workflow=plan-phase; stage=phase_bootstrap; status=blocked; checkpoint=contract_gate; triggers=project_contract_load_info.status starts with blocked | project_contract is empty or null | project_contract_validation.valid is false | project_contract_gate.authoritative is not true; primary=gpd:sync-state|gpd:new-project; rerun=gpd:plan-phase {PHASE}; secondary=gpd:suggest-next.

**If `project_contract_load_info.status` starts with `blocked`:** STOP and checkpoint with the user. Show the specific `project_contract_load_info.errors` / `warnings`; do not silently continue from `ROADMAP.md` or `REQUIREMENTS.md` alone when the stored contract could not even be loaded cleanly. Use `contract_gate_stop`.

**If `project_contract` is empty or null:** STOP and checkpoint with the user. Planning requires an approved scoping contract in `GPD/state.json`; do not infer phase scope from `ROADMAP.md` or `REQUIREMENTS.md` alone. Use `contract_gate_stop`, choosing `gpd:new-project` as primary unless state exists but drifted.

**If `project_contract_validation.valid` is false:** STOP and checkpoint with the user. Quote the `project_contract_validation.errors` explicitly and repair the contract before planning. Use `contract_gate_stop`.

**If `project_contract_gate.authoritative` is not true:** STOP and checkpoint with the user. Treat `project_contract` as authoritative only when `project_contract_gate.authoritative` is true. Show `project_contract_gate`, load errors/warnings, and validation errors. Use `contract_gate_stop`.

Run the executable lifecycle authority gate before any research, planning,
checker, fingerprint, or alignment step:

```bash
LIFECYCLE_CONTRACT_GATE=$(gpd --raw validate lifecycle-contract-gate plan-phase "${PHASE}")
if [ $? -ne 0 ]; then
  echo "$LIFECYCLE_CONTRACT_GATE"
  exit 1
fi
```

<step name="fail_closed_on_state_conflict" priority="first">
Before resolving a missing phase, creating `PHASE_DIR`, spawning agents, or
writing plans, compare state, roadmap, requirements, phase directories, and
conventions. If they disagree about phase/scope, STOP: no new plan, roadmap
rewrite, execution, or generic health check. Repair route:

- state/roadmap phase mismatch or missing active phase directory -> `gpd:sync-state`
- convention-lock or `GPD/CONVENTIONS.md` mismatch -> `gpd:validate-conventions`

Canonical conflict-stop labels: `status: blocked`, `phase_state:
contract_conflict`, `plan_authority: blocked`, `execution_state: not_started`,
`checkpoint: convention_conflict`, artifacts+writes `none`,
`gpd:sync-state`/`gpd:validate-conventions`
</step>

## 1.5 Proof-Obligation Planning Gate

Bootstrap proof invariant: `--skip-verify` never waives proof-bearing plan
audit. The planner and checker stages own the detailed theorem, quantifier,
hypothesis, proof-redteam, and equivalent main-context audit policy.

## 2. Bootstrap Routing

`--inline-discuss` is only a quick gray-area probe for straightforward phases:
ask 2-3 planning-critical questions, record answers in lightweight CONTEXT.md,
and continue. Use `gpd:discuss-phase` for complex phases.

If `context_content` is not null in a later stage-local payload, display:
`Using phase context from: ${PHASE_DIR}/*-CONTEXT.md`.

Hypothesis context is a later-stage constraint: if a structured active
hypothesis exists, bind `HYPOTHESIS_SLUG`, read
`GPD/hypotheses/{HYPOTHESIS_SLUG}/HYPOTHESIS.md`, and make researcher, planner,
checker, and revision prompts serve that investigation rather than the parent
branch approach.

Run the convention check before spawning researcher or planner. Convention
mismatches compound into every planned and executed task; route failures to
convention validation.

Tangent invariant: do not silently branch, widen scope, or create detached side
plans. When multiple viable approaches appear, checkpoint explicitly and let
later planner/checker events apply the detailed tangent model.
If a tangent decision is needed, surface `gpd:tangent`; create
`gpd:branch-hypothesis` only after an explicit branch outcome.

Next, reload `gpd --raw init plan-phase "$PHASE" --stage research_routing` and apply the active staged payload instructions.

</process>
