"""Provider-free Phase 5 useful-action latency tests for large agents."""

from __future__ import annotations

import json
import re
from dataclasses import fields
from pathlib import Path

from tests.helpers.persona_trace import FakePersonaTrace, FakePersonaTurn
from tests.helpers.phase5_agent_latency import (
    PHASE5_AGENT_LATENCY_MATRIX_PATH,
    REQUIRED_PHASE5_AGENT_LATENCY_ROW_IDS,
    ROW_TIERS,
    Phase5AgentLatencyRow,
    load_phase5_agent_latency_rows,
    score_phase5_agent_latency_row,
    score_phase5_agent_latency_rows,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

AGENT_USEFUL_ACTION_EXPECTATIONS = {
    "P5-AGENT-LAT-01": ("gpd-referee", "gpd_referee", "claim_evidence_audit", "claim_evidence_review"),
    "P5-AGENT-LAT-02": (
        "gpd-verifier",
        "gpd_verifier",
        "verification_target_selection",
        "contract_target_review",
    ),
    "P5-AGENT-LAT-03": ("gpd-planner", "gpd_planner", "phase_decomposition", "dependency_graph_started"),
    "P5-AGENT-LAT-04": ("gpd-paper-writer", "gpd_paper_writer", "section_architecture", "section_claim_mapped"),
}


def test_phase5_agent_latency_fixture_contains_required_provider_free_rows() -> None:
    rows = load_phase5_agent_latency_rows()
    scores = score_phase5_agent_latency_rows(rows)
    row_ids = {row.row_id for row in rows}

    assert row_ids == REQUIRED_PHASE5_AGENT_LATENCY_ROW_IDS
    assert {row.row_tier for row in rows} <= ROW_TIERS
    assert {score.row.row_id for score in scores} == REQUIRED_PHASE5_AGENT_LATENCY_ROW_IDS
    assert all(row.provider_launch_allowed is False for row in rows)
    assert all(row.network_allowed is False for row in rows)
    assert all(row.raw_artifacts_allowed is False for row in rows)
    assert all(row.test_owners == ("tests/core/test_phase5_agent_latency.py",) for row in rows)


def test_phase5_agent_latency_fixture_has_no_raw_transcripts_or_provider_fields() -> None:
    payload = json.loads(PHASE5_AGENT_LATENCY_MATRIX_PATH.read_text(encoding="utf-8"))
    forbidden_keys = {
        "raw_prompt",
        "raw_reply",
        "raw_transcript",
        "provider_stdout",
        "provider_stderr",
        "provider_argv",
        "provider_env",
        "provider_path",
        "provider_account",
        "api_key",
        "token",
        "secret",
    }
    row_fields = {field.name for field in fields(Phase5AgentLatencyRow)}

    assert forbidden_keys.isdisjoint(row_fields)
    for row in payload["rows"]:
        assert forbidden_keys.isdisjoint(row)
        assert row.get("provider_launch_allowed", False) is False
        assert row.get("network_allowed", False) is False
        assert row.get("raw_artifacts_allowed", False) is False
        _assert_fixture_values_are_provider_free(row)


def test_phase5_agent_latency_rows_start_with_role_work() -> None:
    rows = load_phase5_agent_latency_rows()

    for row in rows:
        agent_name, persona_class, intent_class, progress_class = AGENT_USEFUL_ACTION_EXPECTATIONS[row.row_id]
        score = score_phase5_agent_latency_row(row)
        first = score.trace.turns[0]

        assert row.agent_name == agent_name
        assert row.persona_class == persona_class
        assert first.turn_index == 0
        assert first.intent_class == intent_class
        assert first.physics_progress_class == progress_class
        assert first.schema_surface_class == "none"
        assert score.passed
        assert score.hard_budget_failures == ()
        assert score.metric_classes["first_useful_action_class"] == "immediate_command"
        assert score.metric_classes["useful_work_latency_class"] == "first_turn"
        assert score.metric_classes["physics_to_schema_ratio_class"] == "progress_dominant"
        assert score.metric_counts["schema_surface_count"] == 0
        assert score.metric_counts["physics_progress_count"] >= 1
        assert score.metric_counts["conversation_turn_count"] == 1


def test_phase5_agent_latency_rows_reject_schema_first_trace() -> None:
    for row in load_phase5_agent_latency_rows():
        _agent_name, _persona_class, useful_intent, useful_progress = AGENT_USEFUL_ACTION_EXPECTATIONS[row.row_id]
        score = score_phase5_agent_latency_row(
            row,
            trace_override=FakePersonaTrace(
                row_id=f"{row.row_id}-BAD-SCHEMA-FIRST",
                persona_class=row.persona_class,
                prompt_variant_class=row.prompt_variant_class,
                turns=(
                    FakePersonaTurn(
                        turn_index=0,
                        speaker_class="assistant",
                        intent_class="schema_explanation",
                        action_class="schema_surface",
                        schema_surface_class="return_schema_wall",
                    ),
                    FakePersonaTurn(
                        turn_index=1,
                        speaker_class="assistant",
                        intent_class=useful_intent,
                        action_class="concrete_command",
                        physics_progress_class=useful_progress,
                    ),
                ),
            ),
        )

        assert not score.passed
        assert score.metric_classes["first_useful_action_class"] == "delayed"
        assert score.metric_classes["useful_work_latency_class"] == "second_turn"
        assert score.metric_counts["schema_surface_count"] == 1
        assert score.metric_counts["physics_progress_count"] == 1
        assert score.metric_counts["conversation_turn_count"] == 2
        assert "schema_surface_count" in score.hard_budget_failures
        assert "conversation_turn_count" in score.hard_budget_failures


def test_phase5_agent_latency_rows_reject_schema_only_trace() -> None:
    for row in load_phase5_agent_latency_rows():
        score = score_phase5_agent_latency_row(
            row,
            trace_override=FakePersonaTrace(
                row_id=f"{row.row_id}-BAD-SCHEMA-ONLY",
                persona_class=row.persona_class,
                prompt_variant_class=row.prompt_variant_class,
                turns=(
                    FakePersonaTurn(
                        turn_index=0,
                        speaker_class="assistant",
                        intent_class="schema_explanation",
                        action_class="schema_surface",
                        schema_surface_class="return_schema_wall",
                    ),
                ),
            ),
        )

        assert not score.passed
        assert score.metric_classes["first_useful_action_class"] == "missing"
        assert score.metric_classes["useful_work_latency_class"] == "missing"
        assert score.metric_counts["physics_progress_count"] == 0
        assert score.metric_counts["schema_surface_count"] == 1
        assert "physics_progress_count" in score.hard_budget_failures
        assert "schema_surface_count" in score.hard_budget_failures


def _assert_fixture_values_are_provider_free(row: dict[str, object]) -> None:
    forbidden_value_fragments = (
        "raw_prompt",
        "raw_reply",
        "raw_transcript",
        "transcript_excerpt",
        "provider_stdout",
        "provider_stderr",
        "auth_path",
        "subprocess",
        "socket",
        "urllib",
        "requests",
    )
    absolute_path_re = re.compile(
        r"(?<![A-Za-z0-9_])(?:/(?:Users|home|private|tmp|var|etc|Volumes|opt|mnt|root)\b|~[/\\])"
    )
    account_re = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    hash_re = re.compile(r"\b(?:[A-Fa-f0-9]{32}|[A-Fa-f0-9]{40}|[A-Fa-f0-9]{64})\b")
    secret_env_re = re.compile(r"\b[A-Z][A-Z0-9_]*(?:API_KEY|AUTH_TOKEN|ACCESS_TOKEN|SECRET|TOKEN)\b")

    for value in _fixture_string_values(row):
        lowered = value.lower()
        assert not any(fragment in lowered for fragment in forbidden_value_fragments), value
        assert absolute_path_re.search(value) is None, value
        assert account_re.search(value) is None, value
        assert hash_re.search(value) is None, value
        assert secret_env_re.search(value) is None, value


def _fixture_string_values(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, dict):
        return tuple(child for item in value.values() for child in _fixture_string_values(item))
    if isinstance(value, list):
        return tuple(child for item in value for child in _fixture_string_values(item))
    return ()
