"""Prompt-budget assertions for `gpd-notation-coordinator` microcompression."""

from __future__ import annotations

from pathlib import Path

from tests.prompt_metrics_support import measure_prompt_surface

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPO_ROOT / "src" / "gpd"
AGENT_PATH = SOURCE_ROOT / "agents" / "gpd-notation-coordinator.md"
CONVENTION_REFS = SOURCE_ROOT / "specs" / "references" / "conventions"
PLAYBOOK_PATH = CONVENTION_REFS / "convention-coordinator-playbook.md"
PATH_PREFIX = "/runtime/"


def _read_agent() -> str:
    return AGENT_PATH.read_text(encoding="utf-8")


def test_expanded_notation_coordinator_prompt_stays_under_slice4_budget() -> None:
    agent = _read_agent()
    metrics = measure_prompt_surface(
        AGENT_PATH,
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )

    assert metrics.raw_include_count == 0
    assert len(agent) < 21_000
    assert metrics.expanded_line_count < 420
    assert metrics.expanded_char_count < 26_000


def test_notation_base_prompt_keeps_authority_and_return_contract_visible() -> None:
    agent = _read_agent()

    for required in (
        "OWNS CONVENTIONS.md",
        "only agent that creates, modifies, or extends",
        "state.json.convention_lock` is authoritative",
        "gpd convention set",
        "convention source of truth",
        "gpd return skeleton --role notation_coordinator --status <status>",
        "files_written: []",
        "conventions_file: GPD/CONVENTIONS.md",
        "CONVENTIONS.md is the projection/audit surface",
        "test_values_defined",
        "change_id",
        "conflicts",
    ):
        assert required in agent


def test_notation_optional_examples_and_tables_are_late_loaded() -> None:
    agent = _read_agent()
    playbook = PLAYBOOK_PATH.read_text(encoding="utf-8")

    assert "references/conventions/convention-coordinator-playbook.md" in agent
    assert PLAYBOOK_PATH.is_file()

    for moved_marker in (
        "Auto-Suggested Conventions for QFT in Curved Spacetime",
        "Extended Convention Interactions (18-Type Coverage)",
        "Numerical Factor Registry",
        "Metric Signature Conversion (+,-,-,- <-> -,+,+,+)",
        "Recovery from partial rollback",
    ):
        assert moved_marker not in agent

    for retained_marker in (
        "CONVENTION NEEDED",
        "QFT in curved spacetime",
        "Cross-Convention Interaction Tables",
        "Convention Changes And Rollback",
        "Conversion Table Templates",
    ):
        assert retained_marker in playbook
