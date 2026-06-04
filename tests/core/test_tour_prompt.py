from __future__ import annotations

from pathlib import Path

from gpd.adapters.install_utils import expand_at_includes
from gpd.core.onboarding_surfaces import beginner_startup_ladder_text
from gpd.registry import get_command, list_commands
from tests.assertion_taxonomy_support import FragmentMode, forbidden_duplicate, fragment_count, semantic_anchor
from tests.doc_surface_contracts import assert_tour_command_surface_contract

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = REPO_ROOT / "src" / "gpd" / "commands"
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
SOURCE_ROOT = REPO_ROOT / "src" / "gpd"
PATH_PREFIX = "/runtime/"


def _extract_between(content: str, start_marker: str, end_marker: str) -> str:
    start = content.index(start_marker) + len(start_marker)
    end = content.index(end_marker, start)
    return content[start:end]


def _extract_step(workflow: str, step_name: str) -> str:
    start = workflow.index(f'<step name="{step_name}">')
    end = workflow.index("</step>", start)
    return workflow[start:end]


def _assert_anchor(text: str, label: str, fragments: tuple[str, ...] | str) -> None:
    semantic_anchor(label, fragments).check(text)


def _assert_absent(text: str, label: str, fragments: tuple[str, ...] | str) -> None:
    semantic_anchor(label, fragments, mode=FragmentMode.ABSENT).check(text)


def _tour_required_entries(workflow: str) -> set[str]:
    table_block = _extract_between(workflow, "Include these entries:", "Keep this table runtime-facing only.")
    return {line.strip()[3:-1] for line in table_block.splitlines() if line.strip().startswith("- `")}


def _default_tour_step(workflow: str) -> str:
    return _extract_step(workflow, "default_contextual_tour")


def _assert_tour_read_only_boundary(text: str) -> None:
    _assert_anchor(
        text,
        "tour read-only boundary",
        (
            "read-only tour",
            "does not create files",
            "change project",
            "state",
            "route into another workflow",
        ),
    )


def test_tour_command_is_registered_and_projectless() -> None:
    assert "tour" in list_commands()
    command = get_command("gpd:tour")
    assert command.name == "gpd:tour"
    assert command.context_mode == "projectless"
    assert command.allowed_tools == ["file_read"]


def test_tour_command_references_workflow() -> None:
    raw_command_prompt = (COMMANDS_DIR / "tour.md").read_text(encoding="utf-8")
    command_prompt = expand_at_includes(raw_command_prompt, SOURCE_ROOT, PATH_PREFIX)

    assert "@{GPD_INSTALL_DIR}/workflows/tour.md" in raw_command_prompt
    assert "@{GPD_INSTALL_DIR}/references/onboarding/beginner-command-taxonomy.md" in raw_command_prompt
    assert 'argument-hint: "[optional short goal | --all | --reference]"' in raw_command_prompt
    assert "gpd:tour --all" in command_prompt
    assert "gpd:tour --reference" in command_prompt
    assert "gpd:help --all" in command_prompt
    assert "gpd:set-tier-models" in command_prompt
    assert "gpd:settings" in command_prompt
    _assert_anchor(
        command_prompt,
        "tour command opens with read-only main-command orientation",
        ("read-only", "tour", "main GPD commands", "will not change", "files"),
    )
    _assert_anchor(command_prompt, "tour uses runtime-native command labels", ("runtime-native command labels", "gpd:"))


def test_tour_workflow_default_is_short_contextual_orientation() -> None:
    workflow = (WORKFLOWS_DIR / "tour.md").read_text(encoding="utf-8")
    expanded_workflow = expand_at_includes(workflow, SOURCE_ROOT, PATH_PREFIX)
    assert_tour_command_surface_contract(workflow)
    default_step = _default_tour_step(workflow)

    assert len(default_step.splitlines()) <= 80
    assert len(default_step) <= 4_500
    _assert_anchor(
        _extract_step(workflow, "parse_arguments"),
        "tour parses default versus reference flags",
        (
            "--all",
            "--reference",
            "default_contextual_tour",
            "all_reference_tour",
            "Unknown flags are context only",
        ),
    )
    _assert_anchor(
        default_step,
        "tour default stays contextual",
        (
            "80 lines or fewer",
            "4500 characters or fewer",
            "no full command reference",
            "no 12-row core-path table",
            "Which path fits?",
            "gpd:start",
            "gpd:tour",
            "gpd:new-project --minimal",
            "gpd:map-research",
            "gpd:resume-work",
            "gpd:tour --all",
            "gpd:help --all",
        ),
    )
    _assert_absent(default_step, "default tour omits broader reference-only rows", "gpd:explain <topic>")
    _assert_absent(default_step, "default tour omits full new-project row", "| `gpd:new-project` |")
    _assert_tour_read_only_boundary(workflow)
    _assert_anchor(
        expanded_workflow,
        "tour startup ladder comes from public surface contract",
        (beginner_startup_ladder_text(), "folder state", "actual path"),
    )


def test_tour_workflow_reference_mode_contains_broader_table() -> None:
    workflow = (WORKFLOWS_DIR / "tour.md").read_text(encoding="utf-8")
    table_entries = _extract_between(workflow, "Include these entries:", "Keep this table runtime-facing only.")
    assert _tour_required_entries(workflow) == {
        "gpd:start",
        "gpd:new-project --minimal",
        "gpd:new-project",
        "gpd:map-research",
        "gpd:resume-work",
        "gpd:progress",
        "gpd:suggest-next",
        "gpd:explain <topic>",
        "gpd:quick",
        "gpd:set-tier-models",
        "gpd:settings",
        "gpd:help",
    }
    _assert_anchor(
        _extract_step(workflow, "all_reference_tour"),
        "tour all and reference mode",
        (
            "--all",
            "--reference",
            "longer guided",
            "gpd:help --all",
            "canonical complete command index",
        ),
    )
    _assert_absent(table_entries, "normal terminal resume is absent from runtime table", "- `gpd resume`")
    _assert_anchor(
        workflow,
        "tour table stays runtime-facing",
        ("runtime-facing only", "gpd resume", "terminal/runtime distinction"),
    )

    _assert_anchor(
        workflow,
        "tour reference mode keeps table, glossary, and start fallback concepts",
        (
            "compact table",
            "four columns",
            "Use this when",
            "Do not use this when",
            "Example",
            "plain English",
            "gpd:start",
        ),
    )

    _assert_anchor(
        _extract_step(workflow, "show_broader_capabilities"),
        "tour surfaces later capability groups",
        (
            "gpd:plan-phase",
            "gpd:execute-phase",
            "gpd:verify-work",
            "gpd:peer-review",
            "gpd:respond-to-referees",
            "gpd:arxiv-submission",
            "gpd:branch-hypothesis",
            "gpd:set-profile",
            "settings/model commands from the startup table",
        ),
    )
    _assert_anchor(
        _extract_step(workflow, "distinguish_terminal_and_runtime"),
        "tour distinguishes normal terminal from runtime",
        (
            "gpd --help",
            "gpd doctor",
            "gpd resume",
            "gpd:resume-work",
            "gpd:settings",
            "gpd:set-tier-models",
            "gpd:tour",
            "does not run",
        ),
    )
    _assert_anchor(
        _extract_step(workflow, "highlight_common_mistakes"),
        "tour highlights common command boundaries",
        (
            "gpd:start",
            "still deciding",
            "not `gpd:new-project`",
            "gpd:resume-work",
            "project already has GPD state",
            "gpd:help",
            "command reference",
            "not a setup wizard",
        ),
    )
    _assert_anchor(
        _extract_step(workflow, "explain_advanced_terms"),
        "tour defines beginner terms without routing",
        ("GPD project", "research map", "phase", "read-only", "without making changes"),
    )

    fragment_count("tour set-tier-models exact mention count", "gpd:set-tier-models", expected_count=3).check(workflow)
    fragment_count("tour settings exact mention count", "gpd:settings", expected_count=3).check(workflow)
    forbidden_duplicate("tour set-tier-models bounded duplicates", "set-tier-models", max_count=4).check(workflow)
    forbidden_duplicate("tour settings bounded duplicates", "settings", max_count=6).check(workflow)
    fragment_count("tour tier-1 model tier appears once", "tier-1", expected_count=1).check(workflow)
