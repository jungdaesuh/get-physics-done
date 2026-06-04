"""Class-only scorers for provider-free Phase 4 persona replay rows."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from gpd.command_labels import runtime_public_command_prefixes
from gpd.core.command_run_hints import build_command_run_hint
from gpd.core.commands import cmd_apply_return_updates
from gpd.core.handoff_artifacts import validate_handoff_artifacts_markdown
from gpd.core.phase_closeout import phase_closeout_readiness
from tests.helpers.phase4_persona.completion import completion_replay_rows, score_completion_replay_row
from tests.helpers.phase4_persona.execution import execution_replay_rows, score_execution_replay_row
from tests.helpers.phase4_persona.project_fixtures import (
    FINAL_SUMMARY_REL,
    PHASE_DIR_REL,
    make_stale,
    render_gpd_return_block,
    write_phase_project,
    write_replay_report,
)


class _PersonaRowLike(Protocol):
    scenario: str
    expected_finding: str
    expected_result_class: str


PersonaScorer = Callable[[_PersonaRowLike, Path], "PersonaOutcome"]
PathPersonaScorer = Callable[[Path], "PersonaOutcome"]


@dataclass(frozen=True, slots=True)
class PersonaOutcome:
    """Sanitized replay result with no raw transcript, command output, or paths."""

    finding_id: str
    result_class: str
    accepted: bool = False
    mutated: bool = False
    provider_launch_allowed: bool = False
    state_status_class: str | None = None
    next_action_class: str | None = None
    failure_classes: tuple[str, ...] = ()
    evidence_classes: tuple[str, ...] = ()


def _outcome(
    *,
    finding_id: str,
    result_class: str,
    accepted: bool = False,
    mutated: bool = False,
    state_status_class: str | None = None,
    next_action_class: str | None = None,
    failure_classes: tuple[str, ...] = (),
    evidence_classes: tuple[str, ...] = (),
) -> PersonaOutcome:
    ordered_failures = tuple(dict.fromkeys((finding_id, *failure_classes)))
    return PersonaOutcome(
        finding_id=finding_id,
        result_class=result_class,
        accepted=accepted,
        mutated=mutated,
        state_status_class=state_status_class,
        next_action_class=next_action_class,
        failure_classes=ordered_failures,
        evidence_classes=tuple(dict.fromkeys(evidence_classes)),
    )


def _path_only(scorer: PathPersonaScorer) -> PersonaScorer:
    def _score(row: _PersonaRowLike, root: Path) -> PersonaOutcome:
        del row
        return scorer(root)

    return _score


def _public_runtime_verify_work(command: str) -> bool:
    command_token = command.strip().split(maxsplit=1)[0]
    return any(command_token == f"{prefix}verify-work" for prefix in runtime_public_command_prefixes())


def _next_action_class(primary: object) -> str | None:
    if not isinstance(primary, str) or not primary.strip():
        return None
    command_token = primary.strip().split(maxsplit=1)[0]
    if command_token.startswith("gpd:"):
        return f"gpd_{command_token.removeprefix('gpd:').replace('-', '_')}"
    if command_token.startswith("$gpd-"):
        return f"gpd_{command_token.removeprefix('$gpd-').replace('-', '_')}"
    if command_token.startswith("/gpd-"):
        return f"gpd_{command_token.removeprefix('/gpd-').replace('-', '_')}"
    if command_token.startswith("gpd-"):
        return f"gpd_{command_token.removeprefix('gpd-').replace('-', '_')}"
    if ":" in command_token:
        return command_token.rsplit(":", 1)[-1].replace("-", "_")
    return command_token


def score_invalid_verify_command_surface(root: Path) -> PersonaOutcome:
    del root
    evidence_classes: list[str] = []
    for command in ("gpd-verify-work 02", "gpd verify phase 02"):
        hint = build_command_run_hint(
            command=command,
            source="phase4-persona-replay",
            action="verify-work",
            phase="02",
        )
        assert not _public_runtime_verify_work(command)
        evidence_classes.append(f"run_hint:{(hint or {}).get('kind', 'no_hint')}")

    return _outcome(
        finding_id="invalid_verify_command_surface",
        result_class="blocked_no_mutation",
        state_status_class="unchanged",
        next_action_class="active_runtime_verify_work",
        evidence_classes=tuple(evidence_classes),
    )


def _score_apply_return_failure(root: Path, content: str) -> PersonaOutcome:
    project = write_phase_project(root)
    report = write_replay_report(root, f"{PHASE_DIR_REL}/PERSONA-RETURN.md", content)
    state_before = project.read_state_text()

    result = cmd_apply_return_updates(root, report)

    assert project.read_state_text() == state_before
    return _outcome(
        finding_id=str(result.primary_failure_class),
        result_class="blocked_no_mutation",
        accepted=result.passed,
        mutated=result.mutated,
        state_status_class="unchanged",
        next_action_class="retry_child_return",
        failure_classes=tuple(str(failure_class) for failure_class in result.failure_classes),
    )


def score_prose_success_no_return(root: Path) -> PersonaOutcome:
    return _score_apply_return_failure(root, "# Result\n\nDone. Verified. Ready to continue.\n")


def score_stale_files_written(root: Path) -> PersonaOutcome:
    write_phase_project(root)
    artifact = root / FINAL_SUMMARY_REL
    fresh_after = make_stale(artifact)

    result = validate_handoff_artifacts_markdown(
        root,
        render_gpd_return_block([FINAL_SUMMARY_REL]),
        allowed_roots=[PHASE_DIR_REL],
        required_suffixes=["-SUMMARY.md"],
        fresh_after=fresh_after,
    )

    assert {failure.code for failure in result.failures} == {"artifact_stale"}
    return _outcome(
        finding_id=str(result.primary_failure_class),
        result_class="blocked_no_mutation",
        accepted=result.passed,
        mutated=result.mutated,
        state_status_class="unchanged",
        next_action_class="retry_fresh_artifact",
        failure_classes=tuple(str(failure_class) for failure_class in result.failure_classes),
    )


def score_checkpoint_missing_bounded_context(root: Path) -> PersonaOutcome:
    project = write_phase_project(root)
    report = write_replay_report(
        root,
        f"{PHASE_DIR_REL}/CHECKPOINT.md",
        render_gpd_return_block(
            ["GPD/state.json"],
            status="checkpoint",
            extra='  phase: "02"\n  plan: "02"\n',
        ),
    )
    state_before = project.read_state_text()

    result = cmd_apply_return_updates(root, report)

    assert result.primary_failure_class == "applicator_failed"
    assert any("continuation_update.bounded_segment.resume_file" in error for error in result.errors)
    assert project.read_state_text() == state_before
    return _outcome(
        finding_id="checkpoint_missing_bounded_segment",
        result_class="blocked_no_mutation",
        accepted=False,
        mutated=result.mutated,
        state_status_class="unchanged",
        next_action_class="create_bounded_resume_context",
        failure_classes=tuple(str(failure_class) for failure_class in result.failure_classes),
    )


def score_bounded_segment_bypass(root: Path) -> PersonaOutcome:
    project = write_phase_project(root, verification_status="passed", bounded_segment=True)
    state_before = project.read_state_text()

    result = phase_closeout_readiness(root, "02", require_verification=True)

    assert result.ready is False
    assert result.active_bounded_segment is True
    assert project.read_state_text() == state_before
    return _outcome(
        finding_id="closeout_authority_blocks_premature_completion",
        result_class="blocked_no_mutation",
        state_status_class="unchanged",
        next_action_class=_next_action_class(result.next_up.get("primary")),
        failure_classes=("bounded_segment_bypass",),
    )


def score_intermediate_plan_cannot_complete_phase(root: Path) -> PersonaOutcome:
    project = write_phase_project(root, current_plan=1, total_plans=2, summary_count=1)
    state_before = project.read_state_text()

    result = phase_closeout_readiness(root, "02", require_verification=False)

    assert result.ready is False
    assert result.all_plans_complete is False
    assert project.read_state_text() == state_before
    return _outcome(
        finding_id="intermediate_plan_completion_blocked",
        result_class="blocked_no_mutation",
        state_status_class="unchanged",
        next_action_class="continue_phase_execution",
        failure_classes=("phase_summaries_incomplete",),
    )


def score_missing_verification_blocks_closeout(root: Path) -> PersonaOutcome:
    project = write_phase_project(root)
    state_before = project.read_state_text()

    result = phase_closeout_readiness(root, "02", require_verification=True)

    assert result.ready is False
    assert result.verification_status is None
    assert project.read_state_text() == state_before
    return _outcome(
        finding_id="verification_missing",
        result_class="blocked_no_mutation",
        state_status_class="unchanged",
        next_action_class="run_verify_work",
        failure_classes=("canonical_verification_missing",),
    )


def score_non_passing_verification_records_blocked(root: Path) -> PersonaOutcome:
    project = write_phase_project(
        root,
        status="Phase complete -- ready for verification",
        verification_status="gaps_found",
    )
    state_before = project.read_state_text()

    result = phase_closeout_readiness(root, "02", require_verification=True)

    assert result.ready is False
    assert result.verification_status == "gaps_found"
    assert project.read_state_text() == state_before
    return _outcome(
        finding_id="verification_non_passing",
        result_class="blocked_no_mutation",
        state_status_class="blocked",
        next_action_class="repair_verification_gaps",
        failure_classes=("verification_non_passing",),
    )


def score_active_bounded_segment_routes_resume_work(root: Path) -> PersonaOutcome:
    return score_bounded_segment_bypass(root)


def score_passed_verification_closeout_readiness_read_only(root: Path) -> PersonaOutcome:
    project = write_phase_project(root, status="Verified", verification_status="passed")
    state_before = project.read_state_text()

    result = phase_closeout_readiness(root, "02", require_verification=True)

    assert result.ready is True
    assert result.closeout_command == "gpd phase complete 02"
    assert result.read_only is True
    assert result.mutated is False
    assert project.read_state_text() == state_before
    return _outcome(
        finding_id="closeout_ready",
        result_class="ready_read_only_no_mutation",
        accepted=True,
        state_status_class="unchanged",
        next_action_class="phase_complete_available",
    )


_EXECUTION_ROWS_BY_SCENARIO = {row.scenario: row for row in execution_replay_rows()}
_COMPLETION_ROWS_BY_SCENARIO = {row.scenario: row for row in completion_replay_rows()}


def _matches_execution_replay_contract(row: _PersonaRowLike, scenario: str) -> bool:
    replay_row = _EXECUTION_ROWS_BY_SCENARIO[scenario]
    return (
        row.expected_finding == replay_row.expected_finding
        and row.expected_result_class == replay_row.expected_result_class
    )


def _provider_free_outcome(outcome: object) -> None:
    if (
        getattr(outcome, "provider_launch_allowed", False)
        or getattr(outcome, "network_allowed", False)
        or getattr(outcome, "raw_artifacts_allowed", False)
    ):
        raise AssertionError("Phase 4 persona replay outcomes must stay provider-free and class-only")


def _score_execution_replay_scenario(row: _PersonaRowLike, root: Path) -> PersonaOutcome:
    outcome = score_execution_replay_row(_EXECUTION_ROWS_BY_SCENARIO[row.scenario], root)
    _provider_free_outcome(outcome)
    return _outcome(
        finding_id=str(outcome.finding_id),
        result_class=str(outcome.result_class),
        accepted=outcome.accepted,
        mutated=outcome.mutated,
        state_status_class=outcome.state_status_class,
        next_action_class=outcome.next_action_class,
        failure_classes=tuple(str(failure_class) for failure_class in outcome.failure_classes),
        evidence_classes=tuple(
            str(evidence_class)
            for evidence_class in (*outcome.applied_operations, *outcome.checked_artifact_classes)
        ),
    )


def _score_completion_replay_scenario(row: _PersonaRowLike, root: Path) -> PersonaOutcome:
    outcome = score_completion_replay_row(_COMPLETION_ROWS_BY_SCENARIO[row.scenario], root)
    _provider_free_outcome(outcome)
    return _outcome(
        finding_id=str(outcome.finding_id),
        result_class=str(outcome.result_class),
        accepted=outcome.ready is True,
        mutated=outcome.mutated,
        state_status_class=outcome.state_status_class,
        next_action_class=outcome.next_action_class,
        failure_classes=tuple(str(failure_class) for failure_class in outcome.failure_classes),
    )


def _score_prose_success_no_return(row: _PersonaRowLike, root: Path) -> PersonaOutcome:
    if _matches_execution_replay_contract(row, "prose_success_no_return"):
        return _score_execution_replay_scenario(row, root)
    return score_prose_success_no_return(root)


def _score_checkpoint_missing_bounded_context(row: _PersonaRowLike, root: Path) -> PersonaOutcome:
    if _matches_execution_replay_contract(row, "checkpoint_missing_bounded_context"):
        return _score_execution_replay_scenario(row, root)
    return score_checkpoint_missing_bounded_context(root)


def _score_intermediate_plan_cannot_complete_phase(row: _PersonaRowLike, root: Path) -> PersonaOutcome:
    if _matches_execution_replay_contract(row, "intermediate_plan_cannot_complete_phase"):
        return _score_execution_replay_scenario(row, root)
    return score_intermediate_plan_cannot_complete_phase(root)


SCORERS: dict[str, PersonaScorer] = {
    **dict.fromkeys(_EXECUTION_ROWS_BY_SCENARIO, _score_execution_replay_scenario),
    **dict.fromkeys(_COMPLETION_ROWS_BY_SCENARIO, _score_completion_replay_scenario),
    "invalid_verify_command_surface": _path_only(score_invalid_verify_command_surface),
    "prose_success_no_return": _score_prose_success_no_return,
    "stale_files_written": _path_only(score_stale_files_written),
    "checkpoint_missing_bounded_context": _score_checkpoint_missing_bounded_context,
    "intermediate_plan_cannot_complete_phase": _score_intermediate_plan_cannot_complete_phase,
    "missing_verification_blocks_closeout": _path_only(score_missing_verification_blocks_closeout),
    "non_passing_verification_records_blocked": _path_only(score_non_passing_verification_records_blocked),
    "active_bounded_segment_routes_resume_work": _path_only(score_active_bounded_segment_routes_resume_work),
    "passed_verification_closeout_readiness_read_only": _path_only(
        score_passed_verification_closeout_readiness_read_only
    ),
}


def registered_phase4_scenarios() -> frozenset[str]:
    """Return canonical fixture scenario ids with executable shared scorers."""

    return frozenset(SCORERS)


def registered_scenarios() -> frozenset[str]:
    return registered_phase4_scenarios()


__all__ = [
    "PersonaOutcome",
    "SCORERS",
    "registered_phase4_scenarios",
    "registered_scenarios",
    "score_bounded_segment_bypass",
    "score_checkpoint_missing_bounded_context",
    "score_invalid_verify_command_surface",
    "score_intermediate_plan_cannot_complete_phase",
    "score_missing_verification_blocks_closeout",
    "score_non_passing_verification_records_blocked",
    "score_passed_verification_closeout_readiness_read_only",
    "score_prose_success_no_return",
    "score_stale_files_written",
]
