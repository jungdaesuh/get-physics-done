from __future__ import annotations

from pathlib import Path

from tests.lifecycle_contract_test_support import (
    assert_forbidden_contract as _assert_forbidden,
)
from tests.lifecycle_contract_test_support import (
    assert_machine_contract as _assert_machine,
)
from tests.lifecycle_contract_test_support import (
    assert_semantic_contract as _assert_semantic,
)
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"
EXECUTION_REFERENCES_DIR = REPO_ROOT / "src/gpd/specs/references/execution"


def test_execute_plan_routes_checkpoints_through_orchestrator_owned_returns() -> None:
    execute_plan = (WORKFLOWS_DIR / "execute-plan.md").read_text(encoding="utf-8")
    checkpoints = (EXECUTION_REFERENCES_DIR / "execute-plan-checkpoints.md").read_text(encoding="utf-8")

    _assert_forbidden(execute_plan, "execute-plan no in-child user wait", "wait for user", "wait for approval")
    _assert_semantic(
        execute_plan,
        "execute-plan checkpoint returns flow through orchestrator",
        "Emit the checkpoint return with the task result and all intermediate values",
        "return structured checkpoint state to the orchestrator",
    )
    _assert_semantic(
        checkpoints,
        "execute-plan checkpoint reference keeps child wait boundary",
        "Awaiting (what the orchestrator must resolve before continuation)",
        "the child never waits for user approval inside the same run",
    )


def test_execute_plan_clean_wave_batching_uses_typed_verification_outcome() -> None:
    execute_plan = (WORKFLOWS_DIR / "execute-plan.md").read_text(encoding="utf-8")

    _assert_machine(
        execute_plan,
        "execute-plan batching typed verification fields",
        'verification.status="passed"',
        "verification.issue_count=0",
    )
    _assert_semantic(
        execute_plan,
        "execute-plan batching avoids prose-gated eligibility",
        'Do not parse prose such as "failure language" to decide batching eligibility.',
        "omits the typed verification outcome",
    )
    _assert_forbidden(
        execute_plan,
        "execute-plan stale failure-language batching gate",
        "verification-complete` without failure language",
    )


def test_execute_phase_requires_on_disk_artifacts_before_accepting_success() -> None:
    execute_phase = workflow_authority_text(WORKFLOWS_DIR, "execute-phase")

    _assert_semantic(
        execute_phase,
        "execute-phase on-disk artifact gate before success",
        "If the SUMMARY marks any `key-files.created` / `key-files.modified` paths as required or "
        "final-deliverable, verify those paths on disk before accepting success",
        "Verify first 2 files from `key-files.created` exist on disk",
    )


def test_executor_handoff_recovery_treats_commits_as_partial_evidence_only() -> None:
    quick = workflow_authority_text(WORKFLOWS_DIR, "quick")
    execute_plan = (WORKFLOWS_DIR / "execute-plan.md").read_text(encoding="utf-8")
    execute_phase = workflow_authority_text(WORKFLOWS_DIR, "execute-phase")

    for source in (quick, execute_plan, execute_phase):
        _assert_machine(source, "executor handoff recovery command", "gpd apply-return-updates")
        _assert_semantic(source, "executor handoff partial evidence gate", "partial evidence", "valid")

    _assert_semantic(quick, "quick handoff commit evidence boundary", "Commits or files do not prove success")
    _assert_semantic(
        execute_plan,
        "execute-plan handoff commit evidence boundary",
        "Commits or output files do not prove success",
        "If the return envelope is missing or invalid, keep the child handoff incomplete",
        "git commits are partial evidence only",
    )
    _assert_semantic(
        execute_phase,
        "execute-phase handoff artifact gate",
        "Run the local child artifact gate before success",
        "git commits are partial evidence only",
    )


def test_execute_plan_recovery_records_commits_as_partial_evidence_until_return_gate_passes() -> None:
    recovery = (EXECUTION_REFERENCES_DIR / "execute-plan-recovery.md").read_text(encoding="utf-8")

    _assert_machine(
        recovery,
        "execute-plan recovery typed return commands",
        "required `gpd_return` envelope validates",
        "required `gpd apply-return-updates` pass has succeeded",
    )
    _assert_semantic(
        recovery,
        "execute-plan recovery partial evidence classification",
        "commits after the checkpoint are partial evidence",
        "Classify completion only after expected artifacts exist",
        "Partial Evidence (not yet success)",
        "require retry or explicit main-context fallback",
    )


def test_execute_phase_fails_closed_on_reverification_and_notation_handoffs() -> None:
    execute_phase = workflow_authority_text(WORKFLOWS_DIR, "execute-phase")

    _assert_machine(
        execute_phase,
        "execute-phase notation handoff commands",
        "The next step is `gpd:validate-conventions`",
        "fresh `gpd:execute-phase {PHASE_NUMBER}` continuation after that workflow reports a typed result",
    )
    _assert_semantic(
        execute_phase,
        "execute-phase reverification and notation handoff boundary",
        "keeps gap-closure state intact",
        "Convention repair is intentionally out-of-line here.",
    )
