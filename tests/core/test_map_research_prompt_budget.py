"""Prompt budget assertions for the `map-research` startup surface."""

from __future__ import annotations

from pathlib import Path

from tests.prompt_metrics_support import count_unfenced_heading, expanded_prompt_text, measure_prompt_surface

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "src" / "gpd" / "agents"
COMMANDS_DIR = REPO_ROOT / "src" / "gpd" / "commands"
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
SOURCE_ROOT = REPO_ROOT / "src" / "gpd"
PATH_PREFIX = "/runtime/"
BOOTSTRAP_AUTHORITY = WORKFLOWS_DIR / "map-research" / "map-bootstrap.md"


def test_map_research_command_prompt_budget_stays_close_to_the_bootstrap_surface() -> None:
    command_text = (COMMANDS_DIR / "map-research.md").read_text(encoding="utf-8")
    metrics = measure_prompt_surface(
        COMMANDS_DIR / "map-research.md",
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )
    bootstrap = measure_prompt_surface(
        BOOTSTRAP_AUTHORITY,
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )

    assert metrics.raw_include_count == 1
    assert "@{GPD_INSTALL_DIR}/workflows/map-research/map-bootstrap.md" in command_text
    assert "@{GPD_INSTALL_DIR}/workflows/map-research.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/references/orchestration/runtime-delegation-note.md" not in command_text
    assert metrics.expanded_line_count > bootstrap.expanded_line_count
    assert metrics.expanded_char_count > bootstrap.expanded_char_count
    assert metrics.expanded_line_count < bootstrap.expanded_line_count + 250
    assert metrics.expanded_char_count < bootstrap.expanded_char_count + 15000

    expanded_command = expanded_prompt_text(
        COMMANDS_DIR / "map-research.md",
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )
    assert 'subagent_type="gpd-research-mapper"' not in expanded_command
    assert "references/orchestration/runtime-delegation-note.md" not in expanded_command


def test_research_mapper_uses_one_canonical_mapping_complete_template() -> None:
    source = (AGENTS_DIR / "gpd-research-mapper.md").read_text(encoding="utf-8")

    assert source.count("## Mapping Complete") == 1
    assert count_unfenced_heading(source, "## Mapping Complete") == 0
    assert "Canonical format. Include optional blocks only when relevant:" in source
    assert "[Optional: quality warnings for documents below the minimum gate.]" in source
    assert "[Optional: staleness of other research-map docs.]" in source
    assert "report staleness in the canonical confirmation" in source
    assert "flag it in the canonical confirmation" in source


def test_research_mapper_defers_template_guidance_and_examples_to_reference() -> None:
    source = (AGENTS_DIR / "gpd-research-mapper.md").read_text(encoding="utf-8")
    guidance = (
        REPO_ROOT / "src" / "gpd" / "specs" / "references" / "templates" / "research-mapper" / "MAPPING-GUIDANCE.md"
    )
    guidance_text = guidance.read_text(encoding="utf-8")

    assert "{GPD_INSTALL_DIR}/references/templates/research-mapper/MAPPING-GUIDANCE.md" in source
    assert "Step 1: Read the model definition" not in source
    assert "Minimum section structures:" in guidance_text
    assert "## Worked Example" in guidance_text
    assert "## Broken Template Fallback" in guidance_text
