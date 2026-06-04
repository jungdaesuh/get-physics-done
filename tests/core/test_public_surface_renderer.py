from __future__ import annotations

from pathlib import Path

import pytest

from gpd.adapters.runtime_catalog import iter_runtime_descriptors
from gpd.core.onboarding_surfaces import BeginnerRuntimeSurface, beginner_runtime_surfaces
from gpd.core.public_surface_renderer import (
    public_surface_block_ids,
    public_surface_context,
    public_surface_runtime_surfaces,
    render_beginner_caveat_list,
    render_beginner_preflight_list,
    render_local_cli_bridge_summary,
    render_os_install_matrix,
    render_os_next_step_table,
    render_post_start_settings_note,
    render_public_surface_block,
    render_recovery_note,
    render_runtime_doc_links,
    render_runtime_quickstart_snippet,
    render_startup_ladder,
    render_supported_runtime_table,
    render_terminal_runtime_bridge_text,
    runtime_doc_filename,
    runtime_quickstart_block_id,
)
from scripts.render_public_surface import (
    check_generated_files,
    check_generated_region_inventory,
    check_generated_regions,
    default_target_contracts,
    generated_region_markers,
    render_generated_region,
    replace_generated_regions,
    update_generated_files,
)
from tests.markdown_test_support import parse_markdown_table
from tests.runtime_command_prefix_support import (
    assert_no_incompatible_beginner_command_labels,
    beginner_runtime_quickstart_labels,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _contains_text(text: str, fragment: str) -> bool:
    return fragment in text


def _synthetic_runtime_surface(display_name: str) -> BeginnerRuntimeSurface:
    return BeginnerRuntimeSurface(
        runtime_name="synthetic-runtime",
        display_name=display_name,
        install_flag="--synthetic",
        launch_command="synthetic",
        help_command="synthetic help",
        start_command="synthetic start",
        tour_command="synthetic tour",
        new_project_command="synthetic new-project",
        new_project_minimal_command="synthetic new-project --minimal",
        map_research_command="synthetic map-research",
        resume_work_command="synthetic resume-work",
        settings_command="synthetic settings",
    )


def test_basic_contract_renderers_emit_canonical_public_surface() -> None:
    context = public_surface_context()
    contract = context.contract

    assert render_startup_ladder(context) == contract.beginner_onboarding.render_startup_ladder()
    assert render_beginner_preflight_list(context).splitlines() == [
        f"- {item}" for item in contract.beginner_onboarding.preflight_requirements
    ]
    assert render_beginner_caveat_list(context).splitlines() == [
        f"- {item}" for item in contract.beginner_onboarding.caveats
    ]
    assert render_post_start_settings_note(context) == contract.post_start_settings.render_note()
    recovery_note = render_recovery_note(context)
    assert recovery_note.startswith(
        contract.recovery_ladder.render_note(
            resume_work_phrase="`resume-work`",
            suggest_next_phrase="`suggest-next`",
            pause_work_phrase="`pause-work`",
        )
    )
    assert contract.resume_authority.durable_authority_phrase in recovery_note
    assert contract.resume_authority.public_vocabulary_intro in recovery_note
    for field in contract.resume_authority.public_fields:
        assert f"`{field}`" in recovery_note


def test_terminal_and_local_cli_bridge_text_derive_from_runtime_and_contract_data() -> None:
    context = public_surface_context()

    terminal_bridge = render_terminal_runtime_bridge_text(context)
    for surface in context.runtime_surfaces:
        assert f"`{surface.launch_command}`" in terminal_bridge
        assert f"`{surface.help_command}`" in terminal_bridge
    assert context.contract.beginner_onboarding.render_startup_ladder() in terminal_bridge

    cli_summary = render_local_cli_bridge_summary(context)
    assert context.contract.local_cli_bridge.render_note() in cli_summary
    for command in context.contract.local_cli_bridge.commands:
        assert f"- `{command}`" in cli_summary


def test_public_runtime_surfaces_follow_catalog_priority_order() -> None:
    catalog_order = tuple(descriptor.runtime_name for descriptor in iter_runtime_descriptors())
    reversed_surfaces = tuple(reversed(beginner_runtime_surfaces()))

    assert tuple(surface.runtime_name for surface in public_surface_runtime_surfaces()) == catalog_order
    ordered_surfaces = public_surface_runtime_surfaces(reversed_surfaces)
    assert tuple(surface.runtime_name for surface in ordered_surfaces) == catalog_order


def test_supported_runtime_and_install_tables_follow_public_runtime_surfaces() -> None:
    context = public_surface_context()

    supported_table = parse_markdown_table(render_supported_runtime_table(context), context="supported runtimes")
    assert supported_table.headers == (
        "Runtime",
        "`npx` flag",
        "Help",
        "Start",
        "Tour",
        "New work",
        "Existing work",
        "Return later",
    )
    assert [row["Runtime"] for row in supported_table.rows] == [
        surface.display_name for surface in context.runtime_surfaces
    ]
    supported_rows = {row["Runtime"]: row for row in supported_table.rows}
    for surface in context.runtime_surfaces:
        assert supported_rows[surface.display_name] == {
            "Runtime": surface.display_name,
            "`npx` flag": surface.install_flag,
            "Help": surface.help_command,
            "Start": surface.start_command,
            "Tour": surface.tour_command,
            "New work": surface.new_project_minimal_command,
            "Existing work": surface.map_research_command,
            "Return later": surface.resume_work_command,
        }

    install_table = parse_markdown_table(render_os_install_matrix(context), context="OS install matrix")
    assert install_table.headers == ("Runtime", "Install command")
    assert [row["Runtime"] for row in install_table.rows] == [
        surface.display_name for surface in context.runtime_surfaces
    ]
    install_rows = {row["Runtime"]: row for row in install_table.rows}
    for surface in context.runtime_surfaces:
        install_command = f"{context.bootstrap_command} {surface.install_flag} --local"
        assert install_rows[surface.display_name]["Install command"] == install_command


def test_os_next_step_table_collapses_matching_runtime_command_columns() -> None:
    context = public_surface_context()
    command_groups: list[tuple[list[str], tuple[str, ...]]] = []
    group_indexes: dict[tuple[str, ...], int] = {}
    for surface in context.runtime_surfaces:
        commands = (
            surface.start_command,
            surface.tour_command,
            surface.new_project_minimal_command,
            surface.map_research_command,
            context.contract.recovery_ladder.local_snapshot_command,
            surface.resume_work_command,
        )
        group_index = group_indexes.get(commands)
        if group_index is None:
            group_indexes[commands] = len(command_groups)
            command_groups.append(([surface.display_name], commands))
        else:
            command_groups[group_index][0].append(surface.display_name)

    expected_headers = ["What you want to do", *(" / ".join(names) for names, _commands in command_groups)]
    expected_rows = (
        ("Not sure which path fits this folder", 0),
        ("Want a guided overview", 1),
        ("Start a new project", 2),
        ("Map an existing folder", 3),
        ("Rediscover the workspace in your normal terminal", 4),
        ("Continue in the reopened runtime", 5),
    )

    table = parse_markdown_table(render_os_next_step_table(context), context="OS next-step table")
    assert table.headers == tuple(expected_headers)
    rows = {row["What you want to do"]: row for row in table.rows}
    for label, command_index in expected_rows:
        assert rows[label] == {
            "What you want to do": label,
            **{
                header: commands[command_index]
                for header, (_names, commands) in zip(expected_headers[1:], command_groups, strict=True)
            },
        }


def test_runtime_doc_links_and_quickstart_snippets_are_runtime_derived() -> None:
    context = public_surface_context()
    doc_links = render_runtime_doc_links(context)

    for surface in context.runtime_surfaces:
        assert f"- [{surface.display_name} quickstart](./{runtime_doc_filename(surface)})" in doc_links

        snippet = render_runtime_quickstart_snippet(surface.runtime_name, context)
        assert f"{context.bootstrap_command} {surface.install_flag} --local" in snippet
        assert "```bash\n" in snippet
        assert f"\n{surface.launch_command}\n```" in snippet
        for command in (
            surface.help_command,
            surface.start_command,
            surface.tour_command,
            surface.new_project_minimal_command,
            surface.map_research_command,
            surface.resume_work_command,
            surface.settings_command,
            context.contract.recovery_ladder.local_snapshot_command,
            context.contract.recovery_ladder.cross_workspace_command,
        ):
            assert command in snippet
        assert context.contract.post_start_settings.default_sentence in snippet


def test_runtime_quickstart_snippets_do_not_leak_incompatible_command_prefixes() -> None:
    context = public_surface_context()

    for surface in context.runtime_surfaces:
        snippet = render_runtime_quickstart_snippet(surface.runtime_name, context)
        for command in beginner_runtime_quickstart_labels(surface):
            assert command in snippet
        assert_no_incompatible_beginner_command_labels(
            snippet,
            surface,
            context=f"{surface.runtime_name} rendered quickstart",
            surfaces=context.runtime_surfaces,
        )


def test_runtime_doc_filename_slugifies_display_names() -> None:
    assert runtime_doc_filename(_synthetic_runtime_surface("Alpha Runtime++")) == "alpha-runtime.md"


def test_public_surface_block_registry_includes_runtime_quickstarts() -> None:
    context = public_surface_context()
    block_ids = public_surface_block_ids(context)

    for block_id in (
        "beginner-startup-ladder",
        "beginner-preflight",
        "beginner-caveats",
        "terminal-runtime-bridge",
        "local-cli-bridge-summary",
        "post-start-settings",
        "recovery-note",
        "supported-runtimes-table",
        "os-install-matrix",
        "os-next-steps-table",
        "runtime-doc-links",
    ):
        assert block_id in block_ids
        assert render_public_surface_block(block_id, context)

    for surface in context.runtime_surfaces:
        block_id = runtime_quickstart_block_id(surface)
        assert block_id in block_ids
        assert render_public_surface_block(block_id, context) == render_runtime_quickstart_snippet(
            surface.runtime_name,
            context,
        )

    with pytest.raises(KeyError, match="Unknown public surface block"):
        render_public_surface_block("unknown-block", context)


def test_generated_region_helpers_check_and_replace_stale_regions() -> None:
    block_id = "beginner-startup-ladder"
    text = "before\n" + render_generated_region(block_id, "stale body") + "\nafter\n"

    diffs = check_generated_regions(text)
    assert len(diffs) == 1
    assert diffs[0].block_id == block_id
    assert "stale body" in diffs[0].diff

    updated = replace_generated_regions(text)
    assert "stale body" not in updated
    assert render_public_surface_block(block_id) in updated
    assert updated.startswith("before\n")
    assert updated.endswith("\nafter\n")
    assert check_generated_regions(updated) == ()


def test_generated_file_helpers_update_explicit_paths(tmp_path: Path) -> None:
    block_id = "beginner-preflight"
    target = tmp_path / "surface.md"
    target.write_text(render_generated_region(block_id, "old") + "\n", encoding="utf-8")

    diffs = check_generated_files((target,), repo_root=tmp_path)
    assert len(diffs) == 1
    assert diffs[0].path == target

    assert update_generated_files((target,), repo_root=tmp_path) == (target,)
    assert check_generated_files((target,), repo_root=tmp_path) == ()
    assert render_public_surface_block(block_id) in target.read_text(encoding="utf-8")
    assert update_generated_files((target,), repo_root=tmp_path) == ()


def test_generated_region_helpers_fail_closed_for_bad_markers() -> None:
    start_marker, _end_marker = generated_region_markers("unknown-block")
    with pytest.raises(ValueError, match="Unknown public surface generated block"):
        replace_generated_regions(f"{start_marker}\nbody\n<!-- gpd-public-surface:unknown-block:end -->")

    known_start, known_end = generated_region_markers("beginner-caveats")
    with pytest.raises(ValueError, match="Missing end marker"):
        replace_generated_regions(f"{known_start}\nbody\n")

    nested_start, nested_end = generated_region_markers("beginner-preflight")
    with pytest.raises(ValueError, match="Nested public surface generated block"):
        replace_generated_regions(f"{known_start}\n{nested_start}\nbody\n{nested_end}\n{known_end}\n")

    with pytest.raises(ValueError, match="Orphan end marker"):
        replace_generated_regions(f"before\n{known_end}\nafter\n")


def test_generated_region_inventory_detects_missing_markers_and_unexpected_duplicates() -> None:
    text = render_generated_region("beginner-preflight", render_public_surface_block("beginner-preflight"))
    target_path = Path("docs/README.md")

    missing = check_generated_region_inventory(
        text,
        required_blocks=("beginner-preflight", "beginner-caveats"),
        path=target_path,
    )
    assert len(missing) == 1
    assert missing[0].path == target_path
    assert missing[0].block_id == "beginner-preflight, beginner-caveats"

    duplicate_text = text + "\n" + text
    duplicate = check_generated_region_inventory(
        duplicate_text,
        required_blocks=("beginner-preflight",),
        path=target_path,
    )
    assert len(duplicate) == 1
    assert duplicate[0].path == target_path
    assert duplicate[0].block_id == "beginner-preflight"

    allowed_duplicate = check_generated_region_inventory(
        duplicate_text,
        required_blocks=("beginner-preflight", "beginner-preflight"),
        allowed_duplicate_blocks=("beginner-preflight",),
    )
    assert allowed_duplicate == ()


def test_default_public_surface_targets_are_current_in_repo() -> None:
    assert check_generated_files(repo_root=REPO_ROOT) == ()


def test_explicit_default_public_surface_path_still_checks_required_inventory(tmp_path: Path) -> None:
    target = tmp_path / "README.md"
    target.write_text("# Missing generated regions\n", encoding="utf-8")

    diffs = check_generated_files((Path("README.md"),), repo_root=tmp_path)

    assert len(diffs) == 1
    assert diffs[0].path == target
    assert _contains_text(diffs[0].diff, "missing")
    assert _contains_text(diffs[0].diff, "expected marker(s)")


def test_default_public_surface_targets_declare_current_marker_inventory() -> None:
    contracts = {target.path.as_posix(): target for target in default_target_contracts()}

    assert "README.md" in contracts
    assert contracts["README.md"].allowed_duplicate_blocks == (
        "recovery-note",
        "local-cli-bridge-summary",
    )
    assert contracts["src/gpd/specs/workflows/help.md"].required_blocks == (
        "local-cli-bridge-summary",
        "recovery-note",
    )

    context = public_surface_context()
    for surface in context.runtime_surfaces:
        path = f"docs/{runtime_doc_filename(surface)}"
        assert contracts[path].required_blocks == (runtime_quickstart_block_id(surface),)
