"""Focused assertions for contract-schema visibility in executor summary creation."""

from __future__ import annotations

from pathlib import Path

from tests.assertion_taxonomy_support import assert_prompt_contracts, machine_exact, semantic_concept

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "src/gpd/agents"
EXECUTION_REFERENCE_DIR = REPO_ROOT / "src/gpd/specs/references/execution"


def _read_executor_prompt() -> str:
    return (AGENTS_DIR / "gpd-executor.md").read_text(encoding="utf-8")


def _read_executor_completion_reference() -> str:
    return (EXECUTION_REFERENCE_DIR / "executor-completion.md").read_text(encoding="utf-8")


def _read_executor_worked_example() -> str:
    return (EXECUTION_REFERENCE_DIR / "executor-worked-example.md").read_text(encoding="utf-8")


def _between(text: str, start: str, end: str) -> str:
    _, start_marker, tail = text.partition(start)
    assert start_marker, f"Missing marker: {start}"
    body, end_marker, _ = tail.partition(end)
    assert end_marker, f"Missing marker: {end}"
    return body


def _assert_contract_schema_tokens_visible(text: str) -> None:
    for token in ("plan_contract_ref", "contract_results", "comparison_verdicts"):
        assert token in text, f"Missing contract-results authority token: {token}"


def test_executor_summary_creation_requires_loading_contract_schema_before_frontmatter() -> None:
    executor = _read_executor_prompt()
    summary_creation = _between(executor, "<summary_creation>", "</summary_creation>")
    completion = _read_executor_completion_reference()

    assert "executor-completion.md" in summary_creation
    assert "@{GPD_INSTALL_DIR}/templates/contract-results-schema.md" not in summary_creation
    assert "@{GPD_INSTALL_DIR}/templates/summary.md" not in summary_creation
    assert "templates/contract-results-schema.md" in summary_creation
    assert "templates/summary.md" in summary_creation
    assert_prompt_contracts(
        summary_creation,
        *semantic_concept(
            "executor summary creation follows canonical ledger fields",
            required=("follow the canonical ledger fields literally",),
        ),
    )
    assert "detailed SUMMARY schema" in summary_creation
    _assert_contract_schema_tokens_visible(completion)
    assert "gpd validate summary-contract" in completion


def test_executor_completion_reference_exposes_required_summary_depth_and_completion_fields() -> None:
    completion = _read_executor_completion_reference()

    assert "**Frontmatter:** phase, plan, depth, physics-area" in completion
    assert "metrics (duration, completed date)" in completion
    assert "plan_contract_ref: \"GPD/phases/XX-name/{phase}-{plan}-PLAN.md#/contract\"" in completion


def test_executor_completion_reference_keeps_summary_contract_authority_and_validator_visible() -> None:
    executor = _read_executor_prompt()
    completion = _read_executor_completion_reference()

    _assert_contract_schema_tokens_visible(completion)
    assert "templates/contract-results-schema.md" in executor
    assert "executor-completion.md" in executor
    assert "gpd validate summary-contract" in completion


def test_executor_reference_examples_keep_uncertainty_markers_explicit_and_non_empty() -> None:
    for text in (_read_executor_completion_reference(), _read_executor_worked_example()):
        assert "uncertainty_markers:" in text
        assert "weakest_anchors: []" not in text
        assert "unvalidated_assumptions: []" not in text
        assert "competing_explanations: []" not in text
        assert "disconfirming_observations: []" not in text
        assert_prompt_contracts(
            text,
            machine_exact(
                "executor uncertainty marker examples stay non-empty",
                (
                    'weakest_anchors: ["finite-term mass matching"]',
                    'unvalidated_assumptions: ["general-gauge-independence"]',
                    'competing_explanations: ["on-shell vs MS-bar finite-part conventions"]',
                    'disconfirming_observations: ["no independent gauge-parameter scan"]',
                ),
            ),
        )
        assert 'unvalidated_assumptions: ["general-gauge-independence"]' in text
