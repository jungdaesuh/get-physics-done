"""Test-only structural helpers for runtime projection assertions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from gpd.adapters.command_projection import classify_projection_shell_fence
from gpd.adapters.install_utils import (
    COMPACT_HELP_BRIDGE_SHIM_SENTINEL,
    COMPACT_STAGED_COMMAND_SHIM_SENTINEL,
    COMPACT_WORKFLOW_COMMAND_SHIM_SENTINEL,
    DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES,
    build_runtime_cli_bridge_command,
)
from gpd.adapters.runtime_catalog import get_runtime_descriptor
from gpd.adapters.shell_fence_projection import shell_fence_runnable_lines
from gpd.core import prompt_diagnostics
from gpd.core.workflow_staging import (
    load_workflow_stage_manifest_from_path,
    staged_protocol_bundle_required_init_fields,
)
from tests.prompt_metrics_support import MarkdownFence, iter_markdown_fences

__all__ = [
    "CompactTagBlock",
    "HELP_BRIDGE_SHIM_SENTINELS",
    "NORMALIZED_RUNTIME_BRIDGE_MARKER",
    "PROTOCOL_BUNDLE_INLINE_CATALOG_MARKERS",
    "ProjectedSection",
    "ProjectedText",
    "RUNTIME_BRIDGE_COMMAND_RE",
    "RUNTIME_BRIDGE_RUNTIME_RE",
    "RUNTIME_NOTE_TAGS",
    "STAGED_SHIM_CONTRACT_FRAGMENTS",
    "STAGED_SHIM_SENTINELS",
    "StagedCommandProjectionCase",
    "UNRESOLVED_INCLUDE_MARKERS",
    "WORKFLOW_REFERENCE_SHIM_SENTINELS",
    "assert_compact_help_bridge_shim",
    "assert_compact_staged_command_shim",
    "assert_compact_workflow_reference_shim",
    "assert_no_unresolved_include_markers",
    "assert_protocol_bundle_jit_shape",
    "assert_runtime_bridge_targets_active_runtime",
    "assert_runtime_note_tag_count",
    "assert_runtime_note_tags_not_repeated",
    "compact_tag_block",
    "compact_tag_blocks",
    "first_runnable_shell_command",
    "first_runnable_shell_commands",
    "has_compact_non_native_shim",
    "has_help_bridge_shim_sentinel",
    "has_staged_shim_sentinel",
    "has_workflow_reference_shim_sentinel",
    "iter_staged_command_projection_cases",
    "normalize_projected_text",
    "normalized_runtime_bridge_text",
    "normalized_runtime_projection_char_count",
    "raw_include_count",
    "runnable_shell_lines",
    "runtime_bridge_command",
    "runtime_bridge_runtimes",
    "shell_fence_bodies",
    "shell_fences",
    "staged_command_has_protocol_bundle_fields",
    "staged_command_protocol_bundle_fields",
    "single_runtime_note_block",
    "tag_count",
]

_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)(?:[ \t]+#+[ \t]*)?$")
_ATTR_RE = re.compile(r"""(?P<name>[A-Za-z_][A-Za-z0-9_:-]*)\s*=\s*(?:"(?P<double>[^"]*)"|'(?P<single>[^']*)')""")
_FIELD_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<name>[A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(?P<value>.*)$")
_LIST_ITEM_RE = re.compile(r"^[ \t]*-[ \t]+`?(?P<value>[A-Za-z_][A-Za-z0-9_]*)`?")
_TOKEN_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`|['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]|([A-Za-z_][A-Za-z0-9_]*)")
RUNTIME_BRIDGE_COMMAND_RE = re.compile(
    r"(?:[^ \n`]+)\s+-m gpd\.runtime_cli\s+--runtime\s+[a-z-]+"
    r"\s+--config-dir\s+[^ \n`]+(?:\s+--install-scope\s+local)?"
)
RUNTIME_BRIDGE_RUNTIME_RE = re.compile(r"(?:[^ \n`]+)\s+-m gpd\.runtime_cli\s+--runtime\s+(?P<runtime>[a-z0-9-]+)\b")
NORMALIZED_RUNTIME_BRIDGE_MARKER = "<runtime-bridge>"
STAGED_SHIM_SENTINELS = (COMPACT_STAGED_COMMAND_SHIM_SENTINEL, "## Compact Staged Command Shim")
HELP_BRIDGE_SHIM_SENTINELS = (COMPACT_HELP_BRIDGE_SHIM_SENTINEL, "CLI-owned compact help surface")
WORKFLOW_REFERENCE_SHIM_SENTINELS = (COMPACT_WORKFLOW_COMMAND_SHIM_SENTINEL,)
UNRESOLVED_INCLUDE_MARKERS = (
    "@ include not resolved:",
    "@ include cycle detected:",
    "@ include read error:",
    "@ include depth limit reached:",
)
RUNTIME_NOTE_TAGS = (
    "codex_runtime_notes",
    "codex_questioning",
    "gemini_runtime_notes",
    "gemini_shell_runtime_notes",
)
STAGED_SHIM_CONTRACT_FRAGMENTS = (
    "workflow_id",
    "first_stage_id",
    "stage_count",
    "payload_contract_version",
    "required_staged_loading_keys",
    "raw_stage_loader_command",
)
PROTOCOL_BUNDLE_INLINE_CATALOG_MARKERS = (
    "Statistical Mechanics Simulation",
    "Numerical Relativity",
    "{GPD_INSTALL_DIR}/references/protocols/monte-carlo.md",
    "{GPD_INSTALL_DIR}/references/protocols/numerical-relativity.md",
    "Estimator policies:",
    "Decisive artifacts:",
)


@dataclass(frozen=True, slots=True)
class CompactTagBlock:
    """One parsed compact runtime shim block."""

    tag_name: str
    attrs: dict[str, str]
    body: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class ProjectedSection:
    """One markdown section from a projected runtime prompt."""

    heading: str
    level: int
    body: str
    start_line: int
    end_line: int

    @property
    def text(self) -> str:
        heading_line = f"{'#' * self.level} {self.heading}"
        return f"{heading_line}\n{self.body}" if self.body else heading_line


@dataclass(frozen=True, slots=True)
class StagedCommandProjectionCase:
    """One checked-in staged command/workflow manifest pair."""

    command_name: str
    first_stage_id: str
    stage_count: int
    native_include_paths: tuple[str, ...]
    staged_loading_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Heading:
    heading: str
    level: int
    line_number: int


@dataclass(frozen=True, slots=True)
class ProjectedText:
    """Normalized view of a projected runtime prompt."""

    text: str

    def sections(self, heading: str | None = None, *, level: int | None = None) -> tuple[ProjectedSection, ...]:
        sections = _sections(self.text)
        if heading is not None:
            sections = tuple(section for section in sections if section.heading == heading)
        if level is not None:
            sections = tuple(section for section in sections if section.level == level)
        return sections

    def section(self, heading: str, *, level: int | None = None) -> ProjectedSection:
        sections = self.sections(heading, level=level)
        assert len(sections) == 1, f"Expected exactly one projected section {heading!r}; found {len(sections)}"
        return sections[0]

    def shell_fences(self) -> tuple[MarkdownFence, ...]:
        return shell_fences(self.text)

    def first_runnable_shell_commands(self) -> tuple[str, ...]:
        return tuple(command for fence in self.shell_fences() if (command := first_runnable_shell_command(fence)))


def normalize_projected_text(text: str) -> ProjectedText:
    return ProjectedText(text=text)


def iter_staged_command_projection_cases(
    *,
    commands_dir: Path,
    workflows_dir: Path,
) -> tuple[StagedCommandProjectionCase, ...]:
    """Return projection cases discovered from checked-in stage manifests."""

    cases: list[StagedCommandProjectionCase] = []
    for manifest_path in sorted(workflows_dir.glob("*-stage-manifest.json")):
        command_name = manifest_path.name.removesuffix("-stage-manifest.json")
        command_path = commands_dir / f"{command_name}.md"
        assert command_path.is_file(), f"{manifest_path.name} has no command surface at {command_path}"

        manifest = load_workflow_stage_manifest_from_path(
            manifest_path,
            expected_workflow_id=command_name,
        )
        if manifest.prompt_usage != "staged_init":
            continue
        assert manifest.stages, f"{manifest_path.name} has no stages"
        first_stage = manifest.stages[0]
        cases.append(
            StagedCommandProjectionCase(
                command_name=command_name,
                first_stage_id=first_stage.id,
                stage_count=len(manifest.stages),
                native_include_paths=tuple(first_stage.mode_paths),
                staged_loading_keys=tuple(manifest.staged_loading_payload(first_stage.id)),
            )
        )

    return tuple(cases)


def first_runnable_shell_command(fence_or_body: MarkdownFence | str) -> str | None:
    body = fence_or_body.body if isinstance(fence_or_body, MarkdownFence) else fence_or_body
    return classify_projection_shell_fence(body).first_command


def runtime_bridge_command(
    runtime: str,
    target_dir: Path,
    *,
    is_global: bool = False,
    explicit_target: bool = False,
) -> str:
    descriptor = get_runtime_descriptor(runtime)
    return build_runtime_cli_bridge_command(
        runtime,
        target_dir=target_dir,
        config_dir_name=descriptor.config_dir_name,
        is_global=is_global,
        explicit_target=explicit_target,
    )


def normalized_runtime_bridge_text(text: str) -> str:
    return RUNTIME_BRIDGE_COMMAND_RE.sub(NORMALIZED_RUNTIME_BRIDGE_MARKER, text)


def runtime_bridge_runtimes(text: str) -> tuple[str, ...]:
    return tuple(match.group("runtime") for match in RUNTIME_BRIDGE_RUNTIME_RE.finditer(text))


def assert_runtime_bridge_targets_active_runtime(
    text: str,
    *,
    runtime: str,
    label: str,
    require_bridge: bool = False,
) -> None:
    bridge_runtimes = runtime_bridge_runtimes(text)
    foreign_runtimes = sorted({bridge_runtime for bridge_runtime in bridge_runtimes if bridge_runtime != runtime})

    assert not foreign_runtimes, (
        f"{label} embeds runtime bridge command(s) for the wrong runtime: "
        f"foreign={foreign_runtimes!r}, observed={bridge_runtimes!r}"
    )
    if require_bridge:
        assert runtime in bridge_runtimes, f"{label} should embed an active {runtime!r} runtime bridge command"


def normalized_runtime_projection_char_count(metric: prompt_diagnostics.RuntimeProjectionMetric) -> int:
    bridge_occurrences = metric.bridge_command_occurrences
    if bridge_occurrences == 0:
        return metric.char_count
    bridge_command = prompt_diagnostics._projection_bridge_command(metric.runtime)
    return metric.char_count - (len(bridge_command) - len(NORMALIZED_RUNTIME_BRIDGE_MARKER)) * bridge_occurrences


def raw_include_count(text: str, include_suffix: str) -> int:
    return sum(
        1 for line in text.splitlines() if line.strip().startswith("@") and line.strip().endswith(include_suffix)
    )


def compact_tag_blocks(text: str, tag_name: str) -> tuple[CompactTagBlock, ...]:
    """Return compact shim blocks for a simple XML-like tag."""

    blocks: list[CompactTagBlock] = []
    open_re = re.compile(rf"<{re.escape(tag_name)}\b(?P<attrs>[^>]*)>", flags=re.DOTALL)
    close_tag = f"</{tag_name}>"
    search_start = 0

    while match := open_re.search(text, search_start):
        body_start = match.end()
        close_start = text.find(close_tag, body_start)
        assert close_start != -1, f"Missing closing tag {close_tag}"
        close_end = close_start + len(close_tag)
        blocks.append(
            CompactTagBlock(
                tag_name=tag_name,
                attrs=_parse_tag_attrs(match.group("attrs")),
                body=text[body_start:close_start],
                start=match.start(),
                end=close_end,
            )
        )
        search_start = close_end

    return tuple(blocks)


def compact_tag_block(text: str, tag_name: str) -> CompactTagBlock:
    blocks = compact_tag_blocks(text, tag_name)
    assert len(blocks) == 1, f"Expected exactly one <{tag_name}> block; found {len(blocks)}"
    return blocks[0]


def shell_fences(text: str) -> tuple[MarkdownFence, ...]:
    fences: list[MarkdownFence] = []
    for fence in iter_markdown_fences(text):
        info = fence.info.strip()
        language = info.split(None, 1)[0].lower() if info else ""
        if language in DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES:
            fences.append(fence)
    return tuple(fences)


def shell_fence_bodies(text: str) -> tuple[str, ...]:
    return tuple(fence.body for fence in shell_fences(text))


def runnable_shell_lines(fence: MarkdownFence) -> tuple[str, ...]:
    return shell_fence_runnable_lines(fence.body)


def first_runnable_shell_commands(text: str) -> tuple[str, ...]:
    return tuple(command for fence in shell_fences(text) if (command := first_runnable_shell_command(fence)))


def has_staged_shim_sentinel(text: str) -> bool:
    return any(sentinel in text for sentinel in STAGED_SHIM_SENTINELS)


def has_help_bridge_shim_sentinel(text: str) -> bool:
    return any(sentinel in text for sentinel in HELP_BRIDGE_SHIM_SENTINELS)


def has_workflow_reference_shim_sentinel(text: str) -> bool:
    return any(sentinel in text for sentinel in WORKFLOW_REFERENCE_SHIM_SENTINELS)


def has_compact_non_native_shim(text: str) -> bool:
    return (
        has_staged_shim_sentinel(text)
        or has_help_bridge_shim_sentinel(text)
        or has_workflow_reference_shim_sentinel(text)
    )


def assert_no_unresolved_include_markers(text: str, *, label: str) -> None:
    lowered = text.lower()
    offenders = [marker for marker in UNRESOLVED_INCLUDE_MARKERS if marker in lowered]
    assert offenders == [], f"{label} contains unresolved include marker(s): {', '.join(offenders)}"


def tag_count(text: str, tag: str) -> tuple[int, int]:
    return text.count(f"<{tag}>"), text.count(f"</{tag}>")


def assert_runtime_note_tags_not_repeated(text: str, *, label: str, tags: tuple[str, ...] = RUNTIME_NOTE_TAGS) -> None:
    for tag in tags:
        opens, closes = tag_count(text, tag)
        assert opens == closes, f"{label} has unbalanced {tag}: {opens}/{closes}"
        assert opens <= 1, f"{label} repeats {tag}: {opens}"


def assert_runtime_note_tag_count(text: str, tag: str, expected_count: int, *, label: str | None = None) -> None:
    opens, closes = tag_count(text, tag)
    detail = f" for {label}" if label else ""
    assert opens == expected_count, f"Expected {expected_count} <{tag}> block(s){detail}; found {opens}"
    assert closes == expected_count, f"Expected {expected_count} </{tag}> block(s){detail}; found {closes}"


def single_runtime_note_block(text: str, tag: str, *, label: str | None = None) -> str:
    assert_runtime_note_tag_count(text, tag, 1, label=label)
    match = re.search(rf"<{re.escape(tag)}>\n(?P<body>.*?)</{re.escape(tag)}>", text, flags=re.DOTALL)
    assert match is not None, f"{label or tag} should have one <{tag}> block"
    return match.group("body").strip()


def assert_compact_staged_command_shim(
    text: str,
    *,
    command_name: str,
    first_stage: str,
    staged_loading_keys: tuple[str, ...] = (),
    command_label: str | None = None,
    stage_count: int | None = None,
    payload_contract_version: str = "1",
    require_runtime_bridge: bool | None = None,
) -> None:
    assert COMPACT_STAGED_COMMAND_SHIM_SENTINEL in text
    block = compact_tag_block(text, "gpd_staged_bootstrap_shim")
    expected_command_label = command_label or f"gpd:{command_name}"
    enforce_runtime_bridge = command_label is not None if require_runtime_bridge is None else require_runtime_bridge

    _assert_attr_value(block, "command", expected_command_label)
    _assert_attr_value(block, ("workflow", "workflow_id"), command_name)
    _assert_attr_value(block, ("first_stage", "first_stage_id"), first_stage)
    _assert_numeric_attr(block, "stage_count", expected=stage_count)
    _assert_attr_value(block, "payload_contract_version", payload_contract_version)
    _assert_full_workflow_include_absent(text, command_name)
    _assert_raw_init_loader_command(
        block,
        command_name=command_name,
        first_stage=first_stage,
        require_runtime_bridge=enforce_runtime_bridge,
    )

    if staged_loading_keys:
        expected_keys = frozenset(staged_loading_keys)
        required_keys, optional_keys = _structured_staged_loading_contract_key_sets(block)
        actual_keys = required_keys | (optional_keys & expected_keys)
        assert actual_keys == expected_keys, (
            f"{command_name} staged-loading contract keys differ: "
            f"missing={sorted(expected_keys - actual_keys)!r}, extra={sorted(actual_keys - expected_keys)!r}"
        )


def assert_compact_workflow_reference_shim(
    text: str,
    *,
    workflow_id: str,
    command_label: str,
    authority_suffixes: tuple[str, ...] = (),
) -> None:
    assert COMPACT_WORKFLOW_COMMAND_SHIM_SENTINEL in text
    block = compact_tag_block(text, "gpd_workflow_reference_shim")
    _assert_attr_value(block, "command", command_label)
    _assert_attr_value(block, ("workflow", "workflow_id"), workflow_id)
    _assert_full_workflow_include_absent(text, workflow_id)

    suffixes = authority_suffixes or (f"workflows/{workflow_id}.md",)
    for suffix in suffixes:
        assert suffix in block.body, f"Missing compact workflow authority suffix {suffix!r}"


def assert_compact_help_bridge_shim(
    text: str,
    *,
    command_label: str,
) -> None:
    assert COMPACT_HELP_BRIDGE_SHIM_SENTINEL in text
    block = compact_tag_block(text, "gpd_help_bridge_shim")
    _assert_attr_value(block, "command", command_label)
    _assert_full_workflow_include_absent(text, "help")
    for suffix in ("--raw help", "--raw help --all", "--raw help --command <name>"):
        _assert_bridge_command_with_suffix(block, suffix=suffix)


def assert_protocol_bundle_jit_shape(
    text: str,
    *,
    case: StagedCommandProjectionCase,
    runtime: str,
    expected_bundle_fields: tuple[str, ...],
) -> None:
    descriptor = get_runtime_descriptor(runtime)
    if not expected_bundle_fields:
        assert "<protocol_bundle_jit>" not in text
        return

    for marker in PROTOCOL_BUNDLE_INLINE_CATALOG_MARKERS:
        assert marker not in text

    if descriptor.native_include_support:
        for include_path in case.native_include_paths:
            assert raw_include_count(text, include_path) == 1
        assert "<protocol_bundle_jit>" not in text
        return

    assert has_staged_shim_sentinel(text)
    block = compact_tag_block(text, "protocol_bundle_jit")
    for field in expected_bundle_fields:
        assert field in block.body or any(field in value for value in block.attrs.values())


def _parse_tag_attrs(raw_attrs: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in _ATTR_RE.finditer(raw_attrs):
        value = match.group("double") if match.group("double") is not None else match.group("single")
        attrs[match.group("name")] = value or ""
    return attrs


def _assert_attr_value(block: CompactTagBlock, attr_name: str | tuple[str, ...], expected: str) -> None:
    names = (attr_name,) if isinstance(attr_name, str) else attr_name
    matched = next((name for name in names if name in block.attrs), None)
    assert matched is not None, f"<{block.tag_name}> missing attribute {names[0]!r}"
    actual = block.attrs[matched]
    assert actual == expected, f"<{block.tag_name}> attribute {matched!r}: expected {expected!r}, found {actual!r}"


def _assert_numeric_attr(block: CompactTagBlock, attr_name: str, *, expected: int | None = None) -> None:
    assert attr_name in block.attrs, f"<{block.tag_name}> missing attribute {attr_name!r}"
    actual = block.attrs[attr_name]
    assert actual.isdigit(), f"<{block.tag_name}> attribute {attr_name!r} should be numeric; found {actual!r}"
    if expected is not None:
        assert int(actual) == expected, (
            f"<{block.tag_name}> attribute {attr_name!r}: expected {expected}, found {actual}"
        )


def _assert_full_workflow_include_absent(text: str, workflow_id: str) -> None:
    offenders = (
        f"<!-- [included: {workflow_id}.md] -->",
        f"<!-- [included: workflows/{workflow_id}.md] -->",
        f"@{{GPD_INSTALL_DIR}}/workflows/{workflow_id}.md",
    )
    found = [offender for offender in offenders if offender in text]
    assert found == [], f"{workflow_id} compact shim contains full workflow include marker(s): {found!r}"


def _assert_raw_init_loader_command(
    block: CompactTagBlock,
    *,
    command_name: str,
    first_stage: str,
    require_runtime_bridge: bool,
) -> None:
    fragment = f"--raw init {command_name}"
    stage_fragment = f"--stage {first_stage}"
    candidates = _candidate_commands_containing(block, fragment)
    stage_candidates = [command for command in candidates if stage_fragment in command]
    assert stage_candidates, (
        f"<{block.tag_name}> should contain a raw init loader for {command_name!r} at stage {first_stage!r}"
    )
    if require_runtime_bridge:
        bridge_candidates = [command for command in stage_candidates if RUNTIME_BRIDGE_COMMAND_RE.search(command)]
        assert bridge_candidates, (
            f"<{block.tag_name}> should contain a runtime bridge raw init loader for "
            f"{command_name!r} at stage {first_stage!r}"
        )
        assert not any(command.strip().startswith(f"gpd {fragment}") for command in stage_candidates)


def _assert_bridge_command_with_suffix(block: CompactTagBlock, *, suffix: str) -> None:
    candidates = _candidate_commands_containing(block, suffix)
    bridge_candidates = [
        command
        for command in candidates
        if RUNTIME_BRIDGE_COMMAND_RE.search(command) and command.strip().endswith(suffix)
    ]
    assert bridge_candidates, f"<{block.tag_name}> should contain a runtime bridge command ending in {suffix!r}"


def _candidate_commands_containing(block: CompactTagBlock, fragment: str) -> tuple[str, ...]:
    commands = list(first_runnable_shell_commands(block.body))
    for line in block.body.splitlines():
        if fragment in line:
            commands.append(_clean_embedded_command_line(line))
    return tuple(dict.fromkeys(command for command in commands if fragment in command))


def _clean_embedded_command_line(line: str) -> str:
    line = line.strip()
    if ":" in line:
        _, value = line.split(":", 1)
        line = value.strip()
    return line.strip("`'\" ")


def _structured_staged_loading_contract_key_sets(block: CompactTagBlock) -> tuple[frozenset[str], frozenset[str]]:
    required = _structured_values(
        block,
        field_names=(
            "required_staged_loading_keys",
            "staged_loading_keys",
            "staged_loading_contract_keys",
            "required_keys",
        ),
    )
    optional = _structured_values(
        block,
        field_names=(
            "optional_staged_loading_keys",
            "optional_keys",
        ),
    )
    assert required or optional, f"<{block.tag_name}> missing structured staged-loading key contract"
    return required, optional


def _structured_values(block: CompactTagBlock, *, field_names: tuple[str, ...]) -> frozenset[str]:
    values: set[str] = set()
    for name in field_names:
        if name in block.attrs:
            values.update(_tokens_from_value(block.attrs[name]))
    lines = block.body.splitlines()
    for index, line in enumerate(lines):
        match = _FIELD_RE.match(line)
        if match is None or match.group("name") not in field_names:
            continue
        values.update(_tokens_from_value(match.group("value")))
        values.update(_list_items_after_field(lines, start_index=index, field_indent=len(match.group("indent"))))
    return frozenset(values)


def _tokens_from_value(value: str) -> tuple[str, ...]:
    return tuple(
        token
        for match in _TOKEN_RE.finditer(value)
        for token in (match.group(1) or match.group(2) or match.group(3),)
        if token
    )


def _list_items_after_field(lines: list[str], *, start_index: int, field_indent: int) -> tuple[str, ...]:
    values: list[str] = []
    for line in lines[start_index + 1 :]:
        if not line.strip():
            if values:
                break
            continue
        field_match = _FIELD_RE.match(line)
        if field_match is not None and len(field_match.group("indent")) <= field_indent:
            break
        item_match = _LIST_ITEM_RE.match(line)
        if item_match is not None:
            values.append(item_match.group("value"))
            continue
        if values:
            break
    return tuple(values)


def staged_command_has_protocol_bundle_fields(
    workflows_dir: Path,
    command_name: str,
) -> bool:
    return bool(staged_command_protocol_bundle_fields(workflows_dir, command_name))


def staged_command_protocol_bundle_fields(workflows_dir: Path, command_name: str) -> tuple[str, ...]:
    manifest = load_workflow_stage_manifest_from_path(
        workflows_dir / f"{command_name}-stage-manifest.json",
        expected_workflow_id=command_name,
    )
    return staged_protocol_bundle_required_init_fields(manifest)


def _sections(text: str) -> tuple[ProjectedSection, ...]:
    lines = text.splitlines()
    headings = _headings_outside_fences(lines)
    sections: list[ProjectedSection] = []

    for index, heading in enumerate(headings):
        end_line = len(lines)
        for later_heading in headings[index + 1 :]:
            if later_heading.level <= heading.level:
                end_line = later_heading.line_number - 1
                break

        body_lines = lines[heading.line_number : end_line]
        sections.append(
            ProjectedSection(
                heading=heading.heading,
                level=heading.level,
                body="\n".join(body_lines),
                start_line=heading.line_number,
                end_line=end_line,
            )
        )

    return tuple(sections)


def _headings_outside_fences(lines: list[str]) -> tuple[_Heading, ...]:
    headings: list[_Heading] = []
    active_fence_marker: str | None = None

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        fence_marker = _fence_marker(stripped)
        if fence_marker is not None:
            if active_fence_marker is None:
                active_fence_marker = fence_marker
            elif fence_marker == active_fence_marker:
                active_fence_marker = None
            continue

        if active_fence_marker is not None:
            continue

        match = _HEADING_RE.match(stripped)
        if match is not None:
            marker, heading = match.groups()
            headings.append(_Heading(heading=heading.strip(), level=len(marker), line_number=line_number))

    return tuple(headings)


def _fence_marker(stripped_line: str) -> str | None:
    if stripped_line.startswith("```"):
        return "```"
    if stripped_line.startswith("~~~"):
        return "~~~"
    return None
