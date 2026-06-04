from __future__ import annotations

import pytest

from gpd.core.command_run_hints import (
    KIND_RUNTIME_COMMAND_LABEL,
    NEXT_COMMAND_OWNER_DISPLAY_ONLY,
    NEXT_COMMAND_OWNER_LOCAL_FINALIZER,
    NEXT_COMMAND_OWNER_LOCAL_HELPER,
    NEXT_COMMAND_OWNER_LOCAL_READONLY,
    NEXT_COMMAND_OWNER_RUNTIME,
    NEXT_COMMAND_SURFACE_CONTEXT_ACTIVE_RUNTIME,
    NextCommand,
    classify_next_command,
)
from gpd.core.next_command_rendering import (
    NextCommandRenderingError,
    render_next_up_block,
    stage_stop_next_runtime_command,
)


def _assert_text_excludes(text: str, fragments: tuple[str, ...]) -> None:
    for fragment in fragments:
        assert fragment not in text


def _classified(command: str, *, action: str | None = None, phase: str | None = None) -> NextCommand:
    next_command = classify_next_command(command=command, action=action, phase=phase)
    assert next_command is not None
    return next_command


def test_runtime_primary_renders_shared_next_up_block_and_stage_stop_projection() -> None:
    primary = _classified("gpd:verify-work 02", action="verify-work", phase="02")

    rendered = render_next_up_block(primary=primary)

    assert rendered.markdown == "## > Next Up\nPrimary: `gpd:verify-work 02`"
    assert rendered.stage_stop_next_runtime_command == "gpd:verify-work 02"
    assert rendered.stage_stop_also_available == ()


@pytest.mark.parametrize(
    ("primary_command", "primary_action", "secondary_command", "secondary_action"),
    (
        ("gpd:discuss-phase 03", "discuss-phase", "gpd:plan-phase 03", "plan-phase"),
        ("gpd:plan-phase 03", "plan-phase", "gpd:discuss-phase 03", "discuss-phase"),
    ),
)
def test_closed_next_phase_runtime_routes_render_one_primary_without_raw_reload(
    primary_command: str,
    primary_action: str,
    secondary_command: str,
    secondary_action: str,
) -> None:
    primary = _classified(primary_command, action=primary_action, phase="03")
    secondary = (
        _classified(secondary_command, action=secondary_action, phase="03"),
        _classified("gpd:suggest-next", action="suggest-next"),
    )

    rendered = render_next_up_block(primary=primary, secondary=secondary)

    assert rendered.markdown.count("Primary:") == 1
    assert rendered.markdown.splitlines() == [
        "## > Next Up",
        f"Primary: `{primary_command}`",
        f"Secondary runtime: `{secondary_command}`",
        "Secondary runtime: `gpd:suggest-next`",
    ]
    _assert_text_excludes(rendered.markdown, ("gpd --raw init", "gpd --raw stage field-access"))
    assert rendered.stage_stop_next_runtime_command == primary_command
    assert rendered.stage_stop_also_available == (secondary_command, "gpd:suggest-next")


def test_local_transition_primary_renders_after_runtime_route_and_secondary_commands() -> None:
    primary = _classified("gpd phase complete 02", action="phase-complete", phase="02")
    after = _classified("gpd:plan-phase 03", action="plan-phase", phase="03")
    runtime_secondary = _classified("gpd:suggest-next", action="suggest-next")
    local_helper = _classified(
        "gpd --raw phase checkpoint cleanup --phase 02 --namespace phase --policy successful-closeout"
    )
    local_finalizer = _classified("gpd verification-report finalize --plan GPD/PLAN.md")
    display_only = NextCommand(
        label="Closeout evidence has already been checked.",
        action=None,
        owner=NEXT_COMMAND_OWNER_DISPLAY_ONLY,
        reason="Closeout evidence has already been checked.",
    )

    rendered = render_next_up_block(
        primary=primary,
        after_this_completes=after,
        secondary=(runtime_secondary, local_helper, local_finalizer, display_only),
    )

    assert rendered.markdown.splitlines() == [
        "## > Next Up",
        "Primary local transition: `gpd phase complete 02`",
        "**After this completes:** `gpd:plan-phase 03`",
        "Secondary runtime: `gpd:suggest-next`",
        (
            "Secondary local helper: "
            "`gpd --raw phase checkpoint cleanup --phase 02 --namespace phase --policy successful-closeout`"
        ),
        "Secondary local finalizer: `gpd verification-report finalize --plan GPD/PLAN.md`",
        "Note: Closeout evidence has already been checked.",
    ]
    assert rendered.stage_stop_next_runtime_command == "gpd:plan-phase 03"
    assert rendered.stage_stop_also_available == ("gpd:suggest-next",)


def test_local_transition_primary_requires_after_runtime_route() -> None:
    primary = _classified("gpd phase complete 02", action="phase-complete", phase="02")

    with pytest.raises(NextCommandRenderingError, match="after_this_completes"):
        render_next_up_block(primary=primary)


def test_local_helpers_and_finalizers_are_not_stage_stop_next_runtime_commands() -> None:
    local_readonly = _classified("gpd phase closeout-readiness 02 --require-verification")
    local_helper = _classified(
        "gpd --raw phase checkpoint cleanup --phase 02 --namespace phase --policy successful-closeout"
    )
    local_finalizer = _classified("gpd verification-report finalize --plan GPD/PLAN.md")

    assert local_readonly.owner == NEXT_COMMAND_OWNER_LOCAL_READONLY
    assert local_helper.owner == NEXT_COMMAND_OWNER_LOCAL_HELPER
    assert local_finalizer.owner == NEXT_COMMAND_OWNER_LOCAL_FINALIZER
    assert stage_stop_next_runtime_command(local_readonly) is None
    assert stage_stop_next_runtime_command(local_helper) is None
    assert stage_stop_next_runtime_command(local_finalizer) is None


def test_shared_next_up_avoids_display_only_command_leaks_in_secondaries() -> None:
    primary = _classified("gpd:resume-work", action="resume-work")
    display_only_commands = tuple(
        _classified(command, action="verify-work", phase="02")
        for command in (
            "gpd --raw init new-project",
            "gpd --raw stage field-access --stage closeout --field next_up",
            "gpd:verify-work 02 && echo unsafe",
            "gpd verify phase 02",
            "gpd-verify-work 02",
        )
    )

    rendered = render_next_up_block(primary=primary, secondary=display_only_commands)

    assert rendered.markdown == "## > Next Up\nPrimary: `gpd:resume-work`"
    _assert_text_excludes(
        rendered.markdown,
        ("gpd --raw init", "gpd --raw stage field-access", "&&", "gpd verify phase", "gpd-verify-work"),
    )


def test_forbidden_display_only_primary_is_rejected() -> None:
    primary = _classified("gpd --raw init new-project")

    with pytest.raises(NextCommandRenderingError, match="unsupported primary"):
        render_next_up_block(primary=primary)


def test_raw_loader_label_is_rejected_even_with_misleading_runtime_owner() -> None:
    primary = NextCommand(
        label="gpd --raw init verify-work 02 --stage session_router",
        action="verify-work",
        owner=NEXT_COMMAND_OWNER_RUNTIME,
        phase="02",
        kind=KIND_RUNTIME_COMMAND_LABEL,
    )

    with pytest.raises(NextCommandRenderingError, match="forbidden command fragment"):
        render_next_up_block(primary=primary)


def test_bridge_prefixed_raw_loader_label_is_rejected_even_with_misleading_runtime_owner() -> None:
    primary = NextCommand(
        label=(
            "/runtime/python -m gpd.runtime_cli --runtime codex --config-dir /tmp/.codex "
            "--install-scope local --raw init verify-work 02 --stage session_router"
        ),
        action="verify-work",
        owner=NEXT_COMMAND_OWNER_RUNTIME,
        phase="02",
        kind=KIND_RUNTIME_COMMAND_LABEL,
    )

    with pytest.raises(NextCommandRenderingError, match="forbidden command fragment"):
        render_next_up_block(primary=primary)


def test_bare_gpd_skill_prefix_can_render_when_active_runtime_classified_it() -> None:
    primary = classify_next_command(
        command="gpd-verify-work 02",
        action="verify-work",
        phase="02",
        surface_context=NEXT_COMMAND_SURFACE_CONTEXT_ACTIVE_RUNTIME,
        active_runtime_public_prefix="gpd-",
    )
    assert primary is not None
    assert primary.owner == NEXT_COMMAND_OWNER_RUNTIME

    rendered = render_next_up_block(primary=primary)

    assert rendered.markdown == "## > Next Up\nPrimary: `gpd-verify-work 02`"
    assert rendered.stage_stop_next_runtime_command == "gpd-verify-work 02"
