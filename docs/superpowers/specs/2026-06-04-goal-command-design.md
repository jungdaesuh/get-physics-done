# Design: `gpd:goal` — goal- and budget-directed autonomous runs

- **Date:** 2026-06-04
- **Status:** Approved design, pre-implementation
- **Context:** GPD hackathon feature ("/goal: set a goal and a budget; the run continues itself"), 1-day solo scope
- **Approach:** Runtime command layered on existing `autonomous` orchestration, with binding budget gate and verifier-gated goal completion

## Problem

GPD's `autonomous` command runs remaining phases unattended, but there is no way to
say *what outcome* the run is for or *how much it may spend*. Cost budgets exist in
`src/gpd/core/costs.py` but are advisory only (`at_or_over_budget`, `near_budget`
states are reported, never enforced). Runs stop on roadmap exhaustion, blocks, or
checkpoints — not on goal achievement, and never on budget.

`gpd:goal` adds both: a typed goal contract with machine-checkable success criteria,
and a USD budget that binds the run.

## User surface

```
/gpd:goal "Derive the dispersion relation for X and verify the long-wavelength limit" --budget-usd 5
/gpd:goal --resume [--budget-usd 8]
gpd goal status        # terminal receipt: spend, criteria, phases, status
gpd validate goal-contract <file.json|->   # typed validation surface
```

Interaction model: one upfront confirmation. GPD drafts machine-checkable success
criteria from the goal statement; the user confirms or edits them once. After that
the run is unattended until it reaches exactly one terminal state:

| Terminal state | Meaning |
|---|---|
| `achieved` | Verification machinery passed **all** success criteria |
| `budget_stopped` | Spend reached budget; clean checkpoint + receipt + resume instructions |
| `blocked` | Existing blocked-recovery path, with goal context attached |

## Goal contract

New `goal_contract` section in `GPD/state.json`, mirrored as a short summary block in
`STATE.md`:

```json
{
  "goal_contract": {
    "schema_version": 1,
    "statement": "...",
    "success_criteria": [
      {
        "id": "GC-1",
        "description": "...",
        "check_ref": "<verification-contract check id>",
        "expected": "pass"
      }
    ],
    "budget_usd": 5.0,
    "baseline_spent_usd": 12.34,
    "status": "active",
    "created": "...",
    "updated": "..."
  }
}
```

- `success_criteria[].check_ref` references the existing verification-contract check
  vocabulary, so criteria are machine-checkable rather than free prose.
- `baseline_spent_usd` snapshots project-scope spend at goal start so the budget
  measures *this run*, not project lifetime.
- `status`: `active | achieved | budget_stopped | blocked`.
- Validated by `gpd validate goal-contract`, following the existing typed-validator
  pattern (`plan-contract`, `review-ledger`, `referee-decision`).

## Run loop and gates

`src/gpd/commands/goal.md` (command descriptor): staged init → draft criteria →
confirm once → delegate into the existing `autonomous` phase-route loop
(`src/gpd/specs/workflows/autonomous/`), with two gates injected at stage boundaries:

**Budget gate** — every phase boundary. Queries project-scoped cost state via the
existing cost machinery. For goal runs the advisory thresholds become binding:

- `near_budget` → wrap-up mode: no new phases are opened; current work is brought to
  a checkpointable state.
- `at_or_over_budget` → checkpoint cleanly, set `status=budget_stopped`, emit receipt.

**Goal gate** — after each verification-route completes. Evaluates
`success_criteria` against verification results. All pass → `status=achieved`, stop.
Otherwise route the next phase as `autonomous` already does.

Anti-reward-hacking property: the run cannot self-declare success. Only the
verification machinery can flip `status` to `achieved`.

## Receipt and observability

- `gpd goal status`: spent vs budget (with percent), criteria pass/fail table,
  phases completed, terminal status. This is the demo "receipt."
- Goal lifecycle events recorded through the existing observability session log:
  `goal.start`, `goal.budget_gate`, `goal.criteria_check`, `goal.stop`.
  `gpd observe export` then replays a long run for presentation.

## Error handling

- **Cost telemetry unavailable → fail closed.** A goal run pauses and asks rather
  than running unbudgeted.
- Malformed or missing goal contract → stable validation error envelopes (existing
  pattern).
- Interruption mid-phase → existing recovery ladder unchanged; `/gpd:goal --resume`
  re-enters the loop on the same contract, optionally with a raised budget.

## Testing

- **Unit (hermetic, no LLM/network):** goal-contract schema validation; budget-gate
  decision function (cost state → continue / wrap-up / stop); criteria evaluation
  against verification results.
- **Registry/adapter:** new command descriptor passes `tests/adapters/test_registry.py`
  and install-roundtrip coverage.
- **CLI:** `gpd validate goal-contract` and `gpd goal status` surface tests in the
  style of `tests/core/test_cli.py`.

## Hackathon eval story

1. **Budget adherence:** did runs stop at or under budget? Overshoot distribution.
2. **Criteria precision:** verifier-confirmed achievements vs self-claimed progress.
3. **Interruption recovery:** kill a run mid-phase; `--resume` completes it.

## Scope cuts (1-day discipline)

- Claude Code runtime first; other runtimes come through the adapter registry but
  are not demo-blocking.
- No multi-goal queueing; one active goal contract per project.
- USD budget only (no wall-clock/token caps).
- Criteria drafting is a prompt step inside the command, not a new specialist agent.

## Out of scope (future work)

- Hard in-process enforcement via a headless-session orchestrator (`gpd goal run`
  driving `claude -p` loops) — the long-term architecture, deliberately deferred.
- Budget top-up policies, multi-goal portfolios, cross-project goals.
