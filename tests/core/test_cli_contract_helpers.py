"""Tests for shared CLI contract helper primitives."""

from __future__ import annotations

import json

import pytest
import typer

from tests.helpers.cli import (
    StableCliRunner,
    assert_cli_help_contract,
    assert_cli_human_contract,
    assert_cli_json_contract,
    assert_cli_json_subset,
    assert_cli_success,
    assert_no_traceback,
    cli_text,
)

sample_cli = typer.Typer()


@sample_cli.command()
def human() -> None:
    typer.echo("Alpha")
    typer.echo("  Beta")
    typer.echo("Gamma")


@sample_cli.command("json-payload")
def json_payload() -> None:
    typer.echo(
        json.dumps(
            {
                "status": "ok",
                "nested": {"count": 2, "label": "ready"},
                "items": [{"name": "first", "value": 1}, {"name": "second", "value": 2}],
                "extra": True,
            }
        )
    )


@sample_cli.command("traceback-text")
def traceback_text() -> None:
    typer.echo("Traceback (most recent call last):")


def test_cli_success_text_and_human_contract_normalize_output() -> None:
    result = StableCliRunner().invoke(sample_cli, ["human"])

    assert assert_cli_success(result) is result
    assert cli_text(result, normalized=True) == "Alpha Beta Gamma"
    assert "Alpha\n  Beta" in cli_text(result, normalized=False)

    text = assert_cli_human_contract(
        result,
        required_all=("Alpha Beta",),
        required_any=("Gamma", "Delta"),
        forbidden=("Traceback",),
    )

    assert text == "Alpha Beta Gamma"


def test_cli_human_contract_failure_lists_all_fragment_groups() -> None:
    with pytest.raises(AssertionError) as exc_info:
        assert_cli_human_contract(
            "Alpha Beta",
            required_all=("Missing",),
            required_any=("One", "Two"),
            forbidden=("Beta",),
        )

    message = str(exc_info.value)
    assert "missing required fragments: ['Missing']" in message
    assert "missing any required fragment from: ['One', 'Two']" in message
    assert "unexpected forbidden fragments: ['Beta']" in message
    assert "output:\nAlpha Beta" in message


def test_cli_json_contract_supports_recursive_subset_and_top_level_keys() -> None:
    result = StableCliRunner().invoke(sample_cli, ["json-payload"])

    payload = assert_cli_json_contract(
        result,
        expected_subset={
            "status": "ok",
            "nested": {"count": 2},
            "items": [{"name": "first"}],
        },
        required_keys=("status", "extra"),
        forbidden_keys=("traceback",),
    )

    assert payload["extra"] is True


def test_cli_json_subset_failure_reports_nested_path() -> None:
    with pytest.raises(AssertionError) as exc_info:
        assert_cli_json_subset(
            {"status": "ok", "nested": {"count": 2}},
            {"nested": {"count": 3}},
        )

    assert "$.nested.count: expected 3, got 2" in str(exc_info.value)


def test_cli_json_contract_rejects_non_object_payload_for_key_contracts() -> None:
    with pytest.raises(AssertionError, match="expected JSON object payload"):
        assert_cli_json_contract(["not", "an", "object"], required_keys=("status",))


def test_cli_help_contract_groups_commands_options_sections_and_forbidden() -> None:
    result = StableCliRunner().invoke(sample_cli, ["--help"])

    text = assert_cli_help_contract(
        result,
        commands=("human", "json-payload"),
        options=("--help",),
        sections=("Commands", "Options"),
        forbidden=("Traceback",),
    )

    assert "json-payload" in text


def test_cli_help_contract_failure_lists_help_groups() -> None:
    with pytest.raises(AssertionError) as exc_info:
        assert_cli_help_contract(
            "Usage: gpd\nOptions: --raw",
            commands=("missing-command",),
            options=("--json",),
            sections=("Commands:",),
            forbidden=("--raw",),
        )

    message = str(exc_info.value)
    assert "missing help commands: ['missing-command']" in message
    assert "missing help options: ['--json']" in message
    assert "missing help sections: ['Commands:']" in message
    assert "unexpected help fragments: ['--raw']" in message


def test_assert_no_traceback_detects_traceback_text() -> None:
    result = StableCliRunner().invoke(sample_cli, ["traceback-text"])

    with pytest.raises(AssertionError, match="unexpected traceback"):
        assert_no_traceback(result)
