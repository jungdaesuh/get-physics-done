from __future__ import annotations

import pytest

from gpd.adapters.runtime_catalog import iter_runtime_descriptors
from gpd.command_labels import runtime_public_command_prefixes
from gpd.core.command_run_hints import (
    KIND_LOCAL_CLI_FINALIZER_COMMAND,
    KIND_LOCAL_CLI_HELPER_COMMAND,
    KIND_LOCAL_CLI_TRANSITION_COMMAND,
    KIND_LOCAL_CLI_VALIDATION_COMMAND,
    KIND_RUNTIME_COMMAND_LABEL,
    KIND_UNKNOWN_DISPLAY_ONLY,
    NEXT_COMMAND_OWNER_DISPLAY_ONLY,
    NEXT_COMMAND_OWNER_LOCAL_FINALIZER,
    NEXT_COMMAND_OWNER_LOCAL_HELPER,
    NEXT_COMMAND_OWNER_LOCAL_READONLY,
    NEXT_COMMAND_OWNER_LOCAL_TRANSITION,
    NEXT_COMMAND_OWNER_RUNTIME,
    NEXT_COMMAND_SURFACE_CONTEXT_ACTIVE_RUNTIME,
    build_command_run_hint,
    classify_next_command,
)
from gpd.core.public_surface_contract import local_cli_bridge_commands


def _runtime_command(slug: str, *args: str) -> str:
    prefix = runtime_public_command_prefixes()[0]
    suffix = f" {' '.join(args)}" if args else ""
    return f"{prefix}{slug}{suffix}"


def _local_cli_command_example(command: str) -> str:
    runtime_name = iter_runtime_descriptors()[0].runtime_name
    return command.replace("<runtime>", runtime_name).replace("<mode>", "review").replace("<PLAN.md>", "GPD/PLAN.md")


def test_runtime_command_label_gets_non_executing_run_hint() -> None:
    command = _runtime_command("verify-work", "02")

    hint = build_command_run_hint(command=command, source="test", action="verify-work", phase="02")

    assert hint is not None
    assert hint["schema_version"] == 1
    assert hint["source"] == "test"
    assert hint["kind"] == KIND_RUNTIME_COMMAND_LABEL
    assert hint["command"] == command
    assert hint["action"] == "verify-work"
    assert hint["phase"] == "02"
    assert hint["execution"] == "not_executed"
    assert hint["requires_user_initiated_runtime_command"] is True
    assert hint["fresh_context_recommended"] is True
    assert "owner" not in hint


def test_next_command_runtime_label_gets_typed_decision_and_legacy_run_hint() -> None:
    command = "gpd:verify-work 02"

    next_command = classify_next_command(
        command=command,
        action="verify-work",
        phase="02",
        reason="Phase 02 is complete but unverified",
    )

    assert next_command is not None
    assert next_command.label == command
    assert next_command.command == command
    assert next_command.action == "verify-work"
    assert next_command.phase == "02"
    assert next_command.owner == NEXT_COMMAND_OWNER_RUNTIME
    assert next_command.reason == "Phase 02 is complete but unverified"
    assert next_command.kind == KIND_RUNTIME_COMMAND_LABEL
    assert next_command.requires_user_initiated_runtime_command is True
    assert next_command.fresh_context_recommended is True
    assert next_command.as_dict()["owner"] == NEXT_COMMAND_OWNER_RUNTIME
    assert next_command.as_run_hint(source="test") == build_command_run_hint(
        command=command,
        source="test",
        action="verify-work",
        phase="02",
    )


@pytest.mark.parametrize("command", [None, "", "   "])
def test_empty_command_returns_no_hint(command: str | None) -> None:
    assert build_command_run_hint(command=command, source="test") is None


def test_unknown_command_is_display_only() -> None:
    hint = build_command_run_hint(command="python -m gpd.cli suggest", source="test", action="suggest")

    assert hint is not None
    assert hint["kind"] == KIND_UNKNOWN_DISPLAY_ONLY
    assert hint["execution"] == "not_executed"
    assert hint["requires_user_initiated_runtime_command"] is False
    assert hint["fresh_context_recommended"] is False
    assert "unrecognized_command_display_only" in hint["notes"]


def test_structural_verify_phase_route_is_not_runtime_verify_work_hint() -> None:
    hint = build_command_run_hint(command="gpd verify phase 02", source="test", action="verify-work", phase="02")

    assert hint is not None
    assert hint["kind"] == KIND_UNKNOWN_DISPLAY_ONLY
    assert hint["execution"] == "not_executed"
    assert hint["requires_user_initiated_runtime_command"] is False
    assert "structural_verify_phase_display_only" in hint["notes"]
    assert "unrecognized_command_display_only" in hint["notes"]

    next_command = classify_next_command(command="gpd verify phase 02", action="verify-work", phase="02")
    assert next_command is not None
    assert next_command.owner == NEXT_COMMAND_OWNER_DISPLAY_ONLY
    assert next_command.kind == KIND_UNKNOWN_DISPLAY_ONLY


def test_bare_skill_label_is_display_only_in_shared_next_up_context() -> None:
    next_command = classify_next_command(command="gpd-verify-work 02", action="verify-work", phase="02")

    assert next_command is not None
    assert next_command.owner == NEXT_COMMAND_OWNER_DISPLAY_ONLY
    assert next_command.kind == KIND_UNKNOWN_DISPLAY_ONLY
    assert next_command.requires_user_initiated_runtime_command is False
    assert "runtime_label_not_valid_for_surface_context" in next_command.notes

    hint = build_command_run_hint(command="gpd-verify-work 02", source="test", action="verify-work", phase="02")
    assert hint is not None
    assert hint["kind"] == KIND_UNKNOWN_DISPLAY_ONLY
    assert hint["requires_user_initiated_runtime_command"] is False


def test_active_runtime_dollar_label_requires_active_runtime_context() -> None:
    active_runtime_prefix = next(
        (prefix for prefix in runtime_public_command_prefixes() if prefix.startswith("$")), None
    )
    if active_runtime_prefix is None:
        pytest.skip("Dollar runtime prefix is not registered")
    command = f"{active_runtime_prefix}verify-work 02"

    shared = classify_next_command(command=command, action="verify-work", phase="02")
    active = classify_next_command(
        command=command,
        action="verify-work",
        phase="02",
        surface_context=NEXT_COMMAND_SURFACE_CONTEXT_ACTIVE_RUNTIME,
        active_runtime_public_prefix=active_runtime_prefix,
    )

    assert shared is not None
    assert shared.owner == NEXT_COMMAND_OWNER_DISPLAY_ONLY
    assert shared.kind == KIND_UNKNOWN_DISPLAY_ONLY
    assert active is not None
    assert active.owner == NEXT_COMMAND_OWNER_RUNTIME
    assert active.kind == KIND_RUNTIME_COMMAND_LABEL
    assert active.requires_user_initiated_runtime_command is True


def test_shell_metacharacters_are_not_classified_as_executable_runtime_labels() -> None:
    command = f"{_runtime_command('verify-work', '02')} && echo should-not-run"

    hint = build_command_run_hint(command=command, source="test", action="verify-work", phase="02")

    assert hint is not None
    assert hint["kind"] == KIND_UNKNOWN_DISPLAY_ONLY
    assert hint["execution"] == "not_executed"
    assert "shell_control_tokens_present" in hint["notes"]
    assert "display_only" in hint["notes"]


def test_contract_local_validation_commands_are_display_copy_safe() -> None:
    commands = tuple(
        _local_cli_command_example(command)
        for command in local_cli_bridge_commands()
        if command.startswith("gpd validate ")
    )
    assert commands

    for command in commands:
        hint = build_command_run_hint(command=command, source="test")

        assert hint is not None
        assert hint["kind"] == KIND_LOCAL_CLI_VALIDATION_COMMAND
        assert hint["execution"] == "not_executed"
        assert hint["requires_user_initiated_runtime_command"] is False
        assert hint["fresh_context_recommended"] is False
        assert "display_copy_safe" in hint["notes"]

        next_command = classify_next_command(command=command)
        assert next_command is not None
        assert next_command.owner == NEXT_COMMAND_OWNER_LOCAL_READONLY
        assert next_command.kind == KIND_LOCAL_CLI_VALIDATION_COMMAND


def test_local_validation_family_commands_remain_display_copy_safe() -> None:
    hint = build_command_run_hint(
        command="gpd validate verification-contract GPD/verification.md",
        source="test",
    )

    assert hint is not None
    assert hint["kind"] == KIND_LOCAL_CLI_VALIDATION_COMMAND
    assert hint["execution"] == "not_executed"
    assert hint["requires_user_initiated_runtime_command"] is False
    assert hint["fresh_context_recommended"] is False
    assert "display_copy_safe" in hint["notes"]


@pytest.mark.parametrize(
    "command",
    [
        "gpd verification-report finalize --plan GPD/PLAN.md",
        "gpd proof-redteam finalize --phase 02",
        "gpd apply-return-updates --phase 02",
    ],
)
def test_local_finalizer_commands_are_display_copy_safe(command: str) -> None:
    hint = build_command_run_hint(command=command, source="test")

    assert hint is not None
    assert hint["kind"] == KIND_LOCAL_CLI_FINALIZER_COMMAND
    assert hint["execution"] == "not_executed"
    assert hint["requires_user_initiated_runtime_command"] is False
    assert hint["fresh_context_recommended"] is False
    assert "display_copy_safe" in hint["notes"]

    next_command = classify_next_command(command=command)
    assert next_command is not None
    assert next_command.owner == NEXT_COMMAND_OWNER_LOCAL_FINALIZER
    assert next_command.kind == KIND_LOCAL_CLI_FINALIZER_COMMAND


@pytest.mark.parametrize(
    "command",
    [
        "gpd phase complete 02",
        "gpd state record-verification --phase 02",
    ],
)
def test_local_transition_commands_have_distinct_owner(command: str) -> None:
    next_command = classify_next_command(command=command, action="phase-complete", phase="02")
    hint = build_command_run_hint(command=command, source="test", action="phase-complete", phase="02")

    assert next_command is not None
    assert next_command.owner == NEXT_COMMAND_OWNER_LOCAL_TRANSITION
    assert next_command.kind == KIND_LOCAL_CLI_TRANSITION_COMMAND
    assert hint is not None
    assert hint["kind"] == KIND_LOCAL_CLI_TRANSITION_COMMAND
    assert hint["requires_user_initiated_runtime_command"] is False


def test_checkpoint_cleanup_command_is_local_helper() -> None:
    command = "gpd --raw phase checkpoint cleanup --phase 02 --namespace phase --policy successful-closeout"

    hint = build_command_run_hint(command=command, source="test")

    assert hint is not None
    assert hint["kind"] == KIND_LOCAL_CLI_HELPER_COMMAND
    assert hint["execution"] == "not_executed"
    assert hint["requires_user_initiated_runtime_command"] is False
    assert hint["fresh_context_recommended"] is False
    assert "display_copy_safe" in hint["notes"]

    next_command = classify_next_command(command=command)
    assert next_command is not None
    assert next_command.owner == NEXT_COMMAND_OWNER_LOCAL_HELPER
    assert next_command.kind == KIND_LOCAL_CLI_HELPER_COMMAND


@pytest.mark.parametrize(
    "command",
    [
        "gpd phase closeout-readiness 02 --require-verification",
        "gpd --raw phase closeout-readiness --phase 02 --require-verification",
    ],
)
def test_phase_closeout_readiness_command_is_local_readonly(command: str) -> None:
    next_command = classify_next_command(command=command, action="closeout-readiness", phase="02")
    hint = build_command_run_hint(command=command, source="test", action="closeout-readiness", phase="02")

    assert next_command is not None
    assert next_command.owner == NEXT_COMMAND_OWNER_LOCAL_READONLY
    assert next_command.kind == KIND_LOCAL_CLI_VALIDATION_COMMAND
    assert hint is not None
    assert hint["kind"] == KIND_LOCAL_CLI_VALIDATION_COMMAND
    assert hint["requires_user_initiated_runtime_command"] is False


@pytest.mark.parametrize(
    ("command", "expected_note"),
    [
        ("gpd --raw init verify-work 02 --stage session_router", "raw_staged_init_display_only"),
        ("--raw init verify-work 02 --stage session_router", "raw_staged_init_display_only"),
        (
            "gpd --raw stage field-access verify-work --stage session_router --style instruction",
            "raw_stage_field_access_display_only",
        ),
        (
            "--raw stage field-access verify-work --stage session_router --style instruction",
            "raw_stage_field_access_display_only",
        ),
    ],
)
def test_raw_loader_commands_are_explicitly_display_only(command: str, expected_note: str) -> None:
    next_command = classify_next_command(command=command, action="verify-work", phase="02")
    hint = build_command_run_hint(command=command, source="test", action="verify-work", phase="02")

    assert next_command is not None
    assert next_command.owner == NEXT_COMMAND_OWNER_DISPLAY_ONLY
    assert next_command.kind == KIND_UNKNOWN_DISPLAY_ONLY
    assert expected_note in next_command.notes
    assert hint is not None
    assert hint["kind"] == KIND_UNKNOWN_DISPLAY_ONLY
    assert hint["requires_user_initiated_runtime_command"] is False
    assert expected_note in hint["notes"]
