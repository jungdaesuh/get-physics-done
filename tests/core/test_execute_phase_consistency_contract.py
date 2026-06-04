"""Focused assertions for the execute-phase consistency-check seam."""

from __future__ import annotations

from pathlib import Path

from tests.assertion_taxonomy_support import (
    FragmentMode,
    MatchMode,
    assert_prompt_contracts,
    machine_exact,
    semantic_anchor,
)
from tests.lifecycle_contract_test_support import artifact_paths, child_gate_from_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
EXECUTE_PHASE_STAGE_DIR = WORKFLOWS_DIR / "execute-phase"


def _read(name: str) -> str:
    return (WORKFLOWS_DIR / name).read_text(encoding="utf-8")


def _read_execute_phase_stage(name: str) -> str:
    return (EXECUTE_PHASE_STAGE_DIR / name).read_text(encoding="utf-8")


def _m(text: str, label: str, *fragments: str) -> None:
    assert_prompt_contracts(text, machine_exact(label, fragments, context=label))


def _f(text: str, label: str, *fragments: str) -> None:
    assert_prompt_contracts(text, machine_exact(label, fragments, mode=FragmentMode.ABSENT, context=label))


def _s(text: str, label: str, *fragments: str) -> None:
    assert_prompt_contracts(text, semantic_anchor(label, fragments, match=MatchMode.CASEFOLD_NORMALIZED, context=label))


def test_execute_phase_consistency_check_uses_typed_return_and_file_gate() -> None:
    workflow = _read_execute_phase_stage("consistency-check.md")
    gate = child_gate_from_text(workflow, "rapid_consistency_check")

    _m(
        workflow,
        "consistency checker typed return and file gate",
        "gpd-consistency-checker.md",
        "<spawn_contract>",
        "expected_artifacts:",
        "{phase_dir}/CONSISTENCY-CHECK.md",
        '<step name="checker_return_status_route">',
        '<step name="consistency_child_gate">',
        "CONSISTENCY_HANDOFF_STARTED_AT=",
        'profile: "execute.consistency_report.v1"',
        'allowed_root: "{phase_dir}"',
        'freshness_marker: "$CONSISTENCY_HANDOFF_STARTED_AT"',
    )
    assert gate.role == "gpd-consistency-checker"
    assert gate.return_profile == "checker"
    assert gate.required_status == "completed"
    assert artifact_paths(gate) == ("{phase_dir}/CONSISTENCY-CHECK.md",)
    assert gate.allowed_roots == ("{phase_dir}",)
    assert gate.freshness is not None
    assert gate.freshness.marker == "$CONSISTENCY_HANDOFF_STARTED_AT"
    assert any("--require-files-written" in validator for validator in gate.validators)
    assert any("--require-status completed" in validator for validator in gate.validators)
    assert any('--fresh-after "$CONSISTENCY_HANDOFF_STARTED_AT"' in validator for validator in gate.validators)
    _s(
        workflow,
        "consistency checker typed return and file gate",
        "Return exactly one typed gpd_return envelope, include files_written",
        "runtime return is canonical",
        "Do not embed or duplicate gpd_return inside the report artifact",
        "Run the local child_gate only for checker returns triaged as `completed`.",
        "`completed`: accept only if the child_gate passes",
        "`checkpoint`: stop, surface the checkpoint payload",
        "`blocked`: stop and route to `gpd:validate-conventions`",
        "`failed`: stop and route to `gpd:validate-conventions`",
        "consistency-check artifact missing",
    )
    _f(
        workflow,
        "consistency checker stale embedded report return",
        "Append the same typed YAML gpd_return block to the artifact before returning",
    )
    assert workflow.index('<step name="spawn_rapid_checker">') < workflow.index(
        '<step name="checker_return_status_route">'
    )
    assert workflow.index('<step name="checker_return_status_route">') < workflow.index("child_gate:")


def test_execute_phase_consistency_check_no_longer_routes_on_legacy_status() -> None:
    workflow = _read_execute_phase_stage("consistency-check.md")

    _f(
        workflow,
        "consistency checker legacy status routing",
        "Return consistency_status with any issues found.",
        "Proceed without cross-phase consistency checking for this wave.",
        "Present issues to user with resolution options",
    )
    _s(
        workflow,
        "consistency checker typed route authority",
        "Do not infer success from prose headings or untyped routing.",
        "Do not hand-author or paste a synthetic `gpd_return`",
    )


def test_execute_phase_consistency_stops_render_from_stage_stop_routes() -> None:
    workflow = _read_execute_phase_stage("consistency-check.md")

    _m(
        workflow,
        "consistency checker stage-stop render routes",
        "| checker spawn/error | `blocked` | `consistency_checker_unavailable`",
        "| checker checkpoint | `checkpoint` | `consistency_checker_checkpoint`",
        "| checker blocked | `blocked` | `consistency_checker_blocked`",
        "| checker failed | `failed` | `consistency_checker_failed`",
        "Primary: `{stage_stop.next_runtime_command}`",
    )
    _s(
        workflow,
        "consistency checker stage-stop render routes",
        "For every consistency-check stop, populate `stage_stop` before rendering.",
    )
    _f(workflow, "consistency checker stale next-up render route", "End with `## > Next Up`: primary")
