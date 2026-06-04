"""Prompt-budget assertions for the `verify-work` startup surface."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from gpd.core.prompt_diagnostics import build_prompt_surface_report, report_to_dict
from tests.assertion_taxonomy_support import assert_prompt_contracts, semantic_concept
from tests.prompt_metrics_support import measure_prompt_surface
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = REPO_ROOT / "src" / "gpd" / "commands"
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
SOURCE_ROOT = REPO_ROOT / "src" / "gpd"
PATH_PREFIX = "/runtime/"
VERIFY_WORK_STAGE_EAGER_CHAR_BUDGETS = {
    "interactive_validation": 12_000,
    "gap_repair": 20_000,
}


@lru_cache
def _verify_work_stage_diagnostics() -> dict[str, object]:
    payload = report_to_dict(
        build_prompt_surface_report(
            REPO_ROOT,
            surfaces=("command",),
            include_tests=False,
            include_runtime_projections=False,
        )
    )
    workflows = payload["stage_diagnostics"]
    assert isinstance(workflows, list)
    for workflow in workflows:
        assert isinstance(workflow, dict)
        if workflow.get("workflow_id") == "verify-work":
            return workflow
    raise AssertionError("verify-work staged diagnostics were not reported")


def test_verify_work_command_only_eagerly_loads_the_workflow() -> None:
    command_text = (COMMANDS_DIR / "verify-work.md").read_text(encoding="utf-8")
    metrics = measure_prompt_surface(
        COMMANDS_DIR / "verify-work.md",
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )

    assert metrics.raw_include_count == 1
    assert "@{GPD_INSTALL_DIR}/references/verification/core/verification-core.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/templates/verification-report.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/templates/contract-results-schema.md" not in command_text


def test_verify_work_workflow_defers_heavy_authorities_until_later_steps() -> None:
    root_index = (WORKFLOWS_DIR / "verify-work.md").read_text(encoding="utf-8")
    workflow_text = workflow_authority_text(WORKFLOWS_DIR, "verify-work")
    overlay_marker = "Update the session overlay only. The canonical verifier verdict remains verifier-owned."
    report_owner_marker = "Keep the current check display, summary, and session overlay in sync with the verifier output. The canonical verifier report content remains owned by `gpd-verifier`."

    assert "<template>" not in root_index
    assert "<required_reading>" not in root_index
    assert "research-verification.md" not in root_index
    assert "verification-report.md" not in root_index
    assert "contract-results-schema.md" not in root_index
    assert "error-propagation-protocol.md" not in root_index
    assert report_owner_marker in workflow_text
    assert overlay_marker in workflow_text


def test_verify_work_interactive_and_gap_stages_keep_schema_packs_conditional() -> None:
    workflow = _verify_work_stage_diagnostics()
    assert workflow["violation_count"] == 0

    stages = workflow["stages"]
    assert isinstance(stages, list)
    stage_by_id = {stage["stage_id"]: stage for stage in stages if isinstance(stage, dict)}

    for stage_id, budget in VERIFY_WORK_STAGE_EAGER_CHAR_BUDGETS.items():
        observed = stage_by_id[stage_id]["eager_char_count"]
        assert isinstance(observed, int)
        assert observed < budget, f"{stage_id} eager chars exceeded deferral cap: observed={observed} max<{budget}"


def test_verify_work_gap_repair_keeps_reference_bodies_deferred_to_targeted_reads() -> None:
    workflow_text = workflow_authority_text(WORKFLOWS_DIR, "verify-work")

    assert_prompt_contracts(
        workflow_text,
        *semantic_concept(
            "verify-work gap repair defers reference bodies to targeted reads",
            required=(
                "reference artifact handles, not embedded bodies",
                "read or quote a listed artifact file only when a diagnosed gap cites that exact artifact",
                "Do not require rendered `protocol_bundle_context`",
            ),
        ),
    )
