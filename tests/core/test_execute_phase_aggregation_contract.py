"""Focused aggregation-boundary assertions for the staged `execute-phase` workflow."""

from __future__ import annotations

from pathlib import Path

from tests.assertion_taxonomy_support import assert_prompt_contracts, machine_exact, semantic_anchor

REPO_ROOT = Path(__file__).resolve().parents[2]
AGGREGATE_WORKFLOW = REPO_ROOT / "src" / "gpd" / "specs" / "workflows" / "execute-phase" / "aggregate-and-verify.md"


def _aggregate_text() -> str:
    return AGGREGATE_WORKFLOW.read_text(encoding="utf-8")


def test_aggregate_stage_boundary_is_result_aggregation_only() -> None:
    workflow = _aggregate_text()

    assert_prompt_contracts(
        workflow,
        semantic_anchor(
            "aggregate stage owns result aggregation only",
            (
                "This stage owns result aggregation only",
                "summary context budgeting",
                "one-line summary extraction",
                "phase execution summary",
                "figure inventory detection",
                "experimental/observational comparison detection",
                "recovery-report routing for failures, skips, or rollbacks",
                "does not spawn verifiers or consistency checkers",
            ),
        ),
    )


def test_aggregate_stage_does_not_own_verification_gap_or_consistency_routing() -> None:
    workflow = _aggregate_text()

    forbidden_fragments = (
        'subagent_type="gpd-verifier"',
        'subagent_type="gpd-debugger"',
        'subagent_type="gpd-consistency-checker"',
        "VERIFIER_HANDOFF_STARTED_AT",
        "REVERIFY_HANDOFF_STARTED_AT",
        "CONSISTENCY_HANDOFF_STARTED_AT",
        "child_gate:",
        "verification_report_skeleton_bridge",
        "verification_report_finalizer_bridge",
        "gpd validate verification-contract",
        "gpd validate handoff-artifacts",
        "verification_status (`passed | gaps_found | expert_needed | human_needed`)",
        "Gap closure cycle:",
        "Maximum 2 verification-gap closure cycles",
    )
    for fragment in forbidden_fragments:
        assert fragment not in workflow


def test_aggregate_stage_preserves_false_success_protection() -> None:
    workflow = _aggregate_text()

    assert_prompt_contracts(
        workflow,
        semantic_anchor(
            "aggregate false-success protection",
            (
                "A stale summary, a failed spot-check, a failed child gate, or a missing required artifact is not evidence of success.",
                "Only aggregate a plan as successful after its current summary, child gate outcome, required artifacts, and spot-check record agree.",
            ),
        ),
        machine_exact("aggregate stale outcome literals", ("`missing`", "`stale`", "`malformed`", "`unsurfaced`")),
    )


def test_figure_comparison_and_recovery_templates_are_conditional_paths() -> None:
    workflow = _aggregate_text()

    assert_prompt_contracts(
        workflow,
        semantic_anchor(
            "aggregate conditional template routing",
            (
                "If figures exist, route to the figure inventory template path",
                "If no figures exist, do not load the template",
                "If such a comparison exists, route to `{GPD_INSTALL_DIR}/templates/paper/experimental-comparison.md`",
                "If no comparison exists, do not load the template",
                "If any recovery condition exists, route to `{GPD_INSTALL_DIR}/templates/recovery-plan.md`",
                "If there are no failures, skips, rollbacks, stale summaries, failed spot-checks, failed child gates, or missing required artifacts, do not load the recovery template",
            ),
        ),
        machine_exact(
            "aggregate conditional template paths",
            (
                "{GPD_INSTALL_DIR}/templates/paper/figure-tracker.md",
                "{GPD_INSTALL_DIR}/templates/paper/experimental-comparison.md",
                "{GPD_INSTALL_DIR}/templates/recovery-plan.md",
            ),
        ),
    )
