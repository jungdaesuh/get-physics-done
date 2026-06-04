"""Contract test for help inventory coverage."""

from __future__ import annotations

import re
from collections import Counter

from gpd import registry as content_registry
from gpd.core import help_renderer
from scripts.render_help_surface import extract_help_surface_region, help_surface_markers
from tests.assertion_taxonomy_support import FragmentMode, fragment_count, semantic_anchor
from tests.doc_surface_contracts import assert_publication_lane_boundary_contract


def _repo_root():
    from pathlib import Path

    return Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (_repo_root() / relative_path).read_text(encoding="utf-8")


def _range(content: str, start_marker: str, end_marker: str) -> str:
    start = content.index(start_marker) + len(start_marker)
    end = content.index(end_marker, start)
    return content[start:end]


def _rendered_detailed_reference() -> str:
    return help_renderer.render_detailed_command_reference_markdown()


def _rendered_command_index_rows() -> dict[str, str]:
    rows = re.findall(r"(?m)^- `([^`]+)` - (.+)$", help_renderer.render_command_index_markdown())
    assert len(rows) == len({command for command, _description in rows})
    return dict(rows)


def _metadata_index_signature(command: content_registry.CommandDef) -> str:
    assert command.help is not None
    if command.help.display_signature:
        return command.help.display_signature
    if command.argument_hint:
        return f"{command.name} {command.argument_hint}"
    return command.name


def _detailed_command_block(content: str, command_heading: str, next_command_heading: str | None = None) -> str:
    detailed_start_marker, _ = help_surface_markers("detailed-command-reference")
    if detailed_start_marker in content:
        detailed_reference = extract_help_surface_region(content, "detailed-command-reference")
    else:
        detailed_reference = content
    start = detailed_reference.index(command_heading)
    if next_command_heading is not None and next_command_heading in detailed_reference[start + len(command_heading) :]:
        end = detailed_reference.index(next_command_heading, start + len(command_heading))
        return detailed_reference[start:end]
    next_heading = re.search(r"(?m)^\*\*`gpd:[a-z0-9-]+\b", detailed_reference[start + len(command_heading) :])
    if next_heading is None:
        return detailed_reference[start:]
    end = start + len(command_heading) + next_heading.start()
    return detailed_reference[start:end]


def _help_command_inventory(*contents: str) -> set[str]:
    surfaces: set[str] = set()
    pattern = re.compile(r"(?m)(?<![A-Za-z0-9-])(?:gpd:|/gpd:|gpd\s+)([a-z0-9-]+)\b")
    for content in contents:
        surfaces.update(pattern.findall(content))
    return surfaces


def _detailed_command_headings(content: str) -> list[str]:
    detailed_start_marker, _ = help_surface_markers("detailed-command-reference")
    if detailed_start_marker in content:
        detailed_reference = extract_help_surface_region(content, "detailed-command-reference")
    else:
        detailed_reference = content
    return re.findall(r"(?m)^\*\*`gpd:([a-z0-9-]+)\b", detailed_reference)


def _command_index_rows(content: str) -> dict[str, str]:
    command_index = extract_help_surface_region(content, "command-index")
    rows = re.findall(r"(?m)^- `([^`]+)` - (.+)$", command_index)
    assert len(rows) == len({command for command, _description in rows})
    return dict(rows)


def _assert_anchor(text: str, label: str, fragments: tuple[str, ...] | str) -> None:
    semantic_anchor(label, fragments).check(text)


def _assert_absent(text: str, label: str, fragments: tuple[str, ...] | str) -> None:
    semantic_anchor(label, fragments, mode=FragmentMode.ABSENT).check(text)


def test_help_inventory_covers_registry_command_inventory() -> None:
    content_registry.invalidate_cache()

    registry_commands = set(content_registry.list_commands())
    help_inventory = _help_command_inventory(
        _read("src/gpd/commands/help.md"),
        help_renderer.render_quick_start_markdown(),
        help_renderer.render_command_index_markdown(),
        _rendered_detailed_reference(),
    )

    missing = sorted(registry_commands - help_inventory)
    assert missing == []


def test_help_command_index_inventory_is_backed_by_command_help_metadata() -> None:
    content_registry.invalidate_cache()
    help_renderer.help_command_groups.cache_clear()

    commands = [
        content_registry.get_command(command_label)
        for command_label in content_registry.list_commands(name_format="label")
    ]
    missing_help = sorted(command.name for command in commands if command.help is None)
    assert missing_help == []

    expected_rows: dict[str, str] = {}
    duplicate_rows: list[str] = []
    help_orders: dict[int, str] = {}
    duplicate_orders: list[str] = []
    for command in commands:
        assert command.help is not None
        if command.help.order in help_orders:
            duplicate_orders.append(f"{help_orders[command.help.order]} / {command.name}")
        help_orders[command.help.order] = command.name

        signature = _metadata_index_signature(command)
        if signature in expected_rows:
            duplicate_rows.append(signature)
        expected_rows[signature] = command.help.compact_description or command.description
        for variant in command.help.variants:
            if variant.command in expected_rows:
                duplicate_rows.append(variant.command)
            expected_rows[variant.command] = variant.description

    assert duplicate_orders == []
    assert duplicate_rows == []

    rows = _rendered_command_index_rows()
    assert set(rows) == set(expected_rows)
    for signature, description in expected_rows.items():
        assert rows[signature] == description

    grouped_base_commands = {
        entry.registry_command
        for group in help_renderer.help_command_groups()
        for entry in group.commands
        if not entry.documented_variant
    }
    assert grouped_base_commands == {command.name for command in commands}


def test_root_detail_inventory_is_selected_by_command_help_metadata() -> None:
    content_registry.invalidate_cache()
    help_renderer._root_detailed_reference_commands.cache_clear()

    commands = [
        content_registry.get_command(command_label)
        for command_label in content_registry.list_commands(name_format="label")
    ]
    missing_help = sorted(command.name for command in commands if command.help is None)
    assert missing_help == []
    root_records = [
        (command.help.root_detail_order, command.name.removeprefix("gpd:"))
        for command in commands
        if command.help is not None and command.help.root_detail_order is not None
    ]
    expected_root_slugs = [slug for _order, slug in sorted(root_records)]

    root_headings = _detailed_command_headings(help_renderer.render_root_detailed_command_reference_markdown())
    assert root_headings == expected_root_slugs


def test_detailed_help_reference_has_one_block_for_each_registry_command() -> None:
    content_registry.invalidate_cache()

    registry_commands = set(content_registry.list_commands())
    detailed_headings = _detailed_command_headings(_rendered_detailed_reference())

    heading_counts = Counter(detailed_headings)
    duplicate_headings = sorted(command for command, count in heading_counts.items() if count > 1)
    assert duplicate_headings == []

    detailed_commands = set(detailed_headings)
    assert sorted(registry_commands - detailed_commands) == []
    assert sorted(detailed_commands - registry_commands) == []


def test_help_inventory_uses_runtime_neutral_framing_in_shared_source() -> None:
    help_sources = [
        _read("src/gpd/commands/help.md"),
        _read("src/gpd/specs/workflows/help.md"),
    ]

    assert all("canonical in-runtime slash-command names in `/gpd:*` form" not in content for content in help_sources)
    assert all("/gpd:*" not in content for content in help_sources)
    assert any("canonical in-runtime command names" in content for content in help_sources)
    assert all("slash-command" not in content for content in help_sources)


def test_help_wrapper_followups_do_not_hard_code_gpd_help_runtime_syntax() -> None:
    help_command = _read("src/gpd/commands/help.md")

    assert "gpd:help --all" not in help_command
    assert "gpd:help --command <name>" not in help_command
    assert "this runtime's help command" not in help_command
    assert "current-help-command" not in help_command
    fragment_count(
        "one runtime-neutral command surface note",
        "Runtime command-surface note:",
        expected_count=1,
    ).check(help_command)
    _assert_anchor(
        help_command,
        "runtime-neutral command surface note",
        ("command that invoked this wrapper", "this help command", "do not print adapter-specific examples"),
    )
    _assert_anchor(
        help_command,
        "runtime-neutral all-commands follow-up",
        ("this help command", "--all", "compact command index"),
    )
    _assert_anchor(
        help_command,
        "runtime-neutral command-detail follow-up",
        ("this help command", "--command <name>", "detailed help", "one command"),
    )
    _assert_anchor(
        help_command,
        "runtime-neutral unknown-command follow-up",
        ("Unknown command", "this help command", "--all", "compact command index"),
    )


def test_help_wrapper_documents_inline_argument_command_lookup_normalization() -> None:
    help_command = _read("src/gpd/commands/help.md")

    semantic_anchor(
        "inline command lookup normalization",
        (
            "gpd:new-project --minimal",
            "current runtime",
            "native command label",
            "inline flags or arguments",
            "base command",
        ),
        section="## Step 4: Single Command Detail Extract (--command <name>)",
    ).check(help_command)


def test_help_workflow_removes_unreachable_contextual_help_variant() -> None:
    help_workflow = _read("src/gpd/specs/workflows/help.md")
    quick_start = extract_help_surface_region(help_workflow, "quick-start")

    assert '<step name="contextual_help">' not in help_workflow
    assert "## Contextual Help (State-Aware Variant)" not in help_workflow
    assert "Returning work" in quick_start
    assert "gpd:resume-work" in quick_start


def test_peer_review_detailed_help_uses_command_policy_instead_of_suffix_inventory() -> None:
    detailed_reference = _rendered_detailed_reference()
    peer_review_detail = _detailed_command_block(
        detailed_reference,
        "**`gpd:peer-review [paper directory | manuscript path | explicit artifact path]`**",
        "**`gpd:respond-to-referees",
    )

    _assert_anchor(
        peer_review_detail,
        "peer-review explicit artifact policy",
        (
            "Explicit artifact intake",
            "command-policy supported suffixes",
            "publication-artifact paths",
            "resolved manuscript entrypoint",
        ),
    )
    assert "`.txt`, `.pdf`, `.docx`, `.csv`, `.tsv`, and `.xlsx`" not in peer_review_detail


def test_help_workflow_paper_toolchain_doctor_row_is_single_sourced() -> None:
    help_workflow = _read("src/gpd/specs/workflows/help.md")

    fragment_count(
        "paper-toolchain doctor row is single-sourced",
        "`gpd doctor --runtime <runtime> --local` / `gpd doctor --runtime <runtime> --global`",
        expected_count=1,
    ).check(help_workflow)
    assert len(re.findall(r"(?m)^\s*gpd doctor --runtime <runtime> --local\|--global\b.*$", help_workflow)) == 0


def test_public_docs_frame_typed_review_surfaces_as_command_policy_specializations() -> None:
    readme = _read("README.md")
    help_workflow = _read("src/gpd/specs/workflows/help.md")

    _assert_anchor(
        readme,
        "typed command metadata public surface",
        (
            "Typed command metadata",
            "not review-only",
            "shared command applicability surface",
            "specialized typed surfaces",
            "review/publication contracts",
        ),
    )
    _assert_anchor(
        help_workflow,
        "typed command metadata help surface",
        (
            "generic typed command-policy check",
            "public runtime surface",
            "specialized typed surfaces",
            "review/publication contracts",
        ),
    )


def test_public_docs_explain_publication_lane_boundary_and_follow_on_command_args() -> None:
    readme = _read("README.md")
    help_workflow = _read("src/gpd/specs/workflows/help.md")
    detailed_reference = _rendered_detailed_reference()
    research_publishing = _range(help_workflow, "### Research Publishing", "### Optional Local CLI Add-Ons")

    assert_publication_lane_boundary_contract(readme)
    assert_publication_lane_boundary_contract(help_workflow)
    _assert_anchor(
        readme,
        "readme publication lane semantics",
        (
            "bounded external-authoring lane",
            "explicit intake manifest only",
            "Project-backed review/response/package outputs",
            "respond-to-referees",
            "arxiv-submission",
        ),
    )
    _assert_anchor(
        research_publishing,
        "help publication lane semantics",
        (
            "bounded external-authoring lane",
            "explicit intake manifest only",
            "explicit subject allowed by its command policy",
            "resolved manuscript root",
            "not a full publication-root migration",
        ),
    )
    assert "GPD/publication/{subject_slug}" in readme
    assert "GPD/publication/{subject_slug}/..." in research_publishing
    assert "`GPD/publication/{subject_slug}/intake/`" in research_publishing
    assert "`GPD/`" in readme
    assert "`GPD/review/`" in readme
    assert "`GPD/` and `GPD/review/`" in research_publishing
    assert "`respond-to-referees`" in readme
    assert "**`gpd:respond-to-referees [--manuscript PATH --report PATH | report path | paste]`**" in detailed_reference
    assert "**`gpd:arxiv-submission [manuscript root or .tex entrypoint]`**" in detailed_reference
    assert (
        "- `gpd:respond-to-referees --manuscript paper/main.tex --report reports/referee-report.md`"
        in detailed_reference
    )
    assert "- `gpd:respond-to-referees reports/referee-report.md`" in detailed_reference
    assert "- `gpd:respond-to-referees paste`" in detailed_reference
    assert "- `gpd:arxiv-submission paper/`" in detailed_reference
    assert "- `gpd:write-paper --intake intake/write-paper-authoring-input.json`" in detailed_reference
    _assert_anchor(
        research_publishing,
        "arxiv submission package boundary",
        ("gpd:arxiv-submission", "GPD-owned manuscript root", ".tex", "does not package arbitrary external"),
    )


def test_public_write_paper_help_surfaces_match_supported_command_metadata() -> None:
    readme = _read("README.md")
    detailed_reference = _rendered_detailed_reference()
    write_paper_workflow = _read("src/gpd/specs/workflows/write-paper.md")
    public_surfaces = (readme, detailed_reference)

    for content in public_surfaces:
        assert "gpd:write-paper [title or topic]" not in content
        assert "--from-phases" not in content
        assert 'gpd:write-paper "' not in content
    assert "write-paper --intake intake/write-paper-authoring-input.json" in readme
    assert "gpd:write-paper --intake intake/write-paper-authoring-input.json" in detailed_reference

    assert "- `gpd:write-paper`" in detailed_reference
    assert "--from-phases" not in write_paper_workflow


def test_help_workflow_export_logs_surfaces_passthrough_filters() -> None:
    help_workflow = _read("src/gpd/specs/workflows/help.md")
    detailed_reference = _rendered_detailed_reference()

    export_index = "- `gpd:export-logs"
    export_detail = "**`gpd:export-logs"
    assert export_index in help_workflow
    assert export_detail in detailed_reference
    for flag in ("--command <label>", "--phase <phase>", "--category <name>"):
        assert flag in detailed_reference
    assert "empty_export: true" in detailed_reference
    assert "- `gpd:export-logs --command execute-phase --phase 3 --category workflow`" in detailed_reference
    _assert_anchor(
        detailed_reference,
        "export logs passthrough filter semantics",
        ("gpd:export-logs", "passthrough filters", "--command <label>", "--phase <phase>", "--category <name>"),
    )


def test_help_workflow_labels_observe_trace_side_effects_and_export_commit_opt_in() -> None:
    detailed_reference = _rendered_detailed_reference()

    assert "**`gpd:export [--format html|latex|zip|all] [--commit]`**" in detailed_reference
    assert "- `gpd:export --format latex --commit`" in detailed_reference
    _assert_anchor(
        detailed_reference,
        "observe and trace read/write boundary",
        (
            "gpd observe execution",
            "gpd observe sessions",
            "gpd observe show",
            "gpd trace show",
            "inspect only",
            "gpd observe event",
            "gpd observe export",
            "gpd trace start|log|stop",
            "write observability",
        ),
    )
    _assert_anchor(
        detailed_reference,
        "export commit opt in",
        ("generated text exports", "committed", "explicit `--commit`"),
    )


def test_help_workflow_error_patterns_uses_pattern_library_categories() -> None:
    detailed_reference = _rendered_detailed_reference()
    error_patterns_section = _detailed_command_block(
        detailed_reference,
        "**`gpd:error-patterns [category]`**",
        "**`gpd:record-backtrack [--reverted-commit=<sha>] [--trigger=<text>] [--phase=<NN-slug>] [description]`**",
    )
    expected_categories = {
        "sign-error",
        "factor-error",
        "convention-pitfall",
        "convergence-issue",
        "approximation-failure",
        "numerical-instability",
        "conceptual-error",
        "dimensional-error",
    }

    for category in expected_categories:
        assert category in error_patterns_section
    assert "- `gpd:error-patterns sign-error`" in error_patterns_section
    assert "Usage: `gpd:error-patterns sign`" not in error_patterns_section
    assert "boundary, gauge, combinatorial" not in error_patterns_section


def test_help_command_uses_one_shared_extract_warning() -> None:
    help_command = _read("src/gpd/commands/help.md")

    fragment_count(
        "one shared help extract warning",
        "Shared wrapper rule:",
        expected_count=1,
    ).check(help_command)
    fragment_count(
        "one shared no-rewrite warning",
        "without rewriting or invented wording",
        expected_count=1,
    ).check(help_command)


def test_help_command_keeps_one_shared_workflow_authority_note() -> None:
    help_command = _read("src/gpd/commands/help.md")

    fragment_count(
        "one shared workflow authority note",
        "fallback extracts preserve workflow marker text",
        expected_count=1,
    ).check(help_command)
    _assert_absent(
        help_command,
        "old duplicated workflow authority wording",
        "Use the loaded workflow help file as the authority.",
    )


def test_help_workflow_keeps_concise_local_cli_surface_note() -> None:
    help_workflow = _read("src/gpd/specs/workflows/help.md")

    _assert_anchor(
        help_workflow,
        "concise local cli surface note",
        ("gpd --help", "local install/readiness/permissions/diagnostics surface"),
    )
    _assert_absent(
        help_workflow,
        "old bootstrap prerequisite help note",
        "The bootstrap installer owns Node.js / Python / `venv` prerequisites",
    )


def test_help_workflow_files_and_structure_and_knowledge_lifecycle_coverages() -> None:
    help_workflow = _read("src/gpd/specs/workflows/help.md")
    detailed_reference = _rendered_detailed_reference()
    files_section = _range(help_workflow, "## Files & Structure", "## Workflow Modes")
    digest_detail = _detailed_command_block(
        detailed_reference,
        "**`gpd:digest-knowledge [topic|arXiv id|source file|knowledge path]`**",
        "**`gpd:review-knowledge",
    )
    review_detail = _detailed_command_block(
        detailed_reference,
        "**`gpd:review-knowledge [knowledge path or knowledge id]`**",
        "### Optional Local CLI Add-Ons",
    )

    assert "literature/" in files_section
    assert "knowledge/" in files_section
    assert "reviews/" in files_section
    assert "research/" not in files_section

    _assert_anchor(
        files_section,
        "files section separates literature and knowledge review paths",
        ("GPD/literature/", "GPD/knowledge/", "GPD/knowledge/reviews/"),
    )
    _assert_anchor(
        digest_detail,
        "digest knowledge lifecycle",
        (
            "draft",
            "in_review",
            "stable",
            "superseded",
            "gpd:review-knowledge",
            "shared runtime reference surfaces",
            "separate authority tier",
        ),
    )
    _assert_anchor(
        digest_detail,
        "digest knowledge canonical current-workspace target",
        ("GPD/knowledge/{knowledge_id}.md", "current workspace", "stops on ambiguity"),
    )
    fragment_count(
        "single digest canonical target resolver",
        "Resolves one canonical `GPD/knowledge/{knowledge_id}.md` target",
        expected_count=1,
        context="digest/review knowledge help",
    ).check(digest_detail + review_detail)
    _assert_anchor(
        review_detail,
        "review knowledge stable traceability",
        ("stable", "superseded", "addressable", "traceable"),
    )
    for sample in (
        '`gpd:digest-knowledge "renormalization group fixed points"`',
        "`gpd:digest-knowledge 2401.12345v2`",
        "`gpd:digest-knowledge hep-th/9901001`",
        "`gpd:digest-knowledge ./notes/rg-notes.md`",
        "`gpd:digest-knowledge GPD/knowledge/K-renormalization-group-fixed-points.md`",
    ):
        assert sample in digest_detail
    assert "legacy arxiv" not in digest_detail.lower()
    _assert_anchor(
        detailed_reference,
        "stable knowledge shared runtime visibility appears in digest and review flows",
        (
            "Stable knowledge",
            "shared runtime reference surfaces",
            "reviewed background synthesis",
            "does not override stronger evidence",
        ),
    )


def test_help_workflow_current_workspace_helpers_and_discover_quick_mode_wording() -> None:
    detailed_reference = _rendered_detailed_reference()
    command_index_rows = _rendered_command_index_rows()
    discover_detail = _detailed_command_block(
        detailed_reference,
        "**`gpd:discover [phase or topic] [--depth quick|medium|deep]`**",
        "**`gpd:show-phase",
    )
    compare_results_detail = _detailed_command_block(
        detailed_reference,
        "**`gpd:compare-results [phase, artifact, or comparison target]`**",
        "**`gpd:validate-conventions",
    )
    digest_detail = _detailed_command_block(
        detailed_reference,
        "**`gpd:digest-knowledge [topic|arXiv id|source file|knowledge path]`**",
        "**`gpd:review-knowledge",
    )
    review_detail = _detailed_command_block(
        detailed_reference,
        "**`gpd:review-knowledge [knowledge path or knowledge id]`**",
        "### Optional Local CLI Add-Ons",
    )
    literature_detail = _detailed_command_block(
        detailed_reference,
        "**`gpd:literature-review [topic or research question]`**",
        "**`gpd:digest-knowledge",
    )

    discover_index_description = command_index_rows["gpd:discover [phase or topic]"]
    assert discover_index_description.strip()
    _assert_anchor(
        discover_index_description,
        "discover command-index description semantics",
        ("Survey", "methods", "literature", "tools", "`quick`", "verification-only"),
    )
    _assert_anchor(
        discover_detail,
        "discover quick/medium/deep write boundary",
        ("quick", "verification-only", "writes no file", "medium", "deep", "write discovery artifacts"),
    )
    _assert_anchor(
        discover_detail,
        "discover artifacts feed planning or standalone analysis",
        ("discovery artifacts", "planning", "standalone analysis"),
    )
    _assert_anchor(
        compare_results_detail,
        "compare-results writes current-workspace comparison artifacts",
        ("decisive comparison artifact", "GPD/comparisons/", "current workspace"),
    )
    _assert_anchor(
        digest_detail,
        "digest current-workspace source modes",
        ("current-workspace knowledge document draft", "topic", "paper", "source file", "explicit knowledge path"),
    )
    _assert_anchor(
        review_detail,
        "review current-workspace typed approval",
        (
            "canonical current-workspace knowledge document",
            "typed approval evidence",
            "promote",
            "stable",
            "canonical path",
            "knowledge id",
            "GPD/knowledge/reviews/",
        ),
    )
    _assert_anchor(
        literature_detail,
        "literature review current project or explicit topic",
        (
            "physics research topic",
            "current project",
            "explicit topic",
            "research question",
            "GPD/literature/",
            "current workspace",
        ),
    )


def test_help_workflow_relaxed_technical_analysis_lane_stays_honest() -> None:
    detailed_reference = _rendered_detailed_reference()

    _assert_anchor(
        detailed_reference,
        "relaxed technical analysis lane",
        (
            "Project-aware technical-analysis lane",
            "gpd:derive-equation",
            "gpd:dimensional-analysis",
            "gpd:limiting-cases",
            "gpd:numerical-convergence",
            "gpd:sensitivity-analysis",
            "GPD/analysis/",
            "gpd:graph",
            "gpd:error-propagation",
            "separate commands",
        ),
    )
