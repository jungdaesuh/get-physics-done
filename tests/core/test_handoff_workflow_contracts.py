"""Focused assertions for handoff contract unification."""

from __future__ import annotations

from pathlib import Path

from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = REPO_ROOT / "src/gpd/specs/templates"
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_planner_template_routes_on_typed_gpd_return_status_not_heading_markers() -> None:
    prompt = _read(TEMPLATES_DIR / "planner-subagent-prompt.md")

    assert (
        "The markdown headings `## PLANNING COMPLETE`, `## CHECKPOINT REACHED`, and `## PLANNING INCONCLUSIVE` are human-readable labels only."
        in prompt
    )
    assert "Do not route on them; route on `gpd_return.status` and the artifact gate below." in prompt
    assert "gpd_return.status: completed" in prompt
    assert "gpd_return.status: checkpoint" in prompt
    assert "gpd_return.status: blocked" in prompt
    assert "gpd_return.status: failed" in prompt
    assert "gpd_return.files_written" in prompt


def test_plan_phase_uses_structured_status_and_artifact_gating_for_research_and_planner_returns() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "plan-phase.md")
    checker_routing = _read(WORKFLOWS_DIR / "plan-phase" / "checker-return-routing.md")

    assert 'REQUIREMENTS=$(echo "$INIT" | gpd json get .requirements_content --default "")' in workflow
    assert 'grep -A100 "## Requirements"' not in workflow
    assert "gpd_return.status: completed" in workflow
    assert "gpd_return.status: checkpoint" in workflow
    assert "gpd_return.status: failed" in checker_routing
    assert "gpd_return.files_written" in workflow
    assert "Checker presentation headings are non-authority" in checker_routing


def test_research_phase_routes_on_typed_status_and_expected_artifacts() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "research-phase")

    assert "Child artifact gate: apply `references/orchestration/child-artifact-gate.md`" in workflow
    assert "role=`gpd-phase-researcher`" in workflow
    assert "expected=`{phase_dir}/{phase_number}-RESEARCH.md`" in workflow
    assert "references/orchestration/continuation-boundary.md" in workflow
    assert "gpd_return.status: completed" in workflow
    assert "gpd_return.status: checkpoint" in workflow
    assert "gpd_return.status: blocked` or `failed" in workflow
    assert "gpd_return.files_written" in workflow
    assert "If the artifact is missing, unreadable, or absent from `gpd_return.files_written`" in workflow


def test_map_research_routes_on_typed_status_and_expected_artifacts() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "map-research")

    assert "Mapper handoff gate: each mapper is one-shot and file-producing." in workflow
    assert "Route on" in workflow
    assert "`gpd_return.files_written` against expected" in workflow
    assert "artifacts before accepting the run" in workflow
    assert workflow.count("<spawn_contract>") >= 4
    assert "shared_state_policy: return_only" in workflow
    assert "gpd_return.status: completed" in workflow
    assert "gpd_return.files_written" in workflow
    assert "gpd --raw config get research_mode" not in workflow
    assert 'RESEARCH_MODE=$(echo "$BOOTSTRAP_INIT" | gpd json get .research_mode --default balanced)' in workflow


def test_verify_work_uses_status_payload_session_lookup_and_canonical_verification_status() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "verify-work")

    assert 'gpd frontmatter get "$file" --field session_status' not in workflow
    assert "Read `active_verification_sessions` from `SESSION_ROUTER_INIT`." in workflow
    assert "Active sessions are payload entries with `session_status` of `validating` or `diagnosed`." in workflow
    assert "Route only on canonical verification frontmatter plus `gpd_return.status`" in workflow
    assert "gpd_return.status" in workflow
    assert (
        "rg -l '^session_status: (validating|diagnosed)$' GPD/phases/*/*-VERIFICATION.md 2>/dev/null | sort | head-5"
        not in workflow
    )
