"""Guardrails that keep prompt-authored CLI references aligned with the real CLI."""

from __future__ import annotations

import re
from pathlib import Path

from gpd.adapters.install_utils import expand_at_includes
from gpd.cli import app as cli_app
from gpd.core import public_surface_contract as public_surface_contract_module
from gpd.core.cli_args import _ROOT_GLOBAL_FLAG_TOKENS
from gpd.core.model_visible_text import command_visibility_note
from gpd.core.public_surface_contract import (
    local_cli_bridge_note,
    local_cli_doctor_global_command,
    local_cli_doctor_local_command,
    local_cli_permissions_status_command,
    local_cli_plan_preflight_command,
    local_cli_resume_command,
    local_cli_resume_recent_command,
    local_cli_unattended_readiness_command,
    local_cli_validate_command_context_command,
    resume_authority_fields,
)
from gpd.core.state import VALID_STATUSES
from gpd.core.workflow_presets import list_workflow_presets
from gpd.registry import VALID_CONTEXT_MODES, _parse_frontmatter, get_command, list_commands
from tests.assertion_taxonomy_support import FragmentMode, MatchMode, assert_prompt_contracts, semantic_anchor
from tests.doc_surface_contracts import (
    DOCTOR_RUNTIME_SCOPE_RE,
    assert_beginner_startup_routing_contract,
    assert_cost_advisory_contract,
    assert_cost_surface_discoverability,
    assert_health_command_public_contract,
    assert_help_command_all_extract_contract,
    assert_help_command_quick_start_extract_contract,
    assert_help_command_single_command_extract_contract,
    assert_help_workflow_command_index_contract,
    assert_help_workflow_quick_start_taxonomy_contract,
    assert_help_workflow_runtime_reference_contract,
    assert_recovery_ladder_contract,
    assert_resume_authority_contract,
    assert_runtime_reset_rediscovery_contract,
    assert_start_workflow_router_contract,
    assert_tour_command_surface_contract,
    assert_unattended_readiness_contract,
    assert_wolfram_plan_boundary_contract,
    assert_workflow_preset_surface_contract,
    resume_authority_public_vocabulary_intro,
    resume_backend_only_fields,
)
from tests.prompt_metrics_support import iter_markdown_fences
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = REPO_ROOT / "src/gpd/commands"
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"
PROMPT_ROOTS = (
    COMMANDS_DIR,
    REPO_ROOT / "src/gpd/agents",
    WORKFLOWS_DIR,
    REPO_ROOT / "src/gpd/specs/references",
    REPO_ROOT / "src/gpd/specs/templates",
)
NON_CANONICAL_GPD_COMMAND_RE = re.compile(r"(?<![A-Za-z0-9_./}])(?:\$gpd-[A-Za-z0-9{}-]+|/gpd-[A-Za-z0-9{}-]+)(?!\.md)")
RAW_AFTER_SUBCOMMAND_RE = re.compile(r"\bgpd\s+(?!--raw\b)[^`\n]*\s+--raw\b")
SUMMARY_EXTRACT_FIELDS_RE = re.compile(r"\bgpd\s+summary-extract\b[^\n`]*\s--fields\b")
COMMAND_INDEX_ENTRY_RE = re.compile(r"^- `(?P<signature>gpd:[^`]+)` - (?P<description>.+)$", re.MULTILINE)
SHELL_FENCE_LANGUAGES = frozenset({"bash", "sh", "shell", "zsh"})
RUNTIME_LABEL_IN_SHELL_RE = re.compile(
    r"(?<![A-Za-z0-9_./}])"
    r"(?:gpd:[A-Za-z0-9][A-Za-z0-9-]*|\$gpd-[A-Za-z0-9][A-Za-z0-9-]*|/gpd[:\-][A-Za-z0-9][A-Za-z0-9-]*)"
    r"(?![A-Za-z0-9_.-])"
)
COMMAND_LOOKING_FENCE_LINE_RE = re.compile(
    r"^\s*(?:"
    r"gpd:[A-Za-z0-9][A-Za-z0-9-]*"
    r"|\$gpd-[A-Za-z0-9][A-Za-z0-9-]*"
    r"|/gpd[:\-][A-Za-z0-9][A-Za-z0-9-]*"
    r"|gpd\s+[A-Za-z0-9][A-Za-z0-9-]*"
    r")(?:\b|\s|$)"
)
BRACKETED_SHELL_PLACEHOLDER_ARG_RE = re.compile(
    r"(?:^|\s)--[A-Za-z0-9][A-Za-z0-9-]*(?:=|\s+)"
    r"(?:"
    r"\"[^\"\n]*\[[A-Za-z{][^\]\n]*\][^\"\n]*\""
    r"|'[^'\n]*\[[A-Za-z{][^\]\n]*\][^'\n]*'"
    r"|\[[A-Za-z{][^\]\n]*\]"
    r"|\S*\[[A-Za-z{][^\]\n]*\]\S*"
    r")"
)
OPTIONAL_BRACKETED_SHELL_ARG_RE = re.compile(r"^\s*\[--[A-Za-z0-9][A-Za-z0-9-]*(?:\s+[^\]]+)?\]\s*\\?\s*$")
GPD_PATH_WRITE_REDIRECT_RE = re.compile(
    r"(?:^|[\s{])(?:cat\s+)?(?:>>?|[0-9]>>?)\s+[\"']?(?:\$\{?[A-Za-z_][A-Za-z0-9_]*\}?/)?GPD/"
)
BRACKETED_GPD_WRITE_PLACEHOLDER_RE = re.compile(r"\[(?:Fill(?::| from)?|[A-Za-z][A-Za-z0-9 _./:;`|-]{0,160})[^\]\n]*\]")
START_ROUTE_RUNTIME_RUN_PROSE_RE = re.compile(
    r"\bas if the researcher had run\b"
    r"|\b(?:run|runs|ran|rerun|re-run|execute|executes|executed)\s+\\?`"
    r"(?:gpd:|\$gpd-|/gpd[:\-])",
    re.IGNORECASE,
)
APPROVED_RUNTIME_LABEL_SHELL_FENCE_LINES = {
    ("src/gpd/commands/suggest-next.md", 'echo "Try gpd:progress for manual project status."'),
    ("src/gpd/agents/gpd-planner.md", 'cat "$phase_dir"/*-CONTEXT.md 2>/dev/null   # From gpd:discuss-phase'),
    (
        "src/gpd/agents/gpd-planner.md",
        'cat "$phase_dir"/*-RESEARCH.md 2>/dev/null   # From gpd:research-phase or discover',
    ),
    ("src/gpd/specs/workflows/discuss-phase.md", 'echo "Use gpd:progress to see available phases."'),
    (
        "src/gpd/specs/workflows/execute-phase/phase-bootstrap.md",
        'echo "ERROR: missing phase. Usage: execute-phase <phase-number> [--gaps-only]"',
    ),
    (
        "src/gpd/specs/workflows/execute-phase/wave-planning.md",
        'Emit a final line `"Next Up: gpd:execute-phase {N}"` so the operator can resume after resolving alignment.',
    ),
    (
        "src/gpd/specs/workflows/plan-milestone-gaps.md",
        'echo "ERROR: No existing phases found. Create phases with gpd:plan-phase first."',
    ),
}
APPROVED_BRACKETED_SHELL_ARG_LINES = {
    (
        "src/gpd/specs/workflows/complete-milestone.md",
        'ARCHIVE=$(gpd milestone complete "v[X.Y]" --name "[Milestone Name]")',
    ),
    ("src/gpd/specs/workflows/new-milestone.md", '--summary "Started milestone v[X.Y]: [Name]" \\'),
}


def _extract_between(content: str, start_marker: str, end_marker: str) -> str:
    start = content.index(start_marker) + len(start_marker)
    end = content.index(end_marker, start)
    return content[start:end]


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _assert_normalized_fragments(content: str, fragments: tuple[str, ...]) -> None:
    normalized = _normalize_text(content)
    missing = [fragment for fragment in fragments if _normalize_text(fragment) not in normalized]
    assert missing == []


def _assert_normalized_absent(content: str, fragments: tuple[str, ...]) -> None:
    normalized = _normalize_text(content)
    present = [fragment for fragment in fragments if _normalize_text(fragment) in normalized]
    assert present == []


def _assert_ordered_fragments(content: str, fragments: tuple[str, ...]) -> None:
    normalized = _normalize_text(content)
    cursor = 0
    missing: list[str] = []
    for fragment in fragments:
        normalized_fragment = _normalize_text(fragment)
        position = normalized.find(normalized_fragment, cursor)
        if position < 0:
            missing.append(fragment)
            continue
        cursor = position + len(normalized_fragment)
    assert missing == []


def _assert_semantic_fragments(content: str, context: str, fragments: tuple[str, ...]) -> None:
    assert_prompt_contracts(
        content,
        semantic_anchor(context, fragments, match=MatchMode.CASEFOLD_NORMALIZED, context=context),
    )


def _assert_semantic_absent(content: str, context: str, fragments: tuple[str, ...]) -> None:
    assert_prompt_contracts(
        content,
        semantic_anchor(
            context,
            fragments,
            mode=FragmentMode.ABSENT,
            match=MatchMode.CASEFOLD_NORMALIZED,
            context=context,
        ),
    )


def _typer_command_name(command_info: object) -> str:
    name = getattr(command_info, "name", None)
    if name:
        return str(name)
    callback = getattr(command_info, "callback", None)
    if callback is not None:
        return str(callback.__name__).replace("_", "-")
    raise AssertionError(f"Typer command metadata has no name or callback: {command_info!r}")


def _declared_command_surfaces() -> set[str]:
    root_commands = _declared_root_commands()
    group_commands = _declared_groups()
    surfaces = set(root_commands)
    surfaces.update(group_commands)
    for group_name, subcommands in group_commands.items():
        surfaces.update(f"{group_name} {subcommand}" for subcommand in subcommands)
    return surfaces


def _declared_root_commands() -> set[str]:
    return {_typer_command_name(command) for command in cli_app.registered_commands}


def _declared_groups() -> dict[str, set[str]]:
    groups: dict[str, set[str]] = {}
    for group in cli_app.registered_groups:
        group_name = getattr(group, "name", None)
        assert group_name, f"Typer group metadata has no name: {group!r}"
        typer_instance = group.typer_instance
        subcommands = {_typer_command_name(command) for command in typer_instance.registered_commands}
        for nested_group in typer_instance.registered_groups:
            nested_name = getattr(nested_group, "name", None)
            assert nested_name, f"Nested Typer group metadata has no name: {nested_group!r}"
            subcommands.add(str(nested_name))
        groups[str(group_name)] = subcommands
    return groups


def _command_index_runtime_labels(command_index_markdown: str) -> set[str]:
    labels: set[str] = set()
    for match in COMMAND_INDEX_ENTRY_RE.finditer(command_index_markdown):
        signature = match.group("signature")
        labels.add(signature.split()[0])
    return labels


def _workflow_preset_labels() -> set[str]:
    return {preset.label for preset in list_workflow_presets()}


def _iter_prompt_sources() -> list[Path]:
    files: list[Path] = []
    for root in PROMPT_ROOTS:
        files.extend(sorted(root.rglob("*.md")))
    return files


def _shell_fence_language(info: str) -> str:
    return info.strip().split(None, 1)[0].casefold() if info.strip() else ""


def _has_bracketed_shell_placeholder_arg(line: str) -> bool:
    return bool(BRACKETED_SHELL_PLACEHOLDER_ARG_RE.search(line) or OPTIONAL_BRACKETED_SHELL_ARG_RE.search(line))


def _iter_markdown_code_samples(content: str) -> list[str]:
    samples: list[str] = []
    fenced_pattern = re.compile(r"```(?:[^\n`]*)\n(.*?)```", re.DOTALL)
    for match in fenced_pattern.finditer(content):
        samples.append(match.group(1))
    inline_source = fenced_pattern.sub("\n", content)
    samples.extend(re.findall(r"`([^`]+)`", inline_source))
    return samples


def _extract_gpd_command_surfaces(
    content: str,
    *,
    root_commands: set[str],
    group_commands: dict[str, set[str]],
) -> list[str]:
    command_roots = root_commands | set(group_commands)
    if not command_roots:
        return []

    root_pattern = "|".join(sorted((re.escape(root) for root in command_roots), key=len, reverse=True))
    root_flag_pattern = "|".join(sorted((re.escape(flag) for flag in _ROOT_GLOBAL_FLAG_TOKENS), key=len, reverse=True))
    prefix_pattern = rf"(?:\s+(?:{root_flag_pattern}|--cwd(?:=[^\s`]+)?|--cwd\s+[^\s`]+))*"
    pattern = re.compile(rf"\bgpd{prefix_pattern}\s+({root_pattern})(?:\s+([a-z0-9-]+))?")
    surfaces: list[str] = []
    for sample in _iter_markdown_code_samples(content):
        for match in pattern.finditer(sample):
            command = match.group(1)
            subcommand = match.group(2)
            if command in root_commands and command not in group_commands:
                surfaces.append(command)
                continue
            if command in group_commands:
                surfaces.append(command if subcommand is None else f"{command} {subcommand}")
    return surfaces


def test_prompt_sources_keep_command_surface_rules_canonical_and_consistent() -> None:
    allowed = _declared_command_surfaces()
    root_commands = _declared_root_commands()
    group_commands = _declared_groups()

    invalid_surfaces: list[str] = []
    noncanonical_surfaces: list[str] = []
    raw_after_subcommand: list[str] = []
    summary_extract_fields: list[str] = []

    for path in _iter_prompt_sources():
        content = path.read_text(encoding="utf-8")
        relpath = str(path.relative_to(REPO_ROOT))

        for surface in _extract_gpd_command_surfaces(
            content, root_commands=root_commands, group_commands=group_commands
        ):
            if surface not in allowed:
                invalid_surfaces.append(f"{relpath} -> {surface}")

        for match in NON_CANONICAL_GPD_COMMAND_RE.finditer(content):
            noncanonical_surfaces.append(f"{relpath} -> {match.group(0)}")

        for match in RAW_AFTER_SUBCOMMAND_RE.finditer(content):
            raw_after_subcommand.append(f"{relpath} -> {match.group(0)}")

        for match in SUMMARY_EXTRACT_FIELDS_RE.finditer(content):
            summary_extract_fields.append(f"{relpath} -> {match.group(0)}")

    assert invalid_surfaces == []
    assert noncanonical_surfaces == []
    assert raw_after_subcommand == []
    assert summary_extract_fields == []


def test_prompt_shell_fences_do_not_add_runtime_command_labels() -> None:
    offenders: list[str] = []

    for path in _iter_prompt_sources():
        content = path.read_text(encoding="utf-8")
        relpath = path.relative_to(REPO_ROOT).as_posix()

        for fence in iter_markdown_fences(content):
            if _shell_fence_language(fence.info) not in SHELL_FENCE_LANGUAGES:
                continue
            for offset, line in enumerate(fence.body.splitlines(), start=1):
                stripped = line.strip()
                if not RUNTIME_LABEL_IN_SHELL_RE.search(line):
                    continue
                if (relpath, stripped) in APPROVED_RUNTIME_LABEL_SHELL_FENCE_LINES:
                    continue
                offenders.append(f"{relpath}:{fence.start_line + offset} -> {stripped}")

    assert offenders == []


def test_agent_infrastructure_distinguishes_structural_phase_verify_from_verify_work() -> None:
    text = (REPO_ROOT / "src/gpd/specs/references/orchestration/agent-infrastructure.md").read_text(encoding="utf-8")

    assert "These terminal `gpd verify ...` commands are structural checks." in text
    assert "They do not" in text
    assert "replace the runtime `gpd:verify-work <phase>` workflow" in text
    assert "gpd verify phase" in text


def test_command_looking_fences_are_explicitly_labeled() -> None:
    offenders: list[str] = []

    for path in _iter_prompt_sources():
        content = path.read_text(encoding="utf-8")
        relpath = path.relative_to(REPO_ROOT).as_posix()

        for fence in iter_markdown_fences(content):
            if fence.info.strip():
                continue
            for offset, line in enumerate(fence.body.splitlines(), start=1):
                stripped = line.strip()
                if COMMAND_LOOKING_FENCE_LINE_RE.search(line):
                    offenders.append(f"{relpath}:{fence.start_line + offset} -> {stripped}")

    assert offenders == []


def test_prompt_shell_arguments_do_not_add_bracketed_placeholders() -> None:
    offenders: list[str] = []

    for path in _iter_prompt_sources():
        content = path.read_text(encoding="utf-8")
        relpath = path.relative_to(REPO_ROOT).as_posix()

        for fence in iter_markdown_fences(content):
            if _shell_fence_language(fence.info) not in SHELL_FENCE_LANGUAGES:
                continue
            for offset, line in enumerate(fence.body.splitlines(), start=1):
                stripped = line.strip()
                if not _has_bracketed_shell_placeholder_arg(line):
                    continue
                if (relpath, stripped) in APPROVED_BRACKETED_SHELL_ARG_LINES:
                    continue
                offenders.append(f"{relpath}:{fence.start_line + offset} -> {stripped}")

    assert offenders == []


def test_prompt_shell_fences_do_not_write_gpd_placeholder_heredocs() -> None:
    offenders: list[str] = []

    for path in _iter_prompt_sources():
        content = path.read_text(encoding="utf-8")
        relpath = path.relative_to(REPO_ROOT).as_posix()

        for fence in iter_markdown_fences(content):
            if _shell_fence_language(fence.info) not in SHELL_FENCE_LANGUAGES:
                continue
            if not GPD_PATH_WRITE_REDIRECT_RE.search(fence.body):
                continue
            for offset, line in enumerate(fence.body.splitlines(), start=1):
                stripped = line.strip()
                if BRACKETED_GPD_WRITE_PLACEHOLDER_RE.search(line):
                    offenders.append(f"{relpath}:{fence.start_line + offset} -> {stripped}")

    assert offenders == []


def test_start_workflow_routes_runtime_labels_without_shell_run_prose() -> None:
    workflow = (WORKFLOWS_DIR / "start.md").read_text(encoding="utf-8")
    route_step = _extract_between(workflow, '<step name="route_choice">', "</step>")

    assert START_ROUTE_RUNTIME_RUN_PROSE_RE.search(route_step) is None


def test_prompt_surface_extractor_matches_shared_root_global_flags() -> None:
    root_commands = _declared_root_commands()
    group_commands = _declared_groups()

    sample = """
    ```text
    gpd --version -v --cwd /tmp/workspace progress bar
    ```
    """

    assert _extract_gpd_command_surfaces(
        sample,
        root_commands=root_commands,
        group_commands=group_commands,
    ) == ["progress"]


def test_help_prompt_delegates_full_reference_to_workflow() -> None:
    help_prompt = (REPO_ROOT / "src/gpd/commands/help.md").read_text(encoding="utf-8")

    assert "@{GPD_INSTALL_DIR}/workflows/help.md" in help_prompt
    assert "workflow-owned help surface" in help_prompt
    assert "Compact Command Index (--all)" in help_prompt
    assert_help_command_all_extract_contract(help_prompt)
    assert_help_command_single_command_extract_contract(help_prompt)


def test_help_prompt_default_quick_start_extracts_workflow_owned_sections() -> None:
    help_prompt = (COMMANDS_DIR / "help.md").read_text(encoding="utf-8")
    help_workflow = (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8")
    quick_start = _extract_between(
        help_prompt,
        "## Step 2: Quick Start Extract (Default Output)",
        "## Step 3: Compact Command Index (--all)",
    )

    assert_help_command_quick_start_extract_contract(quick_start)
    assert_help_workflow_runtime_reference_contract(help_workflow)
    quick_start_reference = _extract_between(help_workflow, "## Quick Start", "## Command Index")
    command_index = _extract_between(help_workflow, "## Command Index", "## Detailed Command Reference")
    assert_help_workflow_quick_start_taxonomy_contract(quick_start_reference)
    assert_help_workflow_command_index_contract(command_index)
    assert_beginner_startup_routing_contract(quick_start_reference)
    assert _command_index_runtime_labels(command_index) == set(list_commands(name_format="label"))
    assert "Usage: `/gpd:start`" not in quick_start_reference
    assert "## Detailed Command Reference" in help_workflow
    _assert_ordered_fragments(
        help_workflow,
        (
            "gpd:new-project",
            "gpd:discuss-phase",
            "gpd:plan-phase",
            "gpd:execute-phase",
            "gpd:verify-work",
            "repeat",
        ),
    )
    assert "gpd init new-project" not in help_workflow
    for token in ("gpd:discuss-phase", "gpd:write-paper", "gpd:tangent", "gpd:set-tier-models", "gpd:settings"):
        assert token in command_index


def test_help_prompt_keeps_workflow_preset_readiness_on_local_cli_surface() -> None:
    help_command = (COMMANDS_DIR / "help.md").read_text(encoding="utf-8")
    help_workflow = (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8")
    quick_start = _extract_between(
        help_command,
        "## Step 2: Quick Start Extract (Default Output)",
        "## Step 3: Compact Command Index (--all)",
    )

    assert "## Invocation Surfaces" not in quick_start
    _assert_semantic_fragments(
        quick_start,
        "help quick-start wrapper extraction",
        (
            "Exclude the marker comment lines themselves.",
            "Append this one wrapper-owned line",
        ),
    )
    assert_help_workflow_runtime_reference_contract(help_workflow)
    optional_addons = _extract_between(help_workflow, "### Optional Local CLI Add-Ons", "Workflow presets are bundles")
    _assert_normalized_fragments(
        optional_addons,
        (
            "Workflow presets",
            "gpd presets list",
            "gpd presets show <preset>",
            "gpd presets apply <preset>",
            "pdflatex --version",
            "tectonic --version",
            "wolframscript -version",
        ),
    )
    assert DOCTOR_RUNTIME_SCOPE_RE.search(help_workflow) is not None
    assert_wolfram_plan_boundary_contract(help_workflow)
    assert_workflow_preset_surface_contract(help_workflow)
    _assert_normalized_fragments(
        help_workflow,
        (
            "Workflow presets are bundles over the existing config keys only",
            "they do not add a separate persisted preset block",
            "Workflow preset tooling is layered on top of the base install",
            "does not change runtime permission alignment",
        ),
    )


def test_start_prompt_delegates_routing_to_workflow_only() -> None:
    start_command = (COMMANDS_DIR / "start.md").read_text(encoding="utf-8")
    start_command_expanded = expand_at_includes(start_command, REPO_ROOT / "src/gpd", "/runtime/")
    start_workflow = (WORKFLOWS_DIR / "start.md").read_text(encoding="utf-8")
    start_registry = get_command("start")
    reopen_recent_branch = _extract_between(
        start_workflow,
        "**If the researcher chooses option_id `reopen_recent`",
        "- STOP after giving those instructions.",
    )

    assert "@{GPD_INSTALL_DIR}/workflows/start.md" in start_command
    assert "@{GPD_INSTALL_DIR}/references/onboarding/beginner-command-taxonomy.md" in start_command
    assert start_registry.argument_hint == "[optional short goal]"
    assert start_registry.context_mode == "projectless"
    _assert_semantic_fragments(
        start_command_expanded,
        "start command wrapper delegates chooser semantics",
        (
            "actual first-run chooser",
            "read-only walkthrough",
            "gpd:tour",
            "same-message explicit choice counts only as the chooser answer",
        ),
    )
    _assert_semantic_fragments(
        start_command,
        "start command wrapper explains terms without parallel routing",
        (
            "explain official terms",
            "first time they appear",
            "do not invent a parallel onboarding state machine",
        ),
    )
    assert_start_workflow_router_contract(start_workflow)
    assert local_cli_resume_recent_command() in reopen_recent_branch
    _assert_semantic_fragments(
        reopen_recent_branch,
        "start reopen recent branch keeps terminal picker and runtime continuation boundary",
        (
            "normal terminal",
            "recent-project picker",
            "advisory",
            "gpd:resume-work",
            "reloads canonical state",
            "auto-select",
            "choose the project explicitly",
            "open that project folder in the runtime",
            "in-runtime continuation step",
            "reopened its workspace",
        ),
    )
    assert "Read `{GPD_INSTALL_DIR}/workflows/new-project.md` with the file-read tool." not in start_workflow
    assert "Read `{GPD_INSTALL_DIR}/workflows/help.md` with the file-read tool." not in start_workflow
    assert "Read `{GPD_INSTALL_DIR}/workflows/tour.md` with the file-read tool." not in start_workflow
    assert "{GPD_INSTALL_DIR}/commands/suggest-next.md" not in start_workflow


def test_tour_prompt_delegates_routing_to_workflow_only() -> None:
    tour_command = (COMMANDS_DIR / "tour.md").read_text(encoding="utf-8")
    tour_command_expanded = expand_at_includes(tour_command, REPO_ROOT / "src/gpd", "/runtime/")
    tour_workflow = (WORKFLOWS_DIR / "tour.md").read_text(encoding="utf-8")

    assert "@{GPD_INSTALL_DIR}/workflows/tour.md" in tour_command
    assert "@{GPD_INSTALL_DIR}/references/onboarding/beginner-command-taxonomy.md" in tour_command
    _assert_semantic_fragments(
        tour_command,
        "tour command is a teaching surface",
        (
            "teaching surface, not a chooser",
            "safe beginner walkthrough of the core GPD command paths",
        ),
    )
    assert "gpd:set-tier-models" in tour_command
    assert "gpd:settings" in tour_command
    assert "gpd:tour --all" in tour_command
    assert "gpd:tour --reference" in tour_command
    assert "gpd:help --all" in tour_command
    assert "gpd:start" in tour_command_expanded
    assert "gpd:resume-work" in tour_command_expanded
    assert_tour_command_surface_contract(tour_workflow)
    assert "$ARGUMENTS" in tour_workflow
    _assert_semantic_fragments(
        tour_workflow,
        "tour workflow does not route",
        (
            "Do not narrow the command list, select a path, or route based on non-flag context.",
            "Unknown flags are context only unless they are exactly `--all` or `--reference`.",
            "the runtime, where you use the GPD command prefix provided for that runtime",
        ),
    )
    _assert_semantic_fragments(
        tour_workflow,
        "tour workflow keeps concise default and reference-mode boundaries",
        (
            "80 lines or fewer",
            "4500 characters or fewer",
            "gpd:help --all",
            "canonical complete command index",
            "Normal terminal vs runtime",
        ),
    )


def test_help_workflow_surfaces_start_as_first_run_router() -> None:
    help_workflow = (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8")
    quick_start_reference = _extract_between(help_workflow, "## Quick Start", "## Command Index")

    assert get_command("start").name in help_workflow
    assert get_command("tour").name in help_workflow
    _assert_semantic_fragments(
        quick_start_reference,
        "help quick start surfaces start as first-run router and tour as explainer",
        (
            "gpd:start",
            "first-run router",
            "safest first step",
            "gpd:tour",
            "read-only",
        ),
    )
    assert_beginner_startup_routing_contract(quick_start_reference)


def test_help_new_project_detail_describes_current_scope_gate_contract() -> None:
    help_workflow = (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8")
    new_project_detail = _extract_between(help_workflow, "**`gpd:new-project`**", "**`gpd:map-research`**")

    for fragment in (
        "All modes build a scoping contract before downstream artifacts.",
        "Blocking gaps get one targeted repair prompt",
        "scope must be explicitly approved",
        "`--minimal @file.md`",
        "still repairs blocking gaps and asks for scoping approval",
        "`--auto`",
        "follows the configured autonomy gates",
    ):
        assert fragment in new_project_detail

    for stale_fragment in (
        "Same file set as full mode",
        "No interactive questions asked",
        "without interaction",
        "auto-generate everything",
    ):
        assert stale_fragment not in new_project_detail


def test_new_project_minimal_prompt_documents_core_artifacts_not_full_mode_outputs() -> None:
    command_text = (COMMANDS_DIR / "new-project.md").read_text(encoding="utf-8")
    workflow_text = workflow_authority_text(WORKFLOWS_DIR, "new-project")
    completion = (WORKFLOWS_DIR / "new-project" / "completion.md").read_text(encoding="utf-8")

    assert "does not promise" in command_text
    assert "no promise is made" in completion
    for content in (command_text, completion):
        assert "GPD/CONVENTIONS.md" in content
        assert "GPD/literature/" in content

    minimal_success = _extract_between(
        command_text,
        "**Minimal mode success criteria (if `--minimal`):**",
        "</success_criteria>",
    )
    assert "documented core startup set" in minimal_success
    _assert_semantic_absent(
        minimal_success,
        "minimal mode does not promise full-mode file set",
        ("Same directory structure and file set as full path",),
    )
    assert "CONVENTIONS.md` created" not in minimal_success
    for stale_fragment in (
        "Ask ONE question, then generate everything",
        "generate everything from the response",
    ):
        assert stale_fragment not in workflow_text


def test_prompt_docs_keep_wolfram_as_shared_capability_not_runtime_config_surface() -> None:
    help_command = (COMMANDS_DIR / "help.md").read_text(encoding="utf-8")
    help_workflow = (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8")
    settings_workflow = (WORKFLOWS_DIR / "settings.md").read_text(encoding="utf-8")
    tooling_ref = (REPO_ROOT / "src/gpd/specs/references/tooling/tool-integration.md").read_text(encoding="utf-8")

    forbidden_tokens = (
        "gpd-wolfram",
        "gpd-mcp-wolfram",
        "GPD_WOLFRAM_MCP_API_KEY",
        "GPD_WOLFRAM_MCP_ENDPOINT",
        "WOLFRAM_MCP_SERVICE_API_KEY",
    )
    for content in (help_command, help_workflow, settings_workflow):
        for token in forbidden_tokens:
            assert token not in content

    assert "@{GPD_INSTALL_DIR}/workflows/help.md" in help_command
    assert_unattended_readiness_contract(help_workflow)
    assert_wolfram_plan_boundary_contract(help_workflow)
    assert "gpd integrations enable wolfram" in help_workflow
    assert "gpd integrations disable wolfram" in help_workflow
    assert_workflow_preset_surface_contract(help_workflow)

    assert "Mathematica / Wolfram Language" in tooling_ref
    assert "declare it as `tool: wolfram` in `tool_requirements`" in tooling_ref
    assert "gpd validate plan-preflight" in tooling_ref


def test_suggest_next_prompt_uses_real_cli_subcommand() -> None:
    suggest_prompt = (REPO_ROOT / "src/gpd/commands/suggest-next.md").read_text(encoding="utf-8")

    assert_runtime_reset_rediscovery_contract(suggest_prompt)
    assert "Uses `gpd --raw suggest`" in suggest_prompt
    assert "Local CLI fallback: `gpd --raw suggest`" in suggest_prompt
    assert (
        f"If you still need to rediscover the project first, do that in your normal terminal with `{local_cli_resume_command()}` for the current workspace or `{local_cli_resume_recent_command()}` for the explicit multi-project picker before reopening the runtime."
        in suggest_prompt
    )
    _assert_semantic_fragments(
        suggest_prompt,
        "suggest-next fresh context and renderer contract",
        (
            "Start the recommended command in a fresh context window; do not treat the fresh context reset as project recovery.",
            "Use the shared renderer shape for this single-recommendation block.",
            "Do not use a separate bold-only command block.",
        ),
    )
    assert "Primary: `{command}`" in suggest_prompt
    assert "/clear" not in suggest_prompt
    assert (
        f"`/clear` first -> fresh context window, then `{{command}}`; if you still need to rediscover the project, use `{local_cli_resume_recent_command()}` before reopening the runtime"
        not in suggest_prompt
    )
    assert "gpd suggest-next to scan" not in suggest_prompt


def test_tangent_prompt_routes_into_existing_workflows() -> None:
    tangent_command = (COMMANDS_DIR / "tangent.md").read_text(encoding="utf-8")
    tangent_workflow = (WORKFLOWS_DIR / "tangent.md").read_text(encoding="utf-8")

    assert "name: gpd:tangent" in tangent_command
    assert "@{GPD_INSTALL_DIR}/workflows/tangent.md" in tangent_command
    assert "gpd:quick" in tangent_command
    assert "gpd:add-todo" in tangent_command
    assert "gpd:branch-hypothesis" in tangent_command

    for token in (
        "Stay on the main path",
        "Run a bounded quick check now",
        "Capture and defer",
        "Open a hypothesis branch",
        "live execution review stop surfaces a tangent proposal",
        "{GPD_INSTALL_DIR}/workflows/quick.md",
        "{GPD_INSTALL_DIR}/workflows/add-todo.md",
        "{GPD_INSTALL_DIR}/workflows/branch-hypothesis.md",
    ):
        assert token in tangent_workflow


def test_progress_prompt_runs_preflight_after_init_context() -> None:
    command = (REPO_ROOT / "src/gpd/commands/progress.md").read_text(encoding="utf-8")
    workflow = (REPO_ROOT / "src/gpd/specs/workflows/progress.md").read_text(encoding="utf-8")

    assert "@{GPD_INSTALL_DIR}/workflows/progress.md" in command
    _assert_semantic_fragments(
        command,
        "progress command delegates workflow logic",
        ("Follow the included workflow exactly. Do not duplicate the workflow logic here.",),
    )
    assert "INIT=$(gpd --raw init progress --include state,roadmap,project,config,references)" not in command
    assert 'CONTEXT=$(gpd --raw validate command-context progress "$ARGUMENTS")' not in command
    _assert_semantic_absent(
        command,
        "progress command excludes resume-recovery branch prose",
        (
            "The recent-project picker is advisory",
            "reloads canonical state for that project",
        ),
    )

    assert "INIT=$(gpd --raw init progress --include state,roadmap,project,config,references)" in workflow
    assert 'CONTEXT=$(gpd --raw validate command-context progress "$ARGUMENTS")' in workflow
    init_index = workflow.index("INIT=$(gpd --raw init progress --include state,roadmap,project,config,references)")
    assert init_index < workflow.index('CONTEXT=$(gpd --raw validate command-context progress "$ARGUMENTS")')


def test_progress_reconcile_prompt_preserves_no_write_confirmation_branches() -> None:
    workflow = (REPO_ROOT / "src/gpd/specs/workflows/progress.md").read_text(encoding="utf-8")

    reconcile_start = workflow.index('<step name="reconcile_state">')
    reconcile_end = workflow.index('<step name="init_context">', reconcile_start)
    reconcile_step = workflow[reconcile_start:reconcile_end]

    _assert_normalized_fragments(
        reconcile_step,
        (
            '"Sync STATE.md to disk" (Recommended)',
            '"Keep STATE.md"',
            '"Show details"',
            "update STATE.md position",
            "before any command that writes reconciled state",
            "explicit user decision",
            "`Sync STATE.md to disk`",
            "`Keep STATE.md`",
            "`Show details`",
            "do not infer consent",
        ),
    )
    assert reconcile_step.index('"Show details"') < reconcile_step.index("If user chooses sync")


def test_health_prompt_documents_the_real_raw_health_report_shape() -> None:
    health_command = (COMMANDS_DIR / "health.md").read_text(encoding="utf-8")

    assert_health_command_public_contract(health_command)
    assert "{fixable_count}" not in health_command
    assert "Run `gpd:health --fix`" in health_command


def test_progress_prompt_requires_project_not_roadmap() -> None:
    command = (REPO_ROOT / "src/gpd/commands/progress.md").read_text(encoding="utf-8")

    assert 'files: ["GPD/PROJECT.md"]' in command
    assert 'files: ["GPD/ROADMAP.md"]' not in command


def test_progress_prompt_and_help_clarify_runtime_vs_local_cli_boundary() -> None:
    command = (REPO_ROOT / "src/gpd/commands/progress.md").read_text(encoding="utf-8")
    help_workflow = (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8")
    progress_section = _extract_between(help_workflow, "**`gpd:progress", "**`gpd:suggest-next")
    progress_registry = get_command("progress")

    assert progress_registry.argument_hint == "[--brief | --full | --reconcile]"
    assert "progress" in _declared_root_commands()
    _assert_normalized_fragments(
        command,
        (
            "`--brief`, `--full`, and `--reconcile`",
            "runtime-surface options for `gpd:progress`",
            "local CLI `gpd progress`",
            "read-only renderer",
            "json|bar|table",
            "does not accept these flags",
        ),
    )
    _assert_normalized_fragments(
        progress_section,
        (
            "`gpd:progress --full`",
            "`gpd:progress --brief`",
            "`gpd:progress --reconcile`",
            "local CLI `gpd progress`",
            "read-only renderer",
            "json|bar|table",
            "Local CLI: `gpd progress json|bar|table`",
        ),
    )


def test_progress_health_advice_uses_runtime_command_wording() -> None:
    workflow = (WORKFLOWS_DIR / "progress.md").read_text(encoding="utf-8")

    assert "Run `gpd:health --fix`" in workflow
    assert "Run `gpd health --fix`" not in workflow


def test_plan_phase_prompt_is_a_thin_dispatch_shell() -> None:
    command = (REPO_ROOT / "src/gpd/commands/plan-phase.md").read_text(encoding="utf-8")

    assert "@{GPD_INSTALL_DIR}/workflows/plan-phase/phase-bootstrap.md" in command
    assert "@{GPD_INSTALL_DIR}/workflows/plan-phase.md" not in command
    assert "@{GPD_INSTALL_DIR}/templates/plan-contract-schema.md" not in command
    assert "@{GPD_INSTALL_DIR}/references/ui/ui-brand.md" not in command
    _assert_semantic_fragments(
        command,
        "plan-phase wrapper delegates later stage loading to manifest authorities",
        ("Later stage loading is manifest-owned by the workflow stage authorities",),
    )
    assert "agent: gpd-planner" in command
    _assert_semantic_absent(
        command,
        "plan-phase dispatch shell excludes planning-guide prose",
        (
            "What Makes a Good Physics Plan",
            "Quick Checklist Before Approving a Plan",
        ),
    )
    assert "Common Failure Modes" not in command
    assert "Domain-Aware Planning" not in command
    assert "gpd --raw init plan-phase" not in command


def test_new_milestone_prompt_mentions_planning_commit_docs() -> None:
    command = (REPO_ROOT / "src/gpd/commands/new-milestone.md").read_text(encoding="utf-8")
    workflow = workflow_authority_text(WORKFLOWS_DIR, "new-milestone")

    for content in (command, workflow):
        assert "planning.commit_docs" in content
        assert "gpd:discuss-phase [N]" in content or "gpd:discuss-phase 1" in content


def test_new_milestone_state_status_literals_are_valid() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "new-milestone")

    statuses = re.findall(r'"--Status"\s+"([^"]+)"', workflow)

    assert statuses
    assert all(status in VALID_STATUSES for status in statuses)
    assert "Defining objectives" not in workflow


def test_new_milestone_roadmapper_stage_parse_and_artifact_words_match_payload() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "new-milestone")

    roadmap_authoring = workflow[workflow.index("ROADMAPPER_INIT=") :]

    assert "`planning_exists`" not in roadmap_authoring.split("Use the bootstrap init", maxsplit=1)[0]
    assert "fresh `SUMMARY.md` proof" not in roadmap_authoring
    assert (
        "gpd validate handoff-artifacts - --expected GPD/ROADMAP.md --expected GPD/REQUIREMENTS.md" in roadmap_authoring
    )
    assert "shared_state_policy: return_only" in roadmap_authoring
    assert "direct roadmapper edit to\n`GPD/STATE.md` is not success proof." in roadmap_authoring


def test_progress_route_d_includes_required_milestone_version_argument() -> None:
    workflow = (WORKFLOWS_DIR / "progress.md").read_text(encoding="utf-8")

    route_step = _extract_between(workflow, '<step name="route">', "</step>")

    assert "SUGGEST=$(gpd --raw suggest)" in route_step
    assert "milestone completion" in route_step
    assert "Do not choose" in route_step
    assert "**Route D: Milestone complete**" not in workflow
    assert "`gpd:complete-milestone {milestone_version}`" not in workflow
    assert "`gpd:complete-milestone`\n" not in workflow


def test_command_prompts_declare_valid_context_modes() -> None:
    missing: list[str] = []
    invalid: list[str] = []

    for path in sorted((REPO_ROOT / "src/gpd/commands").glob("*.md")):
        meta, _body = _parse_frontmatter(path.read_text(encoding="utf-8"))
        mode = meta.get("context_mode")
        if mode is None:
            missing.append(str(path.relative_to(REPO_ROOT)))
            continue
        if str(mode) not in VALID_CONTEXT_MODES:
            invalid.append(f"{path.relative_to(REPO_ROOT)} -> {mode}")

    assert missing == []
    assert invalid == []


def test_new_project_prompt_uses_stdin_for_contract_validation_and_persistence() -> None:
    workflow = (REPO_ROOT / "src/gpd/specs/workflows/new-project/scope-approval.md").read_text(encoding="utf-8")

    assert (
        "printf '%s\\n' \"$PROJECT_CONTRACT_JSON\" | gpd --raw validate project-contract - --mode approved" in workflow
    )
    assert "printf '%s\\n' \"$PROJECT_CONTRACT_JSON\" | gpd state set-project-contract -" in workflow
    assert "/tmp/gpd-project-contract.json" not in workflow
    _assert_semantic_absent(
        workflow,
        "project-contract persistence avoids temporary file fallback",
        ("temporary JSON file if needed",),
    )


def test_state_json_schema_stays_aligned_with_stdin_contract_persistence_flow() -> None:
    schema = expand_at_includes(
        (REPO_ROOT / "src/gpd/specs/templates/state-json-schema.md").read_text(encoding="utf-8"),
        REPO_ROOT / "src/gpd/specs",
        "/runtime/",
    )

    assert "printf '%s\\n' \"$PROJECT_CONTRACT_JSON\" | gpd --raw validate project-contract -" in schema
    assert "printf '%s\\n' \"$PROJECT_CONTRACT_JSON\" | gpd state set-project-contract -" in schema
    assert "gpd state advance" in schema
    assert "gpd state advance-plan" not in schema
    assert "Preferred write path: `gpd state set-project-contract <path-to-contract.json>`." not in schema


def test_new_project_and_state_schema_surface_contract_id_integrity_rules() -> None:
    workflow = (REPO_ROOT / "src/gpd/specs/workflows/new-project/scope-approval.md").read_text(encoding="utf-8")
    schema = expand_at_includes(
        (REPO_ROOT / "src/gpd/specs/templates/state-json-schema.md").read_text(encoding="utf-8"),
        REPO_ROOT / "src/gpd/specs",
        "/runtime/",
    )

    assert "Follow the schema exactly" in workflow
    assert "no invented\nkeys" in workflow
    assert "near-miss enum values" in workflow
    assert "list fields" in workflow
    _assert_semantic_fragments(
        schema,
        "project contract id integrity",
        (
            "Same-kind IDs must be unique within each section.",
            "must not match any declared contract ID",
        ),
    )


def test_compare_branches_prompt_keeps_branch_summary_extraction_in_memory() -> None:
    workflow = (REPO_ROOT / "src/gpd/specs/workflows/compare-branches.md").read_text(encoding="utf-8")

    _assert_semantic_fragments(
        workflow,
        "compare-branches keeps summary extraction in memory",
        (
            "Prefer parsing the `git show` output directly in memory.",
            "Keep branch-summary extraction in memory/stdout only",
        ),
    )
    assert "`GPD/tmp/`" in workflow
    assert "`/tmp`" in workflow


def test_help_prompts_surface_tangent_command_for_side_investigations() -> None:
    help_workflow = (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8")

    assert "gpd:tangent" in help_workflow
    assert re.search(
        r"gpd:tangent[^\n]*?(?:tangent|side investigation|alternative direction|parallel)", help_workflow, re.I
    )


def test_settings_and_research_mode_docs_keep_tangent_branch_taxonomy_strict() -> None:
    settings = (WORKFLOWS_DIR / "settings.md").read_text(encoding="utf-8")
    new_project = workflow_authority_text(WORKFLOWS_DIR, "new-project")
    research_modes = (REPO_ROOT / "src/gpd/specs/references/research/research-modes.md").read_text(encoding="utf-8")
    preset_labels = _workflow_preset_labels()

    assert "Which starting workflow preset should GPD use for `GPD/config.json`?" in new_project
    _assert_semantic_fragments(
        new_project,
        "new-project preset gate stays explicit",
        (
            "First offer a preset choice.",
            "bundles over existing config keys only",
            "Do not create, persist, or infer a separate preset block.",
        ),
    )
    assert "preview" in new_project
    assert "Before writing `GPD/config.json`" in new_project
    assert "Core research" in preset_labels
    assert '"Core research (Recommended)"' in new_project
    for label in sorted(preset_labels - {"Core research"}):
        assert f'"{label}"' in new_project
    assert "multiple hypothesis branches" not in settings
    assert "Minimal branching, fast convergence." not in settings
    _assert_semantic_absent(
        settings,
        "research mode docs avoid automatic exploit switching",
        ("auto-switch to exploit once approach is validated",),
    )
    _assert_semantic_fragments(
        settings,
        "settings tangent branch boundary",
        (
            "does **not** by itself authorize git-backed hypothesis branches",
            "surface tangent decisions explicitly",
            "Suppress optional tangents unless the user explicitly requests them",
            "explicit apply or customize choice",
        ),
    )
    assert "preview" in settings
    _assert_semantic_fragments(
        research_modes,
        "research modes keep tangent decisions explicit",
        (
            "do **not** silently create git-backed hypothesis branches",
            "only explicit tangent decisions become hypothesis branches or parallel plans",
            "Flag complementary approaches as tangent candidates for optional parallel investigation",
        ),
    )


def test_new_project_and_help_surface_runtime_default_and_state_backup_gitignore_guidance() -> None:
    new_project = workflow_authority_text(WORKFLOWS_DIR, "new-project")
    new_project_manifest = (WORKFLOWS_DIR / "new-project-stage-manifest.json").read_text(encoding="utf-8")
    help_workflow = (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8")
    planning_config = (REPO_ROOT / "src/gpd/specs/references/planning/planning-config.md").read_text(encoding="utf-8")

    _assert_semantic_fragments(
        new_project,
        "new-project runtime default model path",
        (
            "without commentary about the missing override",
            'normal "use the runtime default model" path',
        ),
    )
    assert "GPD/state.json.bak" in new_project_manifest
    assert "GPD/state.json.lock" in new_project_manifest
    assert "GPD/state.json.bak" in help_workflow
    assert "GPD/state.json.lock" in help_workflow
    assert "GPD/state.json.bak" in planning_config
    assert "GPD/state.json.lock" in planning_config
    assert "local recovery/coordination files" in help_workflow
    assert "local recovery/coordination files" in planning_config


def test_regression_check_prompt_examples_include_optional_phase_before_quick_flag() -> None:
    verifier_raw = (REPO_ROOT / "src/gpd/agents/gpd-verifier.md").read_text(encoding="utf-8")
    infra = (REPO_ROOT / "src/gpd/specs/references/orchestration/agent-infrastructure.md").read_text(encoding="utf-8")

    assert "agent-infrastructure.md" in verifier_raw
    assert "@{GPD_INSTALL_DIR}/references/orchestration/agent-infrastructure.md" not in verifier_raw
    assert "<!-- [included:" not in verifier_raw
    assert "gpd regression-check [phase] [--quick]" in infra
    assert "gpd regression-check [--quick]" not in infra


def test_verifier_prompt_does_not_claim_regression_check_spawns_verifier() -> None:
    verifier = (REPO_ROOT / "src/gpd/agents/gpd-verifier.md").read_text(encoding="utf-8")

    assert "The regression-check command" not in verifier


def test_help_prompt_workflow_modes_match_current_settings_vocabulary() -> None:
    help_workflow = (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8")

    assert "Interactive Mode" not in help_workflow
    assert "YOLO Mode" not in help_workflow
    assert "Change anytime by editing `GPD/config.json`" not in help_workflow
    assert "Supervised" in help_workflow
    assert "Max quality" in help_workflow
    assert "Balanced" in help_workflow
    assert "Budget-aware" in help_workflow
    assert "runtime defaults" in help_workflow
    assert "tier-1" in help_workflow
    assert "tier-2" in help_workflow
    assert "tier-3" in help_workflow
    assert "YOLO" in help_workflow
    assert "gpd:set-tier-models" in help_workflow
    assert "gpd:settings" in help_workflow
    assert "gpd:discuss-phase" in help_workflow
    assert "execution.review_cadence" in help_workflow
    assert "planning.commit_docs" in help_workflow
    assert "git.branching_strategy" in help_workflow
    assert "gpd observe execution" in help_workflow
    assert_cost_surface_discoverability(help_workflow)


def test_help_prompt_surfaces_workflow_presets_on_the_local_cli_surface() -> None:
    help_workflow = (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8")
    optional_addons = _extract_between(help_workflow, "### Optional Local CLI Add-Ons", "Workflow presets are bundles")
    preset_ids = {preset.id for preset in list_workflow_presets()}

    assert "### Optional Local CLI Add-Ons" in help_workflow
    assert "**Workflow presets**" in help_workflow
    assert "publication-manuscript" in preset_ids
    assert "Paper/manuscript workflows" in optional_addons
    assert DOCTOR_RUNTIME_SCOPE_RE.search(help_workflow) is not None
    assert_workflow_preset_surface_contract(help_workflow)
    _assert_normalized_fragments(
        optional_addons,
        (
            "paper-toolchain readiness",
            "degrade `write-paper`",
            "`paper-build` remains the build contract",
            "`arxiv-submission` requires the built manuscript",
            "pdflatex --version",
            "tectonic --version",
            "wolframscript -version",
        ),
    )
    assert "gpd:set-tier-models" in help_workflow
    assert "gpd:settings" in help_workflow
    assert "gpd:set-profile" in help_workflow


def test_help_prompt_surfaces_bounded_write_paper_external_authoring_lane() -> None:
    help_workflow = (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8")

    _assert_semantic_fragments(
        help_workflow,
        "write-paper external authoring lane boundary",
        (
            "bounded external-authoring lane driven by an explicit intake manifest only",
            "does not mine arbitrary folders",
            "embedded external staged-review parity is out of scope",
        ),
    )
    assert "GPD-authored outputs live under `GPD/publication/{subject_slug}/...`" in help_workflow
    assert "`GPD/publication/{subject_slug}/intake/`" in help_workflow
    assert "`gpd:write-paper --intake intake/write-paper-authoring-input.json`" in help_workflow


def test_help_prompt_selected_signatures_match_registry_argument_hints() -> None:
    help_workflow = (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8")

    for command_name in ("write-paper", "arxiv-submission", "record-backtrack", "execute-phase"):
        command = get_command(command_name)
        signature = f"`{command.name} {command.argument_hint}`"
        assert signature in help_workflow


def test_help_prompt_plan_phase_skip_verify_keeps_proof_bearing_exception() -> None:
    help_workflow = (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8")

    assert "`--skip-verify`" in help_workflow
    _assert_semantic_fragments(
        help_workflow,
        "plan-phase skip-verify proof-bearing exception",
        ("proof-bearing plans still require checker review or an equivalent main-context audit",),
    )


def test_help_prompt_keeps_cost_surface_on_local_cli_not_runtime_slash_command() -> None:
    help_workflow = (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8")

    assert "gpd cost" in help_workflow
    assert "/gpd:cost" not in help_workflow
    assert_cost_advisory_contract(help_workflow)


def test_prompt_and_public_surface_contract_agree_on_runtime_readiness_and_plan_validation_surfaces() -> None:
    help_workflow = (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8")
    bridge_note = local_cli_bridge_note()

    assert local_cli_unattended_readiness_command() in help_workflow
    assert local_cli_permissions_status_command() in help_workflow
    assert local_cli_plan_preflight_command() in help_workflow
    assert local_cli_doctor_local_command() in help_workflow
    assert local_cli_doctor_global_command() in help_workflow
    assert local_cli_validate_command_context_command() in help_workflow
    assert public_surface_contract_module.local_cli_bridge_purpose_phrase() in bridge_note


def test_help_workflow_mentions_all_authoritative_local_cli_bridge_commands() -> None:
    help_workflow = (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8")
    for (
        command
    ) in public_surface_contract_module.load_public_surface_contract().local_cli_bridge.named_commands.ordered():
        assert command in help_workflow

    assert local_cli_doctor_local_command() in help_workflow
    assert local_cli_doctor_global_command() in help_workflow
    assert local_cli_validate_command_context_command() in help_workflow


def test_help_prompt_session_management_keeps_pause_before_leave_and_resume_on_return() -> None:
    help_workflow = expand_at_includes(
        (WORKFLOWS_DIR / "help.md").read_text(encoding="utf-8"),
        REPO_ROOT / "src/gpd",
        "/runtime/",
    )

    assert_runtime_reset_rediscovery_contract(
        help_workflow,
        extra_reset_fragments=(f"then run {local_cli_resume_command()} in your normal terminal",),
        extra_reset_not_recovery_fragments=(f"then run {local_cli_resume_command()} in your normal terminal",),
    )
    assert "**`gpd:resume-work`**" in help_workflow
    assert "**`gpd:pause-work`**" in help_workflow
    assert_resume_authority_contract(
        help_workflow,
        allow_explicit_alias_examples=False,
        require_canonical_note=True,
    )
    assert resume_authority_public_vocabulary_intro() in help_workflow
    assert "state.json.continuation.handoff.resume_file" not in help_workflow
    assert "`resume_surface`" not in help_workflow
    assert resume_authority_fields() == (
        "active_resume_kind",
        "active_resume_origin",
        "active_resume_pointer",
        "active_bounded_segment",
        "derived_execution_head",
        "active_resume_result",
        "continuity_handoff_file",
        "recorded_continuity_handoff_file",
        "missing_continuity_handoff_file",
        "resume_candidates",
    )
    assert not any(alias in resume_authority_fields() for alias in resume_backend_only_fields())
    assert_recovery_ladder_contract(
        help_workflow,
        resume_work_fragments=("gpd:resume-work", "/gpd:resume-work"),
        suggest_next_fragments=("gpd:suggest-next", "/gpd:suggest-next"),
        pause_work_fragments=("gpd:pause-work", "/gpd:pause-work"),
    )


def test_new_project_prompt_surfaces_discuss_phase_before_planning_in_command_and_workflow() -> None:
    command = (REPO_ROOT / "src/gpd/commands/new-project.md").read_text(encoding="utf-8")
    workflow = (REPO_ROOT / "src/gpd/specs/workflows/new-project/completion.md").read_text(encoding="utf-8")

    for content in (command, workflow):
        assert "gpd:discuss-phase 1" in content

    assert "Discuss phase 1 now?" in command
    assert "`gpd:discuss-phase 1`" in workflow
    assert "Plan phase 1 now?" not in command
    assert "Plan phase 1 now?" not in workflow


def test_execute_phase_failure_recovery_counts_only_top_level_verification_statuses() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "execute-phase")

    _assert_semantic_fragments(
        workflow,
        "execute-phase failure recovery counts authoritative statuses",
        (
            "Count only top-level report status and structured gap ledgers",
            "do not use unanchored text search over nested `status:` fields",
        ),
    )
    assert 'grep -c "status: failed"' not in workflow
    assert 'grep -c "status:"' not in workflow


def test_execute_phase_closeout_always_surfaces_concrete_next_commands() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "execute-phase")
    offer_next = _extract_between(workflow, '<step name="offer_next">', "</step>")

    assert "## > Next Up" in offer_next
    _assert_normalized_fragments(
        offer_next,
        (
            "refresh the lifecycle route",
            "lifecycle_next_up.rendered_markdown",
            "next_up.rendered_markdown",
            "lifecycle_next_up.stage_stop_*",
            "next_up.stage_stop_*",
            "shared renderer shape",
            "The prompt must not decide",
            "surface the helper JSON instead of hand-rendering a route",
        ),
    )
    _assert_normalized_absent(
        offer_next,
        (
            "one matching variant",
            "gpd:discuss-phase {PHASE_NUMBER_PLUS_ONE}",
            "gpd:plan-phase {PHASE_NUMBER_PLUS_ONE}",
            "Primary: `gpd:discuss-phase {PHASE_NUMBER_PLUS_ONE}`",
            "Primary: `gpd:plan-phase {PHASE_NUMBER_PLUS_ONE}`",
            "Primary: `gpd:audit-milestone`",
            "Primary: `gpd:discuss-phase {X+1}` if context is missing",
            "If context is missing:",
            "If context exists:",
        ),
    )


def test_execute_phase_closeout_prompt_orders_readiness_before_safe_mutation() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "execute-phase")

    _assert_ordered_fragments(
        workflow,
        (
            "gpd --raw phase closeout-readiness",
            'gpd phase complete "${phase_number}"',
        ),
    )
    _assert_normalized_fragments(
        workflow,
        (
            "Before any roadmap/state transition, run the read-only helper",
            "rechecks lifecycle readiness before mutating",
            "Primary local transition",
        ),
    )


def test_command_requirements_force_concrete_next_up_for_stops() -> None:
    note = command_visibility_note()

    _assert_semantic_fragments(
        note,
        "command visibility stop closeout",
        (
            "completion, checkpoint, blocked return, failed return, retry gate, or stop",
            "must end with `## > Next Up`",
            "concrete GPD commands",
        ),
    )
    assert "`gpd:suggest-next`" in note


def test_continuation_format_covers_stop_and_checkpoint_routes() -> None:
    continuation = (REPO_ROOT / "src/gpd/specs/references/orchestration/continuation-format.md").read_text(
        encoding="utf-8"
    )

    assert "## Stop And Checkpoint Rules" in continuation
    _assert_normalized_fragments(
        continuation,
        (
            "stage-stop envelope",
            "lifecycle route",
            "typed suggestion payload",
            "rendered next-up markdown",
            "stage_stop.next_runtime_command",
            "must not choose lifecycle routes itself",
        ),
    )
    for command in (
        "`gpd:resume-work`",
        "`gpd:new-project --minimal @file.md`",
        "`gpd:suggest-next`",
    ):
        assert command in continuation


def test_new_project_and_new_milestone_closeouts_include_concrete_next_up_commands() -> None:
    new_project = workflow_authority_text(WORKFLOWS_DIR, "new-project")
    new_milestone = workflow_authority_text(WORKFLOWS_DIR, "new-milestone")
    new_milestone_command = (COMMANDS_DIR / "new-milestone.md").read_text(encoding="utf-8")

    _assert_semantic_fragments(
        new_project,
        "new-project blocked closeout includes next up",
        ("not available, stop with `## > Next Up`",),
    )
    assert "`gpd:discuss-phase 1`" in new_project
    assert "`gpd:plan-phase 1`" in new_project
    assert "`gpd:suggest-next`" in new_project
    assert "user sees `gpd:discuss-phase 1` as the primary next step" in new_project

    assert "`gpd:discuss-phase [N]`" in new_milestone
    assert "`gpd:plan-phase [N]`" in new_milestone
    assert "`gpd:suggest-next`" in new_milestone
    assert "primary `gpd:new-milestone [milestone name]`" in new_milestone
    assert "**After:** `gpd:discuss-phase [N]`" in new_milestone_command
