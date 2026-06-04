"""Focused assertions for the verify-work checker routing seam."""

from pathlib import Path

from tests.assertion_taxonomy_support import assert_prompt_contracts, machine_exact
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY_WORK = REPO_ROOT / "src" / "gpd" / "specs" / "workflows" / "verify-work.md"


def test_verify_work_routes_on_structured_checker_statuses() -> None:
    workflow = workflow_authority_text(VERIFY_WORK.parent, "verify-work")

    assert "route on `gpd_return.status` and the structured plan lists" in workflow
    assert_prompt_contracts(
        workflow,
        machine_exact(
            "verify-work checker status routing contract",
            (
                "- `completed`: accept only after fresh on-disk plans still match planner `files_written`.",
                "- `checkpoint`: some plans are approved and others need revision; record `approved_plans` and `blocked_plans`",
                "- `blocked`: nothing is approved; feed the checker issues and blocked plan IDs back into the revision loop without rewriting approved plans.",
                "- `failed`: present the issues and offer retry or manual revision.",
            ),
        ),
    )


def test_verify_work_references_one_shot_checker_contract_in_the_gap_closure_loop() -> None:
    workflow = workflow_authority_text(VERIFY_WORK.parent, "verify-work")

    assert 'id: "verify_work_gap_plan_checker"' in workflow
    assert "shared gate and continuation rules live in `references/orchestration/child-artifact-gate.md`" in workflow
    assert_prompt_contracts(
        workflow,
        machine_exact(
            "verify-work gap plan checker structured route fields",
            "route from structured `approved_plans`, `blocked_plans`, and `issues`",
        ),
    )
    assert "not on presentation text" in workflow
