"""Regression checks for compact analysis workflow authority references."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"
REFERENCES_DIR = REPO_ROOT / "src/gpd/specs/references"


def _workflow(name: str) -> str:
    return (WORKFLOWS_DIR / f"{name}.md").read_text(encoding="utf-8")


def _assert_all_present(text: str, fragments: tuple[str, ...]) -> None:
    missing = [fragment for fragment in fragments if fragment not in text]
    assert missing == []


def test_medium_analysis_workflows_defer_detailed_recipes_to_analysis_reference() -> None:
    reference = REFERENCES_DIR / "analysis" / "physics-validation-recipes.md"
    reference_text = reference.read_text(encoding="utf-8")

    _assert_all_present(
        reference_text,
        (
            "Shared Validation Floor",
            "Derivation Checks",
            "Numerical Convergence Checks",
            "Parameter Sweep Checks",
            "Sensitivity Checks",
            "Limiting-Case Checks",
        ),
    )

    for workflow_name in (
        "derive-equation",
        "parameter-sweep",
        "numerical-convergence",
        "sensitivity-analysis",
        "limiting-cases",
    ):
        workflow_text = _workflow(workflow_name)
        _assert_all_present(workflow_text, ("references/analysis/physics-validation-recipes.md",))


def test_analysis_workflows_reference_canonical_child_status_and_continuation_authorities() -> None:
    parameter_sweep = _workflow("parameter-sweep")
    numerical_convergence = _workflow("numerical-convergence")

    _assert_all_present(
        parameter_sweep,
        (
            "references/orchestration/child-artifact-gate.md",
            "references/orchestration/continuation-boundary.md",
        ),
    )
    _assert_all_present(numerical_convergence, ("references/verification/verification-status-authority.md",))


def test_settings_and_discuss_phase_keep_late_read_boundaries_visible() -> None:
    settings = _workflow("settings")
    discuss_phase = _workflow("discuss-phase")

    _assert_all_present(
        settings,
        (
            "@{GPD_INSTALL_DIR}/references/shared/interactive-choice-fallback.md",
            "references/tooling/runtime-config-guide.md",
        ),
    )
    _assert_all_present(discuss_phase, ("templates/context.md` only now",))
