"""Execute-phase verification finalizer bridge wiring tests."""

from __future__ import annotations

from pathlib import Path

from gpd.core.context import init_execute_phase
from gpd.core.workflow_staging import load_workflow_stage_manifest
from tests.lifecycle_contract_test_support import child_gate_from_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"
EXECUTE_PHASE_STAGE_DIR = WORKFLOWS_DIR / "execute-phase"


def _read_execute_phase_stage(name: str) -> str:
    return (EXECUTE_PHASE_STAGE_DIR / name).read_text(encoding="utf-8")


def _verification_bridge_stage_id() -> str:
    manifest = load_workflow_stage_manifest("execute-phase")
    return "verification_handoff" if "verification_handoff" in manifest.stage_ids() else "aggregate_and_verify"


def _write_phase(root: Path) -> None:
    phase_dir = root / "GPD" / "phases" / "01-demo"
    phase_dir.mkdir(parents=True)
    (phase_dir / "01-PLAN.md").write_text(
        "---\nwave: 1\ndepends_on: []\nfiles_modified: []\n---\n\n## Task 1\n",
        encoding="utf-8",
    )


def test_execute_phase_aggregate_stage_contains_verification_report_bridges(tmp_path: Path) -> None:
    _write_phase(tmp_path)

    payload = init_execute_phase(tmp_path, "1", stage=_verification_bridge_stage_id())

    assert "verification_report_skeleton_bridge" in payload
    assert "verification_report_finalizer_bridge" in payload
    assert payload["verification_report_skeleton_bridge"]["command_name"] == "gpd verification-report skeleton"
    assert payload["verification_report_finalizer_bridge"]["command_name"] == "gpd verification-report finalize"
    assert payload["verification_report_finalizer_bridge"]["expected_verification_path"].endswith(
        "GPD/phases/01-demo/01-VERIFICATION.md"
    )


def test_execute_phase_manifest_scopes_bridges_to_aggregate_stage() -> None:
    manifest = load_workflow_stage_manifest("execute-phase")
    bridge_stage_id = _verification_bridge_stage_id()

    assert "verification_report_skeleton_bridge" in manifest.stage(bridge_stage_id).required_init_fields
    assert "verification_report_finalizer_bridge" in manifest.stage(bridge_stage_id).required_init_fields
    assert "verification_report_skeleton_bridge" not in manifest.stage("phase_bootstrap").required_init_fields
    assert "verification_report_finalizer_bridge" not in manifest.stage("phase_bootstrap").required_init_fields
    if bridge_stage_id == "verification_handoff":
        assert "verification_report_skeleton_bridge" not in manifest.stage("aggregate_and_verify").required_init_fields
        assert "verification_report_finalizer_bridge" not in manifest.stage("aggregate_and_verify").required_init_fields


def test_execute_phase_workflow_routes_report_construction_through_finalizer_bridge() -> None:
    workflow = _read_execute_phase_stage("verification-handoff.md")
    gate = child_gate_from_text(workflow, "post_execution_verifier")

    assert "verification_report_finalizer_bridge" in workflow
    assert "verification_report_skeleton_bridge" in workflow
    assert "Do not hand-author frontmatter." in workflow
    assert "verification-report skeleton/finalizer bridge" in workflow
    assert "gpd validate verification-contract {phase_dir}/{phase_number}-VERIFICATION.md" in gate.validators
    assert workflow.index("verification_report_finalizer_bridge") < workflow.index("<step name=\"verifier_child_gate\">")


def test_execute_phase_verification_handoff_keeps_verify_phase_child_readable() -> None:
    workflow = _read_execute_phase_stage("verification-handoff.md")

    assert "{GPD_INSTALL_DIR}/workflows/verify-phase.md" in workflow
    assert "child-readable" in workflow
    assert "Do not eagerly load or restate the full verifier workflow" in workflow
    assert "workflows/verify-phase.md\"]," not in workflow


def test_execute_phase_verification_handoff_routes_on_canonical_status() -> None:
    workflow = _read_execute_phase_stage("verification-handoff.md")
    gate = child_gate_from_text(workflow, "post_execution_verifier")

    assert 'id: "post_execution_verifier"' in workflow
    assert "verification-status-authority.md status rules" in gate.validators
    assert "canonical verification_status: passed | gaps_found | expert_needed | human_needed" in workflow
    assert "| `passed` | Continue to `consistency_check`; do not close the phase yet. |" in workflow
    assert "| `gaps_found` | Continue to `gap_reverification` or stop with the gap route below. |" in workflow
    assert "not headings, marker strings, `session_status`, or prose" in workflow
