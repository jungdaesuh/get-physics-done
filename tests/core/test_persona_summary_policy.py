"""Unit coverage for shared class-only persona summary validation."""

from __future__ import annotations

import pytest

from scripts.validate_phase4_persona_summary import validate_summary as validate_phase4_script_summary
from tests.helpers.persona_summary import (
    make_phase4_live_smoke_summary,
    make_phase7_live_canary_summary,
    phase4_live_smoke_policy,
    phase7_live_canary_policy,
    provider_launch_command_in_text,
    validate_persona_summary,
)
from tests.helpers.phase7_live_like import phase7_fixture_rows_by_id


def _first_row(summary: dict[str, object]) -> dict[str, object]:
    rows = summary["rows"]
    assert isinstance(rows, list)
    row = rows[0]
    assert isinstance(row, dict)
    return row


def _has_finding(findings: tuple[str, ...], prefix: str, suffix: str = "") -> bool:
    return any(finding.startswith(prefix) and finding.endswith(suffix) for finding in findings)


@pytest.mark.parametrize(
    ("summary", "policy"),
    [
        (make_phase4_live_smoke_summary(), phase4_live_smoke_policy()),
        (make_phase7_live_canary_summary(), phase7_live_canary_policy()),
    ],
)
def test_persona_summary_policy_accepts_generated_public_summaries(summary: object, policy: object) -> None:
    result = validate_persona_summary(summary, policy)

    assert result.valid is True
    assert result.findings == ()


def test_phase7_public_summary_seed_row_uses_canonical_manifest_id() -> None:
    row = _first_row(make_phase7_live_canary_summary())

    assert row["row_id"] == "LP01-START-PROJECTLESS-READONLY"
    assert row["row_id"] in phase7_fixture_rows_by_id()


def test_phase7_summary_policy_rejects_raw_material_on_canonical_seed_row() -> None:
    summary = make_phase7_live_canary_summary()
    _first_row(summary)["provider_reply"] = "redacted"

    result = validate_persona_summary(summary, phase7_live_canary_policy())

    assert result.valid is False
    assert "forbidden_key:rows.0.provider_reply" in result.findings


@pytest.mark.parametrize("raw_key", ["raw_prompt_class", "stdout_count", "env_counts"])
def test_phase4_script_and_shared_helper_both_reject_raw_suffix_keys(raw_key: str) -> None:
    summary = make_phase4_live_smoke_summary()
    _first_row(summary)[raw_key] = 0 if raw_key.endswith(("_count", "_counts")) else "redacted"

    script_result = validate_phase4_script_summary(summary)
    helper_result = validate_persona_summary(summary, phase4_live_smoke_policy())

    assert script_result.valid is False
    assert helper_result.valid is False


@pytest.mark.parametrize(
    "raw_key",
    [
        "raw_prompt",
        "stdout",
        "stderr",
        "argv",
        "env",
        "auth_path",
        "account_id",
        "absolute_path",
        "provider_prompt",
        "provider_reply",
        "provider_output",
        "transcript",
        "transcript_path",
        "command_line",
        "file_hash",
        "token_value",
        "note",
        "request_id_class",
        "session_id",
        "trace_id_class",
        "usage_json_class",
        "home_path",
        "provider_session_url_class",
        "runtime_home_alias_class",
        "raw_diff_sidecar_class",
        "provider_command_details_class",
        "raw_prompt_class",
        "provider_reply_class",
        "command_line_class",
        "auth_path_class",
        "file_hash_class",
        "stdout_count",
        "stderr_counts",
        "argv_class",
        "env_counts",
        "secret_classes",
    ],
)
@pytest.mark.parametrize(
    ("summary_factory", "policy"),
    [
        (make_phase4_live_smoke_summary, phase4_live_smoke_policy()),
        (make_phase7_live_canary_summary, phase7_live_canary_policy()),
    ],
)
def test_persona_summary_policy_rejects_raw_keys_even_with_class_or_count_suffix(
    raw_key: str,
    summary_factory: object,
    policy: object,
) -> None:
    summary = summary_factory()
    _first_row(summary)[raw_key] = 0 if raw_key.endswith(("_count", "_counts")) else "redacted"

    result = validate_persona_summary(summary, policy)

    assert any(finding.startswith("forbidden_key:") for finding in result.findings)


@pytest.mark.parametrize(
    "raw_value",
    [
        "Prompt text: run the whole phase and tell me the answer",
        "raw prompt: run the whole phase and tell me the answer",
        "raw prompt: run this exact provider input",
        "provider_prompt: launch with this exact input",
        "provider_prompt: run this exact input",
        "raw provider reply: the derivation is complete",
        "assistant_reply",
        "model_reply",
        "model-reply",
        "provider_reply:accepted",
        "provider_output: final answer text",
        "provider_stdout",
        "provider_stderr",
        "provider_argv",
        "provider_env",
        "transcript excerpt from provider",
        "stdout",
        "stderr",
        "argv",
        "env",
        "command line: gpd progress --raw",
        "req_01HF7YAT00EXAMPLE",
        "trace_01HF7YAT00EXAMPLE",
        "usage_json",
        "https://chat.openai.com/c/session_abc123",
        "CODEX_HOME",
        "raw_diff_sidecar.patch",
        "provider_command_details",
        "stdout.jsonl",
        "stderr.txt",
        "prompt.enveloped.txt",
        "provider-output.log",
        "/Users/example/.codex/auth.json",
        r"C:\Users\example\.gemini",
        "../outside/transcript.md",
        "researcher@example.com",
        "0123456789abcdef0123456789abcdef01234567",
        "OPENAI_API_KEY",
        "api_key",
        "client_secret",
        "secret",
        "Bearer sk-test-secret",
        "Bearer sk-testsecret1234567890",
        "ghp_0123456789abcdef0123456789abcdef",
        "github_pat_0123456789abcdef0123456789abcdef",
        "a" * 48,
    ],
)
@pytest.mark.parametrize(
    ("summary_factory", "policy"),
    [
        (make_phase4_live_smoke_summary, phase4_live_smoke_policy()),
        (make_phase7_live_canary_summary, phase7_live_canary_policy()),
    ],
)
def test_persona_summary_policy_rejects_raw_values_in_public_string_lists(
    raw_value: str,
    summary_factory: object,
    policy: object,
) -> None:
    summary = summary_factory()
    _first_row(summary)["finding_classes"] = [raw_value]

    result = validate_persona_summary(summary, policy)

    assert any(finding.startswith("raw_value:") for finding in result.findings)


def test_persona_summary_policy_rejects_raw_values_under_class_count_and_counts() -> None:
    summary = make_phase7_live_canary_summary()
    row = _first_row(summary)
    row["result_class"] = "provider reply"
    row["provider_leak_count"] = "stdout"
    row["event_class_counts"] = {"raw_prompt": "stderr"}

    result = validate_persona_summary(summary, phase7_live_canary_policy())

    assert _has_finding(result.findings, "raw_value:provider_prompt_or_reply:", ".result_class")
    assert _has_finding(result.findings, "forbidden_key:", ".provider_leak_count")
    assert _has_finding(result.findings, "raw_value:raw_stream_or_capture:", ".provider_leak_count")
    assert _has_finding(result.findings, "invalid_count_value:", ".provider_leak_count")
    assert _has_finding(result.findings, "raw_value:count_key:", ".raw_prompt")
    assert _has_finding(result.findings, "raw_value:raw_stream_or_capture:", ".raw_prompt")
    assert _has_finding(result.findings, "invalid_count_value:", ".raw_prompt")


@pytest.mark.parametrize("value", ["two words", "class/with/slash"])
def test_persona_summary_policy_rejects_non_class_token_strings(value: str) -> None:
    summary = make_phase7_live_canary_summary()
    _first_row(summary)["result_class"] = value

    result = validate_persona_summary(summary, phase7_live_canary_policy())

    assert any(finding.startswith("raw_value:non_class_token:") for finding in result.findings)


@pytest.mark.parametrize("value", [True, -1, "1", 1.5])
def test_persona_summary_policy_rejects_invalid_scalar_counts(value: object) -> None:
    summary = make_phase7_live_canary_summary()
    summary["row_count"] = value

    result = validate_persona_summary(summary, phase7_live_canary_policy())

    assert any(finding.startswith("invalid_count_value:row_count") for finding in result.findings)


def test_persona_summary_policy_rejects_missing_required_row_count() -> None:
    summary = make_phase7_live_canary_summary()
    del summary["row_count"]

    result = validate_persona_summary(summary, phase7_live_canary_policy())

    assert "required_policy:row_count" in result.findings


@pytest.mark.parametrize(
    "count_map",
    [
        {"blocked": True},
        {"blocked": -1},
        {"blocked": "1"},
        {"blocked": 1.5},
        {"stdout": 1},
    ],
)
def test_persona_summary_policy_rejects_invalid_count_maps(count_map: dict[str, object]) -> None:
    summary = make_phase7_live_canary_summary()
    summary["aggregate_class_counts"] = count_map

    result = validate_persona_summary(summary, phase7_live_canary_policy())

    assert result.valid is False


@pytest.mark.parametrize(
    ("field_name", "field_value", "expected_finding"),
    [
        ("row_count", 2, "required_policy:row_count"),
        ("rows", {"row_id": "LP-RO-RUNTIME"}, "required_policy:rows"),
    ],
)
def test_persona_summary_policy_rejects_row_count_or_rows_shape_errors(
    field_name: str, field_value: object, expected_finding: str
) -> None:
    summary = make_phase7_live_canary_summary()
    summary[field_name] = field_value

    result = validate_persona_summary(summary, phase7_live_canary_policy())

    assert expected_finding in result.findings


def test_persona_summary_policy_rejects_failing_redaction_scan() -> None:
    summary = make_phase7_live_canary_summary()
    redaction_scan = summary["redaction_scan"]
    assert isinstance(redaction_scan, dict)
    redaction_scan["status_class"] = "fail"

    result = validate_persona_summary(summary, phase7_live_canary_policy())

    assert _has_finding(result.findings, "required_policy:", "redaction_scan.status_class")


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("schema_version", "phase7.live-persona-canary-summary.v0"),
        ("execution_mode_class", "automatic"),
        ("trigger_class", "pull_request"),
        ("ci_provider_launch_allowed", True),
        ("release_publish_provider_launch_allowed", True),
        ("nightly_allowed_triggers", ["pull_request"]),
    ],
)
def test_persona_summary_policy_rejects_incorrect_required_policy(field_name: str, field_value: object) -> None:
    summary = make_phase7_live_canary_summary()
    summary[field_name] = field_value

    result = validate_persona_summary(summary, phase7_live_canary_policy())

    assert any(finding.startswith(f"required_policy:{field_name}") for finding in result.findings)


@pytest.mark.parametrize(
    "command_line",
    [
        "codex exec --json -o output.json -",
        "env FOO=bar uv run codex exec -",
        "time command claude --print hello",
        "npx opencode run",
        "npm exec gemini -- --prompt hello",
    ],
)
def test_persona_summary_policy_rejects_provider_command_lines_through_shell_wrappers(
    command_line: str,
) -> None:
    summary = make_phase7_live_canary_summary()
    _first_row(summary)["next_step_class"] = command_line

    result = validate_persona_summary(summary, phase7_live_canary_policy())

    assert provider_launch_command_in_text(command_line) is not None
    assert any(finding.startswith("raw_value:provider_command_line:") for finding in result.findings)


def test_make_summary_helpers_return_independent_copies() -> None:
    first = make_phase7_live_canary_summary()
    second = make_phase7_live_canary_summary()
    _first_row(first)["result_class"] = "changed"

    assert _first_row(second)["result_class"] == "blocked"


def test_phase7_summary_policy_accepts_shadow_live_class_count_observation_fields() -> None:
    summary = make_phase7_live_canary_summary()
    row = _first_row(summary)
    row.update(
        {
            "shadow_live_mode_class": "manual_observation_only",
            "artifact_policy_class": "operator_ignored_tmp",
            "summary_policy_class": "classes_and_counts_only",
            "shadow_live_event_counts": {"manual_row_observed": 1, "redaction_pass": 1},
        }
    )

    result = validate_persona_summary(summary, phase7_live_canary_policy())

    assert result.valid is True
    assert result.findings == ()


def test_phase7_summary_policy_accepts_ergonomic_class_counts() -> None:
    summary = make_phase7_live_canary_summary()
    row = _first_row(summary)
    row.update(
        {
            "useful_work_latency_class": "first_turn",
            "reload_loop_class": "no_reload_loop",
            "instruction_injection_timing_class": "active_stage_only",
            "runtime_route_class": "active_runtime",
            "ergonomic_score_class": "green",
            "conversation_turn_count": 1,
            "physics_progress_count": 1,
            "schema_surface_count": 0,
            "invalid_command_suggestion_count": 0,
            "schema_repair_loop_count": 0,
            "raw_reload_leakage_count": 0,
            "content_hydration_before_selection_count": 0,
        }
    )

    result = validate_persona_summary(summary, phase7_live_canary_policy())

    assert result.valid is True
    assert result.findings == ()
