"""Upgrade migration contract for the removed built-in MCP servers.

Installing or upgrading over a config written by a pre-removal GPD release must
delete exactly the legacy ``gpd-*`` entries and preserve every user-defined
server byte-for-byte. This is the one path that decides whether real users end
up with orphaned server processes after upgrading.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from gpd.adapters.claude_code import ClaudeCodeAdapter
from gpd.adapters.codex import CodexAdapter
from gpd.adapters.gemini import GeminiAdapter
from gpd.adapters.opencode import OpenCodeAdapter
from gpd.mcp.builtin_servers import GPD_MCP_SERVER_KEYS
from tests.runtime_install_helpers import legacy_builtin_mcp_server_entries

USER_SERVER_KEY = "acme-internal-tools"
USER_SERVER_ENTRY: dict[str, object] = {
    "command": "node",
    "args": ["/opt/acme/mcp-server.js", "--profile", "prod"],
    "env": {"ACME_TOKEN_FILE": "/etc/acme/token"},
    "cwd": "/opt/acme",
    "type": "stdio",
}


def _seeded_mcp_servers() -> dict[str, object]:
    return {**legacy_builtin_mcp_server_entries(), USER_SERVER_KEY: dict(USER_SERVER_ENTRY)}


def test_claude_code_install_scrubs_every_legacy_key_and_keeps_the_user_server(
    gpd_root: Path,
    tmp_path: Path,
) -> None:
    target = tmp_path / "workspace" / ".claude"
    target.mkdir(parents=True)
    mcp_config = target.parent / ".mcp.json"
    seeded = _seeded_mcp_servers()
    mcp_config.write_text(json.dumps({"mcpServers": seeded}, indent=2) + "\n", encoding="utf-8")

    assert set(seeded) == GPD_MCP_SERVER_KEYS | {USER_SERVER_KEY}

    ClaudeCodeAdapter().install(gpd_root, target)

    cleaned = json.loads(mcp_config.read_text(encoding="utf-8"))["mcpServers"]
    assert set(cleaned) == {USER_SERVER_KEY}
    assert cleaned[USER_SERVER_KEY] == USER_SERVER_ENTRY


def test_codex_install_scrubs_every_legacy_section_and_keeps_the_user_server(
    gpd_root: Path,
    tmp_path: Path,
) -> None:
    target = tmp_path / ".codex"
    target.mkdir()
    skills = tmp_path / "skills"
    skills.mkdir()
    config_toml = target / "config.toml"
    legacy_sections = "".join(
        f"[mcp_servers.{key}]\ncommand = \"python3\"\nargs = [\"-m\", \"gpd.mcp.servers.stub\"]\n\n"
        f"[mcp_servers.{key}.env]\nLOG_LEVEL = \"WARNING\"\n\n"
        for key in sorted(GPD_MCP_SERVER_KEYS)
    )
    config_toml.write_text(
        legacy_sections
        + f"[mcp_servers.{USER_SERVER_KEY}]\n"
        + 'command = "node"\n'
        + 'args = ["/opt/acme/mcp-server.js", "--profile", "prod"]\n'
        + 'cwd = "/opt/acme"\n\n'
        + f"[mcp_servers.{USER_SERVER_KEY}.env]\n"
        + 'ACME_TOKEN_FILE = "/etc/acme/token"\n',
        encoding="utf-8",
    )

    CodexAdapter().install(gpd_root, target, skills_dir=skills)

    cleaned = tomllib.loads(config_toml.read_text(encoding="utf-8"))["mcp_servers"]
    assert set(cleaned) == {USER_SERVER_KEY}
    assert cleaned[USER_SERVER_KEY] == {
        "command": "node",
        "args": ["/opt/acme/mcp-server.js", "--profile", "prod"],
        "cwd": "/opt/acme",
        "env": {"ACME_TOKEN_FILE": "/etc/acme/token"},
    }


def test_gemini_install_scrubs_every_legacy_key_and_keeps_the_user_server(
    gpd_root: Path,
    tmp_path: Path,
) -> None:
    target = tmp_path / ".gemini"
    target.mkdir()
    settings_path = target / "settings.json"
    settings_path.write_text(json.dumps({"mcpServers": _seeded_mcp_servers()}, indent=2) + "\n", encoding="utf-8")

    adapter = GeminiAdapter()
    adapter.finalize_install(adapter.install(gpd_root, target))

    cleaned = json.loads(settings_path.read_text(encoding="utf-8"))["mcpServers"]
    assert set(cleaned) == {USER_SERVER_KEY}
    assert cleaned[USER_SERVER_KEY] == USER_SERVER_ENTRY


def test_opencode_install_scrubs_every_legacy_key_and_keeps_the_user_server(
    gpd_root: Path,
    tmp_path: Path,
) -> None:
    target = tmp_path / ".opencode"
    target.mkdir()
    config_path = target / "opencode.json"
    user_entry = {"type": "local", "command": ["node", "/opt/acme/mcp-server.js"], "enabled": True}
    legacy = {
        key: {"type": "local", "command": ["python3", "-m", "gpd.mcp.servers.stub"], "enabled": True}
        for key in sorted(GPD_MCP_SERVER_KEYS)
    }
    config_path.write_text(
        json.dumps({"mcp": {**legacy, USER_SERVER_KEY: user_entry}}, indent=2) + "\n",
        encoding="utf-8",
    )

    OpenCodeAdapter().install(gpd_root, target)

    cleaned = json.loads(config_path.read_text(encoding="utf-8"))["mcp"]
    assert set(cleaned) == {USER_SERVER_KEY}
    assert cleaned[USER_SERVER_KEY] == user_entry


def test_uninstall_reaches_every_legacy_key_after_a_clean_install(gpd_root: Path, tmp_path: Path) -> None:
    """A user who installs the new release and then uninstalls keeps their own server."""
    target = tmp_path / "workspace" / ".claude"
    target.mkdir(parents=True)
    mcp_config = target.parent / ".mcp.json"

    adapter = ClaudeCodeAdapter()
    adapter.install(gpd_root, target)
    mcp_config.write_text(json.dumps({"mcpServers": _seeded_mcp_servers()}, indent=2) + "\n", encoding="utf-8")

    adapter.uninstall(target)

    cleaned = json.loads(mcp_config.read_text(encoding="utf-8"))["mcpServers"]
    assert set(cleaned) == {USER_SERVER_KEY}
    assert cleaned[USER_SERVER_KEY] == USER_SERVER_ENTRY
