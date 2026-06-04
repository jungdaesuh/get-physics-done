"""Behavior-focused adapter assertions."""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from gpd.adapters.install_utils import build_runtime_managed_mcp_servers, runtime_managed_mcp_server_keys
from gpd.core.public_surface_contract import local_cli_bridge_commands
from gpd.mcp.builtin_servers import GPD_MCP_SERVER_KEYS


def test_write_settings_errors_reference_the_directory(tmp_path: Path) -> None:
    from gpd.adapters.install_utils import write_settings

    settings_path = tmp_path / "settings.json"

    with patch("pathlib.Path.write_text", side_effect=PermissionError("denied")):
        with pytest.raises(PermissionError, match=re.escape(str(tmp_path))):
            write_settings(settings_path, {"key": "value"})


def test_write_settings_mkdir_errors_reference_settings_directory(tmp_path: Path) -> None:
    from gpd.adapters.install_utils import write_settings

    settings_path = tmp_path / "deep" / "nested" / "settings.json"

    with patch("pathlib.Path.mkdir", side_effect=PermissionError("denied")):
        with pytest.raises(PermissionError, match="settings directory"):
            write_settings(settings_path, {"key": "value"})


def test_copy_with_path_replacement_rejects_unknown_runtime_without_partial_dest(tmp_path: Path) -> None:
    from gpd.adapters.install_utils import copy_with_path_replacement

    src = tmp_path / "src"
    src.mkdir()
    (src / "probe.md").write_text("Path: {GPD_INSTALL_DIR}\n", encoding="utf-8")
    dest = tmp_path / "dest"

    with pytest.raises(KeyError, match=r"Unknown runtime 'not-a-runtime'"):
        copy_with_path_replacement(src, dest, "/runtime/", "not-a-runtime")

    assert not dest.exists()
    assert not list(tmp_path.glob("dest.tmp.*"))


def test_convert_tool_references_uses_literal_replacements() -> None:
    from gpd.adapters.install_utils import convert_tool_references_in_body

    assert "todo_write" in convert_tool_references_in_body(
        "Use TodoWrite to record tasks.",
        {"TodoWrite": "todo_write"},
    )
    assert "new\\1tool" in convert_tool_references_in_body(
        "Use OldTool to do things.",
        {"OldTool": "new\\1tool"},
    )


def test_codex_install_restores_skills_dir_after_failure(gpd_root: Path, tmp_path: Path) -> None:
    from gpd.adapters.codex import CodexAdapter

    adapter = CodexAdapter()
    sentinel = Path("/original/skills/dir")
    adapter._skills_dir = sentinel

    target = tmp_path / ".codex"
    target.mkdir()

    with patch.object(
        CodexAdapter.__bases__[0],
        "install",
        side_effect=RuntimeError("simulated install failure"),
    ):
        with pytest.raises(RuntimeError, match="simulated install failure"):
            adapter.install(gpd_root, target, is_global=False, skills_dir=tmp_path / "new-skills")

    assert adapter._skills_dir == sentinel


def test_codex_install_restores_skills_dir_after_success(gpd_root: Path, tmp_path: Path) -> None:
    from gpd.adapters.codex import CodexAdapter

    adapter = CodexAdapter()
    sentinel = Path("/original/skills/dir")
    adapter._skills_dir = sentinel

    target = tmp_path / ".codex"
    target.mkdir()
    fake_result = {"runtime": "codex", "target": str(target), "commands": 0, "agents": 0}

    with patch.object(CodexAdapter.__bases__[0], "install", return_value=fake_result):
        result = adapter.install(gpd_root, target, is_global=False, skills_dir=tmp_path / "new-skills")

    assert result == fake_result
    assert adapter._skills_dir == sentinel


def test_configure_opencode_permissions_fails_closed_for_non_dict_json(tmp_path: Path) -> None:
    from gpd.adapters.opencode import configure_opencode_permissions

    config_dir = tmp_path / "opencode"
    config_dir.mkdir()
    (config_dir / "opencode.json").write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    before = (config_dir / "opencode.json").read_text(encoding="utf-8")

    with pytest.raises(RuntimeError, match="malformed"):
        configure_opencode_permissions(config_dir)

    assert (config_dir / "opencode.json").read_text(encoding="utf-8") == before


def test_write_mcp_servers_opencode_fails_closed_for_non_dict_mcp_key(tmp_path: Path) -> None:
    from gpd.adapters.opencode import _write_mcp_servers_opencode

    config_dir = tmp_path / "opencode"
    config_dir.mkdir()
    (config_dir / "opencode.json").write_text(json.dumps({"mcp": "not a dict"}), encoding="utf-8")
    before = (config_dir / "opencode.json").read_text(encoding="utf-8")

    with pytest.raises(RuntimeError, match="malformed"):
        _write_mcp_servers_opencode(
            config_dir,
            {
                "gpd-errors": {
                    "command": "python",
                    "args": ["-m", "gpd.mcp.servers.errors_mcp"],
                }
            },
        )

    assert (config_dir / "opencode.json").read_text(encoding="utf-8") == before


def test_runtime_managed_mcp_projection_helper_hides_api_key_and_preserves_endpoint() -> None:
    env = {
        "GPD_WOLFRAM_MCP_API_KEY": "super-secret-token",
        "GPD_WOLFRAM_MCP_ENDPOINT": "https://example.invalid/api/mcp",
    }

    servers = build_runtime_managed_mcp_servers(
        env=env,
        python_path="/tmp/gpd-managed-python",
        include_builtin=False,
    )
    wolfram = servers["gpd-wolfram"]
    payload = json.dumps(wolfram)

    assert wolfram["command"] == "/tmp/gpd-managed-python"
    assert wolfram["args"] == ["-m", "gpd.mcp.integrations.wolfram_bridge"]
    assert "super-secret-token" not in payload
    assert "GPD_WOLFRAM_MCP_API_KEY" not in payload
    assert "https://example.invalid/api/mcp" in payload


@pytest.mark.parametrize(
    ("include_builtin", "expected_keys"),
    [
        (False, frozenset({"gpd-wolfram"})),
        (True, frozenset({*GPD_MCP_SERVER_KEYS, "gpd-wolfram"})),
    ],
)
def test_runtime_managed_mcp_key_helper_includes_registry_backed_optional_keys(
    include_builtin: bool,
    expected_keys: frozenset[str],
) -> None:
    keys = runtime_managed_mcp_server_keys(include_builtin=include_builtin)

    assert keys == expected_keys


@pytest.mark.parametrize(
    ("module_name", "function_name"),
    [
        ("gpd.adapters.claude_code", "_rewrite_gpd_cli_invocations"),
        ("gpd.adapters.codex", "_rewrite_codex_gpd_cli_invocations"),
        ("gpd.adapters.gemini", "_rewrite_gpd_cli_invocations"),
        ("gpd.adapters.opencode", "_rewrite_gpd_cli_invocations"),
    ],
)
@pytest.mark.parametrize(
    ("shell_line", "expected_fragment"),
    [
        ("gpd; echo ok\n", "/runtime/gpd; echo ok"),
        ("echo $(gpd)\n", "echo $(/runtime/gpd)"),
        ("gpd>out.log\n", "/runtime/gpd>out.log"),
    ],
)
def test_runtime_shell_rewriters_handle_metacharacter_terminated_gpd_commands(
    module_name: str,
    function_name: str,
    shell_line: str,
    expected_fragment: str,
) -> None:
    module = importlib.import_module(module_name)
    rewrite = getattr(module, function_name)

    result = rewrite(f"```bash\n{shell_line}```\n", "/runtime/gpd")

    assert expected_fragment in result


def test_shared_runtime_shell_rewriter_handles_fenced_command_positions() -> None:
    from gpd.adapters.install_utils import rewrite_gpd_cli_invocations_to_runtime_bridge

    content = "Prose keeps `gpd status` unchanged.\n```bash\ngpd status\necho 'gpd status'\necho $(gpd status)\n```\n"

    result = rewrite_gpd_cli_invocations_to_runtime_bridge(content, "/runtime/gpd")

    assert "Prose keeps `gpd status` unchanged." in result
    assert "/runtime/gpd status" in result
    assert "echo 'gpd status'" in result
    assert "echo $(/runtime/gpd status)" in result


def test_command_projection_shell_bridge_wrapper_uses_shared_rewriter() -> None:
    from gpd.adapters.command_projection import rewrite_projection_shell_bridge

    content = "```bash\ngpd status\n```\n```python\ngpd status\n```\n"

    result = rewrite_projection_shell_bridge(content, "/runtime/gpd")

    assert "```bash\n/runtime/gpd status\n```" in result
    assert "```python\ngpd status\n```" in result


def test_command_projection_note_prepend_preserves_frontmatter_and_replaces_old_note() -> None:
    from gpd.adapters.command_projection import prepend_projection_note

    old_note_re = re.compile(r"<runtime_note>\n.*?</runtime_note>\n*", re.DOTALL)
    content = "---\nname: probe\n---\n<runtime_note>\nold\n</runtime_note>\n\nBody\n"
    note = "<runtime_note>\nnew\n</runtime_note>\n\n"

    result = prepend_projection_note(content, note, strip_patterns=(old_note_re,))
    second = prepend_projection_note(result, note, strip_patterns=(old_note_re,))

    assert result == second
    assert result.startswith("---\nname: probe\n---\n<runtime_note>\nnew\n</runtime_note>\n\nBody\n")
    assert "old" not in result


def test_shared_runtime_shell_rewriter_handles_double_quoted_command_substitutions() -> None:
    from gpd.adapters.install_utils import rewrite_gpd_cli_invocations_to_runtime_bridge

    content = (
        "```bash\n"
        'if [ "$(echo "$ROADMAP_INFO" | gpd json get .found --default false)" != "true" ]; then\n'
        "  echo \"$(printf 'gpd status')\"\n"
        "fi\n"
        "```\n"
    )

    result = rewrite_gpd_cli_invocations_to_runtime_bridge(content, "/runtime/gpd")

    assert 'if [ "$(echo "$ROADMAP_INFO" | /runtime/gpd json get .found --default false)" != "true" ]; then' in result
    assert "echo \"$(printf 'gpd status')\"" in result


def test_shared_runtime_shell_rewriter_handles_reserved_word_command_positions() -> None:
    from gpd.adapters.install_utils import rewrite_gpd_cli_invocations_to_runtime_bridge

    content = (
        "```bash\n"
        "if gpd status; then\n"
        "  while gpd config ensure-section; do\n"
        "    time gpd state add-decision\n"
        "    { gpd graph; }\n"
        "  done\n"
        "fi\n"
        "```\n"
    )

    result = rewrite_gpd_cli_invocations_to_runtime_bridge(content, "/runtime/gpd")

    assert "if /runtime/gpd status; then" in result
    assert "while /runtime/gpd config ensure-section; do" in result
    assert "time /runtime/gpd state add-decision" in result
    assert "{ /runtime/gpd graph; }" in result


@pytest.mark.parametrize(
    ("module_name", "function_name"),
    [
        ("gpd.adapters.claude_code", "_rewrite_gpd_cli_invocations"),
        ("gpd.adapters.codex", "_rewrite_codex_gpd_cli_invocations"),
        ("gpd.adapters.gemini", "_rewrite_gpd_cli_invocations"),
        ("gpd.adapters.opencode", "_rewrite_gpd_cli_invocations"),
    ],
)
def test_runtime_rewriters_preserve_public_local_cli_contract(module_name: str, function_name: str) -> None:
    module = importlib.import_module(module_name)
    rewrite = getattr(module, function_name)

    public_commands = local_cli_bridge_commands()
    content = (
        "Use `gpd --help` before anything else.\n"
        "Keep `gpd config ensure-section` bridged because it is an executable shell step.\n"
        "```bash\n" + "\n".join([*public_commands, "gpd config ensure-section"]) + "\n```\n"
    )

    result = rewrite(content, "/runtime/gpd")

    assert "`gpd --help`" in result
    assert "`gpd config ensure-section`" in result
    for command in public_commands:
        assert command in result
        assert f"/runtime/gpd{command[3:]}" not in result
    assert "/runtime/gpd config ensure-section" in result
