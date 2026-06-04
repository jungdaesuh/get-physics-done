"""Prompt budget assertions for the `gpd-plan-checker` surface."""

from __future__ import annotations

from pathlib import Path

from tests.prompt_metrics_support import measure_prompt_surface

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPO_ROOT / "src" / "gpd"
PATH_PREFIX = "/runtime/"
PLAN_CHECKER = REPO_ROOT / "src" / "gpd" / "agents" / "gpd-plan-checker.md"
PLAN_CHECKER_REFS = REPO_ROOT / "src" / "gpd" / "specs" / "references" / "verification" / "plan-checker"


def _read_plan_checker() -> str:
    return PLAN_CHECKER.read_text(encoding="utf-8")


def test_plan_checker_prompt_stays_thin_while_preserving_direct_schema_visibility() -> None:
    metrics = measure_prompt_surface(
        PLAN_CHECKER,
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )

    assert metrics.raw_include_count == 0
    assert len(_read_plan_checker().splitlines()) < 900
    assert len(_read_plan_checker()) < 20_500
    assert metrics.expanded_char_count < 45_000
    assert metrics.expanded_line_count < 900


def test_plan_checker_return_surface_uses_checker_profile_and_read_only_policy() -> None:
    source = _read_plan_checker()
    process = source.split("## Step 5: Decide Machine Status", 1)[1].split("</verification_process>", 1)[0]
    returns = source.split("<structured_returns>", 1)[1].split("</structured_returns>", 1)[0]

    assert "gpd return skeleton --role checker --status <status>" in process
    assert "gpd --raw return profiles" in process
    assert "do not restate the shared status table" in process
    assert "shared_state_policy: return_only" in returns
    assert "files_written: []" in returns
    assert (
        "Partial approval is allowed only when every approved plan's full dependency chain is also approved." in returns
    )
    assert "Any D0 contract-gate failure is not approvable and blocks dependents." in returns


def test_plan_checker_points_to_jit_references_without_inlining_full_catalogs() -> None:
    source = _read_plan_checker()
    dimensions_ref = (PLAN_CHECKER_REFS / "checker-dimensions.md").read_text(encoding="utf-8")
    depth_ref = (PLAN_CHECKER_REFS / "checker-depth-profiles.md").read_text(encoding="utf-8")
    returns_ref = (PLAN_CHECKER_REFS / "checker-return-protocol.md").read_text(encoding="utf-8")

    assert "{GPD_INSTALL_DIR}/references/verification/plan-checker/checker-dimensions.md" in source
    assert "{GPD_INSTALL_DIR}/references/verification/plan-checker/checker-depth-profiles.md" in source
    assert "{GPD_INSTALL_DIR}/references/verification/plan-checker/checker-return-protocol.md" in source
    assert "Exact diagonalization planned for Hilbert space dimension > 10^6" not in source
    assert "Exact diagonalization planned for Hilbert space dimension > 10^6" in dimensions_ref
    assert "| **yolo** | **Maximum scrutiny.**" not in source
    assert "| **yolo** | **Maximum scrutiny.**" in depth_ref
    assert "## PARTIAL APPROVAL" not in source
    assert "## PARTIAL APPROVAL" in returns_ref


def test_plan_checker_collapses_duplicate_dimension_steps_but_keeps_all_dimensions() -> None:
    source = _read_plan_checker()

    for dimension in range(17):
        assert f"## Dimension {dimension}:" in source

    assert "## Step 4: Run Verification Dimensions" in source
    assert "Do not repeat their checklists here" in source
    assert "Dimensions 0-16 are evaluated using the dimension sections and Step 4 matrix" in source

    for removed_step in (
        "## Step 4: Check Research Question Coverage",
        "## Step 5: Validate Task Structure",
        "## Step 6: Check Mathematical Prerequisites",
        "## Step 7: Verify Approximation Validity",
        "## Step 8: Assess Computational Feasibility",
        "## Step 9: Verify Validation Strategy",
        "## Step 10: Check Result Wiring",
        "## Step 11: Verify Dependency Graph",
        "## Step 12: Assess Scope",
        "## Step 13: Verify Contract Coverage And Artifact Derivation",
        "## Step 14: Check Literature Awareness",
        "## Step 15: Assess Path to Publication",
        "## Step 16: Identify Failure Modes",
        "## Step 16.5: Validate Computational Environment",
    ):
        assert removed_step not in source

    assert (
        "When a phase has multiple plans, some may pass while others have blockers. Rather than blocking the entire phase, use partial approval to let passing plans proceed."
        in (PLAN_CHECKER_REFS / "checker-return-protocol.md").read_text(encoding="utf-8")
    )
