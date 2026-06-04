"""Focused assertions for beginner onboarding docs."""

from __future__ import annotations

from pathlib import Path

import pytest

from gpd.adapters.runtime_catalog import get_runtime_descriptor, get_shared_install_metadata, iter_runtime_descriptors
from gpd.core.onboarding_surfaces import beginner_runtime_surface, beginner_runtime_surfaces
from gpd.core.public_surface_contract import beginner_onboarding_hub_url
from gpd.core.public_surface_renderer import runtime_doc_filename, runtime_quickstart_block_id
from tests.assertion_taxonomy_support import FragmentMode
from tests.doc_surface_contracts import (
    assert_any_docs_semantic_anchor,
    assert_beginner_hub_preflight_contract,
    assert_beginner_startup_routing_contract,
    assert_default_recovery_note_hides_raw_reference_vocabulary,
    assert_docs_public_exact,
    assert_docs_release_source_policy_contract,
    assert_docs_semantic_anchor,
    assert_local_heading_links_resolve,
)
from tests.markdown_test_support import (
    assert_forbidden_fragments,
    assert_markdown_link,
    assert_ordered_fragments,
    extract_markdown_section,
    extract_marker_range,
    markdown_fence_bodies,
)
from tests.runtime_command_prefix_support import (
    assert_no_incompatible_beginner_command_labels,
    beginner_runtime_quickstart_labels,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
_SHARED_INSTALL = get_shared_install_metadata()
_RUNTIME_DOCS_WITH_UNATTENDED_READINESS_LOOP = tuple(
    descriptor.runtime_name
    for descriptor in iter_runtime_descriptors()
    if descriptor.capabilities.statusline_surface == "explicit"
)


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


@pytest.mark.parametrize("surface", beginner_runtime_surfaces(), ids=lambda surface: surface.runtime_name)
def test_runtime_quickstarts_surface_the_beginner_next_steps(surface) -> None:
    doc_path = f"docs/{runtime_doc_filename(surface)}"
    content = _read(doc_path)
    fragments = (
        surface.help_command,
        surface.start_command,
        surface.tour_command,
        surface.new_project_minimal_command,
        surface.map_research_command,
        surface.resume_work_command,
        surface.settings_command,
    )
    assert_docs_public_exact(content, "runtime guide command labels", fragments, context=doc_path)
    assert_ordered_fragments(content, fragments[:3], context=f"{doc_path} first-launch order", normalize=False)
    assert_markdown_link(content, "GPD Onboarding Hub", "./README.md", context=doc_path)
    assert_docs_public_exact(
        content,
        "runtime guide stable headings",
        ("## Choose this runtime if", "## What must already be true", "## 2) Install, start, and use GPD"),
        context=doc_path,
    )


@pytest.mark.parametrize("surface", beginner_runtime_surfaces(), ids=lambda surface: surface.runtime_name)
def test_runtime_quickstart_blocks_do_not_leak_incompatible_command_prefixes(surface) -> None:
    doc_path = f"docs/{runtime_doc_filename(surface)}"
    content = _read(doc_path)
    block_id = runtime_quickstart_block_id(surface)
    quickstart = extract_marker_range(
        content,
        f"<!-- gpd-public-surface:{block_id}:start -->",
        f"<!-- gpd-public-surface:{block_id}:end -->",
        context=doc_path,
    )

    for command in beginner_runtime_quickstart_labels(surface):
        assert command in quickstart
    assert_no_incompatible_beginner_command_labels(
        quickstart,
        surface,
        context=f"{doc_path} generated quickstart",
    )


@pytest.mark.parametrize("runtime_name", _RUNTIME_DOCS_WITH_UNATTENDED_READINESS_LOOP)
def test_runtime_quickstarts_keep_unattended_readiness_loop(runtime_name: str) -> None:
    descriptor = get_runtime_descriptor(runtime_name)
    surface = beginner_runtime_surface(runtime_name)
    doc_path = f"docs/{runtime_doc_filename(surface)}"
    content = _read(doc_path)
    readiness = extract_markdown_section(content, "## Readiness before unattended runs", context=doc_path)
    readiness_command = f"gpd validate unattended-readiness --runtime {runtime_name} --autonomy supervised"
    permissions_sync_command = f"gpd permissions sync --runtime {runtime_name} --autonomy supervised"

    assert_docs_public_exact(
        readiness,
        "runtime unattended readiness commands and verdicts",
        (
            readiness_command,
            permissions_sync_command,
            "`not-ready`",
            "`relaunch-required`",
        ),
        context=f"{doc_path} readiness section",
    )
    assert_docs_semantic_anchor(
        readiness,
        "runtime unattended readiness loop semantics",
        (
            "from your normal terminal",
            "Use the autonomy mode you selected if it is not `supervised`",
            "unattended use as ready",
        ),
        context=f"{doc_path} readiness section",
    )
    assert_ordered_fragments(
        readiness,
        (readiness_command, permissions_sync_command, readiness_command),
        context=f"{doc_path} readiness loop",
        normalize=False,
    )

    if descriptor.capabilities.permissions_surface == "launch-wrapper":
        assert_docs_semantic_anchor(
            readiness,
            "runtime launcher-wrapper readiness guidance",
            "GPD-managed launcher wrapper",
            context=f"{doc_path} readiness section",
        )
    else:
        assert_docs_public_exact(
            readiness,
            "runtime relaunch command label",
            f"relaunch `{descriptor.launch_command}`",
            context=f"{doc_path} readiness section",
        )


@pytest.mark.parametrize(
    "doc_name",
    ["macos.md", "windows.md", "linux.md"],
)
def test_os_quickstarts_link_runtime_guides_and_post_install_help(doc_name: str) -> None:
    content = _read(f"docs/{doc_name}")
    runtime_commands = tuple(
        dict.fromkeys(
            command
            for surface in beginner_runtime_surfaces()
            for command in (surface.start_command, surface.tour_command, surface.resume_work_command)
        )
    )

    assert_docs_public_exact(
        content,
        "OS guide post-install command labels",
        (
            "Confirm success",
            "gpd --help",
            *runtime_commands,
        ),
        context=f"docs/{doc_name}",
    )
    assert_markdown_link(content, "GPD Onboarding Hub", "./README.md", context=f"docs/{doc_name}")
    for surface in beginner_runtime_surfaces():
        assert_markdown_link(
            content,
            f"{surface.display_name} quickstart",
            f"./{runtime_doc_filename(surface)}",
            context=f"docs/{doc_name}",
        )


def test_docs_onboarding_hub_links_os_and_runtime_guides() -> None:
    content = _read("docs/README.md")
    assert_beginner_hub_preflight_contract(content)

    assert_docs_public_exact(
        content,
        "onboarding hub stable navigation labels",
        (
            "# GPD Onboarding Hub",
            "## First: terminal vs runtime",
            "./macos.md",
            "./windows.md",
            "./linux.md",
            "## After the guides",
        ),
        context="docs/README.md",
    )
    assert_docs_semantic_anchor(
        content,
        "onboarding hub beginner navigation concepts",
        (
            "full beginner path",
            "normal terminal",
            "runtime",
            "beginner terms",
        ),
        context="docs/README.md",
    )
    assert_beginner_startup_routing_contract(content)
    for surface in beginner_runtime_surfaces():
        guide = runtime_doc_filename(surface)
        assert_markdown_link(content, f"{surface.display_name} quickstart", f"./{guide}", context="docs/README.md")
        assert_docs_public_exact(
            content,
            f"{surface.display_name} install command",
            f"{_SHARED_INSTALL.bootstrap_command} {surface.install_flag} --local",
            context="docs/README.md",
        )
    assert_ordered_fragments(
        content,
        (
            "## Before you open the guides",
            "## First: terminal vs runtime",
            "## Choose your OS",
            "## Choose your runtime",
            "## After the guides",
        ),
        context="docs/README.md heading order",
        normalize=False,
    )


def test_docs_onboarding_hub_surfaces_release_source_policy() -> None:
    content = _read("docs/README.md")

    assert_docs_release_source_policy_contract(content, context="docs/README.md")
    assert_forbidden_fragments(content, "Graduate to Balanced", context="docs/README.md")


@pytest.mark.parametrize(
    "relative_path",
    (
        "README.md",
        "docs/README.md",
        "docs/macos.md",
        "docs/windows.md",
        "docs/linux.md",
        "src/gpd/specs/workflows/help.md",
    ),
)
def test_default_recovery_notes_hide_raw_reference_vocabulary(relative_path: str) -> None:
    content = _read(relative_path)

    assert_default_recovery_note_hides_raw_reference_vocabulary(content, context=relative_path)


def test_root_readme_settings_short_wording_matches_model_profile_contract() -> None:
    content = _read("README.md")
    quick_start = extract_markdown_section(content, "## Quick Start", context="README.md")

    assert_docs_semantic_anchor(
        quick_start,
        "root README settings model-cost posture",
        (
            "workflow defaults",
            "model-cost posture",
            "runtime permission sync",
            "preset/tier overrides",
            "review",
            "runtime defaults",
        ),
        context="README.md Quick Start",
    )
    assert_forbidden_fragments(quick_start, "graduate to Balanced (`balanced`)", context="README.md Quick Start")


def test_root_readme_start_here_links_to_docs_onboarding_hub() -> None:
    content = _read("README.md")
    start_here = extract_markdown_section(content, "## Start Here", context="README.md")

    assert_markdown_link(
        start_here,
        "Beginner Onboarding Hub",
        beginner_onboarding_hub_url(),
        context="README.md Start Here",
    )
    assert_docs_semantic_anchor(
        start_here,
        "root README beginner terminal/runtime bridge",
        ("single beginner path", "two places", "normal system terminal", "AI runtime"),
        context="README.md Start Here",
    )


def test_root_readme_local_heading_anchors_resolve() -> None:
    content = _read("README.md")

    assert_local_heading_links_resolve(content, context="README.md")


def test_root_readme_install_source_policy_and_peer_review_target_are_current() -> None:
    content = _read("README.md")
    quick_start = extract_markdown_section(content, "## Quick Start", context="README.md")
    install_options_start = quick_start.index("<summary><strong>Install options</strong></summary>")
    install_options = quick_start[install_options_start : quick_start.index("</details>", install_options_start)]
    command_context = extract_markdown_section(content, "## Key GPD Paths", context="README.md")

    assert_docs_public_exact(
        install_options,
        "root README install source policy labels",
        (
            "PyPI pinned release first",
            "tagged GitHub release sources",
            "`--upgrade`",
            "latest unreleased GitHub `main` source",
        ),
        mode=FragmentMode.ORDERED,
        context="README.md install options",
    )
    assert_forbidden_fragments(install_options, "matching tagged GitHub source", context="README.md install options")
    assert_docs_semantic_anchor(
        command_context,
        "peer-review explicit target semantics",
        ("one explicit manuscript", "artifact path", "paper directory target"),
        context="README.md Key GPD Paths",
    )
    assert_forbidden_fragments(command_context, "`.tex`, `.md`, `.txt`, `.pdf`", context="README.md Key GPD Paths")


def test_root_readme_runtime_workflow_examples_are_prefixless_and_uninstall_link_is_current() -> None:
    content = _read("README.md")
    quick_start = extract_markdown_section(content, "## Quick Start", context="README.md")
    worked_example = extract_markdown_section(content, "## Worked Example", context="README.md")
    uninstall = extract_markdown_section(content, "## Uninstall", context="README.md")

    assert_docs_semantic_anchor(
        quick_start,
        "prefixless new-project workflow framing",
        ("new-project workflow", "command names without runtime prefixes"),
        context="README.md Quick Start",
    )
    assert_docs_public_exact(
        quick_start,
        "root README quick-start workflow sequence",
        "`new-project -> discuss-phase 1 -> plan-phase 1 -> execute-phase 1 -> verify-work 1`",
        context="README.md Quick Start",
    )
    assert_docs_semantic_anchor(
        worked_example,
        "prefixless worked-example framing",
        ("canonical command names", "without runtime prefixes"),
        context="README.md Worked Example",
    )
    assert_forbidden_fragments(
        worked_example,
        ("Claude Code / Gemini CLI syntax", "```text\ngpd:new-project\n", "`gpd:plan-phase N`"),
        context="README.md Worked Example",
        normalize=False,
    )
    text_blocks = markdown_fence_bodies(worked_example, info="text")
    assert any(block.startswith("new-project\n") for block in text_blocks)
    assert "plan-phase 1\nexecute-phase 1\nverify-work 1" in text_blocks
    assert "write-paper\npeer-review\nrespond-to-referees\narxiv-submission" in text_blocks
    assert_docs_public_exact(
        content,
        "root README research and publication loop labels",
        (
            "Typical research loop:",
            "`new-project -> discuss-phase 1 -> plan-phase 1 -> execute-phase 1 -> verify-work -> repeat -> complete-milestone`",
            "Typical publication loop:",
            "`write-paper -> peer-review -> respond-to-referees -> arxiv-submission`",
        ),
        context="README.md",
    )
    assert_forbidden_fragments(content, ("gpd:new-project ->", "gpd:write-paper ->"), context="README.md")
    assert_forbidden_fragments(
        uninstall,
        "matching uninstall command from [Start Here]",
        context="README.md Uninstall",
    )
    assert_docs_public_exact(
        uninstall,
        "root README uninstall command",
        "npx -y get-physics-done --uninstall",
        context="README.md Uninstall",
    )


def test_root_readme_project_contract_validation_placeholder_is_current() -> None:
    content = _read("README.md")
    validation_commands = extract_markdown_section(content, "## Advanced CLI Utilities", context="README.md")

    assert_docs_public_exact(
        validation_commands,
        "project-contract CLI placeholder",
        "`gpd validate project-contract <file.json|-> [--mode approved|draft]`",
        context="README.md Advanced CLI Utilities",
    )
    assert_forbidden_fragments(
        validation_commands,
        "`gpd validate project-contract <file.json or -> [--mode approved|draft]`",
        context="README.md Advanced CLI Utilities",
    )


def test_root_readme_supported_runtimes_omits_internal_config_overrides() -> None:
    content = _read("README.md")

    assert_forbidden_fragments(
        content,
        (
            "Config path overrides",
            "CLAUDE_CONFIG_DIR",
            "CODEX_SKILLS_DIR",
            "GEMINI_CONFIG_DIR",
            "OPENCODE_CONFIG_DIR",
        ),
        context="README.md",
    )


def test_root_readme_model_overrides_example_covers_catalog_runtimes() -> None:
    content = _read("README.md")
    config_example = extract_markdown_section(
        content,
        "## Optional: Model Profiles And Tier Overrides",
        context="README.md",
    )

    for surface in beginner_runtime_surfaces():
        assert f'"{surface.runtime_name}"' in config_example


def test_runtime_config_guide_omits_unsupported_skip_mcp_advice() -> None:
    content = _read("src/gpd/specs/references/tooling/runtime-config-guide.md")

    assert "--skip-mcp" not in content
    assert_docs_semantic_anchor(
        content,
        "runtime config low-resource install guidance",
        ("disk space", "managed environment", "runtime config", "recreated"),
        context="runtime-config-guide.md",
    )


def test_set_tier_models_workflow_keeps_runtime_model_examples_generic() -> None:
    content = _read("src/gpd/specs/workflows/set-tier-models.md")

    assert "adapter catalog" not in content
    assert_docs_semantic_anchor(
        content,
        "runtime-native model example guidance",
        (
            "Runtime-native examples",
            "not hard-coded",
            "exact string accepted by the active runtime",
            "runtime/provider",
            "model documentation",
        ),
        context="set-tier-models.md",
    )


def test_runtime_quickstarts_keep_current_provider_specific_setup_notes() -> None:
    docs = {
        surface.runtime_name: _read(f"docs/{runtime_doc_filename(surface)}") for surface in beginner_runtime_surfaces()
    }

    assert_any_docs_semantic_anchor(
        docs,
        "Claude Code account-access setup note",
        ("Claude Code", "account", "free Claude.ai plan"),
        context="runtime quickstarts",
    )
    assert_any_docs_semantic_anchor(
        docs,
        "Gemini Cloud project setup note",
        ("GOOGLE_CLOUD_PROJECT", "Gemini Code Assist", "official authentication guide"),
        context="runtime quickstarts",
    )
    assert_any_docs_semantic_anchor(
        docs,
        "OpenCode connect setup note",
        ("/connect", "provider", "API-key or billing setup"),
        context="runtime quickstarts",
    )


def test_progress_docs_do_not_reference_nonexistent_list_todos_command() -> None:
    command = _read("src/gpd/commands/progress.md")
    workflow = _read("src/gpd/specs/workflows/progress.md")

    assert "list-todos" not in command
    assert "list-todos" not in workflow
    assert "@{GPD_INSTALL_DIR}/workflows/progress.md" in command
    assert "gpd --raw init todos" in workflow


def test_progress_workflow_reconcile_mode_uses_supported_state_snapshot_fields() -> None:
    content = _read("src/gpd/specs/workflows/progress.md")

    assert "gpd --raw state snapshot" in content
    assert '.current_phase --default ""' in content
    assert '.current_plan --default ""' in content
    assert ".current_phase.number" not in content
    assert ".current_execution.plan" not in content
