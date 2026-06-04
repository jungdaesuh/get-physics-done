"""Provider-free Phase 4 completion and verification replay rows."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers.phase4_persona.behavior_metrics import assert_behavior_contract
from tests.helpers.phase4_persona.completion import (
    SCHEMA_VERSION,
    CompletionReplayRow,
    completion_replay_rows,
    phase2_completion_replay_rows,
    score_completion_replay_row,
)
from tests.helpers.phase4_persona.matrix import (
    NEXT_UP_SPECIFICITY_CLASSES,
    PERSONA_CLASSES,
    PHASE4_PERSONA_SCHEMA_VERSION,
    SCHEMA_WRESTLING_CLASSES,
    SMOOTHNESS_CLASSES,
)


def test_phase4_completion_replay_rows_are_provider_free_and_owned() -> None:
    rows = completion_replay_rows()
    rows_by_scenario = {row.scenario: row for row in rows}
    expected_row_ids = {
        "P4-COMP-01",
        "P4-COMP-02",
        "P4-COMP-03",
        "P4-COMP-04",
        "P4-COMP-05",
        "P4-COMP-06",
        "P4-COMP-07",
        "P4-COMP-08",
        "P4-COMP-09",
    }

    assert len(rows) == len(expected_row_ids)
    assert {row.row_id for row in rows} == expected_row_ids
    assert all(row.schema_version == SCHEMA_VERSION for row in rows)
    assert SCHEMA_VERSION == PHASE4_PERSONA_SCHEMA_VERSION
    assert all(row.surface == "completion" for row in rows)
    assert all(row.fixture_family.endswith("_class") for row in rows)
    assert all(row.runtime_scope == ("provider_free",) for row in rows)
    assert {row.persona_class for row in rows} <= set(PERSONA_CLASSES)
    assert all(row.prompt_variant_class for row in rows)
    assert all(row.metadata_source in {"canonical_fixture", "compatibility_adapter"} for row in rows)
    assert all(row.provider_launch_allowed is False for row in rows)
    assert all(row.network_allowed is False for row in rows)
    assert all(row.raw_artifacts_allowed is False for row in rows)
    assert all(row.behavior_contract_id for row in rows)
    assert {row.expected_smoothness_class for row in rows} <= set(SMOOTHNESS_CLASSES)
    assert {row.expected_schema_wrestling_class for row in rows} <= set(SCHEMA_WRESTLING_CLASSES)
    assert {row.expected_next_up_specificity_class for row in rows} <= set(NEXT_UP_SPECIFICITY_CLASSES) | {None}
    assert {row.expected_mutation_guard_class for row in rows} <= {"no_write", "expected_write_only"}

    repo_root = Path(__file__).resolve().parents[2]
    for row in rows:
        for owner in (*row.source_owners, *row.test_owners):
            assert (repo_root / owner).exists(), f"{row.row_id} owner missing: {owner}"

    split_owner_by_scenario = {
        "missing_verification_blocks_required_closeout": "src/gpd/specs/workflows/execute-phase/verification-handoff.md",
        "gaps_found_verification_blocks": "src/gpd/specs/workflows/execute-phase/gap-reverification.md",
        "proof_bearing_without_passed_proof_redteam_blocks_closeout": (
            "src/gpd/specs/workflows/execute-phase/proof-critic-dispatch.md"
        ),
        "bounded_segment_blocks_closeout": "src/gpd/specs/workflows/execute-phase/checkpoint-resume.md",
        "closeout_readiness_read_only_no_mutation": "src/gpd/specs/workflows/execute-phase/closeout.md",
    }
    for scenario, split_owner in split_owner_by_scenario.items():
        if (repo_root / split_owner).is_file():
            assert split_owner in rows_by_scenario[scenario].source_owners


def test_phase4_completion_replay_rows_cover_required_completion_cases() -> None:
    rows = completion_replay_rows()

    assert {row.expected_finding for row in rows} >= {
        "missing_verification_blocks_closeout",
        "gaps_found_verification_blocks",
        "human_needed_verification_blocks",
        "expert_needed_verification_blocks",
        "passed_verification_allows_readiness",
        "bounded_segment_blocks_closeout",
        "proof_redteam_not_passed_blocks_closeout",
        "runtime_verify_work_suggestion",
        "closeout_readiness_read_only",
    }


def test_phase2_completion_replay_rows_are_provider_free_and_owned() -> None:
    rows = phase2_completion_replay_rows()
    expected_scenarios = {
        "direct_phase_complete_without_verification_blocks",
        "direct_phase_complete_with_non_passing_verification_blocks",
        "verified_not_closed_suggests_local_closeout_transition",
        "closed_phase_allows_next_phase_discussion",
    }

    assert {row.scenario for row in rows} == expected_scenarios
    assert {row.row_id for row in rows} == {"P4-COMP-10", "P4-COMP-11", "P4-COMP-12", "P4-COMP-13"}
    assert all(row.provider_launch_allowed is False for row in rows)
    assert all(row.network_allowed is False for row in rows)
    assert all(row.raw_artifacts_allowed is False for row in rows)
    assert all(row.runtime_scope == ("provider_free",) for row in rows)
    assert all(row.fixture_family.endswith("_class") for row in rows)
    assert all(row.expected_mutation_guard_class == "no_write" for row in rows)

    repo_root = Path(__file__).resolve().parents[2]
    for row in rows:
        for owner in (*row.source_owners, *row.test_owners):
            assert (repo_root / owner).exists(), f"{row.row_id} owner missing: {owner}"


@pytest.mark.parametrize("row", completion_replay_rows(), ids=lambda row: f"{row.row_id}-{row.scenario}")
def test_phase4_persona_completion_replay(
    row: CompletionReplayRow,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcome = score_completion_replay_row(row, tmp_path, monkeypatch)

    assert outcome.provider_launch_allowed is False
    assert outcome.network_allowed is False
    assert outcome.raw_artifacts_allowed is False
    assert outcome.finding_id == row.expected_finding
    assert outcome.result_class == row.expected_result_class
    assert row.expected_finding in outcome.finding_id
    assert outcome.read_only is True
    if row.expected_ready is not None:
        assert outcome.ready is row.expected_ready
    if row.expected_state_status_class is not None:
        assert outcome.state_status_class == row.expected_state_status_class
    if row.expected_next_action_class is not None:
        assert outcome.next_action_class == row.expected_next_action_class
    if row.expect_no_mutation:
        assert outcome.mutated is False
    assert_behavior_contract(row, outcome)


@pytest.mark.parametrize("row", phase2_completion_replay_rows(), ids=lambda row: f"{row.row_id}-{row.scenario}")
def test_phase2_persona_completion_replay(
    row: CompletionReplayRow,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcome = score_completion_replay_row(row, tmp_path, monkeypatch)

    assert outcome.provider_launch_allowed is False
    assert outcome.network_allowed is False
    assert outcome.raw_artifacts_allowed is False
    assert outcome.finding_id == row.expected_finding
    assert outcome.result_class == row.expected_result_class
    if row.expected_ready is not None:
        assert outcome.ready is row.expected_ready
    if row.expected_state_status_class is not None:
        assert outcome.state_status_class == row.expected_state_status_class
    if row.expected_next_action_class is not None:
        assert outcome.next_action_class == row.expected_next_action_class
    if row.scenario.startswith("direct_phase_complete"):
        assert outcome.read_only is False
        assert outcome.mutated is False
    else:
        assert outcome.read_only is True
    assert_behavior_contract(row, outcome)


def test_phase4_completion_runtime_verify_work_row_rejects_structural_verify_phase(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = next(row for row in completion_replay_rows() if row.row_id == "P4-COMP-08")

    outcome = score_completion_replay_row(row, tmp_path, monkeypatch)

    assert outcome.commands
    assert all("verify-work" in command for command in outcome.commands)
    assert all("gpd verify phase" not in command for command in outcome.commands)
    assert outcome.failure_classes == ("runtime_verify_work", "no_structural_verify_phase", "read_only")
    score = assert_behavior_contract(row, outcome)
    assert score.metric_counts["invalid_command_suggestion_count"] == 0
    assert score.metric_classes["next_up_specificity_class"] == "runtime_verify_work"


def test_phase4_completion_readiness_row_does_not_mutate_state_roadmap_or_checkpoint_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = next(row for row in completion_replay_rows() if row.row_id == "P4-COMP-09")

    outcome = score_completion_replay_row(row, tmp_path, monkeypatch)

    assert outcome.ready is True
    assert outcome.mutated is False
    assert outcome.result_class == "read_only_ready_closeout"
    assert outcome.next_action_class == "phase_complete"


def test_phase4_completion_replay_rows_pin_closeout_stop_classes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = {row.scenario: row for row in completion_replay_rows()}

    missing = score_completion_replay_row(
        rows["missing_verification_blocks_required_closeout"],
        tmp_path / "missing-verification",
        monkeypatch,
    )
    missing_score = assert_behavior_contract(rows["missing_verification_blocks_required_closeout"], missing)
    assert missing.ready is False
    assert missing.mutated is False
    assert "missing_verification" in missing.failure_classes
    assert "phase_closeout_readiness" in missing_score.structured_authority_sources
    assert missing_score.metric_counts["unsupported_completion_claim_count"] == 0

    proof = score_completion_replay_row(
        rows["proof_bearing_without_passed_proof_redteam_blocks_closeout"],
        tmp_path / "proof-redteam",
        monkeypatch,
    )
    proof_score = assert_behavior_contract(rows["proof_bearing_without_passed_proof_redteam_blocks_closeout"], proof)
    assert proof.ready is False
    assert proof.mutated is False
    assert {"proof_redteam_missing", "proof_redteam_non_passing", "proof_redteam_not_passed"} <= set(
        proof.failure_classes
    )
    assert "phase_closeout_readiness" in proof_score.structured_authority_sources

    for scenario, stop_class in {
        "human_needed_verification_blocks": "human_needed_stop",
        "expert_needed_verification_blocks": "expert_needed_stop",
    }.items():
        outcome = score_completion_replay_row(rows[scenario], tmp_path / scenario, monkeypatch)
        score = assert_behavior_contract(rows[scenario], outcome)

        assert outcome.ready is False
        assert outcome.state_status_class == "blocked"
        assert stop_class in outcome.failure_classes
        assert outcome.next_action_class == "verify_work"
        assert all("phase complete" not in command for command in outcome.commands)
        assert "verification_status" in score.structured_authority_sources
