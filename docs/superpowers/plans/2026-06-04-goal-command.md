# `gpd:goal` Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `gpd:goal "<statement>" --budget-usd X` — a goal- and budget-directed autonomous run with a typed goal contract, a binding budget gate, verifier-gated completion, and a `gpd goal status` receipt.

**Architecture:** A new pure-Python core module (`goal_contract.py`) holds the typed contract and gate decision logic; a `goal_contract` field is added to `ResearchState` (mirroring the existing `project_contract` field); a `gpd goal` typer sub-app exposes `status` (human receipt) and `gate` (machine decision the runtime loop shells out to); a `gpd validate goal-contract` command follows the existing typed-validator pattern; finally a `goal.md` command descriptor delegates the run loop to the existing `autonomous` workflow stages with gates between phases.

**Tech Stack:** Python 3.11+, pydantic v2, typer, pytest (`-n 0` for targeted runs). Spec: `docs/superpowers/specs/2026-06-04-goal-command-design.md`.

**Working rules for every task:**
- Run commands from the repo root (the worktree).
- Inside Claude Code, always run pytest as `env -u FORCE_COLOR uv run pytest ...` — the harness injects `FORCE_COLOR=3`, which breaks rich-output string assertions.
- The pre-commit hook runs ruff with `--fix --unsafe-fixes` on staged Python files; if it modifies files, `git add` them and commit again.
- Do not bump package versions (repo guardrail).

---

### Task 1: Goal contract models and state field

**Files:**
- Create: `src/gpd/core/goal_contract.py`
- Modify: `src/gpd/core/state.py` (add one field to `ResearchState`, around line 503 next to `contract_alignment`)
- Test: `tests/core/test_goal_contract.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_goal_contract.py`:

```python
"""Tests for the gpd:goal goal-contract models and validation."""

from gpd.core.goal_contract import (
    GoalContract,
    GoalCriterion,
    validate_goal_contract_payload,
)


def _valid_payload() -> dict:
    return {
        "schema_version": 1,
        "statement": "Derive the dispersion relation and verify the long-wavelength limit",
        "success_criteria": [
            {
                "id": "GC-1",
                "description": "Dispersion relation passes dimensional analysis",
                "check_ref": "dimensional_analysis",
                "expected": "pass",
            }
        ],
        "budget_usd": 5.0,
        "baseline_spent_usd": 0.0,
        "status": "active",
    }


def test_goal_contract_parses_valid_payload() -> None:
    contract = GoalContract.model_validate(_valid_payload())
    assert contract.statement.startswith("Derive")
    assert contract.success_criteria[0].id == "GC-1"
    assert contract.status == "active"


def test_goal_contract_rejects_unknown_status() -> None:
    issues = validate_goal_contract_payload({**_valid_payload(), "status": "victorious"})
    assert any("status" in issue for issue in issues)


def test_goal_contract_requires_positive_budget() -> None:
    issues = validate_goal_contract_payload({**_valid_payload(), "budget_usd": 0})
    assert any("budget_usd" in issue for issue in issues)


def test_goal_contract_requires_at_least_one_criterion() -> None:
    issues = validate_goal_contract_payload({**_valid_payload(), "success_criteria": []})
    assert any("success_criteria" in issue for issue in issues)


def test_goal_contract_criterion_ids_must_be_unique() -> None:
    payload = _valid_payload()
    payload["success_criteria"] = [
        payload["success_criteria"][0],
        {**payload["success_criteria"][0], "description": "duplicate id"},
    ]
    issues = validate_goal_contract_payload(payload)
    assert any("GC-1" in issue for issue in issues)


def test_validate_returns_no_issues_for_valid_payload() -> None:
    assert validate_goal_contract_payload(_valid_payload()) == []


def test_research_state_round_trips_goal_contract() -> None:
    from gpd.core.state import ResearchState

    state = ResearchState.model_validate({"goal_contract": _valid_payload()})
    assert state.goal_contract is not None
    assert state.goal_contract.budget_usd == 5.0
    dumped = state.model_dump(mode="json")
    assert dumped["goal_contract"]["statement"].startswith("Derive")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u FORCE_COLOR uv run pytest tests/core/test_goal_contract.py -n 0 -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gpd.core.goal_contract'`

- [ ] **Step 3: Write the implementation**

Create `src/gpd/core/goal_contract.py`:

```python
"""Typed goal contract for gpd:goal runs.

The goal contract lives in ``GPD/state.json`` under the ``goal_contract`` key
(a first-class ``ResearchState`` field, mirroring ``project_contract``). It
records the goal statement, machine-checkable success criteria, the binding
USD budget, and the run status.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

__all__ = [
    "GOAL_STATUSES",
    "GoalContract",
    "GoalCriterion",
    "validate_goal_contract_payload",
]

GOAL_STATUSES = ("active", "achieved", "budget_stopped", "blocked")


class GoalCriterion(BaseModel):
    """One machine-checkable success criterion."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    check_ref: str = Field(min_length=1)
    expected: Literal["pass"] = "pass"


class GoalContract(BaseModel):
    """Schema for the ``goal_contract`` section of state.json."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    statement: str = Field(min_length=1)
    success_criteria: list[GoalCriterion] = Field(min_length=1)
    budget_usd: float = Field(gt=0)
    baseline_spent_usd: float = Field(default=0.0, ge=0)
    status: Literal["active", "achieved", "budget_stopped", "blocked"] = "active"
    created: str | None = None
    updated: str | None = None


def validate_goal_contract_payload(payload: object) -> list[str]:
    """Validate a goal-contract payload; return stable issue strings."""
    if not isinstance(payload, dict):
        return ["goal_contract: payload must be a JSON object"]
    try:
        contract = GoalContract.model_validate(payload)
    except ValidationError as exc:
        issues: list[str] = []
        for error in exc.errors():
            location = ".".join(str(part) for part in error.get("loc", ())) or "goal_contract"
            issues.append(f"goal_contract.{location}: {error.get('msg', 'invalid value')}")
        return issues
    seen: set[str] = set()
    issues = []
    for criterion in contract.success_criteria:
        if criterion.id in seen:
            issues.append(f"goal_contract.success_criteria: duplicate criterion id {criterion.id}")
        seen.add(criterion.id)
    return issues
```

Modify `src/gpd/core/state.py` — in `ResearchState`, directly after the
`contract_alignment` field, add:

```python
    goal_contract: GoalContract | None = None
```

and add the import near the other `gpd.core.*` imports at the top of the file:

```python
from gpd.core.goal_contract import GoalContract
```

(`goal_contract.py` must not import from `state.py`, so no circular import.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `env -u FORCE_COLOR uv run pytest tests/core/test_goal_contract.py -n 0 -v`
Expected: 7 passed

- [ ] **Step 5: Run state regression tests**

Run: `env -u FORCE_COLOR uv run pytest tests/core/test_state.py tests/core/test_sync_state* -n 0 -q`
(If those exact files don't exist, run `env -u FORCE_COLOR uv run pytest tests/core -n 0 -q -k "state"`.)
Expected: all pass — the new optional field must not break existing state handling.

- [ ] **Step 6: Commit**

```bash
git add src/gpd/core/goal_contract.py src/gpd/core/state.py tests/core/test_goal_contract.py
git commit -m "feat: add typed goal contract and ResearchState.goal_contract field"
```

---

### Task 2: Budget gate and criteria evaluation logic

**Files:**
- Create: `src/gpd/core/goal_gate.py`
- Test: `tests/core/test_goal_gate.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_goal_gate.py`:

```python
"""Tests for gpd:goal budget gate and criteria evaluation decisions."""

from gpd.core.goal_contract import GoalContract
from gpd.core.goal_gate import (
    budget_gate_decision,
    evaluate_goal_criteria,
    goal_gate_summary,
)


def _contract(**overrides) -> GoalContract:
    payload = {
        "statement": "Derive and verify the dispersion relation",
        "success_criteria": [
            {"id": "GC-1", "description": "dimensional analysis passes", "check_ref": "dimensional_analysis"},
            {"id": "GC-2", "description": "long-wavelength limit verified", "check_ref": "limiting_cases"},
        ],
        "budget_usd": 5.0,
        "baseline_spent_usd": 10.0,
    }
    payload.update(overrides)
    return GoalContract.model_validate(payload)


def test_budget_gate_continues_when_spend_is_low() -> None:
    assert budget_gate_decision(_contract(), spent_usd=11.0) == "continue"


def test_budget_gate_wraps_up_near_budget() -> None:
    # baseline 10 + budget 5 => run spend 4.5/5.0 = 90% >= default 85% threshold
    assert budget_gate_decision(_contract(), spent_usd=14.5) == "wrap_up"


def test_budget_gate_stops_at_or_over_budget() -> None:
    assert budget_gate_decision(_contract(), spent_usd=15.0) == "stop"
    assert budget_gate_decision(_contract(), spent_usd=20.0) == "stop"


def test_budget_gate_ignores_spend_before_baseline() -> None:
    # Project lifetime spend below baseline means this run has spent nothing.
    assert budget_gate_decision(_contract(), spent_usd=3.0) == "continue"


def test_criteria_all_pass_means_achieved() -> None:
    result = evaluate_goal_criteria(
        _contract(),
        check_outcomes={"dimensional_analysis": "pass", "limiting_cases": "pass"},
    )
    assert result.achieved is True
    assert {c.id: c.outcome for c in result.criteria} == {"GC-1": "pass", "GC-2": "pass"}


def test_criteria_missing_outcome_is_pending_not_achieved() -> None:
    result = evaluate_goal_criteria(
        _contract(),
        check_outcomes={"dimensional_analysis": "pass"},
    )
    assert result.achieved is False
    assert {c.id: c.outcome for c in result.criteria} == {"GC-1": "pass", "GC-2": "pending"}


def test_criteria_fail_outcome_is_not_achieved() -> None:
    result = evaluate_goal_criteria(
        _contract(),
        check_outcomes={"dimensional_analysis": "fail", "limiting_cases": "pass"},
    )
    assert result.achieved is False


def test_goal_gate_summary_combines_budget_and_criteria() -> None:
    summary = goal_gate_summary(
        _contract(),
        spent_usd=11.0,
        check_outcomes={"dimensional_analysis": "pass", "limiting_cases": "pass"},
    )
    assert summary.budget_decision == "continue"
    assert summary.achieved is True
    assert summary.run_spent_usd == 1.0
    assert summary.remaining_usd == 4.0


def test_goal_gate_summary_budget_stop_wins_even_if_not_achieved() -> None:
    summary = goal_gate_summary(_contract(), spent_usd=15.2, check_outcomes={})
    assert summary.budget_decision == "stop"
    assert summary.achieved is False
    assert summary.remaining_usd == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u FORCE_COLOR uv run pytest tests/core/test_goal_gate.py -n 0 -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gpd.core.goal_gate'`

- [ ] **Step 3: Write the implementation**

Create `src/gpd/core/goal_gate.py`:

```python
"""Budget gate and goal-criteria evaluation for gpd:goal runs.

Pure decision logic: no I/O, no cost-ledger reads. Callers (the ``gpd goal``
CLI surface) supply the current project-scope spend and verification check
outcomes; these functions return decisions.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gpd.core.goal_contract import GoalContract

__all__ = [
    "DEFAULT_NEAR_BUDGET_FRACTION",
    "BudgetDecision",
    "CriterionOutcome",
    "GoalCriteriaResult",
    "GoalGateSummary",
    "budget_gate_decision",
    "evaluate_goal_criteria",
    "goal_gate_summary",
]

DEFAULT_NEAR_BUDGET_FRACTION = 0.85

BudgetDecision = Literal["continue", "wrap_up", "stop"]


class CriterionOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    check_ref: str
    outcome: Literal["pass", "fail", "pending"]


class GoalCriteriaResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    achieved: bool
    criteria: list[CriterionOutcome] = Field(default_factory=list)


class GoalGateSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    budget_decision: BudgetDecision
    achieved: bool
    budget_usd: float
    run_spent_usd: float
    remaining_usd: float
    criteria: list[CriterionOutcome] = Field(default_factory=list)


def _run_spent_usd(contract: GoalContract, spent_usd: float) -> float:
    """Spend attributable to this goal run (project spend minus baseline)."""
    return round(max(0.0, spent_usd - contract.baseline_spent_usd), 6)


def budget_gate_decision(
    contract: GoalContract,
    *,
    spent_usd: float,
    near_fraction: float = DEFAULT_NEAR_BUDGET_FRACTION,
) -> BudgetDecision:
    """Decide whether a goal run may continue, must wrap up, or must stop."""
    run_spent = _run_spent_usd(contract, spent_usd)
    if run_spent >= contract.budget_usd:
        return "stop"
    if run_spent >= contract.budget_usd * near_fraction:
        return "wrap_up"
    return "continue"


def evaluate_goal_criteria(
    contract: GoalContract,
    *,
    check_outcomes: dict[str, str],
) -> GoalCriteriaResult:
    """Map verification check outcomes onto the contract's success criteria.

    ``check_outcomes`` maps ``check_ref`` -> "pass" | "fail". Criteria whose
    check_ref is absent are "pending". The goal is achieved only when every
    criterion's outcome equals its expected value ("pass").
    """
    outcomes: list[CriterionOutcome] = []
    for criterion in contract.success_criteria:
        raw = check_outcomes.get(criterion.check_ref)
        outcome = raw if raw in ("pass", "fail") else "pending"
        outcomes.append(
            CriterionOutcome(id=criterion.id, check_ref=criterion.check_ref, outcome=outcome)
        )
    achieved = bool(outcomes) and all(c.outcome == "pass" for c in outcomes)
    return GoalCriteriaResult(achieved=achieved, criteria=outcomes)


def goal_gate_summary(
    contract: GoalContract,
    *,
    spent_usd: float,
    check_outcomes: dict[str, str],
    near_fraction: float = DEFAULT_NEAR_BUDGET_FRACTION,
) -> GoalGateSummary:
    """Combined gate verdict used by ``gpd goal gate`` and ``gpd goal status``."""
    run_spent = _run_spent_usd(contract, spent_usd)
    criteria_result = evaluate_goal_criteria(contract, check_outcomes=check_outcomes)
    return GoalGateSummary(
        budget_decision=budget_gate_decision(contract, spent_usd=spent_usd, near_fraction=near_fraction),
        achieved=criteria_result.achieved,
        budget_usd=contract.budget_usd,
        run_spent_usd=run_spent,
        remaining_usd=round(max(0.0, contract.budget_usd - run_spent), 6),
        criteria=criteria_result.criteria,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `env -u FORCE_COLOR uv run pytest tests/core/test_goal_gate.py tests/core/test_goal_contract.py -n 0 -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/gpd/core/goal_gate.py tests/core/test_goal_gate.py
git commit -m "feat: add goal budget gate and criteria evaluation logic"
```

---

### Task 3: CLI surface — `gpd goal status`, `gpd goal gate`, `gpd validate goal-contract`

**Files:**
- Modify: `src/gpd/cli.py` (new `goal_app` typer sub-app — place it near the `stage_app` block around line 4477; new `@validate_app.command("goal-contract")` near the other validators around line 8025)
- Test: `tests/core/test_cli_goal.py`

**Pattern notes for the implementer (verified against the codebase):**
- CLI command bodies use lazy imports (`from gpd.core... import ...` inside the function), `_get_cwd()` for the working directory, `_raw` + `_output(payload)` for `--raw` JSON output, and `_error(str)` for stable error envelopes. Mirror the `cost` command at `src/gpd/cli.py:4459` and the `validate_app` commands at `src/gpd/cli.py:8025+`.
- Read the goal contract via the state-load path used by other state readers (see how `cost`/`resume` resolve project state from `_get_cwd()`; `gpd.core.state` exposes the load entry — follow the import used by the `validate consistency` command). The contract payload is `state.get("goal_contract")`.
- Current project-scope spend comes from `build_cost_summary(_get_cwd(), last_sessions=0)` (`gpd.core.costs`); use the project rollup's spent-USD field (`CostProjectSummary` — confirm the exact attribute name in `costs.py` when implementing; it is the same value `gpd cost` renders as project spend).
- Check outcomes for criteria: schema_version-1 reads them from the latest phase VERIFICATION artifacts via the existing verification-status helpers (`gpd.core.verification_status`); if no verification artifacts exist yet, pass `check_outcomes={}` (criteria render as "pending").
- Before writing the tests, skim the top of `tests/core/test_cli.py` and reuse its runner/fixture pattern (it invokes the typer app via `typer.testing.CliRunner` or a helper; mirror whichever it uses).

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_cli_goal.py` (adapt the runner import/fixture to match `tests/core/test_cli.py`):

```python
"""CLI tests for gpd goal status/gate and gpd validate goal-contract."""

import json

from tests.core.test_cli import runner, invoke_cli  # reuse the existing harness helpers; adapt names to what test_cli.py actually defines


GOAL_CONTRACT = {
    "schema_version": 1,
    "statement": "Derive and verify the dispersion relation",
    "success_criteria": [
        {"id": "GC-1", "description": "dims", "check_ref": "dimensional_analysis", "expected": "pass"}
    ],
    "budget_usd": 5.0,
    "baseline_spent_usd": 0.0,
    "status": "active",
}


def test_validate_goal_contract_accepts_valid_payload(tmp_path):
    contract_file = tmp_path / "goal.json"
    contract_file.write_text(json.dumps(GOAL_CONTRACT))
    result = invoke_cli("--raw", "validate", "goal-contract", str(contract_file))
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["valid"] is True
    assert payload["issues"] == []


def test_validate_goal_contract_reports_issues(tmp_path):
    contract_file = tmp_path / "goal.json"
    contract_file.write_text(json.dumps({**GOAL_CONTRACT, "budget_usd": -1}))
    result = invoke_cli("--raw", "validate", "goal-contract", str(contract_file))
    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["valid"] is False
    assert any("budget_usd" in issue for issue in payload["issues"])


def test_goal_status_errors_cleanly_without_goal_contract(tmp_path):
    # In a directory with no GPD project / no goal contract, the command must
    # return a stable error envelope, not a traceback.
    result = invoke_cli("--raw", "--cwd", str(tmp_path), "goal", "status")
    assert result.exit_code != 0
    assert "goal" in result.stdout.lower() or "goal" in (result.stderr or "").lower()


def test_goal_gate_emits_machine_decision(tmp_path, gpd_project_with_state):
    # gpd_project_with_state: use/adapt the existing project-scaffold fixture
    # from tests/core/test_cli.py that writes GPD/state.json; seed it with
    # GOAL_CONTRACT under the "goal_contract" key.
    project_root = gpd_project_with_state(goal_contract=GOAL_CONTRACT)
    result = invoke_cli("--raw", "--cwd", str(project_root), "goal", "gate")
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["budget_decision"] in ("continue", "wrap_up", "stop")
    assert payload["achieved"] in (True, False)
    assert payload["budget_usd"] == 5.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u FORCE_COLOR uv run pytest tests/core/test_cli_goal.py -n 0 -v`
Expected: FAIL — `goal` is not a registered command ("No such command 'goal'").

- [ ] **Step 3: Implement the CLI surface**

In `src/gpd/cli.py`, after the `cost` command block (around line 4473), add:

```python
# ═══════════════════════════════════════════════════════════════════════════
# goal — Goal- and budget-directed run surface
# ═══════════════════════════════════════════════════════════════════════════

goal_app = typer.Typer(help="Goal-contract status and gate decisions for gpd:goal runs")
app.add_typer(goal_app, name="goal")


def _load_goal_contract_or_error() -> "GoalContract":
    from gpd.core.goal_contract import GoalContract, validate_goal_contract_payload
    from gpd.core.state import state_load

    loaded = state_load(_get_cwd())
    payload = (loaded.state or {}).get("goal_contract")
    if payload is None:
        _error("No goal contract found. Start one with /gpd:goal \"<statement>\" --budget-usd <amount>.")
    issues = validate_goal_contract_payload(payload)
    if issues:
        _error("Invalid goal contract: " + "; ".join(issues))
    return GoalContract.model_validate(payload)


def _goal_gate_payload() -> dict:
    from gpd.core.costs import build_cost_summary
    from gpd.core.goal_gate import goal_gate_summary
    from gpd.core.verification_status import latest_check_outcomes  # adapt: use the actual helper in verification_status.py

    contract = _load_goal_contract_or_error()
    cost_summary = build_cost_summary(_get_cwd(), last_sessions=0)
    spent_usd = cost_summary.project.spent_usd  # adapt to the real CostProjectSummary attribute
    check_outcomes = latest_check_outcomes(_get_cwd())  # adapt; {} when no verification artifacts
    summary = goal_gate_summary(contract, spent_usd=spent_usd, check_outcomes=check_outcomes)
    return summary.model_dump(mode="json")


@goal_app.command("gate")
def goal_gate() -> None:
    """Emit the machine gate decision for the active goal run (budget + criteria)."""
    payload = _goal_gate_payload()
    if _raw:
        _output(payload)
        return
    _output(payload)  # gate is primarily machine-facing; raw and human output match


@goal_app.command("status")
def goal_status() -> None:
    """Show the goal run receipt: spend vs budget, criteria, and status."""
    payload = _goal_gate_payload()
    if _raw:
        _output(payload)
        return
    _render_goal_status(payload)
```

Add `_render_goal_status` next to the other `_render_*` helpers (match the
rich rendering style used by `_render_cost_summary`):

```python
def _render_goal_status(payload: dict) -> None:
    from rich.table import Table

    percent = 0.0
    if payload["budget_usd"]:
        percent = round(payload["run_spent_usd"] / payload["budget_usd"] * 100.0, 1)
    _console.print(
        f"Budget: ${payload['run_spent_usd']:.2f} of ${payload['budget_usd']:.2f} used ({percent}%) — "
        f"decision: {payload['budget_decision']}"
    )
    table = Table("Criterion", "Check", "Outcome")
    for criterion in payload["criteria"]:
        table.add_row(criterion["id"], criterion["check_ref"], criterion["outcome"])
    _console.print(table)
    _console.print("Goal achieved." if payload["achieved"] else "Goal not yet achieved.")
```

(Adapt `_console` to however `cli.py` names its rich console.)

In the `validate_app` section (around line 8025), add:

```python
@validate_app.command("goal-contract")
def validate_goal_contract(
    file: str = typer.Argument(..., help="Path to a goal-contract JSON file, or - for stdin"),
) -> None:
    """Validate a gpd:goal goal-contract payload."""
    import json as _json
    import sys

    from gpd.core.goal_contract import validate_goal_contract_payload

    raw_text = sys.stdin.read() if file == "-" else Path(file).read_text(encoding="utf-8")
    try:
        payload = _json.loads(raw_text)
    except _json.JSONDecodeError as exc:
        _output({"valid": False, "issues": [f"goal_contract: invalid JSON ({exc})"]})
        raise typer.Exit(code=1)
    issues = validate_goal_contract_payload(payload)
    _output({"valid": not issues, "issues": issues})
    if issues:
        raise typer.Exit(code=1)
```

(Mirror exit-code and output conventions from the adjacent validators — check
how `validate consistency` signals failure and follow it exactly.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `env -u FORCE_COLOR uv run pytest tests/core/test_cli_goal.py tests/core/test_cli.py -n 0 -q`
Expected: all pass (existing CLI tests must not regress)

- [ ] **Step 5: Commit**

```bash
git add src/gpd/cli.py tests/core/test_cli_goal.py
git commit -m "feat: add gpd goal status/gate CLI and validate goal-contract"
```

---

### Task 4: Command descriptor and goal workflow

**Files:**
- Create: `src/gpd/commands/goal.md`
- Create: `src/gpd/specs/workflows/goal/goal-bootstrap.md`
- Test: existing suites (`tests/adapters/test_registry.py`, `tests/adapters/test_install_roundtrip.py`, `tests/test_metadata_consistency.py`)

- [ ] **Step 1: Write the command descriptor**

Create `src/gpd/commands/goal.md` (frontmatter mirrors `autonomous.md`; help
group mirrors the "Planning and execution" group):

```markdown
---
name: gpd:goal
description: Run toward a stated goal under a binding USD budget until achieved, budget-stopped, or blocked
argument-hint: "\"<goal statement>\" --budget-usd <amount> | --resume [--budget-usd <amount>]"
context_mode: project-required
requires:
  files: ["GPD/ROADMAP.md", "GPD/STATE.md"]
allowed-tools:
  - file_read
  - shell
  - find_files
  - search_files
  - ask_user
  - task
help:
  group: Planning and execution
  order: 205
  compact_description: Goal- and budget-directed autonomous run with verifier-gated completion
  display_signature: gpd:goal "<goal>" --budget-usd <amount>
---

<objective>
Run the project toward an explicit goal contract under a binding USD budget.
The run continues itself through the autonomous phase loop and terminates in
exactly one state: achieved (verification passed every success criterion),
budget_stopped (clean checkpoint with receipt), or blocked.
</objective>

<execution_context>
@{GPD_INSTALL_DIR}/workflows/goal/goal-bootstrap.md
</execution_context>

<context>
`--budget-usd <amount>` sets the binding budget for this run. `--resume`
re-enters a stopped goal run on the existing contract, optionally raising the
budget. Staged init resolves project context.
</context>

<process>
Follow the included first-stage authority. The goal contract may only be
marked achieved by the verification-gated criteria check — never by
self-assessment.
</process>
```

- [ ] **Step 2: Write the workflow bootstrap stage**

Create `src/gpd/specs/workflows/goal/goal-bootstrap.md`. Before writing it,
read `src/gpd/specs/workflows/autonomous/initialize-discover.md` and copy its
staged-init preamble structure exactly (the staged init block, context
resolution, and stage-handoff conventions). The goal-specific body:

```markdown
# Goal Run Bootstrap

## Stage authority

This stage owns: goal-contract creation or resume, baseline cost snapshot,
criteria confirmation, and handoff into the autonomous phase loop with goal
gates. Child stages own phase work exactly as in the autonomous workflow.

## 1. Resolve mode

- With a goal statement argument: this is a new goal run. If `state.json`
  already has a `goal_contract` with status `active`, stop and tell the user
  to `--resume` or finish that goal first (one active goal per project).
- With `--resume`: load the existing contract; if `--budget-usd` is provided,
  update `budget_usd` to the new amount; set status back to `active`.

## 2. Create the goal contract (new runs)

1. Snapshot the project-scope spend baseline:
   run `gpd --raw cost` and record the project spent-USD value as
   `baseline_spent_usd`.
2. Draft 2-5 machine-checkable success criteria from the goal statement.
   Each criterion's `check_ref` must name a verification check that
   `verify-work` can produce (for example `dimensional_analysis`,
   `limiting_cases`, `numerical_convergence`). Prefer fewer, decisive criteria.
3. Present the drafted criteria and the budget to the user for confirmation
   (this is the single upfront interaction). Apply edits.
4. Validate before writing: pipe the contract JSON through
   `gpd --raw validate goal-contract -`. Fix any issues.
5. Write the contract to `state.json` under `goal_contract` via the state
   update commands, and mirror a two-line summary into `STATE.md`.
6. Record the start event:
   `gpd observe event goal start --status ok --data '{"budget_usd": <amount>}'`.

## 3. Goal loop

Repeat until a terminal state:

1. **Budget gate.** Run `gpd --raw goal gate`.
   - `budget_decision: stop` → go to step 4 (budget stop).
   - `budget_decision: wrap_up` → do not open new phases; bring current work
     to a checkpointable state, run verification, then re-check the gate.
   - `budget_decision: continue` → proceed.
   - Record: `gpd observe event goal budget_gate --status ok --data '<gate payload>'`.
   - If `gpd --raw goal gate` itself fails because cost telemetry is
     unavailable, FAIL CLOSED: pause, surface the error to the user, and do
     not continue the run unbudgeted.
2. **Phase work.** Delegate one phase iteration to the autonomous phase loop
   (`@{GPD_INSTALL_DIR}/workflows/autonomous/phase-route.md` conventions),
   including its verification route. Goal runs never skip verification.
3. **Goal gate.** After verification completes, run `gpd --raw goal gate`.
   - `achieved: true` → set `goal_contract.status` to `achieved`, record
     `gpd observe event goal stop --status ok --data '{"terminal": "achieved"}'`,
     show the receipt (`gpd goal status`), and stop.
   - Otherwise record the criteria check event and loop to step 1.
4. **Budget stop.** Checkpoint cleanly (same checkpoint discipline as the
   autonomous workflow's stop path), set `goal_contract.status` to
   `budget_stopped`, record
   `gpd observe event goal stop --status ok --data '{"terminal": "budget_stopped"}'`,
   and show the user the receipt plus resume instructions:
   `/gpd:goal --resume --budget-usd <new amount>`.
5. **Blocked.** If the autonomous loop reports a block it cannot recover
   (per its blocked-recovery stage), set `goal_contract.status` to `blocked`,
   record the stop event with `"terminal": "blocked"`, and surface the
   blocker with the receipt.
```

- [ ] **Step 3: Regenerate generated surfaces**

Adding a command changes generated artifacts. Run each sync, then its check:

```bash
uv run python scripts/sync_repo_graph_contract.py
uv run python scripts/render_public_surface.py
uv run python scripts/render_help_surface.py
uv run python scripts/sync_repo_graph_contract.py --check
uv run python scripts/render_public_surface.py --check
uv run python scripts/render_help_surface.py --check
```

Expected: syncs may rewrite generated files (review the diff — only goal-command
additions); all three `--check` runs exit 0.

- [ ] **Step 4: Run the cross-runtime and metadata suites**

```bash
env -u FORCE_COLOR uv run pytest -n 0 tests/test_metadata_consistency.py -q
env -u FORCE_COLOR uv run pytest -n 0 tests/adapters/test_registry.py tests/adapters/test_install_roundtrip.py -q
```

Expected: all pass (command/agent counts are computed dynamically; failures
here mean a generated surface or registry contract needs the goal command
added — read the assertion message and fix forward).

- [ ] **Step 5: Commit**

```bash
git add src/gpd/commands/goal.md src/gpd/specs/workflows/goal/ <any regenerated files from step 3>
git commit -m "feat: add gpd:goal command descriptor and goal run workflow"
```

---

### Task 5: Changelog, full suite, and PR

**Files:**
- Modify: `CHANGELOG.md` (add under `## vNEXT`)

- [ ] **Step 1: Add the release note**

In `CHANGELOG.md`, under the `## vNEXT` heading (create the section at the top
if absent — match the existing entry style):

```markdown
- Added `gpd:goal`: goal- and budget-directed autonomous runs. A typed goal
  contract (statement, machine-checkable success criteria, binding USD budget)
  drives the autonomous phase loop; runs terminate as achieved (verifier-gated),
  budget_stopped (clean checkpoint + receipt), or blocked. New CLI surfaces:
  `gpd goal status`, `gpd goal gate`, `gpd validate goal-contract`.
```

- [ ] **Step 2: Run the full fast suite**

Run: `env -u FORCE_COLOR uv run pytest tests/ -q`
Expected: 0 failures (baseline on this machine: 12,941 passed, 7 skipped, ~85s)

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add vNEXT release note for gpd:goal"
```

- [ ] **Step 4: Push branch and open PR**

`main` is protected; work goes through a PR with the required `tests` workflow.

```bash
git push -u origin worktree-goal-command
gh pr create --title "feat: add gpd:goal — goal- and budget-directed autonomous runs" --body "$(cat <<'EOF'
## Summary
- New `gpd:goal "<statement>" --budget-usd X` command: runs the autonomous phase loop toward a typed goal contract under a binding USD budget
- Verifier-gated completion: only verification check outcomes can mark the goal achieved
- Budget gate built on the existing advisory cost thresholds (binding for goal runs); fail-closed when cost telemetry is unavailable
- New CLI surfaces: `gpd goal status` (receipt), `gpd goal gate` (machine decision), `gpd validate goal-contract`
- Design spec: docs/superpowers/specs/2026-06-04-goal-command-design.md

## Test plan
- [x] `tests/core/test_goal_contract.py`, `tests/core/test_goal_gate.py`, `tests/core/test_cli_goal.py`
- [x] `tests/adapters/test_registry.py`, `tests/adapters/test_install_roundtrip.py`, `tests/test_metadata_consistency.py`
- [x] Full suite `uv run pytest tests/ -q`
- [x] Generated-surface checks (`sync_repo_graph_contract.py --check`, `render_public_surface.py --check`, `render_help_surface.py --check`)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review notes

- **Spec coverage:** user surface (Tasks 3-4), goal contract + typed validator (Tasks 1, 3), budget gate binding semantics + wrap-up mode (Tasks 2, 4), verifier-gated achievement (Tasks 2, 4 step 3.3), receipt (Task 3 `goal status`), observability events (Task 4 workflow, via existing `gpd observe event` CLI — no new Python), fail-closed cost-telemetry handling (Task 4 workflow step 3.1), resume (Task 4 workflow step 1), scope cuts respected (no new agents, no queueing, USD only).
- **Known adaptation points (flagged inline, not placeholders):** the exact `CostProjectSummary` spent-USD attribute name, the `tests/core/test_cli.py` harness helper names, the `verification_status` helper for latest check outcomes, and the rich console name in `cli.py`. Each is a one-line lookup in the named file at implementation time; the surrounding code is complete.
- **Type consistency:** `GoalContract`/`GoalCriterion` defined in Task 1 are the types consumed in Tasks 2-3; gate decision literals (`continue|wrap_up|stop`) and status literals (`active|achieved|budget_stopped|blocked`) are identical across tasks and match the spec.
