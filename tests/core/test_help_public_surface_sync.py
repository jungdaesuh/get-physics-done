"""Sync checks for generated help workflow marker bodies."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from gpd.adapters.install_utils import parse_at_include_path
from scripts.render_help_surface import (
    check_help_surface_text,
    extract_help_surface_region,
    help_surface_block_ids,
    help_surface_markers,
    replace_help_surface_text,
    update_help_surface_file,
)
from tests.assertion_taxonomy_support import assert_prompt_contracts, machine_exact

_HELP_MARKERS = help_surface_block_ids()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_workflow_help() -> str:
    return (_repo_root() / "src/gpd/specs/workflows/help.md").read_text(encoding="utf-8")


def _help_detail_reference_path() -> Path:
    return _repo_root() / "src/gpd/specs/references/help/detailed-command-reference.md"


def _read_help_detail_reference() -> str:
    return _help_detail_reference_path().read_text(encoding="utf-8")


def _read_command_help() -> str:
    return (_repo_root() / "src/gpd/commands/help.md").read_text(encoding="utf-8")


def _normalized_block(text: str) -> str:
    return text.strip().replace("\r\n", "\n")


def _single_line_starting(text: str, prefix: str) -> str:
    matches = [line for line in text.splitlines() if line.startswith(prefix)]
    assert len(matches) == 1
    return matches[0]


def _help_renderer() -> object:
    return pytest.importorskip(
        "gpd.core.help_renderer",
        reason="Worker B help renderer API has not landed in this checkout yet",
    )


def _rendered_markdown(result: object) -> str:
    if isinstance(result, str):
        return _normalized_block(result)
    markdown = getattr(result, "markdown", None)
    if isinstance(markdown, str):
        return _normalized_block(markdown)
    pytest.fail(f"expected renderer result to be markdown text, got {type(result)!r}")


def _call_with_supported_kwargs(function: object, /, **kwargs: object) -> object:
    signature = inspect.signature(function)
    supported_kwargs = {name: value for name, value in kwargs.items() if name in signature.parameters}
    return function(**supported_kwargs)


def _build_catalog(renderer: object) -> object:
    build_help_catalog = getattr(renderer, "build_help_catalog", None)
    if build_help_catalog is None:
        pytest.fail("gpd.core.help_renderer must expose build_help_catalog()")
    return build_help_catalog()


def _render_quick_start(renderer: object) -> str:
    render_quick_start = getattr(renderer, "render_quick_start", None)
    if render_quick_start is None:
        pytest.fail("gpd.core.help_renderer must expose render_quick_start()")
    return _rendered_markdown(_call_with_supported_kwargs(render_quick_start, public_prefix="gpd:"))


def _render_default_help(renderer: object) -> str:
    render_default_help = getattr(renderer, "render_default_help", None)
    if render_default_help is None:
        pytest.fail("gpd.core.help_renderer must expose render_default_help()")
    return _rendered_markdown(_call_with_supported_kwargs(render_default_help, public_prefix="gpd:"))


def _render_command_index(renderer: object) -> str:
    render_command_index = getattr(renderer, "render_command_index", None)
    if render_command_index is None:
        pytest.fail("gpd.core.help_renderer must expose render_command_index()")

    catalog = _build_catalog(renderer)
    signature = inspect.signature(render_command_index)
    parameters = signature.parameters
    if "catalog" in parameters:
        result = _call_with_supported_kwargs(
            render_command_index,
            catalog=catalog,
            public_prefix="gpd:",
            include_quick_start=False,
        )
    else:
        result = _call_with_supported_kwargs(
            render_command_index,
            public_prefix="gpd:",
            include_quick_start=False,
        )
    return _rendered_markdown(result)


def _render_detailed_command_reference(renderer: object) -> str:
    render_detailed = getattr(renderer, "render_detailed_command_reference_markdown", None)
    if render_detailed is None:
        pytest.fail("gpd.core.help_renderer must expose render_detailed_command_reference_markdown()")
    return _rendered_markdown(_call_with_supported_kwargs(render_detailed, public_prefix="gpd:"))


def _render_root_detailed_command_reference(renderer: object) -> str:
    render_detailed = getattr(renderer, "render_root_detailed_command_reference_markdown", None)
    if render_detailed is None:
        pytest.fail("gpd.core.help_renderer must expose render_root_detailed_command_reference_markdown()")
    return _rendered_markdown(_call_with_supported_kwargs(render_detailed, public_prefix="gpd:"))


def test_help_marker_comments_are_unique_ordered_extraction_anchors() -> None:
    workflow_help = _read_workflow_help()
    positions: list[int] = []

    for marker_name in _HELP_MARKERS:
        start_marker, end_marker = help_surface_markers(marker_name)
        assert workflow_help.count(start_marker) == 1
        assert workflow_help.count(end_marker) == 1

        start_position = workflow_help.index(start_marker)
        end_position = workflow_help.index(end_marker, start_position)
        assert start_position < end_position
        positions.extend([start_position, end_position])

    assert positions == sorted(positions)


def test_help_wrapper_extraction_contract_uses_exact_marker_anchors() -> None:
    help_command = _read_command_help()

    marker_pairs = tuple("`" + start + "` / `" + end + "`" for start, end in map(help_surface_markers, _HELP_MARKERS))
    for marker_pair in marker_pairs:
        assert marker_pair in help_command

    default_start, default_end = help_surface_markers("default")
    quick_start_start, _quick_start_end = help_surface_markers("quick-start")
    _, command_index_end = help_surface_markers("command-index")
    extraction_rules = (
        "Return marker contents only; never print the HTML marker comments themselves.",
        "Visible headings inside marker ranges are output labels only.",
        f"Extract from `{default_start}` through `{default_end}`.",
        f"Extract from `{quick_start_start}` through `{command_index_end}`.",
        "whose visible heading is `## Detailed Command Reference`.",
    )
    for extraction_rule in extraction_rules:
        assert extraction_rule in help_command


def test_help_wrapper_prefers_renderer_backed_bridge_without_eager_workflow_include() -> None:
    help_command = _read_command_help()

    assert "gpd --raw help" in help_command
    assert "gpd --raw help --all" in help_command
    assert "gpd --raw help --command <name>" in help_command
    bridge_rule = _single_line_starting(help_command, "Bridge command rule:")
    for bridge_token in ("local CLI", "JSON", "renderer-backed"):
        assert bridge_token in bridge_rule
    for detail_token in ("`detail_markdown`", "`canonical_command`", "`allowed_tools`"):
        assert detail_token in help_command
    assert "`@{GPD_INSTALL_DIR}/workflows/help.md` - Fallback marker source path" in help_command
    assert all(parse_at_include_path(line.strip()) is None for line in help_command.splitlines())


def test_help_quick_start_marker_matches_renderer_output() -> None:
    renderer = _help_renderer()
    workflow_help = _read_workflow_help()

    checked_in_quick_start = _normalized_block(extract_help_surface_region(workflow_help, "quick-start"))
    assert checked_in_quick_start == _render_quick_start(renderer)


def test_help_default_marker_matches_renderer_output() -> None:
    renderer = _help_renderer()
    workflow_help = _read_workflow_help()

    checked_in_default = _normalized_block(extract_help_surface_region(workflow_help, "default"))
    assert checked_in_default == _render_default_help(renderer)


def test_help_command_index_marker_matches_renderer_output() -> None:
    renderer = _help_renderer()
    workflow_help = _read_workflow_help()

    checked_in_command_index = _normalized_block(extract_help_surface_region(workflow_help, "command-index"))
    assert checked_in_command_index == _render_command_index(renderer)


def test_help_detailed_reference_marker_matches_renderer_output() -> None:
    renderer = _help_renderer()
    workflow_help = _read_workflow_help()

    checked_in_root_reference = _normalized_block(
        extract_help_surface_region(workflow_help, "detailed-command-reference")
    )
    assert checked_in_root_reference == _render_root_detailed_command_reference(renderer)


def test_help_detail_reference_file_marker_matches_renderer_output() -> None:
    renderer = _help_renderer()
    detail_reference = _read_help_detail_reference()

    checked_in_detailed_reference = _normalized_block(
        extract_help_surface_region(detail_reference, "detailed-command-reference")
    )
    assert checked_in_detailed_reference == _render_detailed_command_reference(renderer)


def test_respond_to_referees_help_distinguishes_manuscript_edits_from_response_roots() -> None:
    command_help = (_repo_root() / "src/gpd/commands/respond-to-referees.md").read_text(encoding="utf-8")
    expected_note = (
        "Manuscript edits stay beside the resolved manuscript; GPD-authored response artifacts use the selected GPD "
        "roots (`GPD/` and `GPD/review/` for project-backed response rounds, or "
        "`GPD/publication/{subject_slug}` plus its `review/` subtree for managed/external subjects)."
    )
    stale_note = "Project-backed review/response/package outputs stay under the resolved manuscript root"

    for help_surface in (command_help, _read_workflow_help(), _read_help_detail_reference()):
        assert expected_note in help_surface
        assert stale_note not in help_surface


def test_help_surface_marker_script_is_idempotent() -> None:
    workflow_help = _read_workflow_help()
    detail_reference = _read_help_detail_reference()

    assert check_help_surface_text(workflow_help) == ()
    assert check_help_surface_text(detail_reference, path=_help_detail_reference_path()) == ()
    assert replace_help_surface_text(workflow_help) == workflow_help


def test_help_surface_update_rejects_missing_and_duplicate_marker_inventory(tmp_path: Path) -> None:
    workflow_help = _read_workflow_help()
    start_marker, end_marker = help_surface_markers("quick-start")
    start = workflow_help.index(start_marker)
    end = workflow_help.index(end_marker, start) + len(end_marker)
    quick_start_region = workflow_help[start:end]

    cases = (
        (
            "missing-help.md",
            workflow_help[:start] + workflow_help[end:],
            "missing 1 expected marker(s) for 'quick-start'",
        ),
        (
            "duplicate-help.md",
            workflow_help + "\n" + quick_start_region,
            "duplicate marker for 'quick-start' is not allowed",
        ),
    )

    for filename, text, expected_diagnostic in cases:
        path = tmp_path / filename
        path.write_text(text, encoding="utf-8")

        with pytest.raises(ValueError) as error:
            update_help_surface_file(path)

        inventory_failure = "Cannot update help surface generated regions because marker inventory is invalid."
        assert inventory_failure in str(error.value)
        assert expected_diagnostic in str(error.value)
        assert path.read_text(encoding="utf-8") == text


def test_help_detail_reference_inventory_detects_missing_and_duplicate_marker() -> None:
    detail_reference = _read_help_detail_reference()
    start_marker, end_marker = help_surface_markers("detailed-command-reference")
    start = detail_reference.index(start_marker)
    end = detail_reference.index(end_marker, start) + len(end_marker)
    detail_region = detail_reference[start:end]
    missing_reference = detail_reference[:start] + detail_reference[end:]
    detail_path = _help_detail_reference_path()

    missing = check_help_surface_text(missing_reference, path=detail_path)
    assert len(missing) == 1
    assert_prompt_contracts(
        missing[0].diff,
        machine_exact(
            "help detail reference missing marker diagnostic",
            (
                "help surface marker inventory mismatch",
                "missing 1 expected marker(s) for 'detailed-command-reference'",
            ),
        ),
    )

    duplicate = check_help_surface_text(detail_reference + "\n" + detail_region, path=detail_path)
    assert len(duplicate) == 1
    assert "found 2 marker(s) for 'detailed-command-reference', expected 1" in duplicate[0].diff
    assert_prompt_contracts(
        duplicate[0].diff,
        machine_exact(
            "help detail reference duplicate marker diagnostic",
            "duplicate marker for 'detailed-command-reference' is not allowed",
        ),
    )
