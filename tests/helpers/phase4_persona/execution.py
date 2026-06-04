"""Provider-free Phase 4 execution replay rows and scorers."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from gpd.command_labels import runtime_public_command_prefixes
from gpd.core.command_run_hints import build_command_run_hint
from gpd.core.commands import cmd_apply_return_updates
from gpd.core.handoff_artifacts import validate_handoff_artifacts_markdown
from gpd.core.return_repair_classifier import classify_gpd_return_repair
from gpd.core.state import default_state_dict, generate_state_markdown, state_status_class
from tests.helpers.phase4_persona.matrix import (
    PHASE4_PERSONA_SCHEMA_VERSION,
    PersonaMatrixRow,
)
from tests.helpers.phase4_persona.matrix import (
    load_phase4_rows as load_phase4_matrix_rows,
)
from tests.return_skeleton_support import render_gpd_return_block

PHASE = "02"
PLAN = "02"
PHASE_NAME = "analysis"
PHASE_DIR = f"GPD/phases/{PHASE}-{PHASE_NAME}"
SUMMARY_PATH = f"{PHASE_DIR}/{PHASE}-{PLAN}-SUMMARY.md"
RESUME_PATH = f"{PHASE_DIR}/.continue-here.md"
REPO_ROOT = Path(__file__).resolve().parents[3]

WAVE_RETURN_CHECKPOINT_OWNER = "src/gpd/specs/workflows/execute-phase/wave-return-checkpoint.md"
VERIFICATION_HANDOFF_OWNER = "src/gpd/specs/workflows/execute-phase/verification-handoff.md"
CHECKPOINT_RESUME_OWNER = "src/gpd/specs/workflows/execute-phase/checkpoint-resume.md"
CLOSEOUT_OWNER = "src/gpd/specs/workflows/execute-phase/closeout.md"

_SPLIT_STAGE_SOURCE_OWNERS_BY_SCENARIO = {
    "valid_final_plan_ready_to_execute": (WAVE_RETURN_CHECKPOINT_OWNER,),
    "invalid_gpd_verify_work_surface": (VERIFICATION_HANDOFF_OWNER,),
    "invalid_gpd_verify_phase_surface": (VERIFICATION_HANDOFF_OWNER,),
    "prose_success_no_return": (WAVE_RETURN_CHECKPOINT_OWNER,),
    "multiple_gpd_returns": (WAVE_RETURN_CHECKPOINT_OWNER,),
    "unfenced_raw_return_candidate": (WAVE_RETURN_CHECKPOINT_OWNER,),
    "empty_files_written_required_artifact": (WAVE_RETURN_CHECKPOINT_OWNER,),
    "omitted_files_written_field": (WAVE_RETURN_CHECKPOINT_OWNER,),
    "stale_artifact": (WAVE_RETURN_CHECKPOINT_OWNER,),
    "wrong_sibling_artifact": (WAVE_RETURN_CHECKPOINT_OWNER,),
    "checkpoint_missing_bounded_context": (WAVE_RETURN_CHECKPOINT_OWNER, CHECKPOINT_RESUME_OWNER),
    "checkpoint_with_bounded_context": (WAVE_RETURN_CHECKPOINT_OWNER, CHECKPOINT_RESUME_OWNER),
    "intermediate_plan_cannot_complete_phase": (WAVE_RETURN_CHECKPOINT_OWNER, CLOSEOUT_OWNER),
    "applicator_result_prose_only": (WAVE_RETURN_CHECKPOINT_OWNER,),
}


@dataclass(frozen=True, slots=True)
class ExecutionReplayRow:
    row_id: str
    scenario: str
    fixture_family: str
    expected_finding: str
    expected_result_class: str
    schema_version: str = PHASE4_PERSONA_SCHEMA_VERSION
    surface: str = "execution"
    runtime_scope: tuple[str, ...] = ("provider_free",)
    expected_accepted: bool = False
    expected_mutated: bool = False
    mutation_allowed: bool = False
    expected_state_status_class: str | None = None
    expected_next_action_class: str | None = None
    behavior_contract_id: str | None = None
    persona_class: str = "executor"
    prompt_variant_class: str = "child_return_replay"
    expected_smoothness_class: str | None = None
    expected_schema_wrestling_class: str | None = None
    expected_next_up_specificity_class: str | None = None
    expected_mutation_guard_class: str | None = None
    expected_metric_bounds: tuple[tuple[str, int], ...] = ()
    provider_launch_allowed: bool = False
    network_allowed: bool = False
    raw_artifacts_allowed: bool = False
    source_owners: tuple[str, ...] = ()
    test_owners: tuple[str, ...] = (
        "tests/helpers/phase4_persona/execution.py",
        "tests/core/test_phase4_persona_execution_replay.py",
    )
    metadata_source: str = "compatibility_adapter"


@dataclass(frozen=True, slots=True)
class ExecutionReplayOutcome:
    row_id: str
    finding_id: str
    result_class: str
    accepted: bool
    mutated: bool
    provider_launch_allowed: bool = False
    network_allowed: bool = False
    raw_artifacts_allowed: bool = False
    state_status_class: str | None = None
    next_action_class: str | None = None
    failure_classes: tuple[str, ...] = ()
    applied_operations: tuple[str, ...] = ()
    checked_artifact_classes: tuple[str, ...] = ()


_EXECUTION_ROWS = (
    ExecutionReplayRow(
        "P4-EXEC-01",
        "valid_final_plan_ready_to_execute",
        "child_return_applicator",
        "valid_final_plan_completed",
        "accepted",
        expected_accepted=True,
        expected_mutated=True,
        mutation_allowed=True,
        expected_state_status_class="phase_ready_for_verification",
        expected_next_action_class="runtime_verify_work",
        source_owners=("src/gpd/core/child_return_application.py", "src/gpd/core/state.py"),
    ),
    ExecutionReplayRow(
        "P4-EXEC-02",
        "invalid_gpd_verify_work_surface",
        "command_surface",
        "invalid_verify_command_surface",
        "blocked",
        source_owners=("src/gpd/core/command_run_hints.py", "src/gpd/command_labels.py"),
    ),
    ExecutionReplayRow(
        "P4-EXEC-03",
        "invalid_gpd_verify_phase_surface",
        "command_surface",
        "invalid_verify_command_surface",
        "blocked",
        source_owners=("src/gpd/core/command_run_hints.py",),
    ),
    ExecutionReplayRow(
        "P4-EXEC-04",
        "prose_success_no_return",
        "return_gate",
        "return_missing",
        "retry_child",
        source_owners=("src/gpd/core/return_contract.py", "src/gpd/core/commands.py"),
    ),
    ExecutionReplayRow(
        "P4-EXEC-05",
        "multiple_gpd_returns",
        "return_gate",
        "return_malformed_blocking",
        "blocked",
        source_owners=("src/gpd/core/return_contract.py", "src/gpd/core/commands.py"),
    ),
    ExecutionReplayRow(
        "P4-EXEC-06",
        "unfenced_raw_return_candidate",
        "return_gate",
        "unfenced_candidate",
        "retry_child",
        source_owners=("src/gpd/core/return_repair_classifier.py",),
    ),
    ExecutionReplayRow(
        "P4-EXEC-07",
        "empty_files_written_required_artifact",
        "artifact_gate",
        "artifact_missing",
        "blocked",
        source_owners=("src/gpd/core/handoff_artifacts.py",),
    ),
    ExecutionReplayRow(
        "P4-EXEC-08",
        "omitted_files_written_field",
        "artifact_gate",
        "return_malformed_repairable",
        "retry_child",
        source_owners=("src/gpd/core/handoff_artifacts.py", "src/gpd/core/return_contract.py"),
    ),
    ExecutionReplayRow(
        "P4-EXEC-09",
        "stale_artifact",
        "artifact_gate",
        "artifact_stale",
        "blocked",
        source_owners=("src/gpd/core/handoff_artifacts.py",),
    ),
    ExecutionReplayRow(
        "P4-EXEC-10",
        "wrong_sibling_artifact",
        "artifact_gate",
        "artifact_missing",
        "blocked",
        source_owners=("src/gpd/core/handoff_artifacts.py",),
    ),
    ExecutionReplayRow(
        "P4-EXEC-11",
        "checkpoint_missing_bounded_context",
        "checkpoint",
        "checkpoint_missing_bounded_segment",
        "blocked",
        source_owners=("src/gpd/core/child_return_application.py",),
    ),
    ExecutionReplayRow(
        "P4-EXEC-12",
        "checkpoint_with_bounded_context",
        "checkpoint",
        "checkpoint_bounded_segment_recorded",
        "checkpoint_recorded",
        expected_accepted=True,
        expected_mutated=True,
        mutation_allowed=True,
        expected_state_status_class="executing",
        expected_next_action_class="resume_work",
        source_owners=("src/gpd/core/checkpoint_intent.py", "src/gpd/core/child_return_application.py"),
    ),
    ExecutionReplayRow(
        "P4-EXEC-13",
        "intermediate_plan_cannot_complete_phase",
        "child_return_applicator",
        "applicator_failed",
        "blocked",
        source_owners=("src/gpd/core/child_return_application.py", "src/gpd/core/state.py"),
    ),
    ExecutionReplayRow(
        "P4-EXEC-14",
        "applicator_result_prose_only",
        "return_gate",
        "applicator_output_only",
        "blocked",
        source_owners=("src/gpd/core/return_contract.py", "src/gpd/core/commands.py"),
    ),
)


def execution_replay_rows() -> tuple[ExecutionReplayRow, ...]:
    canonical_rows = _canonical_rows_by_exact_contract()
    return tuple(
        _with_split_stage_source_owners(_with_canonical_metadata(row, canonical_rows)) for row in _EXECUTION_ROWS
    )


def _canonical_rows_by_exact_contract() -> dict[tuple[str, str, str, str], PersonaMatrixRow]:
    try:
        return {
            (row.row_id, row.scenario, row.expected_finding, row.expected_result_class): row
            for row in load_phase4_matrix_rows("execution")
        }
    except (FileNotFoundError, KeyError, TypeError, ValueError):
        return {}


def _with_canonical_metadata(
    row: ExecutionReplayRow,
    canonical_rows: dict[tuple[str, str, str, str], PersonaMatrixRow],
) -> ExecutionReplayRow:
    row = _with_behavior_contract_defaults(row)
    canonical = canonical_rows.get((row.row_id, row.scenario, row.expected_finding, row.expected_result_class))
    if canonical is None:
        return row

    return replace(
        row,
        schema_version=canonical.schema_version,
        fixture_family=canonical.fixture_family,
        runtime_scope=canonical.runtime_scope,
        source_owners=canonical.source_owners,
        test_owners=canonical.test_owners,
        provider_launch_allowed=canonical.provider_launch_allowed,
        network_allowed=canonical.network_allowed,
        raw_artifacts_allowed=canonical.raw_artifacts_allowed,
        behavior_contract_id=getattr(canonical, "behavior_contract_id", row.behavior_contract_id),
        persona_class=getattr(canonical, "persona_class", row.persona_class),
        prompt_variant_class=getattr(canonical, "prompt_variant_class", row.prompt_variant_class),
        expected_smoothness_class=getattr(
            canonical,
            "expected_smoothness_class",
            row.expected_smoothness_class,
        ),
        expected_schema_wrestling_class=getattr(
            canonical,
            "expected_schema_wrestling_class",
            row.expected_schema_wrestling_class,
        ),
        expected_next_up_specificity_class=getattr(
            canonical,
            "expected_next_up_specificity_class",
            row.expected_next_up_specificity_class,
        ),
        expected_mutation_guard_class=getattr(
            canonical,
            "expected_mutation_guard_class",
            row.expected_mutation_guard_class,
        ),
        expected_metric_bounds=_normalize_metric_bounds(
            getattr(canonical, "expected_metric_bounds", row.expected_metric_bounds)
        ),
        metadata_source="canonical_fixture",
    )


def _with_split_stage_source_owners(row: ExecutionReplayRow) -> ExecutionReplayRow:
    split_stage_owners = tuple(
        owner for owner in _SPLIT_STAGE_SOURCE_OWNERS_BY_SCENARIO.get(row.scenario, ()) if (REPO_ROOT / owner).is_file()
    )
    if not split_stage_owners:
        return row
    return replace(row, source_owners=tuple(dict.fromkeys((*split_stage_owners, *row.source_owners))))


def _with_behavior_contract_defaults(row: ExecutionReplayRow) -> ExecutionReplayRow:
    expected_schema_wrestling_class = row.expected_schema_wrestling_class or _schema_wrestling_class(row.scenario)
    expected_mutation_guard_class = row.expected_mutation_guard_class or _mutation_guard_class(row)
    return replace(
        row,
        fixture_family=_class_fixture_family(row.fixture_family),
        behavior_contract_id=row.behavior_contract_id or f"phase4.execution.{row.scenario}",
        expected_smoothness_class=row.expected_smoothness_class or _smoothness_class(row),
        expected_schema_wrestling_class=expected_schema_wrestling_class,
        expected_next_up_specificity_class=(
            row.expected_next_up_specificity_class or _next_up_specificity_class(row.expected_next_action_class)
        ),
        expected_mutation_guard_class=expected_mutation_guard_class,
        expected_metric_bounds=row.expected_metric_bounds or _metric_bounds(row, expected_schema_wrestling_class),
    )


def _class_fixture_family(fixture_family: str) -> str:
    return fixture_family if fixture_family.endswith("_class") else f"{fixture_family}_class"


def _schema_wrestling_class(scenario: str) -> str:
    if scenario in {"multiple_gpd_returns", "applicator_result_prose_only"}:
        return "high"
    if scenario in {"prose_success_no_return", "unfenced_raw_return_candidate", "omitted_files_written_field"}:
        return "minor"
    return "none"


def _smoothness_class(row: ExecutionReplayRow) -> str:
    if _schema_wrestling_class(row.scenario) != "none":
        return "clunky"
    if row.expected_result_class in {"accepted", "checkpoint_recorded"}:
        return "smooth"
    if row.expected_result_class == "blocked":
        return "acceptable"
    return "smooth"


def _next_up_specificity_class(expected_next_action_class: str | None) -> str:
    if expected_next_action_class is None:
        return "none"
    if expected_next_action_class == "runtime_verify_work":
        return "runtime_verify_work"
    if expected_next_action_class == "resume_work":
        return "bounded_resume"
    return "concrete_command"


def _mutation_guard_class(row: ExecutionReplayRow) -> str:
    if row.expected_mutated and row.mutation_allowed:
        return "expected_write_only"
    if row.expected_mutated:
        return "unexpected_write"
    return "no_write"


def _metric_bounds(row: ExecutionReplayRow, schema_wrestling_class: str) -> tuple[tuple[str, int], ...]:
    bounds = [("structured_authority_coverage", 1), ("unexpected_write_count", 0)]
    if row.scenario in {"invalid_gpd_verify_work_surface", "invalid_gpd_verify_phase_surface"}:
        bounds.append(("invalid_command_suggestion_count", 0))
    if row.scenario in {"prose_success_no_return", "multiple_gpd_returns", "applicator_result_prose_only"}:
        bounds.append(("prose_claim_mismatch_count", 1))
    if schema_wrestling_class != "none":
        bounds.append(("schema_repair_loop_count", 1))
    if row.scenario == "stale_artifact":
        bounds.append(("stale_artifact_trust_count", 0))
    if row.scenario in {"intermediate_plan_cannot_complete_phase", "applicator_result_prose_only"}:
        bounds.append(("unsupported_completion_claim_count", 1))
    return tuple(bounds)


def _normalize_metric_bounds(value: object) -> tuple[tuple[str, int], ...]:
    if isinstance(value, dict):
        return tuple(sorted((str(key), int(bound)) for key, bound in value.items()))
    if isinstance(value, (list, tuple)):
        normalized: list[tuple[str, int]] = []
        for item in value:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                normalized.append((str(item[0]), int(item[1])))
        if normalized:
            return tuple(normalized)
    return ()


def score_execution_replay_row(row: ExecutionReplayRow, root: Path) -> ExecutionReplayOutcome:
    match row.scenario:
        case "valid_final_plan_ready_to_execute":
            return _score_valid_final_plan_ready_to_execute(row, root)
        case "invalid_gpd_verify_work_surface":
            return _score_invalid_verify_command_surface(row, "gpd-verify-work 02")
        case "invalid_gpd_verify_phase_surface":
            return _score_invalid_verify_command_surface(row, "gpd verify phase 02")
        case "prose_success_no_return":
            return _score_apply_return_failure(row, root, "# Result\n\nDone. Verified. Ready to continue.\n")
        case "multiple_gpd_returns":
            return _score_apply_return_failure(
                row, root, _return_block([SUMMARY_PATH]) + "\n" + _blocked_return_block()
            )
        case "unfenced_raw_return_candidate":
            return _score_unfenced_raw_return_candidate(row)
        case "empty_files_written_required_artifact":
            return _score_empty_files_written(row, root)
        case "omitted_files_written_field":
            return _score_omitted_files_written_field(row, root)
        case "stale_artifact":
            return _score_stale_artifact(row, root)
        case "wrong_sibling_artifact":
            return _score_wrong_sibling_artifact(row, root)
        case "checkpoint_missing_bounded_context":
            return _score_checkpoint_missing_bounded_context(row, root)
        case "checkpoint_with_bounded_context":
            return _score_checkpoint_with_bounded_context(row, root)
        case "intermediate_plan_cannot_complete_phase":
            return _score_intermediate_plan_cannot_complete_phase(row, root)
        case "applicator_result_prose_only":
            return _score_applicator_result_prose_only(row, root)
    raise AssertionError(f"unhandled execution replay scenario: {row.scenario}")


def _write_phase_project(
    root: Path,
    *,
    current_plan: int = 2,
    total_plans: int = 2,
    status: str = "Ready to execute",
    summaries: int = 2,
) -> Path:
    gpd_dir = root / "GPD"
    phase_dir = gpd_dir / "phases" / f"{PHASE}-{PHASE_NAME}"
    phase_dir.mkdir(parents=True, exist_ok=True)
    (gpd_dir / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
    (gpd_dir / "ROADMAP.md").write_text(
        "# Roadmap\n\n## Phase 1: Setup\n\n## Phase 2: Analysis\n\n## Phase 3: Synthesis\n",
        encoding="utf-8",
    )
    for index in range(1, total_plans + 1):
        (phase_dir / f"{PHASE}-{index:02d}-PLAN.md").write_text(
            f"# Phase {PHASE} Plan {index:02d}\n",
            encoding="utf-8",
        )
    for index in range(1, summaries + 1):
        (phase_dir / f"{PHASE}-{index:02d}-SUMMARY.md").write_text(
            f"# Phase {PHASE} Plan {index:02d} Summary\n",
            encoding="utf-8",
        )

    state = default_state_dict()
    state["position"]["current_phase"] = PHASE
    state["position"]["current_phase_name"] = PHASE_NAME.title()
    state["position"]["current_plan"] = str(current_plan)
    state["position"]["total_plans_in_phase"] = total_plans
    state["position"]["total_phases"] = 3
    state["position"]["progress_percent"] = 66
    state["position"]["status"] = status
    (gpd_dir / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    (gpd_dir / "STATE.md").write_text(generate_state_markdown(state), encoding="utf-8")
    return phase_dir


def _return_block(
    files_written: list[str],
    *,
    status: str = "completed",
    issues: list[str] | None = None,
    next_actions: list[str] | None = None,
    extra: str = "",
) -> str:
    return render_gpd_return_block(
        files_written,
        status=status,
        issues=issues,
        next_actions=next_actions,
        extra_yaml=extra,
    )


def _completed_plan_return(files_written: list[str]) -> str:
    return _return_block(
        files_written,
        next_actions=[f"gpd:verify-work {PHASE}"],
        extra=(f'  phase: "{PHASE}"\n  plan: "{PLAN}"\n  state_updates:\n    advance_plan: true\n'),
    )


def _blocked_return_block() -> str:
    return _return_block(
        [],
        status="blocked",
        issues=["conflicting return"],
        extra=("  blockers:\n    - conflicting return\n"),
    )


def _score_valid_final_plan_ready_to_execute(row: ExecutionReplayRow, root: Path) -> ExecutionReplayOutcome:
    phase_dir = _write_phase_project(root, status="Ready to execute")
    summary = phase_dir / f"{PHASE}-{PLAN}-SUMMARY.md"
    summary.write_text("# Completed Summary\n\n" + _completed_plan_return([SUMMARY_PATH]), encoding="utf-8")

    result = cmd_apply_return_updates(root, summary)
    state_status = _state_status_class(root)

    assert result.passed is True
    assert result.mutated is True
    assert "advance_plan:last_plan" in result.applied_state_operations
    assert state_status == "phase_ready_for_verification"

    return ExecutionReplayOutcome(
        row_id=row.row_id,
        finding_id="valid_final_plan_completed",
        result_class="accepted",
        accepted=True,
        mutated=result.mutated,
        state_status_class=state_status,
        next_action_class="runtime_verify_work",
        applied_operations=tuple(result.applied_state_operations),
    )


def _score_invalid_verify_command_surface(row: ExecutionReplayRow, command: str) -> ExecutionReplayOutcome:
    hint = build_command_run_hint(
        command=command,
        source="phase4-persona-execution-replay",
        action="verify-work",
        phase=PHASE,
    )
    command_token = command.strip().split(maxsplit=1)[0]
    public_verify_tokens = {f"{prefix}verify-work" for prefix in runtime_public_command_prefixes()}

    assert hint is not None
    assert hint["execution"] == "not_executed"
    assert command_token not in public_verify_tokens
    command_failure_class = str(hint["kind"])
    if command == "gpd verify phase 02":
        assert hint["kind"] == "unknown_display_only"
        command_failure_class = "structural_verify_phase"

    return ExecutionReplayOutcome(
        row_id=row.row_id,
        finding_id="invalid_verify_command_surface",
        result_class="blocked",
        accepted=False,
        mutated=False,
        failure_classes=("invalid_verify_command_surface", command_failure_class, str(hint["kind"])),
    )


def _score_apply_return_failure(row: ExecutionReplayRow, root: Path, content: str) -> ExecutionReplayOutcome:
    phase_dir = _write_phase_project(root, status="Ready to execute")
    report = phase_dir / "PERSONA-RETURN.md"
    report.write_text(content, encoding="utf-8")
    state_path = root / "GPD" / "state.json"
    state_before = state_path.read_text(encoding="utf-8")

    result = cmd_apply_return_updates(root, report)

    assert result.passed is False
    assert result.mutated is False
    assert state_path.read_text(encoding="utf-8") == state_before
    return ExecutionReplayOutcome(
        row_id=row.row_id,
        finding_id=str(result.primary_failure_class),
        result_class="retry_child" if result.primary_failure_class == "return_missing" else "blocked",
        accepted=False,
        mutated=result.mutated,
        state_status_class=_state_status_class(root),
        failure_classes=tuple(str(failure_class) for failure_class in result.failure_classes),
    )


def _score_unfenced_raw_return_candidate(row: ExecutionReplayRow) -> ExecutionReplayOutcome:
    result = classify_gpd_return_repair(
        json.dumps(
            {
                "gpd_return": {
                    "status": "completed",
                    "files_written": [SUMMARY_PATH],
                    "issues": [],
                    "next_actions": [f"gpd:verify-work {PHASE}"],
                }
            }
        )
    )

    assert result.valid is False
    assert result.accepted_for_success is False
    assert result.primary_class == "unfenced_candidate"
    return ExecutionReplayOutcome(
        row_id=row.row_id,
        finding_id=result.primary_class,
        result_class="retry_child",
        accepted=False,
        mutated=result.mutated,
        failure_classes=tuple(result.failure_classes or [result.primary_class]),
    )


def _score_empty_files_written(row: ExecutionReplayRow, root: Path) -> ExecutionReplayOutcome:
    phase_dir = _write_phase_project(root, status="Ready to execute")
    expected = phase_dir / f"{PHASE}-{PLAN}-SUMMARY.md"
    expected.write_text("# Fresh summary\n", encoding="utf-8")

    result = validate_handoff_artifacts_markdown(
        root,
        _return_block([]),
        expected_artifacts=[SUMMARY_PATH],
        allowed_roots=[PHASE_DIR],
        required_suffixes=["-SUMMARY.md"],
        require_files_written=True,
        fresh_after=datetime.now(tz=UTC) - timedelta(minutes=1),
    )

    codes = {failure.code for failure in result.failures}
    assert result.passed is False
    assert {"files_written_empty", "expected_artifact_omitted"} <= codes
    return _artifact_outcome(row, result)


def _score_omitted_files_written_field(row: ExecutionReplayRow, root: Path) -> ExecutionReplayOutcome:
    _write_phase_project(root, status="Ready to execute")
    content = "```yaml\ngpd_return:\n  status: completed\n  issues: []\n  next_actions: []\n```\n"

    result = validate_handoff_artifacts_markdown(
        root,
        content,
        expected_artifacts=[SUMMARY_PATH],
        allowed_roots=[PHASE_DIR],
        required_suffixes=["-SUMMARY.md"],
        require_files_written=True,
    )

    assert result.passed is False
    assert result.primary_failure_class == "return_malformed_repairable"
    assert {failure.code for failure in result.failures} == {"missing_required_field"}
    return _artifact_outcome(row, result, result_class="retry_child")


def _score_stale_artifact(row: ExecutionReplayRow, root: Path) -> ExecutionReplayOutcome:
    phase_dir = _write_phase_project(root, status="Ready to execute")
    artifact = phase_dir / f"{PHASE}-{PLAN}-SUMMARY.md"
    artifact.write_text("# Stale summary\n", encoding="utf-8")
    stale_time = datetime.now(tz=UTC) - timedelta(hours=2)
    os.utime(artifact, (stale_time.timestamp(), stale_time.timestamp()))

    result = validate_handoff_artifacts_markdown(
        root,
        _return_block([SUMMARY_PATH]),
        expected_artifacts=[SUMMARY_PATH],
        allowed_roots=[PHASE_DIR],
        required_suffixes=["-SUMMARY.md"],
        require_files_written=True,
        fresh_after=datetime.now(tz=UTC) - timedelta(minutes=1),
    )

    assert result.passed is False
    assert {failure.code for failure in result.failures} == {"artifact_stale"}
    return _artifact_outcome(row, result)


def _score_wrong_sibling_artifact(row: ExecutionReplayRow, root: Path) -> ExecutionReplayOutcome:
    phase_dir = _write_phase_project(root, status="Ready to execute")
    wrong = f"{PHASE_DIR}/{PHASE}-01-SUMMARY.md"
    (phase_dir / f"{PHASE}-01-SUMMARY.md").write_text("# Wrong sibling\n", encoding="utf-8")
    (phase_dir / f"{PHASE}-{PLAN}-SUMMARY.md").write_text("# Expected sibling\n", encoding="utf-8")

    result = validate_handoff_artifacts_markdown(
        root,
        _return_block([wrong]),
        expected_artifacts=[SUMMARY_PATH],
        allowed_roots=[PHASE_DIR],
        required_suffixes=["-SUMMARY.md"],
        require_files_written=True,
        fresh_after=datetime.now(tz=UTC) - timedelta(minutes=1),
    )

    assert result.passed is False
    assert "expected_artifact_omitted" in {failure.code for failure in result.failures}
    return _artifact_outcome(row, result, checked_artifact_classes=("wrong_sibling", "expected_sibling"))


def _score_checkpoint_missing_bounded_context(row: ExecutionReplayRow, root: Path) -> ExecutionReplayOutcome:
    phase_dir = _write_phase_project(root, status="Executing")
    report = phase_dir / "CHECKPOINT.md"
    report.write_text(
        _return_block(
            ["GPD/state.json"],
            status="checkpoint",
            extra=f'  phase: "{PHASE}"\n  plan: "{PLAN}"\n',
        ),
        encoding="utf-8",
    )
    state_path = root / "GPD" / "state.json"
    state_before = state_path.read_text(encoding="utf-8")

    result = cmd_apply_return_updates(root, report)

    assert result.passed is False
    assert result.mutated is False
    assert any("continuation_update.bounded_segment.resume_file" in error for error in result.errors)
    assert state_path.read_text(encoding="utf-8") == state_before
    return ExecutionReplayOutcome(
        row_id=row.row_id,
        finding_id="checkpoint_missing_bounded_segment",
        result_class="blocked",
        accepted=False,
        mutated=result.mutated,
        state_status_class=_state_status_class(root),
        failure_classes=("checkpoint_missing_bounded_segment", *tuple(result.failure_classes)),
    )


def _score_checkpoint_with_bounded_context(row: ExecutionReplayRow, root: Path) -> ExecutionReplayOutcome:
    phase_dir = _write_phase_project(root, status="Executing")
    (phase_dir / ".continue-here.md").write_text("Resume from execution checkpoint.\n", encoding="utf-8")
    report = phase_dir / "CHECKPOINT.md"
    report.write_text(
        _return_block(
            [],
            status="checkpoint",
            next_actions=["gpd:resume-work"],
            extra=(
                f'  phase: "{PHASE}"\n'
                f'  plan: "{PLAN}"\n'
                "  checkpoint_intent:\n"
                "    checkpoint_reason: first_result_gate\n"
                "    awaiting: user_review\n"
                "    first_result_gate_pending: true\n"
                "    downstream_locked: true\n"
            ),
        ),
        encoding="utf-8",
    )

    result = cmd_apply_return_updates(root, report, checkpoint_resume_file=RESUME_PATH)
    state = json.loads((root / "GPD" / "state.json").read_text(encoding="utf-8"))
    bounded_segment = state["continuation"]["bounded_segment"]

    assert result.passed is True
    assert result.mutated is True
    assert result.applied_continuation_operations == ["set_bounded_segment"]
    assert bounded_segment["resume_file"] == RESUME_PATH
    assert bounded_segment["checkpoint_reason"] == "first_result_gate"
    assert bounded_segment["first_result_gate_pending"] is True
    return ExecutionReplayOutcome(
        row_id=row.row_id,
        finding_id="checkpoint_bounded_segment_recorded",
        result_class="checkpoint_recorded",
        accepted=True,
        mutated=result.mutated,
        state_status_class=_state_status_class(root),
        next_action_class="resume_work",
        applied_operations=tuple(result.applied_continuation_operations),
    )


def _score_intermediate_plan_cannot_complete_phase(row: ExecutionReplayRow, root: Path) -> ExecutionReplayOutcome:
    phase_dir = _write_phase_project(root, current_plan=1, total_plans=2, status="Ready to execute", summaries=1)
    report = phase_dir / "DIRECT-COMPLETE.md"
    report.write_text(
        _return_block(
            [f"{PHASE_DIR}/{PHASE}-01-SUMMARY.md"],
            extra=(f'  phase: "{PHASE}"\n  plan: "01"\n  state_updates:\n    complete_phase: true\n'),
        ),
        encoding="utf-8",
    )
    state_path = root / "GPD" / "state.json"
    state_before = state_path.read_text(encoding="utf-8")

    result = cmd_apply_return_updates(root, report)

    assert result.passed is False
    assert result.mutated is False
    assert result.primary_failure_class == "applicator_failed"
    assert any("state_updates.complete_phase" in error for error in result.errors)
    assert state_path.read_text(encoding="utf-8") == state_before
    return ExecutionReplayOutcome(
        row_id=row.row_id,
        finding_id="applicator_failed",
        result_class="blocked",
        accepted=False,
        mutated=result.mutated,
        state_status_class=_state_status_class(root),
        failure_classes=tuple(result.failure_classes),
    )


def _score_applicator_result_prose_only(row: ExecutionReplayRow, root: Path) -> ExecutionReplayOutcome:
    content = (
        "# Child result\n\n"
        "ApplyChildReturnResult(passed=True, status='completed', "
        "files_written=['GPD/phases/02-analysis/02-02-SUMMARY.md'], "
        "applied_state_operations=['advance_plan:last_plan'])\n"
    )
    outcome = _score_apply_return_failure(row, root, content)
    assert outcome.finding_id == "return_missing"
    return ExecutionReplayOutcome(
        row_id=row.row_id,
        finding_id="applicator_output_only",
        result_class="blocked",
        accepted=False,
        mutated=outcome.mutated,
        state_status_class=outcome.state_status_class,
        failure_classes=("applicator_output_only", *outcome.failure_classes),
    )


def _artifact_outcome(
    row: ExecutionReplayRow,
    result,
    *,
    result_class: str = "blocked",
    checked_artifact_classes: tuple[str, ...] = (),
) -> ExecutionReplayOutcome:
    return ExecutionReplayOutcome(
        row_id=row.row_id,
        finding_id=str(result.primary_failure_class),
        result_class=result_class,
        accepted=result.passed,
        mutated=result.mutated,
        failure_classes=tuple(str(failure_class) for failure_class in result.failure_classes)
        + tuple(failure.code for failure in result.failures),
        checked_artifact_classes=checked_artifact_classes,
    )


def _state_status_class(root: Path) -> str:
    state = json.loads((root / "GPD" / "state.json").read_text(encoding="utf-8"))
    return state_status_class(state["position"].get("status"))
