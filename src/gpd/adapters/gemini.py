"""Gemini CLI runtime adapter.

Gemini CLI uses:
- ``.md`` agent files with YAML frontmatter (tools as YAML array, no ``color:``)
- ``.toml`` command files (TOML with ``prompt`` and ``description`` fields)
- ``settings.json`` for hooks, statusline, and ``experimental.enableAgents``
- ``@`` include directives must be expanded at install time (no native support)
- ``<sub>`` HTML tags must be stripped (terminal rendering)
"""

from __future__ import annotations

import json
import logging
import re
import shlex
import shutil
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from gpd.adapters.base import RuntimeAdapter
from gpd.adapters.command_projection import (
    classify_projection_shell_fence,
    prepend_projection_note,
    rewrite_projection_shell_bridge,
    strip_projection_note_blocks,
)
from gpd.adapters.gemini_shell_patches import (
    GEMINI_APPROVED_CONTRACT_PATH,
    rewrite_gemini_shell_workflow_guidance,
)
from gpd.adapters.install_utils import (
    DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES,
    HOOK_SCRIPTS,
    MANIFEST_NAME,
    _is_hook_command_for_script,
    _markdown_fence_language,
    _markdown_fence_marker,
    build_hook_command,
    build_runtime_managed_mcp_servers,
    cleanup_settings_json_managed_entries,
    compile_command_markdown_for_runtime,
    compile_markdown_for_runtime,
    convert_tool_references_in_body,
    ensure_update_hook,
    parse_jsonc,
    process_attribution,
    protect_runtime_agent_prompt,
    prune_empty_ancestors,
    read_settings,
    remove_stale_agents,
    render_markdown_frontmatter,
    runtime_managed_mcp_server_keys,
    split_markdown_frontmatter,
    strip_sub_tags,
    verify_installed,
    write_manifest,
    write_settings_if_modified_and_prune_empty,
)
from gpd.adapters.install_utils import (
    finish_install as _finish_install,
)
from gpd.adapters.runtime_catalog import get_manifest_metadata_list_policy_key, get_runtime_descriptor
from gpd.adapters.tool_names import build_runtime_alias_map, reference_translation_map, translate_for_runtime
from gpd.command_labels import rewrite_runtime_command_surfaces_to_public, validated_public_command_prefix

logger = logging.getLogger(__name__)

_GEMINI_AGENT_FRONTMATTER_FIELDS: frozenset[str] = frozenset(
    {
        "kind",
        "name",
        "description",
        "display_name",
        "tools",
        "model",
        "temperature",
        "max_turns",
        "timeout_mins",
        "agent_card_url",
        "auth",
    }
)
# Gemini's agent loader uses a strict schema, so installs must drop any
# adapter-owned metadata keys that fall outside this allowlist.

_TOOL_NAME_MAP: dict[str, str] = {
    "file_read": "read_file",
    "file_write": "write_file",
    "file_edit": "replace",
    "shell": "run_shell_command",
    "search_files": "search_file_content",
    "find_files": "glob",
    "web_search": "google_web_search",
    "web_fetch": "web_fetch",
    "notebook_edit": "notebook_edit",
    "agent": "agent",
    "ask_user": "ask_user",
    "todo_write": "write_todos",
    "task": "task",
    "slash_command": "slash_command",
    "tool_search": "tool_search",
}
_TOOL_ALIAS_MAP = build_runtime_alias_map(_TOOL_NAME_MAP)
_AUTO_DISCOVERED_TOOLS = frozenset({"task"})
_DROP_MCP_FRONTMATTER_TOOLS = True
_TOOL_REFERENCE_MAP = reference_translation_map(
    _TOOL_NAME_MAP,
    alias_map=_TOOL_ALIAS_MAP,
    auto_discovered_tools=_AUTO_DISCOVERED_TOOLS,
    drop_mcp_frontmatter_tools=_DROP_MCP_FRONTMATTER_TOOLS,
)

_GEMINI_POLICY_DIR_NAME = "policies"
_GEMINI_POLICY_FILE_NAME = "gpd-auto-edit.toml"
_GEMINI_RUNTIME_BIN_DIR_NAME = "bin"
_GEMINI_YOLO_WRAPPER_NAME = "gemini-gpd-yolo"
_GEMINI_APPROVED_CONTRACT_PATH = GEMINI_APPROVED_CONTRACT_PATH
_GEMINI_STATIC_POLICY_COMMAND_PREFIXES: tuple[str, ...] = (
    "git init",
    "mkdir -p GPD",
    "cat GPD/",
    "ls -d GPD",
    "test -d GPD",
    "test -f GPD/",
)
GeminiShellFenceKind = Literal["runnable-bridge", "terminal-example", "pseudocode", "policy-static", "non-runnable"]


@dataclass(frozen=True, slots=True)
class GeminiShellFenceClassification:
    """Gemini rendering decision for one source shell fence."""

    kind: GeminiShellFenceKind
    first_runnable_command: str | None
    reasons: tuple[str, ...]


_GEMINI_COMMAND_RUNTIME_NOTE = (
    "<gemini_runtime_notes>\n"
    "Gemini runtime compatibility:\n"
    "- Runtime bridge for runnable shell GPD CLI calls: {launcher}.\n"
    "- Stable runtime rules: installed `get-physics-done/references/tooling/runtime-command-snippets.md`.\n"
    "- Public labels: `gpd ...` for terminals and `{public_prefix}...` for Gemini commands.\n"
    "</gemini_runtime_notes>\n\n"
)
_GEMINI_COMMAND_RUNTIME_NOTE_BLOCK_RE = re.compile(
    r"<gemini_runtime_notes>\n.*?</gemini_runtime_notes>\n*",
    re.DOTALL,
)
_GEMINI_COMMAND_SHELL_ALLOWLIST_NOTE = (
    "<gemini_shell_runtime_notes>\n"
    "Gemini shell compatibility: enforced shell-prefix allowlist for auto-edit mode:\n{allowlist}\n"
    "- Use direct commands; runnable GPD CLI shell calls must start with {launcher}.\n"
    "- Stable shell rules: installed `get-physics-done/references/tooling/runtime-command-snippets.md`.\n"
    "- If `run_shell_command` is denied by policy, stop and report the policy block. Do not replace validation or persistence commands with unvalidated file writes.\n"
    "</gemini_shell_runtime_notes>\n\n"
)
_GEMINI_COMMAND_SHELL_ALLOWLIST_NOTE_BLOCK_RE = re.compile(
    r"<gemini_shell_runtime_notes>\n.*?</gemini_shell_runtime_notes>\n*",
    re.DOTALL,
)
_GEMINI_RUNTIME_HELPER_RE = re.compile(r"(?:gpd\.runtime_cli|\bgpd_cli\s+--raw\b|\bgpd\s+--raw\b)")


def _manifest_gemini_managed_runtime_files_key() -> str:
    """Return the catalog-owned manifest key for Gemini managed runtime files."""
    return get_manifest_metadata_list_policy_key("gemini", value_kind="relpath")


def _convert_gemini_tool_name(tool_name: str) -> str | None:
    """Convert a canonical GPD tool name or runtime alias to Gemini CLI format.

    Returns ``None`` if the tool should be excluded from the Gemini config
    (MCP tools are auto-discovered at runtime and ``task`` is auto-registered).
    """
    return translate_for_runtime(
        tool_name,
        _TOOL_NAME_MAP,
        auto_discovered_tools=_AUTO_DISCOVERED_TOOLS,
        drop_mcp_frontmatter_tools=_DROP_MCP_FRONTMATTER_TOOLS,
    )


def _gemini_settings_shape_is_valid(settings: dict[str, object]) -> bool:
    hooks = settings.get("hooks")
    if hooks is not None and not isinstance(hooks, dict):
        return False
    if isinstance(hooks, dict):
        session_start = hooks.get("SessionStart")
        if session_start is not None and not isinstance(session_start, list):
            return False

    experimental = settings.get("experimental")
    if experimental is not None and not isinstance(experimental, dict):
        return False

    policy_paths = settings.get("policyPaths")
    if policy_paths is not None and not isinstance(policy_paths, list):
        return False

    mcp_servers = settings.get("mcpServers")
    if mcp_servers is not None and not isinstance(mcp_servers, dict):
        return False
    if isinstance(mcp_servers, dict) and any(not isinstance(entry, dict) for entry in mcp_servers.values()):
        return False

    return True


def _read_gemini_settings_state(settings_path: Path) -> tuple[dict[str, object] | None, str | None]:
    """Return parsed Gemini settings and a malformed marker when parsing fails."""
    if not settings_path.exists():
        return None, None
    try:
        parsed = parse_jsonc(settings_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, "malformed"
    if not isinstance(parsed, dict):
        return None, "malformed"
    if not _gemini_settings_shape_is_valid(parsed):
        return None, "malformed"
    return parsed, None


def _validated_deferred_install_payload(
    install_result: Mapping[str, object],
) -> tuple[str | Path, dict[str, object], str, bool]:
    """Return deferred settings payload or fail closed before finalization."""
    settings_written = install_result.get("settingsWritten", False)
    if type(settings_written) is not bool:
        raise RuntimeError("Gemini deferred install result is malformed; refusing to finalize install.")

    settings_path = install_result.get("settingsPath")
    settings = install_result.get("settings")
    statusline_command = install_result.get("statuslineCommand")
    should_install_statusline = install_result.get("shouldInstallStatusline", True)

    if not isinstance(settings_path, (str, Path)):
        raise RuntimeError("Gemini deferred install result is malformed; refusing to finalize install.")
    if not isinstance(settings, dict):
        raise RuntimeError("Gemini deferred install result is malformed; refusing to finalize install.")
    if not _gemini_settings_shape_is_valid(settings):
        raise RuntimeError("Gemini deferred install result is malformed; refusing to finalize install.")
    if not isinstance(statusline_command, str):
        raise RuntimeError("Gemini deferred install result is malformed; refusing to finalize install.")
    if type(should_install_statusline) is not bool:
        raise RuntimeError("Gemini deferred install result is malformed; refusing to finalize install.")

    return settings_path, settings, statusline_command, should_install_statusline


def _gemini_policy_command_prefixes(bridge_command: str) -> tuple[str, ...]:
    """Return the narrow shell prefixes GPD auto-approves for Gemini."""
    return (
        bridge_command,
        *_GEMINI_STATIC_POLICY_COMMAND_PREFIXES,
    )


def _render_gemini_shell_allowlist(bridge_command: str) -> str:
    """Render the enforced Gemini shell-prefix allowlist for model-facing content."""
    return "\n".join(f"  - `{prefix}`" for prefix in _gemini_policy_command_prefixes(bridge_command))


def _rewrite_gpd_cli_invocations(content: str, bridge_command: str) -> str:
    """Rewrite shell-command ``gpd`` calls to the shared runtime CLI bridge.

    Restrict rewrites to fenced shell code blocks and command positions only.
    This keeps prose and inline code spans canonical while still rewriting
    runnable shell steps.
    """
    return rewrite_projection_shell_bridge(content, bridge_command)


def _contains_gemini_shell_fence(content: str) -> bool:
    """Return whether content contains a fenced shell block Gemini will execute under policy."""
    return any(
        line.lstrip().startswith("```")
        and line.lstrip()[3:].strip().lower() in DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES
        for line in content.splitlines()
    )


def _inject_gemini_command_runtime_note(
    content: str,
    bridge_command: str,
    *,
    include_runtime_note: bool = True,
    include_shell_allowlist: bool = False,
) -> str:
    """Prepend Gemini-specific shell guidance to installed top-level commands."""
    note = ""
    if include_runtime_note:
        public_prefix = validated_public_command_prefix(get_runtime_descriptor("gemini"))
        note += _GEMINI_COMMAND_RUNTIME_NOTE.format(
            launcher=bridge_command,
            public_prefix=public_prefix,
        )
    if include_shell_allowlist:
        note += _GEMINI_COMMAND_SHELL_ALLOWLIST_NOTE.format(
            launcher=bridge_command,
            allowlist=_render_gemini_shell_allowlist(bridge_command),
        )
    return prepend_projection_note(
        content,
        note,
        strip_patterns=(
            _GEMINI_COMMAND_RUNTIME_NOTE_BLOCK_RE,
            _GEMINI_COMMAND_SHELL_ALLOWLIST_NOTE_BLOCK_RE,
        ),
    )


def _strip_gemini_command_runtime_notes(content: str) -> str:
    """Return Gemini command content without adapter-injected note blocks."""
    return strip_projection_note_blocks(
        content,
        (
            _GEMINI_COMMAND_RUNTIME_NOTE_BLOCK_RE,
            _GEMINI_COMMAND_SHELL_ALLOWLIST_NOTE_BLOCK_RE,
        ),
    )


def _needs_gemini_runtime_note(content: str, *, bridge_command: str) -> bool:
    """Return whether note-free content still needs Gemini runtime bridge guidance."""
    note_free_content = _strip_gemini_command_runtime_notes(content)
    return bridge_command in note_free_content or _GEMINI_RUNTIME_HELPER_RE.search(note_free_content) is not None


_GEMINI_SHELL_SQUARE_PLACEHOLDER_RE = re.compile(r"\[[A-Za-z][^\]\n]*(?:dir|file|hash|name|path|phase|slug)[^\]\n]*\]")
_GEMINI_SHELL_UNSAFE_FRAGMENTS = (
    "<<",
    "mktemp",
    "PROJECT_CONTRACT_JSON",
    "printf '%s\\n'",
)
_GEMINI_HARD_UNSAFE_PROJECTION_KINDS = frozenset(
    {
        "control_flow",
        "heredoc_or_stdin_contract_write",
        "variable_capture",
    }
)
_GEMINI_DIRECT_PLACEHOLDER_REASONS = frozenset(
    {
        "ellipsis-placeholder",
        "template-placeholder",
    }
)


def _gemini_direct_command_prefixes(bridge_command: str | None) -> tuple[str, ...]:
    """Return direct command prefixes Gemini may keep executable."""
    if bridge_command is None:
        return ("gpd ",)
    return ("gpd ", bridge_command)


def _gemini_extra_shell_block_reasons(body: str) -> tuple[str, ...]:
    """Return Gemini-only blockers that are intentionally outside the shared classifier."""
    reasons: list[str] = []
    if any(fragment in body for fragment in _GEMINI_SHELL_UNSAFE_FRAGMENTS):
        reasons.append("unsafe-shell-fragment")
    if _GEMINI_SHELL_SQUARE_PLACEHOLDER_RE.search(body):
        reasons.append("template-placeholder")
    return tuple(dict.fromkeys(reasons))


def _is_gemini_direct_bridge_projection(
    kind: str,
    reasons: tuple[str, ...],
    first_command: str,
    direct_prefixes: tuple[str, ...],
) -> bool:
    """Return whether a shared projection maps to Gemini's runnable bridge class."""
    if not _starts_with_gemini_direct_prefix(first_command, direct_prefixes):
        return False
    if kind == "direct_command":
        return True
    return kind == "pseudocode" and bool(reasons) and set(reasons) <= _GEMINI_DIRECT_PLACEHOLDER_REASONS


def _is_safe_gemini_static_policy_projection(kind: str, reasons: tuple[str, ...]) -> bool:
    """Return whether a static Gemini allowlist prefix has no unsafe shell structure."""
    return kind == "terminal_example" or reasons == ("unclassified-shell-shape",)


def _starts_with_gemini_direct_prefix(command: str, prefixes: tuple[str, ...]) -> bool:
    return any(command.startswith(prefix) for prefix in prefixes)


def _classify_gemini_shell_fence_body(
    body: str,
    *,
    bridge_command: str | None = None,
) -> GeminiShellFenceClassification:
    """Classify one shell fence before Gemini command rendering.

    Gemini headless auto-edit policy checks the first runnable shell command
    syntactically. Source prompts often use shell fences for terminal examples
    and pseudocode, so Gemini projection must decide which fences remain
    runnable instead of trying to patch every prose variant with exact rewrites.
    """
    direct_prefixes = _gemini_direct_command_prefixes(bridge_command)
    projection = classify_projection_shell_fence(body, direct_command_prefixes=direct_prefixes)
    first = projection.first_command
    if first is None or projection.kind == "non_runnable":
        return GeminiShellFenceClassification("non-runnable", first, projection.reasons)

    gemini_reasons = _gemini_extra_shell_block_reasons(body)
    if gemini_reasons:
        return GeminiShellFenceClassification("pseudocode", first, gemini_reasons)
    if projection.kind in _GEMINI_HARD_UNSAFE_PROJECTION_KINDS:
        return GeminiShellFenceClassification("pseudocode", first, projection.reasons)
    if _is_gemini_direct_bridge_projection(projection.kind, projection.reasons, first, direct_prefixes):
        if bridge_command is not None and first.startswith(bridge_command):
            return GeminiShellFenceClassification("runnable-bridge", first, ("bridge-command",))
        return GeminiShellFenceClassification("runnable-bridge", first, ("canonical-gpd-command",))
    if first.startswith(_GEMINI_STATIC_POLICY_COMMAND_PREFIXES) and _is_safe_gemini_static_policy_projection(
        projection.kind,
        projection.reasons,
    ):
        return GeminiShellFenceClassification("policy-static", first, ("static-policy-prefix",))
    if projection.kind == "terminal_example":
        return GeminiShellFenceClassification("terminal-example", first, projection.reasons)
    return GeminiShellFenceClassification("pseudocode", first, projection.reasons)


def classify_gemini_shell_fence_body(
    body: str,
    *,
    bridge_command: str | None = None,
) -> GeminiShellFenceClassification:
    """Classify a Gemini shell fence body using the renderer's decision logic."""
    return _classify_gemini_shell_fence_body(body, bridge_command=bridge_command)


def _replace_markdown_fence_language(line: str, marker: str, language: str) -> str:
    """Return *line* with its opening fence language replaced."""
    stripped = line.lstrip()
    indent = line[: len(line) - len(stripped)]
    eol = "\n" if line.endswith("\n") else ""
    return f"{indent}{marker}{language}{eol}"


def _render_gemini_classified_shell_fences(content: str, *, bridge_command: str) -> tuple[str, bool]:
    """Downgrade Gemini-non-runnable shell fences and report if shell policy is needed."""
    rendered: list[str] = []
    active_marker: str | None = None
    opening_line = ""
    opening_is_shell = False
    body_lines: list[str] = []
    shell_policy_required = False

    for line in content.splitlines(keepends=True):
        stripped = line.lstrip()
        fence_marker = _markdown_fence_marker(stripped)
        if active_marker is None:
            if fence_marker is None:
                rendered.append(line)
                continue

            active_marker = fence_marker
            opening_line = line
            opening_is_shell = (
                _markdown_fence_language(stripped, fence_marker) in DEFAULT_RUNTIME_BRIDGE_SHELL_FENCE_LANGUAGES
            )
            body_lines = []
            continue

        if fence_marker == active_marker:
            body = "".join(body_lines)
            if not opening_is_shell:
                rendered.append(opening_line)
                rendered.append(body)
                rendered.append(line)
            else:
                classification = _classify_gemini_shell_fence_body(body, bridge_command=bridge_command)
                if classification.kind in {"runnable-bridge", "policy-static"}:
                    shell_policy_required = True
                    rendered.append(opening_line)
                else:
                    rendered.append(_replace_markdown_fence_language(opening_line, active_marker, "text"))
                rendered.append(body)
                rendered.append(line)
            active_marker = None
            opening_line = ""
            opening_is_shell = False
            body_lines = []
            continue

        body_lines.append(line)

    if active_marker is not None:
        rendered.append(opening_line)
        rendered.extend(body_lines)

    return "".join(rendered), shell_policy_required


def _render_gemini_command_prompt(
    content: str,
    *,
    bridge_command: str,
    command_name: str | None = None,
) -> str:
    """Render one canonical command markdown source into Gemini prompt text."""
    content = strip_sub_tags(content)
    content = convert_tool_references_in_body(content, _TOOL_REFERENCE_MAP)
    content = _rewrite_gemini_shell_workflow_guidance(content, command_name=command_name)
    content, shell_allowlist_required = _render_gemini_classified_shell_fences(
        content,
        bridge_command=bridge_command,
    )
    rewritten = _rewrite_gpd_cli_invocations(content, bridge_command)
    shell_allowlist_required = shell_allowlist_required or rewritten != content
    runtime_note_required = _needs_gemini_runtime_note(rewritten, bridge_command=bridge_command)
    return _inject_gemini_command_runtime_note(
        rewritten,
        bridge_command,
        include_runtime_note=runtime_note_required,
        include_shell_allowlist=shell_allowlist_required,
    )


def _validate_existing_gemini_managed_state(target_dir: Path) -> None:
    """Fail closed when the prior Gemini manifest tracks managed config with the wrong shape."""
    manifest_path = target_dir / MANIFEST_NAME
    if not manifest_path.exists():
        return

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Gemini install manifest is malformed; refusing to overwrite managed config state.") from exc
    if not isinstance(manifest, dict):
        raise RuntimeError("Gemini install manifest is malformed; refusing to overwrite managed config state.")

    managed_config = manifest.get("managed_config")
    if managed_config is not None:
        if not isinstance(managed_config, dict):
            raise RuntimeError("Gemini managed_config is malformed; refusing to overwrite managed config state.")
        enable_agents = managed_config.get("experimental.enableAgents")
        if enable_agents is not None and not isinstance(enable_agents, bool):
            raise RuntimeError("Gemini managed_config.experimental.enableAgents is malformed.")
        policy_paths = managed_config.get("policyPaths")
        if policy_paths is not None and not (
            isinstance(policy_paths, list) and all(isinstance(path, str) and path for path in policy_paths)
        ):
            raise RuntimeError("Gemini managed_config.policyPaths is malformed.")

    managed_runtime_files = manifest.get(_manifest_gemini_managed_runtime_files_key())
    if managed_runtime_files is not None and not (
        isinstance(managed_runtime_files, list)
        and all(isinstance(path, str) and path for path in managed_runtime_files)
    ):
        raise RuntimeError("Gemini managed_runtime_files is malformed.")


def _rewrite_gemini_shell_workflow_guidance(content: str, *, command_name: str | None = None) -> str:
    """Rewrite known shell-heavy workflow snippets into Gemini-safe forms.

    Gemini CLI's policy engine validates shell commands syntactically from the
    start of each command segment. GPD's canonical markdown includes some bash
    examples that rely on shell variables, command substitution, or combined
    blocks. Those examples work for humans and more permissive runtimes, but in
    Gemini headless auto-edit they lead the model to generate commands that are
    denied before GPD ever runs.
    """
    return rewrite_gemini_shell_workflow_guidance(content, command_name=command_name)


# ---------------------------------------------------------------------------
# Frontmatter conversion
# ---------------------------------------------------------------------------


def _convert_frontmatter_to_gemini(content: str) -> str:
    """Convert canonical GPD agent/file frontmatter to Gemini CLI format.

    - ``allowed-tools:`` → ``tools:`` as YAML array
    - Tool names converted to Gemini built-in names
    - Non-Gemini agent metadata removed (Gemini validates frontmatter strictly)
    - ``mcp__*`` tools excluded (auto-discovered at runtime)
    - ``<sub>`` tags in body stripped for terminal rendering
    """
    preamble, frontmatter, separator, body = split_markdown_frontmatter(content)
    if not frontmatter:
        return strip_sub_tags(content)

    lines = frontmatter.split("\n")
    new_lines: list[str] = []
    in_allowed_tools = False
    current_field_supported = True
    tools: list[str] = []

    for line in lines:
        trimmed = line.strip()
        top_level_field_match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if top_level_field_match:
            current_field_supported = False
            field_name, field_value = top_level_field_match.groups()

            # Convert allowed-tools YAML array to tools list
            if field_name == "allowed-tools":
                in_allowed_tools = True
                continue

            # Handle inline tools: field (comma-separated string)
            if field_name == "tools":
                if field_value:
                    parsed = [t.strip() for t in field_value.split(",") if t.strip()]
                    for t in parsed:
                        mapped = _convert_gemini_tool_name(t)
                        if mapped:
                            tools.append(mapped)
                else:
                    # tools: with no value means YAML array follows
                    in_allowed_tools = True
                continue

            if field_name not in _GEMINI_AGENT_FRONTMATTER_FIELDS:
                continue

            current_field_supported = True
            in_allowed_tools = False
            new_lines.append(line)
            continue

        if line.startswith((" ", "\t")) and not in_allowed_tools:
            if current_field_supported:
                new_lines.append(line)
            continue

        if not trimmed:
            if current_field_supported:
                new_lines.append(line)
            continue

        # Collect allowed-tools/tools array items
        if in_allowed_tools:
            if trimmed.startswith("- "):
                mapped = _convert_gemini_tool_name(trimmed[2:].strip())
                if mapped:
                    tools.append(mapped)
                continue
            elif trimmed and not trimmed.startswith("-"):
                in_allowed_tools = False

        if not in_allowed_tools and current_field_supported:
            new_lines.append(line)

    # Deduplicate tools while preserving order
    seen: set[str] = set()
    unique_tools: list[str] = []
    for tool in tools:
        if tool not in seen:
            seen.add(tool)
            unique_tools.append(tool)

    # Add tools as YAML array (Gemini requires array format)
    if unique_tools:
        new_lines.append("tools:")
        for tool in unique_tools:
            new_lines.append(f"  - {tool}")

    new_frontmatter = "\n".join(new_lines).strip()
    return render_markdown_frontmatter(preamble, new_frontmatter, separator, strip_sub_tags(body))


def _normalize_string_list(value: object) -> list[str]:
    """Return a normalized list of strings from a settings value."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _merge_unique_strings(existing: object, additions: list[str]) -> tuple[list[str], list[str]]:
    """Append new string values while preserving order and existing items."""
    merged = _normalize_string_list(existing)
    seen = set(merged)
    added: list[str] = []
    for item in additions:
        if item not in seen:
            merged.append(item)
            seen.add(item)
            added.append(item)
    return merged, added


def _managed_gemini_policy_path(target_dir: Path) -> Path:
    """Return the GPD-managed Gemini policy file path."""
    return target_dir / _GEMINI_POLICY_DIR_NAME / _GEMINI_POLICY_FILE_NAME


def _managed_gemini_yolo_wrapper_path(target_dir: Path) -> Path:
    """Return the GPD-managed Gemini launch wrapper for yolo sessions."""
    return target_dir / "get-physics-done" / _GEMINI_RUNTIME_BIN_DIR_NAME / _GEMINI_YOLO_WRAPPER_NAME


def _render_gemini_yolo_wrapper() -> str:
    """Render a small launcher that starts Gemini in yolo approval mode."""
    launcher = shlex.quote(get_runtime_descriptor("gemini").launch_command)
    return f'#!/bin/sh\nexec {launcher} --approval-mode=yolo "$@"\n'


def _render_gemini_policy_toml(bridge_command: str) -> str:
    """Render the Gemini policy file GPD installs for headless auto-edit flows."""
    rendered_prefixes: list[str] = []
    for prefix in _gemini_policy_command_prefixes(bridge_command):
        rendered_prefixes.append(json.dumps(prefix))
    prefixes = ",\n  ".join(rendered_prefixes)
    return (
        "# Managed by Get Physics Done (GPD).\n"
        "#\n"
        "# Policy Engine rules that auto-approve the narrow set of shell commands\n"
        "# GPD's bootstrap workflows rely on. The runtime CLI bridge validates the\n"
        "# install contract and pins the active runtime before dispatching to the\n"
        "# shared CLI implementation.\n"
        "\n"
        "[[rule]]\n"
        'toolName = "run_shell_command"\n'
        "commandPrefix = [\n"
        f"  {prefixes}\n"
        "]\n"
        'decision = "allow"\n'
        "priority = 350\n"
        'modes = ["autoEdit"]\n'
        "allowRedirection = true\n"
    )


# ---------------------------------------------------------------------------
# TOML conversion for commands
# ---------------------------------------------------------------------------


def _convert_to_gemini_toml(content: str) -> str:
    """Convert Claude Code markdown command to Gemini TOML format.

    Extracts selected frontmatter fields and puts body into ``prompt``.
    Preserves non-runtime command metadata as TOML comments so installed
    Gemini commands stay inspectable and closer to the canonical source.
    Uses TOML multi-line literal strings (``'''``) to avoid escape issues
    with backslashes in LaTeX/physics content.
    """
    _preamble, frontmatter, _separator, body = split_markdown_frontmatter(content)
    if not frontmatter:
        body = content.strip()
        if "'''" in body:
            return f"prompt = {json.dumps(body, ensure_ascii=False)}\n"
        return f"prompt = '''\n{body}\n'''\n"
    body = body.strip()

    # Extract selected frontmatter fields
    description = ""
    context_mode = ""
    for line in frontmatter.split("\n"):
        trimmed = line.strip()
        if trimmed.startswith("description:"):
            description = trimmed[12:].strip()
        elif trimmed.startswith("context_mode:"):
            context_mode = trimmed[13:].strip()

    toml = ""
    metadata_comments = _render_preserved_frontmatter_comments(frontmatter)
    if metadata_comments:
        toml += metadata_comments + "\n"
    if description:
        toml += f"description = {json.dumps(description)}\n"
    if context_mode:
        toml += f"context_mode = {json.dumps(context_mode)}\n"

    # Use TOML multi-line literal strings (''') to avoid escape issues.
    # Fall back to double-quoted string with JSON-style escaping if content contains '''.
    if "'''" in body:
        toml += f"prompt = {json.dumps(body, ensure_ascii=False)}\n"
    else:
        toml += f"prompt = '''\n{body}\n'''\n"

    return toml


def _render_preserved_frontmatter_comments(frontmatter: str) -> str:
    """Render non-runtime frontmatter metadata as TOML comments.

    Gemini commands only honor a narrow TOML surface, but the canonical GPD
    markdown commands carry other important metadata such as ``name``,
    ``argument-hint``, and ``requires``. Preserve those source fields as
    comments so the installed command remains auditable without inventing new
    runtime semantics.
    """
    excluded_keys = {"allowed-tools", "tools", "color", "description", "context_mode"}
    preserved: list[str] = []
    include_current = False

    for line in frontmatter.split("\n"):
        stripped = line.strip()
        if not stripped:
            if include_current and preserved and preserved[-1] != "":
                preserved.append("")
            continue

        if line == line.lstrip() and ":" in line:
            key = line.split(":", 1)[0].strip()
            include_current = key not in excluded_keys

        if include_current:
            preserved.append(line.rstrip())

    while preserved and preserved[0] == "":
        preserved.pop(0)
    while preserved and preserved[-1] == "":
        preserved.pop()

    if not preserved:
        return ""

    comment_lines = ["# Source frontmatter preserved for parity:"]
    for line in preserved:
        comment_lines.append("#" if not line else f"# {line}")
    return "\n".join(comment_lines)


def _policy_path_matches(value: str, candidates: set[str]) -> bool:
    """Return True when a settings policy path matches a managed candidate."""
    if value in candidates:
        return True
    try:
        return str(Path(value).expanduser().resolve()) in candidates
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Agent installation
# ---------------------------------------------------------------------------


def _copy_agents_gemini(
    agents_src: Path,
    agents_dest: Path,
    path_prefix: str,
    gpd_src_root: Path | None = None,
    attribution: str | None = "",
    install_scope: str | None = None,
    *,
    bridge_command: str,
) -> None:
    """Install agent .md files with Gemini-specific conversions.

    - Replace path placeholders
    - Process attribution
    - Expand ``@`` includes (Gemini doesn't support native ``@`` includes)
    - Convert frontmatter (allowed-tools → tools array, strip color)
    - Convert tool name references in body text
    - Remove stale gpd-* agents not in the new set
    """
    if not agents_src.is_dir():
        return

    agents_dest.mkdir(parents=True, exist_ok=True)
    source_root = gpd_src_root or agents_src.parent / "specs"

    new_agent_names: set[str] = set()
    for agent_md in sorted(agents_src.glob("*.md")):
        content = compile_markdown_for_runtime(
            agent_md.read_text(encoding="utf-8"),
            runtime="gemini",
            path_prefix=path_prefix,
            install_scope=install_scope,
            src_root=source_root,
        )
        content = process_attribution(content, attribution)
        content = protect_runtime_agent_prompt(content, "gemini")
        content = _convert_frontmatter_to_gemini(content)
        content = convert_tool_references_in_body(content, _TOOL_REFERENCE_MAP)
        content = _rewrite_gpd_cli_invocations(content, bridge_command)

        (agents_dest / agent_md.name).write_text(content, encoding="utf-8")
        new_agent_names.add(agent_md.name)

    remove_stale_agents(agents_dest, new_agent_names)


# ---------------------------------------------------------------------------
# Command installation (nested structure, .toml format)
# ---------------------------------------------------------------------------


def _install_commands_as_toml(
    commands_src: Path,
    commands_dest: Path,
    path_prefix: str,
    workflow_target_dir: Path,
    gpd_src_root: Path,
    attribution: str | None = "",
    install_scope: str | None = None,
    *,
    bridge_command: str,
    explicit_target: bool = False,
) -> None:
    """Install commands as .toml files in nested ``commands/gpd/`` structure.

    Gemini commands are TOML files with ``description`` and ``prompt`` fields.
    """
    if not commands_src.is_dir():
        return

    # Clean destination before copy
    if commands_dest.exists():
        shutil.rmtree(commands_dest)
    commands_dest.mkdir(parents=True, exist_ok=True)

    _copy_commands_recursive(
        commands_src,
        commands_dest,
        path_prefix,
        workflow_target_dir,
        attribution,
        gpd_src_root,
        install_scope,
        bridge_command=bridge_command,
        explicit_target=explicit_target,
    )


def _copy_commands_recursive(
    src_dir: Path,
    dest_dir: Path,
    path_prefix: str,
    workflow_target_dir: Path,
    attribution: str | None,
    gpd_src_root: Path,
    install_scope: str | None = None,
    *,
    bridge_command: str,
    explicit_target: bool = False,
) -> None:
    """Recursively copy commands, converting .md to .toml for Gemini."""
    for entry in sorted(src_dir.iterdir()):
        if entry.is_dir():
            sub_dest = dest_dir / entry.name
            sub_dest.mkdir(parents=True, exist_ok=True)
            _copy_commands_recursive(
                entry,
                sub_dest,
                path_prefix,
                workflow_target_dir,
                attribution,
                gpd_src_root,
                install_scope,
                bridge_command=bridge_command,
                explicit_target=explicit_target,
            )
        elif entry.suffix == ".md":
            content = compile_command_markdown_for_runtime(
                entry.read_text(encoding="utf-8"),
                runtime="gemini",
                command_name=entry.stem,
                path_prefix=path_prefix,
                install_scope=install_scope,
                src_root=gpd_src_root,
                workflow_target_dir=workflow_target_dir,
                explicit_target=explicit_target,
                bridge_command=bridge_command,
            )
            content = process_attribution(content, attribution)
            public_prefix = validated_public_command_prefix(get_runtime_descriptor("gemini"))
            content = content.replace("`gpd:`", f"`{public_prefix}`")
            content = rewrite_runtime_command_surfaces_to_public(content, public_prefix=public_prefix)
            content = _render_gemini_command_prompt(
                content,
                bridge_command=bridge_command,
                command_name=entry.stem,
            )
            toml_content = _convert_to_gemini_toml(content)
            toml_path = dest_dir / entry.with_suffix(".toml").name
            toml_path.write_text(toml_content, encoding="utf-8")
        else:
            shutil.copy2(entry, dest_dir / entry.name)


# ---------------------------------------------------------------------------
# Adapter class
# ---------------------------------------------------------------------------


class GeminiAdapter(RuntimeAdapter):
    """Adapter for Google Gemini CLI."""

    tool_name_map = _TOOL_NAME_MAP
    auto_discovered_tools = _AUTO_DISCOVERED_TOOLS
    drop_mcp_frontmatter_tools = _DROP_MCP_FRONTMATTER_TOOLS
    strip_sub_tags_in_shared_markdown = True

    @property
    def runtime_name(self) -> str:
        return "gemini"

    def project_markdown_surface(
        self,
        content: str,
        *,
        surface_kind: str,
        path_prefix: str,
        command_name: str | None = None,
        bridge_command: str | None = None,
    ) -> str:
        del path_prefix
        if surface_kind != "command":
            return super().project_markdown_surface(
                content,
                surface_kind=surface_kind,
                path_prefix="",
                bridge_command=bridge_command,
            )
        if bridge_command is None:
            raise ValueError("bridge_command is required for projected Gemini command surfaces")
        content = self.translate_shared_command_references(content)
        rendered = _render_gemini_command_prompt(
            content,
            bridge_command=bridge_command,
            command_name=command_name,
        )
        prompt = tomllib.loads(_convert_to_gemini_toml(rendered)).get("prompt")
        if not isinstance(prompt, str):
            raise ValueError("gemini projected command surface must expose a prompt string")
        return prompt

    def _runtime_bridge_only_relpaths(self) -> tuple[str, ...]:
        """Return Gemini artifacts that appear only after finalize_install()."""
        return ("settings.json",)

    def runtime_install_required_relpaths(self) -> tuple[str, ...]:
        """Return Gemini-owned files required for a complete install."""
        return (
            f"{_GEMINI_POLICY_DIR_NAME}/{_GEMINI_POLICY_FILE_NAME}",
            *self._runtime_bridge_only_relpaths(),
        )

    def commit_attribution_config_path(self, *, explicit_config_dir: str | None = None) -> Path | None:
        """Gemini stores commit attribution in settings.json, not policy TOML."""
        config_dir = Path(explicit_config_dir).expanduser() if explicit_config_dir else self.resolve_global_config_dir()
        return config_dir / "settings.json"

    def install(
        self,
        gpd_root: Path,
        target_dir: Path,
        *,
        is_global: bool = False,
        explicit_target: bool = False,
    ) -> dict[str, object]:
        """Install Gemini surfaces and defer settings persistence to finalization.

        Unlike Claude Code, Gemini requires ``settings.json`` to enable
        ``experimental.enableAgents`` for the installed agents to function.
        ``install()`` prepares those settings in-memory; ``finalize_install()``
        writes them to disk once the caller is ready to complete the runtime
        configuration step.
        """
        previous_finalize_pending = getattr(self, "_gemini_finalize_pending", False)
        self._gemini_finalize_pending = True
        try:
            result = super().install(gpd_root, target_dir, is_global=is_global, explicit_target=explicit_target)
        finally:
            self._gemini_finalize_pending = previous_finalize_pending

        return result

    # --- Template method hooks ---

    def _install_commands(self, gpd_root: Path, target_dir: Path, path_prefix: str, failures: list[str]) -> int:
        commands_src = gpd_root / "commands"
        commands_dest = target_dir / "commands" / "gpd"
        (target_dir / "commands").mkdir(parents=True, exist_ok=True)
        bridge_command = self.runtime_cli_bridge_command(target_dir)
        _install_commands_as_toml(
            commands_src,
            commands_dest,
            path_prefix,
            target_dir,
            gpd_root / "specs",
            attribution=self.get_commit_attribution(explicit_config_dir=str(target_dir)),
            install_scope=self._current_install_scope_flag(),
            bridge_command=bridge_command,
            explicit_target=getattr(self, "_install_explicit_target", False),
        )
        if verify_installed(commands_dest):
            logger.info("Installed commands/gpd (TOML format)")
        else:
            failures.append("commands/gpd")
        return sum(1 for f in commands_dest.rglob("*.toml") if f.is_file()) if commands_dest.exists() else 0

    def _install_agents(self, gpd_root: Path, target_dir: Path, path_prefix: str, failures: list[str]) -> int:
        agents_src = gpd_root / "agents"
        agents_dest = target_dir / "agents"
        bridge_command = self.runtime_cli_bridge_command(target_dir)
        _copy_agents_gemini(
            agents_src,
            agents_dest,
            path_prefix,
            gpd_root / "specs",
            attribution=self.get_commit_attribution(explicit_config_dir=str(target_dir)),
            install_scope=self._current_install_scope_flag(),
            bridge_command=bridge_command,
        )
        if verify_installed(agents_dest):
            logger.info("Installed agents")
        else:
            failures.append("agents")
        return sum(1 for f in agents_dest.iterdir() if f.is_file() and f.suffix == ".md") if agents_dest.exists() else 0

    def _install_content(self, gpd_root: Path, target_dir: Path, path_prefix: str, failures: list[str]) -> None:
        """Install shared specs content with Gemini-specific bridge rewrites."""
        bridge_command = self.runtime_cli_bridge_command(target_dir)

        def _translate(content: str, prefix: str, install_scope: str | None = None) -> str:
            translated = super(GeminiAdapter, self).translate_shared_markdown(
                content,
                prefix,
                install_scope=install_scope,
            )
            translated = _rewrite_gemini_shell_workflow_guidance(translated)
            translated, _shell_allowlist_required = _render_gemini_classified_shell_fences(
                translated,
                bridge_command=bridge_command,
            )
            return _rewrite_gpd_cli_invocations(translated, bridge_command)

        from gpd.adapters.install_utils import install_gpd_content

        failures.extend(
            install_gpd_content(
                gpd_root / "specs",
                target_dir,
                path_prefix,
                self.runtime_name,
                install_scope=self._current_install_scope_flag(),
                markdown_transform=_translate,
                explicit_target=getattr(self, "_install_explicit_target", False),
            )
        )

    def _preflight_runtime_config(self, target_dir: Path, is_global: bool) -> None:
        """Fail before copying files when Gemini-owned config is malformed."""
        self._preflight_project_integrations_config(target_dir, is_global)
        settings_path = target_dir / "settings.json"
        _validate_existing_gemini_managed_state(target_dir)
        _, settings_parse_error = _read_gemini_settings_state(settings_path)
        if settings_parse_error is not None:
            raise RuntimeError("Gemini settings.json is malformed; refusing to overwrite it during install.")

    def _configure_runtime(self, target_dir: Path, is_global: bool) -> dict[str, object]:
        settings_path = target_dir / "settings.json"
        _validate_existing_gemini_managed_state(target_dir)
        settings_state, settings_parse_error = _read_gemini_settings_state(settings_path)
        if settings_parse_error is not None:
            raise RuntimeError("Gemini settings.json is malformed; refusing to overwrite it during install.")
        settings = settings_state or {}
        self._managed_policy_paths = []
        self._managed_runtime_files = []

        # Enable experimental agents (required for custom sub-agents in Gemini CLI)
        experimental = settings.get("experimental")
        enable_agents_was_present = isinstance(experimental, dict) and experimental.get("enableAgents") is True
        if not isinstance(experimental, dict):
            experimental = {}
            settings["experimental"] = experimental
        if not experimental.get("enableAgents"):
            experimental["enableAgents"] = True
            logger.info("Enabled experimental agents")
        self._managed_enable_agents = not enable_agents_was_present

        # Build hook commands (Python hooks, same as Claude Code)
        should_install_statusline = self._installed_hook_script_available(HOOK_SCRIPTS["statusline"])
        should_install_update_hook = self._installed_hook_script_available(HOOK_SCRIPTS["check_update"])
        statusline_cmd = build_hook_command(
            target_dir,
            HOOK_SCRIPTS["statusline"],
            is_global=is_global,
            config_dir_name=self.config_dir_name,
            explicit_target=getattr(self, "_install_explicit_target", False),
        )
        update_check_cmd = build_hook_command(
            target_dir,
            HOOK_SCRIPTS["check_update"],
            is_global=is_global,
            config_dir_name=self.config_dir_name,
            explicit_target=getattr(self, "_install_explicit_target", False),
        )
        if should_install_update_hook:
            ensure_update_hook(
                settings,
                update_check_cmd,
                target_dir=target_dir,
                config_dir_name=self.config_dir_name,
            )
        else:
            logger.warning("Skipping update check hook because hooks/check_update.py is not GPD-managed")

        bridge_command = self.runtime_cli_bridge_command(target_dir)

        # Install a runtime-owned policy file so Gemini loads the minimum
        # GPD shell allowlist even while workspace policies are disabled.
        policy_path = _managed_gemini_policy_path(target_dir)
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        policy_path.write_text(_render_gemini_policy_toml(bridge_command), encoding="utf-8")
        self._managed_runtime_files = [
            policy_path.relative_to(target_dir).as_posix(),
        ]

        policy_dir_setting = str(policy_path.parent.resolve())
        merged_policy_paths, added_policy_paths = _merge_unique_strings(
            settings.get("policyPaths"), [policy_dir_setting]
        )
        if merged_policy_paths:
            settings["policyPaths"] = merged_policy_paths
        self._managed_policy_paths = added_policy_paths

        # Wire MCP servers into settings so they start automatically.
        from gpd.mcp.builtin_servers import merge_managed_mcp_servers

        project_cwd = self._project_cwd_for_runtime_config(target_dir, is_global)
        mcp_servers = build_runtime_managed_mcp_servers(cwd=project_cwd)
        if mcp_servers:
            existing_mcp = settings.get("mcpServers", {})
            merged_mcp = merge_managed_mcp_servers(existing_mcp, mcp_servers)
            for server_name in mcp_servers:
                existing_entry = existing_mcp.get(server_name) if isinstance(existing_mcp, dict) else None
                if not isinstance(existing_entry, dict) or "trust" not in existing_entry:
                    merged_mcp.setdefault(server_name, {})["trust"] = True
            settings["mcpServers"] = merged_mcp

        return {
            "settingsPath": str(settings_path),
            "settings": settings,
            "statuslineCommand": statusline_cmd,
            "shouldInstallStatusline": should_install_statusline,
            "mcpServers": len(mcp_servers),
        }

    def runtime_permissions_status(self, target_dir: Path, *, autonomy: str) -> dict[str, object]:
        """Report whether a Gemini yolo launcher is ready for the next session."""
        wrapper_path = _managed_gemini_yolo_wrapper_path(target_dir)
        wrapper_exists = wrapper_path.is_file()
        desired_mode = "yolo" if autonomy == "yolo" else "default"
        next_step: str | None = None
        message = "Gemini is using its normal approval-mode defaults."
        if desired_mode == "yolo":
            if wrapper_exists:
                message = "Gemini only supports yolo at launch time. The GPD launcher is ready for the next session."
                next_step = (
                    "Exit the current Gemini session and relaunch with "
                    f"{shlex.quote(str(wrapper_path))} so the runtime itself starts in yolo mode."
                )
            else:
                message = (
                    "Gemini only supports yolo at launch time. Generate and use the GPD launcher before "
                    "expecting uninterrupted yolo execution."
                )
        return {
            "runtime": self.runtime_name,
            "desired_mode": desired_mode,
            "configured_mode": "launch-wrapper" if wrapper_exists else "default",
            "config_aligned": wrapper_exists if desired_mode == "yolo" else True,
            "requires_relaunch": wrapper_exists if desired_mode == "yolo" else False,
            "managed_by_gpd": wrapper_exists,
            "launch_command": shlex.quote(str(wrapper_path)) if wrapper_exists else None,
            "message": message,
            "next_step": next_step,
        }

    def sync_runtime_permissions(self, target_dir: Path, *, autonomy: str) -> dict[str, object]:
        """Create or remove the Gemini yolo launcher for the requested autonomy."""
        wrapper_path = _managed_gemini_yolo_wrapper_path(target_dir)
        changed = False
        if autonomy == "yolo":
            wrapper_path.parent.mkdir(parents=True, exist_ok=True)
            content = _render_gemini_yolo_wrapper()
            current = wrapper_path.read_text(encoding="utf-8") if wrapper_path.exists() else None
            if current != content:
                wrapper_path.write_text(content, encoding="utf-8")
                wrapper_path.chmod(0o755)
                changed = True
        elif wrapper_path.exists():
            wrapper_path.unlink()
            changed = True

        status = self.runtime_permissions_status(target_dir, autonomy=autonomy)
        result = {
            **status,
            "changed": changed,
            "sync_applied": bool(status.get("config_aligned")),
            "requires_relaunch": autonomy == "yolo",
        }
        if autonomy == "yolo" and status.get("launch_command"):
            result["next_step"] = (
                "Exit the current Gemini session and relaunch with "
                f"{status['launch_command']} so the runtime itself starts in yolo mode."
            )
        elif changed:
            result["next_step"] = "Future Gemini sessions will use the normal approval mode unless you re-enable yolo."
        return result

    def _write_manifest(self, target_dir: Path, version: str) -> None:
        """Record manifest metadata for shared config keys GPD actually introduced."""
        managed_config: dict[str, object] = {}
        if getattr(self, "_managed_enable_agents", False):
            managed_config["experimental.enableAgents"] = True
        if getattr(self, "_managed_policy_paths", []):
            managed_config["policyPaths"] = list(self._managed_policy_paths)
        metadata: dict[str, object] = {}
        if managed_config:
            metadata["managed_config"] = managed_config
        if getattr(self, "_managed_runtime_files", []):
            metadata[_manifest_gemini_managed_runtime_files_key()] = list(self._managed_runtime_files)
        write_manifest(
            target_dir,
            version,
            runtime=self.runtime_name,
            metadata=metadata or None,
            install_scope=self._current_install_scope_flag(),
            explicit_target=getattr(self, "_install_explicit_target", False),
        )

    def install_verification_relpaths(self) -> tuple[str, ...]:
        """Return Gemini artifacts that must exist before ``install()`` returns."""
        return (
            *self.install_detection_relpaths(),
            f"{_GEMINI_POLICY_DIR_NAME}/{_GEMINI_POLICY_FILE_NAME}",
        )

    def missing_install_artifacts(self, target_dir: Path) -> tuple[str, ...]:
        """Return missing or malformed Gemini-owned install artifacts."""
        missing = list(super().missing_install_artifacts(target_dir))

        def _append_once(label: str) -> None:
            if label not in missing:
                missing.append(label)

        settings_path = target_dir / "settings.json"
        if not settings_path.exists():
            return tuple(missing)

        settings, settings_parse_error = _read_gemini_settings_state(settings_path)
        if settings_parse_error is not None:
            _append_once("settings.json")
            return tuple(missing)

        settings = settings or {}
        experimental = settings.get("experimental")
        if not isinstance(experimental, dict) or experimental.get("enableAgents") is not True:
            _append_once("settings.json experimental.enableAgents")

        mcp_servers = settings.get("mcpServers")
        if not isinstance(mcp_servers, dict) or not mcp_servers:
            _append_once("settings.json mcpServers")

        if (target_dir / "hooks" / HOOK_SCRIPTS["check_update"]).is_file():
            hooks = settings.get("hooks")
            session_start = hooks.get("SessionStart") if isinstance(hooks, dict) else None
            if not isinstance(session_start, list) or not any(
                _entry_has_gpd_hook(entry, target_dir=target_dir, config_dir_name=self.config_dir_name)
                for entry in session_start
            ):
                _append_once("settings.json update hook")

        return tuple(missing)

    def finish_install(
        self,
        settings_path: str | Path,
        settings: dict[str, object],
        statusline_command: str,
        should_install_statusline: bool,
        *,
        force_statusline: bool = False,
    ) -> None:
        """Apply statusline config and write settings atomically."""
        _finish_install(
            settings_path,
            settings,
            statusline_command,
            should_install_statusline,
            force_statusline=force_statusline,
        )

    def finalize_install(
        self,
        install_result: dict[str, object],
        *,
        force_statusline: bool = False,
    ) -> None:
        """Persist Gemini settings when install produced an in-memory config."""
        settings_written = install_result.get("settingsWritten", False)
        if type(settings_written) is not bool:
            raise RuntimeError("Gemini deferred install result is malformed; refusing to finalize install.")

        settings_path, settings, statusline_command, should_install_statusline = _validated_deferred_install_payload(
            install_result
        )
        target_dir = Path(settings_path).expanduser().resolve(strict=False).parent
        if settings_written:
            self._verify(target_dir)
            return

        _validate_existing_gemini_managed_state(target_dir)
        _, settings_parse_error = _read_gemini_settings_state(Path(settings_path))
        if settings_parse_error is not None:
            raise RuntimeError("Gemini settings.json is malformed; refusing to overwrite it during finalize.")
        self.finish_install(
            settings_path,
            settings,
            statusline_command,
            should_install_statusline,
            force_statusline=force_statusline,
        )
        self._verify(target_dir)
        install_result["settingsWritten"] = True

    def uninstall(self, target_dir: Path) -> dict[str, object]:
        """Remove GPD from a Gemini CLI .gemini/ directory.

        Extends base uninstall with Gemini-specific settings.json cleanup.
        """
        manifest = read_settings(target_dir / MANIFEST_NAME)
        has_authoritative_manifest = self._has_authoritative_install_manifest(target_dir)
        managed_config = manifest.get("managed_config")
        managed_runtime_files = manifest.get(_manifest_gemini_managed_runtime_files_key())
        remove_managed_enable_agents = (
            isinstance(managed_config, dict) and managed_config.get("experimental.enableAgents") is True
        )
        managed_policy_paths = []
        if isinstance(managed_config, dict):
            managed_policy_paths = _normalize_string_list(managed_config.get("policyPaths"))

        result = super().uninstall(target_dir)

        settings_path = target_dir / "settings.json"
        if settings_path.exists():
            settings = read_settings(settings_path)
            modified = False

            cleanup = cleanup_settings_json_managed_entries(
                settings,
                target_dir=target_dir,
                config_dir_name=self.config_dir_name,
                session_start_hook_filenames=(HOOK_SCRIPTS["check_update"],),
                mcp_server_keys=runtime_managed_mcp_server_keys(),
            )
            modified = cleanup.modified

            # Remove experimental.enableAgents only when GPD introduced it.
            experimental = settings.get("experimental")
            if (
                remove_managed_enable_agents
                and isinstance(experimental, dict)
                and experimental.get("enableAgents") is True
            ):
                del experimental["enableAgents"]
                if not experimental:
                    del settings["experimental"]
                modified = True

            policy_paths = _normalize_string_list(settings.get("policyPaths"))
            if policy_paths:
                candidate_policy_paths = set(managed_policy_paths)
                candidate_policy_paths.add(str((_managed_gemini_policy_path(target_dir).parent).resolve()))
                filtered_policy_paths = [
                    value for value in policy_paths if not _policy_path_matches(value, candidate_policy_paths)
                ]
                if filtered_policy_paths != policy_paths:
                    modified = True
                    if filtered_policy_paths:
                        settings["policyPaths"] = filtered_policy_paths
                    else:
                        settings.pop("policyPaths", None)

            if write_settings_if_modified_and_prune_empty(
                settings_path,
                settings,
                modified=modified,
                prune_empty=has_authoritative_manifest,
            ):
                result.setdefault("removed", []).append(settings_path.name)
            if modified:
                logger.info("Cleaned up Gemini settings.json (statusline, hooks, experimental, MCP)")

        policy_dir = _managed_gemini_policy_path(target_dir).parent
        if has_authoritative_manifest:
            policy_files = _normalize_string_list(managed_runtime_files)
            if not policy_files:
                policy_files = [_managed_gemini_policy_path(target_dir).relative_to(target_dir).as_posix()]
            for rel_path in policy_files:
                candidate = target_dir / rel_path
                if candidate.exists():
                    candidate.unlink()
                    result.setdefault("removed", []).append(rel_path)
            if policy_dir.is_dir() and not any(policy_dir.iterdir()):
                policy_dir.rmdir()

        for path in (
            target_dir / "commands",
            target_dir / "agents",
            target_dir / "hooks",
            target_dir / "cache",
            policy_dir,
            target_dir,
        ):
            prune_empty_ancestors(path, stop_at=target_dir.parent)

        return result

    def _verify(self, target_dir: Path) -> None:
        """Verify the Gemini install is usable, including persisted settings."""
        super()._verify(target_dir)

        if getattr(self, "_gemini_finalize_pending", False):
            return

        settings_path = target_dir / "settings.json"
        if not settings_path.exists():
            raise RuntimeError("Gemini install incomplete: settings.json was not written")

        settings = read_settings(settings_path)
        experimental = settings.get("experimental")
        if not isinstance(experimental, dict) or experimental.get("enableAgents") is not True:
            raise RuntimeError("Gemini install incomplete: experimental.enableAgents is not enabled")

        if self._installed_hook_script_available(HOOK_SCRIPTS["check_update"]):
            hooks = settings.get("hooks")
            session_start = hooks.get("SessionStart") if isinstance(hooks, dict) else None
            if not isinstance(session_start, list) or not any(
                _entry_has_gpd_hook(entry, target_dir=target_dir, config_dir_name=self.config_dir_name)
                for entry in session_start
            ):
                raise RuntimeError("Gemini install incomplete: update hook not configured")

        mcp_servers = settings.get("mcpServers")
        if not isinstance(mcp_servers, dict) or not mcp_servers:
            raise RuntimeError("Gemini install incomplete: MCP servers are not configured")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _entry_has_gpd_hook(
    entry: object,
    *,
    target_dir: Path | None,
    config_dir_name: str | None,
) -> bool:
    """Check if a hook entry contains the GPD-managed Gemini update hook."""
    if not isinstance(entry, dict):
        return False
    entry_hooks = entry.get("hooks")
    if not isinstance(entry_hooks, list):
        return False
    return any(
        isinstance(h, dict)
        and isinstance(h.get("command"), str)
        and _is_hook_command_for_script(
            h["command"],
            HOOK_SCRIPTS["check_update"],
            target_dir=target_dir,
            config_dir_name=config_dir_name,
        )
        for h in entry_hooks
    )


__all__ = ["GeminiAdapter"]
