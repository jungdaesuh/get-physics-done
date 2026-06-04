from __future__ import annotations

from gpd.core.public_surface_contract import (
    local_cli_bridge_commands,
)
from gpd.core.public_surface_contract import (
    local_cli_bridge_note as public_local_cli_bridge_note,
)
from gpd.core.public_surface_contract import (
    post_start_settings_note as public_post_start_settings_note,
)
from gpd.core.public_surface_contract import (
    post_start_settings_recommendation as public_post_start_settings_recommendation,
)
from gpd.core.public_surface_contract import (
    recovery_ladder_note as public_recovery_ladder_note,
)
from gpd.core.surface_phrases import (
    command_follow_up_action,
    cost_after_run_action,
    cost_after_runs_guidance,
    cost_inspect_action,
    cost_summary_surface_note,
    local_cli_bridge_note,
    observe_execution_action,
    observe_execution_surface_note,
    observe_tangent_routing_note,
    post_start_settings_note,
    post_start_settings_recommendation,
    recovery_action_lines,
    recovery_continue_action,
    recovery_continue_reason,
    recovery_fast_next_action,
    recovery_fast_next_reason,
    recovery_ladder_note,
    recovery_next_actions,
    recovery_primary_reason,
    recovery_recent_action,
    recovery_resume_action,
    tangent_branch_later_action,
    tangent_branch_later_follow_up_lines,
    tangent_chooser_action,
    workflow_preset_storage_note,
    workflow_preset_surface_note,
)
from tests.assertion_taxonomy_support import (
    FragmentMode,
    MatchMode,
    assert_prompt_contracts,
    machine_exact,
    semantic_anchor,
    semantic_concept,
)
from tests.doc_surface_contracts import assert_recovery_ladder_contract
from tests.runtime_test_support import PRIMARY_RUNTIME, runtime_resume_work_command


def _assert_machine_surface(
    text: str,
    label: str,
    fragments: str | tuple[str, ...],
    *,
    mode: FragmentMode = FragmentMode.ALL,
) -> None:
    assert_prompt_contracts(text, machine_exact(label, fragments, mode=mode, context=label))


def _assert_semantic_surface(
    text: str,
    label: str,
    fragments: str | tuple[str, ...],
    *,
    mode: FragmentMode = FragmentMode.ALL,
) -> None:
    assert_prompt_contracts(
        text,
        semantic_anchor(label, fragments, mode=mode, match=MatchMode.CASEFOLD_NORMALIZED, context=label),
    )


def _assert_semantic_concept(
    text: str,
    label: str,
    *,
    required: tuple[str, ...],
    forbidden: tuple[str, ...] = (),
) -> None:
    assert_prompt_contracts(text, *semantic_concept(label, required=required, forbidden=forbidden, context=label))


def test_cost_surface_phrases_stay_conservative_and_advisory() -> None:
    inspect_action = cost_inspect_action()
    _assert_machine_surface(inspect_action, "cost inspect command", "`gpd cost`")
    _assert_semantic_surface(
        inspect_action, "cost inspect advisory scope", ("local usage/cost summary", "USD budget warnings")
    )

    after_run_action = cost_after_run_action()
    _assert_machine_surface(after_run_action, "cost after-run command", "`gpd cost`")
    _assert_semantic_surface(
        after_run_action, "cost after-run advisory scope", ("after a run", "local usage/cost", "USD budget warnings")
    )

    after_runs_guidance = cost_after_runs_guidance()
    _assert_machine_surface(after_runs_guidance, "cost after-runs command", "`gpd cost`")
    _assert_semantic_surface(after_runs_guidance, "cost after-runs guardrails", ("budget guardrails", "billing truth"))

    summary_note = cost_summary_surface_note()
    _assert_semantic_surface(
        summary_note,
        "cost summary conservative scope",
        ("advisory only", "budget guardrails", "provider billing truth", "partial or estimated rather than exact"),
    )


def test_recovery_surface_phrases_cover_current_and_cross_project_paths() -> None:
    resume_action = recovery_resume_action()
    _assert_machine_surface(resume_action, "recovery current command", "`gpd resume`")
    _assert_semantic_surface(
        resume_action, "recovery current read-only snapshot", ("current-workspace", "read-only recovery snapshot")
    )

    recent_action = recovery_recent_action()
    _assert_machine_surface(recent_action, "recovery recent command", "`gpd resume --recent`")
    _assert_semantic_surface(
        recent_action, "recovery recent cross-workspace lookup", ("find the workspace first", "different one")
    )

    _assert_semantic_surface(
        recovery_primary_reason(
            mode="current-workspace",
            execution_resumable=True,
            has_interrupted_agent=False,
            has_live_execution=False,
            has_continuity_handoff=False,
            missing_continuity_handoff=False,
            machine_change_notice=None,
        ),
        "recovery current resumable reason",
        ("current workspace", "bounded resumable execution segment"),
    )
    _assert_semantic_surface(
        recovery_primary_reason(
            mode="recent-projects",
            forced_recent=False,
            execution_resumable=False,
            has_interrupted_agent=False,
            has_live_execution=False,
            has_continuity_handoff=False,
            missing_continuity_handoff=False,
            machine_change_notice=None,
        ),
        "recovery recent find reason",
        ("machine-local recent-project index", "find", "workspace", "reopen"),
    )
    _assert_semantic_surface(
        recovery_primary_reason(
            mode="recent-projects",
            forced_recent=True,
            execution_resumable=False,
            has_interrupted_agent=False,
            has_live_execution=False,
            has_continuity_handoff=False,
            missing_continuity_handoff=False,
            machine_change_notice=None,
        ),
        "recovery recent choose reason",
        ("machine-local recent-project index", "choose", "workspace", "reopen"),
    )

    continue_command = runtime_resume_work_command(PRIMARY_RUNTIME)
    current_continue_action = recovery_continue_action(
        mode="current-workspace",
        continue_command=continue_command,
    )
    _assert_machine_surface(current_continue_action, "recovery current continue command", f"`{continue_command}`")
    _assert_semantic_surface(
        current_continue_action,
        "recovery current continue selected state",
        ("continues in-runtime", "selected project state"),
    )

    _assert_semantic_surface(
        recovery_continue_reason(mode="current-workspace"),
        "recovery current continue reason",
        ("continue paused work", "current workspace"),
    )
    _assert_semantic_surface(
        recovery_continue_reason(mode="recent-projects"),
        "recovery recent continue reason",
        ("continue paused work", "selected workspace"),
    )

    recent_continue_action = recovery_continue_action(mode="recent-projects", continue_command="runtime `resume-work`")
    _assert_machine_surface(recent_continue_action, "recovery recent continue command", "runtime `resume-work`")
    _assert_semantic_surface(
        recent_continue_action,
        "recovery recent continue selected state",
        ("selecting a workspace", "continue", "selected project state"),
    )

    fast_next_action = recovery_fast_next_action(fast_next_command="/gpd:suggest-next")
    _assert_machine_surface(fast_next_action, "recovery fast-next command", "`/gpd:suggest-next`")
    _assert_semantic_surface(
        fast_next_action, "recovery fast-next guidance", ("fastest post-resume next command", "next action")
    )
    _assert_semantic_surface(
        recovery_fast_next_reason(),
        "recovery fast-next reason",
        ("fastest post-resume next command", "next action"),
    )

    ladder_note = recovery_ladder_note(
        resume_work_phrase="`/gpd:resume-work`",
        suggest_next_phrase="`/gpd:suggest-next`",
        pause_work_phrase="`/gpd:pause-work`",
    )
    assert ladder_note == public_recovery_ladder_note(
        resume_work_phrase="`/gpd:resume-work`",
        suggest_next_phrase="`/gpd:suggest-next`",
        pause_work_phrase="`/gpd:pause-work`",
    )
    assert_recovery_ladder_contract(
        ladder_note,
        resume_work_fragments=("`/gpd:resume-work`",),
        suggest_next_fragments=("`/gpd:suggest-next`",),
        pause_work_fragments=("`/gpd:pause-work`",),
    )


def test_recovery_next_actions_respect_local_target_gating_and_resume_dedup() -> None:
    assert recovery_next_actions(
        primary_command="gpd resume",
        mode="current-workspace",
        continue_command="runtime `resume-work`",
        fast_next_command="runtime `suggest-next`",
        existing_actions=[recovery_resume_action()],
    ) == [
        recovery_continue_action(mode="current-workspace", continue_command="runtime `resume-work`"),
        recovery_fast_next_action(fast_next_command="runtime `suggest-next`"),
    ]


def test_recovery_next_actions_keep_recent_projects_follow_ups() -> None:
    assert recovery_next_actions(
        primary_command="gpd resume --recent",
        mode="recent-projects",
        continue_command="runtime `resume-work`",
        fast_next_command="runtime `suggest-next`",
    ) == [
        recovery_recent_action(),
        recovery_continue_action(mode="recent-projects", continue_command="runtime `resume-work`"),
        recovery_fast_next_action(fast_next_command="runtime `suggest-next`"),
    ]


def test_recovery_action_lines_render_structured_actions_with_availability_filter() -> None:
    actions = [
        {"kind": "primary", "command": "gpd resume --recent", "availability": "now"},
        {"kind": "continue", "command": "runtime `resume-work`", "availability": "after_selection"},
        {"kind": "fast-next", "command": "runtime `suggest-next`", "availability": "after_selection"},
    ]

    assert recovery_action_lines(actions=actions, mode="recent-projects") == [
        recovery_recent_action(),
        recovery_continue_action(mode="recent-projects", continue_command="runtime `resume-work`"),
        recovery_fast_next_action(fast_next_command="runtime `suggest-next`"),
    ]
    assert recovery_action_lines(
        actions=actions,
        mode="recent-projects",
        allowed_availability={"now"},
    ) == [recovery_recent_action()]


def test_observe_surface_phrases_stay_read_only_and_route_follow_ups_explicitly() -> None:
    follow_up_action = command_follow_up_action(
        command="gpd observe show --last 20",
        reason="inspect the recent execution trail",
    )
    _assert_machine_surface(follow_up_action, "observe show follow-up command", "`gpd observe show --last 20`")
    _assert_semantic_surface(follow_up_action, "observe show follow-up reason", "inspect the recent execution trail")

    execution_action = observe_execution_action()
    _assert_machine_surface(execution_action, "observe execution command", "`gpd observe execution`")
    _assert_semantic_surface(
        execution_action, "observe execution read-only terminal", ("read-only long-run visibility", "normal terminal")
    )

    execution_note = observe_execution_surface_note()
    _assert_semantic_surface(
        execution_note,
        "observe execution conservative note",
        ("read-only long-run visibility", "progress / waiting state", "possibly stalled", "read-only checks"),
    )

    cli_tangent_note = observe_tangent_routing_note(
        tangent_phrase="/gpd:tangent",
        branch_phrase="/gpd:branch-hypothesis",
    )
    _assert_machine_surface(
        cli_tangent_note,
        "observe tangent CLI command order",
        ("`gpd observe execution`", "`/gpd:tangent`", "`/gpd:branch-hypothesis`"),
        mode=FragmentMode.ORDERED,
    )
    _assert_semantic_surface(
        cli_tangent_note,
        "observe tangent CLI routing",
        ("alternative-path follow-up", "branch later", "explicit choice"),
    )

    runtime_tangent_note = observe_tangent_routing_note(
        tangent_phrase="runtime `tangent`",
        branch_phrase="runtime `branch-hypothesis`",
    )
    _assert_machine_surface(
        runtime_tangent_note,
        "observe tangent runtime command order",
        ("`gpd observe execution`", "runtime `tangent`", "runtime `branch-hypothesis`"),
        mode=FragmentMode.ORDERED,
    )
    _assert_semantic_surface(
        runtime_tangent_note,
        "observe tangent runtime routing",
        ("alternative-path follow-up", "branch later", "explicit choice"),
    )

    chooser_action = tangent_chooser_action()
    _assert_machine_surface(chooser_action, "tangent chooser command", "`tangent`")
    _assert_semantic_surface(
        chooser_action,
        "tangent chooser options",
        ("main path", "bounded quick check", "capture and defer", "hypothesis branch"),
    )

    branch_later_action = tangent_branch_later_action()
    _assert_machine_surface(
        branch_later_action,
        "tangent branch-later default command order",
        ("runtime `tangent`", "runtime `branch-hypothesis`"),
        mode=FragmentMode.ORDERED,
    )
    _assert_semantic_surface(
        branch_later_action,
        "tangent branch-later default routing",
        ("bounded stop", "chooser explicit", "alternative path", "git-backed alternative path"),
    )

    follow_up_lines = tangent_branch_later_follow_up_lines()
    assert len(follow_up_lines) == 2
    _assert_machine_surface(follow_up_lines[0], "tangent follow-up default chooser command", "runtime `tangent`")
    _assert_semantic_surface(
        follow_up_lines[0], "tangent follow-up default chooser", ("chooser explicit", "alternative path")
    )
    _assert_machine_surface(
        follow_up_lines[1], "tangent follow-up default branch command", "runtime `branch-hypothesis`"
    )
    _assert_semantic_surface(
        follow_up_lines[1], "tangent follow-up default branch", ("git-backed alternative path", "bounded stop")
    )

    runtime_follow_up_lines = tangent_branch_later_follow_up_lines(
        tangent_phrase="runtime `tangent`",
        branch_phrase="runtime `branch-hypothesis`",
    )
    assert len(runtime_follow_up_lines) == 2
    _assert_machine_surface(
        runtime_follow_up_lines[0], "tangent follow-up runtime chooser command", "runtime `tangent`"
    )
    _assert_semantic_surface(
        runtime_follow_up_lines[0], "tangent follow-up runtime chooser", ("chooser explicit", "alternative path")
    )
    _assert_machine_surface(
        runtime_follow_up_lines[1], "tangent follow-up runtime branch command", "runtime `branch-hypothesis`"
    )
    _assert_semantic_surface(
        runtime_follow_up_lines[1], "tangent follow-up runtime branch", ("git-backed alternative path", "bounded stop")
    )

    runtime_branch_later_action = tangent_branch_later_action(
        tangent_phrase="runtime `tangent`",
        branch_phrase="runtime `branch-hypothesis`",
    )
    _assert_machine_surface(
        runtime_branch_later_action,
        "tangent branch-later runtime command order",
        ("runtime `tangent`", "runtime `branch-hypothesis`"),
        mode=FragmentMode.ORDERED,
    )
    _assert_semantic_surface(
        runtime_branch_later_action,
        "tangent branch-later runtime routing",
        ("bounded stop", "chooser explicit", "alternative path", "git-backed alternative path"),
    )


def test_preset_and_local_bridge_phrases_remain_command_oriented() -> None:
    _assert_semantic_concept(
        workflow_preset_storage_note(),
        "workflow preset storage boundary",
        required=("workflow presets", "existing config keys", "do not add", "separate persisted preset block"),
    )
    preset_note = workflow_preset_surface_note()
    for token in (
        "gpd presets list",
        "gpd presets show <preset>",
        "gpd presets apply <preset> --dry-run",
        "core-research",
        "theory",
        "numerics",
        "publication-manuscript",
        "full-research",
    ):
        _assert_machine_surface(preset_note, f"workflow preset token {token}", token)

    bridge_note = local_cli_bridge_note()
    assert bridge_note == public_local_cli_bridge_note()
    _assert_machine_surface(bridge_note, "local CLI bridge help command", "`gpd --help`")
    _assert_semantic_surface(bridge_note, "local CLI bridge scope", ("normal terminal", "broader local CLI surface"))
    _assert_machine_surface(
        bridge_note,
        "local CLI bridge excludes plan preflight",
        "gpd validate plan-preflight <PLAN.md>",
        mode=FragmentMode.ABSENT,
    )
    _assert_machine_surface(
        bridge_note,
        "local CLI bridge excludes permission sync",
        "gpd permissions sync --runtime <runtime> --autonomy <mode>",
        mode=FragmentMode.ABSENT,
    )

    bridge_inventory = local_cli_bridge_commands()
    for token in (
        "gpd --help",
        "gpd doctor",
        "gpd validate unattended-readiness --runtime <runtime> --autonomy <mode>",
        "gpd permissions status --runtime <runtime> --autonomy <mode>",
        "gpd permissions sync --runtime <runtime> --autonomy <mode>",
        "gpd resume",
        "gpd resume --recent",
        "gpd observe execution",
        "gpd cost",
        "gpd presets list",
        "gpd integrations status wolfram",
    ):
        _assert_machine_surface(bridge_inventory, f"local CLI bridge inventory {token}", token)

    settings_note = post_start_settings_note()
    assert settings_note == public_post_start_settings_note()
    _assert_machine_surface(settings_note, "post-start settings command", "runtime `settings`")
    _assert_semantic_surface(
        settings_note,
        "post-start settings review scope",
        (
            "first successful start",
            "autonomy",
            "workflow defaults",
            "model-cost posture",
            "runtime permission sync",
            "preset/tier overrides",
        ),
    )

    settings_recommendation = post_start_settings_recommendation()
    assert settings_recommendation == public_post_start_settings_recommendation()
    _assert_machine_surface(settings_recommendation, "post-start settings default profile", "`review`")
    _assert_semantic_surface(
        settings_recommendation,
        "post-start settings default posture",
        ("runtime defaults", "scientific rigor", "explicit uncertainty", "missing evidence", "artifacts explicit"),
    )
