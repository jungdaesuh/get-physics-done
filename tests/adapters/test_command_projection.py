"""Shared command projection rendering tests."""

from gpd.adapters.command_projection import render_projected_command_shell_fences

BRIDGE = "/runtime/python -m gpd.runtime_cli --runtime codex --config-dir /tmp/.codex --install-scope local"


def test_shared_command_shell_renderer_bridges_direct_gpd_calls_only() -> None:
    source = (
        "Inline `gpd status` stays prose.\n"
        "\n"
        "```bash\n"
        "gpd status\n"
        "```\n"
        "\n"
        "```bash\n"
        "git status --porcelain\n"
        "```\n"
        "\n"
        "```bash\n"
        "if [ -d GPD ]; then\n"
        "  gpd status\n"
        "fi\n"
        "```\n"
        "\n"
        "```bash\n"
        "gpd set-profile <profile>\n"
        "```\n"
        "\n"
        "```bash\n"
        "# comment only\n"
        "```\n"
    )

    rendered = render_projected_command_shell_fences(source, bridge_command=BRIDGE)

    assert f"```bash\n{BRIDGE} status\n```" in rendered
    assert "Inline `gpd status` stays prose." in rendered
    assert "```bash\ngit status --porcelain\n```" not in rendered
    assert "```text\ngit status --porcelain\n```" in rendered
    assert "```bash\nif [ -d GPD ]; then" not in rendered
    assert "```text\nif [ -d GPD ]; then" in rendered
    assert "```bash\ngpd set-profile <profile>\n```" not in rendered
    assert "```text\ngpd set-profile <profile>\n```" in rendered
    assert "```text\n# comment only\n```" in rendered


def test_shared_command_shell_renderer_keeps_direct_argument_token_commands() -> None:
    source = (
        "```bash\n"
        'gpd --raw init plan-phase "$ARGUMENTS" --stage phase_bootstrap\n'
        "```\n"
        "\n"
        "```bash\n"
        "gpd set-profile <profile>\n"
        "```\n"
    )

    rendered = render_projected_command_shell_fences(source, bridge_command=BRIDGE)

    assert f'```bash\n{BRIDGE} --raw init plan-phase "$ARGUMENTS" --stage phase_bootstrap\n```' in rendered
    assert "```text\ngpd set-profile <profile>\n```" in rendered


def test_shared_command_shell_renderer_downgrades_variable_and_stdin_shell_shapes() -> None:
    source = (
        "```bash\n"
        "INIT=$(gpd --raw init progress --include state,config)\n"
        'echo "$INIT"\n'
        "```\n"
        "\n"
        "```bash\n"
        "printf '%s\\n' \"$PROJECT_CONTRACT_JSON\" | gpd --raw validate project-contract - --mode approved\n"
        "```\n"
    )

    rendered = render_projected_command_shell_fences(source, bridge_command=BRIDGE)

    assert "```bash\n" not in rendered
    assert f"```text\nINIT=$({BRIDGE} --raw init progress --include state,config)" in rendered
    assert "INIT=$(gpd --raw init progress --include state,config)" not in rendered
    assert "```text\nprintf '%s\\n' \"$PROJECT_CONTRACT_JSON\" | gpd --raw validate project-contract" in rendered
    assert rendered.count(BRIDGE) == 1


def test_shared_command_shell_renderer_bridges_context_capture_before_text_downgrade() -> None:
    source = (
        "```bash\n"
        "CONTEXT=$(gpd --raw init progress --include state,config 2>&1)\n"
        "printf '%s\\n' \"$CONTEXT\"\n"
        "```\n"
    )

    rendered = render_projected_command_shell_fences(source, bridge_command=BRIDGE)

    assert "```bash\n" not in rendered
    assert f"```text\nCONTEXT=$({BRIDGE} --raw init progress --include state,config 2>&1)" in rendered
    assert "CONTEXT=$(gpd --raw init progress --include state,config 2>&1)" not in rendered


def test_shared_command_shell_renderer_is_idempotent() -> None:
    source = "```bash\ngpd --raw init progress --include state,config\n```\n\n```bash\ngit status --porcelain\n```\n"

    once = render_projected_command_shell_fences(source, bridge_command=BRIDGE)
    twice = render_projected_command_shell_fences(once, bridge_command=BRIDGE)

    assert once == twice
    assert once.count(BRIDGE) == 1
