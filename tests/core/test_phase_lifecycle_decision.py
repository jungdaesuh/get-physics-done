"""Read-only phase lifecycle decision helper tests."""

from __future__ import annotations

import json
from pathlib import Path

from gpd.core.phase_closeout import phase_closeout_readiness
from gpd.core.phase_lifecycle import phase_lifecycle_decision
from gpd.core.state import default_state_dict

_FORBIDDEN_NEXT_UP_RELOAD_FRAGMENTS = (
    "gpd --raw init",
    "--raw init",
    "gpd --raw stage field-access",
    "--raw stage field-access",
)


def _command_text(command: object | None) -> str | None:
    if command is None:
        return None
    return command.command


def _command_texts(commands: object) -> tuple[str, ...]:
    return tuple(command.command for command in commands)


def _assert_route(
    route: object,
    *,
    status_class: str,
    transition_owner: str,
    current_blocking_gate: str | None,
    primary_runtime_command: str | None,
    local_transition_command: str | None,
    after_local_runtime_command: str | None,
    secondary_runtime_commands: tuple[str, ...] = (),
    secondary_local_commands: tuple[str, ...] = (),
    next_phase_context_class: str | None = None,
) -> None:
    assert route.status_class == status_class
    assert route.transition_owner == transition_owner
    assert route.current_blocking_gate == current_blocking_gate
    assert _command_text(route.primary_runtime_command) == primary_runtime_command
    assert _command_text(route.local_transition_command) == local_transition_command
    assert _command_text(route.after_local_runtime_command) == after_local_runtime_command
    assert _command_texts(route.secondary_runtime_commands) == secondary_runtime_commands
    assert _command_texts(route.secondary_local_commands) == secondary_local_commands
    if next_phase_context_class is not None:
        assert route.next_phase_context_class == next_phase_context_class


def _assert_legacy_projection(payload: dict[str, object], route: object) -> None:
    assert payload == route.to_legacy_payload()


def _write_phase_project(
    root: Path,
    *,
    summaries: tuple[str, ...] = ("02-01-SUMMARY.md", "02-02-SUMMARY.md"),
    verification_status: str | None = "passed",
    proof_bearing: bool = False,
    recovery: bool = False,
    bounded_segment: bool = False,
    state_current_phase: str | None = "02",
    state_status: str | None = "Verified",
    roadmap_closed: bool = False,
) -> Path:
    gpd_dir = root / "GPD"
    phase_dir = gpd_dir / "phases" / "02-analysis"
    phase_dir.mkdir(parents=True)
    (gpd_dir / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
    marker = "x" if roadmap_closed else " "
    (gpd_dir / "ROADMAP.md").write_text(
        "# Roadmap\n\n"
        f"- [{marker}] Phase 2: Analysis\n"
        "- [ ] Phase 3: Synthesis\n\n"
        "## Phase 2: Analysis\n\n"
        "## Phase 3: Synthesis\n",
        encoding="utf-8",
    )
    for index in range(1, 3):
        proof_flag = "proof_bearing: true\n" if proof_bearing and index == 1 else ""
        (phase_dir / f"02-{index:02d}-PLAN.md").write_text(
            f"---\nwave: {index}\n{proof_flag}---\n\n# Plan {index}\n",
            encoding="utf-8",
        )
    for summary_name in summaries:
        (phase_dir / summary_name).write_text(f"# {summary_name}\n", encoding="utf-8")
    if verification_status is not None:
        (phase_dir / "02-VERIFICATION.md").write_text(
            f"---\nstatus: {verification_status}\nscore: lifecycle test\n---\n\n# Verification\n",
            encoding="utf-8",
        )
    if recovery:
        (phase_dir / "RECOVERY-02.md").write_text("# Recovery\n", encoding="utf-8")

    state = default_state_dict()
    state["position"]["current_phase"] = state_current_phase
    state["position"]["current_phase_name"] = "Analysis" if state_current_phase == "02" else "Synthesis"
    state["position"]["current_plan"] = "02" if state_current_phase == "02" else None
    state["position"]["total_plans_in_phase"] = 2 if state_current_phase == "02" else None
    state["position"]["status"] = state_status
    if bounded_segment:
        state["continuation"]["bounded_segment"] = {
            "resume_file": "GPD/phases/02-analysis/.continue-here.md",
            "phase": "02",
            "plan": "02",
            "segment_id": "seg-02-02",
            "segment_status": "paused",
        }
    (gpd_dir / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return phase_dir


def _write_next_phase_context(root: Path) -> None:
    phase_dir = root / "GPD" / "phases" / "03-synthesis"
    phase_dir.mkdir(parents=True)
    (phase_dir / "03-CONTEXT.md").write_text("# Phase 3 Context\n", encoding="utf-8")
    (phase_dir / "03-RESEARCH.md").write_text("# Phase 3 Research\n", encoding="utf-8")
    (phase_dir / "03-01-PLAN.md").write_text("---\nwave: 1\n---\n\n# Plan\n", encoding="utf-8")


_ROADMAP_ONLY_FORBIDDEN_NEXT_PHASE_COMMANDS = frozenset(("gpd:discuss-phase 03", "gpd:plan-phase 03"))


def _assert_not_next_phase_route(decision: object) -> None:
    assert decision.roadmap_complete is True
    assert decision.phase_closed is False
    assert decision.decision != "closed_ready_next_phase"
    assert decision.lifecycle_class != "closed_ready_next_phase"
    assert decision.next_phase == "03"
    assert decision.primary_command not in _ROADMAP_ONLY_FORBIDDEN_NEXT_PHASE_COMMANDS
    route = decision.lifecycle_next_up
    assert route is not None
    assert route.status == "blocked"
    assert route.primary.command not in _ROADMAP_ONLY_FORBIDDEN_NEXT_PHASE_COMMANDS


def test_lifecycle_decision_ready_closeout_matches_closeout_readiness_and_stays_read_only(tmp_path: Path) -> None:
    _write_phase_project(tmp_path)
    before_roadmap = (tmp_path / "GPD" / "ROADMAP.md").read_text(encoding="utf-8")
    before_state = (tmp_path / "GPD" / "state.json").read_text(encoding="utf-8")

    decision = phase_lifecycle_decision(tmp_path, "2")
    closeout = phase_closeout_readiness(tmp_path, "02", require_verification=True)

    assert decision.decision == "ready_for_closeout"
    assert decision.primary_command == "gpd phase complete 02"
    assert decision.primary_owner == "local_transition"
    assert decision.closeout_readiness == closeout
    assert decision.lifecycle_class == "ready_for_local_closeout"
    route = decision.lifecycle_next_up
    closeout_route = closeout.lifecycle_next_up
    assert route is not None
    assert closeout_route is not None
    _assert_route(
        route,
        status_class="ready_for_local_closeout",
        transition_owner="local_transition",
        current_blocking_gate="none",
        primary_runtime_command="gpd:suggest-next",
        local_transition_command="gpd phase complete 02",
        after_local_runtime_command="gpd:suggest-next",
        secondary_local_commands=(
            "gpd --raw phase checkpoint cleanup --phase 02 --namespace phase --policy successful-closeout",
        ),
    )
    assert _command_text(route.local_transition_command) == decision.primary_command
    assert route.transition_owner == decision.primary_owner
    assert route.stage_stop_next_runtime_command == _command_text(route.after_local_runtime_command)
    assert route.rendered_markdown.startswith("## > Next Up\nPrimary local transition:")
    assert "**After this completes:** `gpd:suggest-next`" in route.rendered_markdown
    assert all(fragment not in route.rendered_markdown for fragment in _FORBIDDEN_NEXT_UP_RELOAD_FRAGMENTS)
    _assert_legacy_projection(decision.next_up, route)
    _assert_legacy_projection(closeout.next_up, closeout_route)
    assert (tmp_path / "GPD" / "ROADMAP.md").read_text(encoding="utf-8") == before_roadmap
    assert (tmp_path / "GPD" / "state.json").read_text(encoding="utf-8") == before_state


def test_lifecycle_decision_counts_only_matching_summaries(tmp_path: Path) -> None:
    _write_phase_project(tmp_path, summaries=("02-01-SUMMARY.md", "02-99-SUMMARY.md"))

    decision = phase_lifecycle_decision(tmp_path, "02")

    assert decision.decision == "needs_execution"
    assert decision.summary_count == 1
    assert decision.closeout_readiness.summary_count == 1
    assert decision.closeout_readiness.all_plans_complete is False
    assert "02-02-PLAN.md" in decision.closeout_readiness.incomplete_plans
    assert any("phase summaries incomplete: 1/2" in blocker for blocker in decision.closeout_blockers)
    assert decision.primary_command == "gpd:execute-phase 02"
    assert decision.lifecycle_class == "needs_execution"
    route = decision.lifecycle_next_up
    assert route is not None
    _assert_route(
        route,
        status_class="needs_execution",
        transition_owner="runtime",
        current_blocking_gate="summaries_incomplete",
        primary_runtime_command="gpd:execute-phase 02",
        local_transition_command=None,
        after_local_runtime_command=None,
    )
    assert route.primary.action == "execute-phase"
    assert route.stage_stop_next_runtime_command == _command_text(route.primary_runtime_command)
    assert route.rendered_markdown == "## > Next Up\nPrimary: `gpd:execute-phase 02`"


def test_lifecycle_decision_missing_verification_routes_to_runtime_verify_work(tmp_path: Path) -> None:
    _write_phase_project(tmp_path, verification_status=None, state_status="Phase complete - ready for verification")

    decision = phase_lifecycle_decision(tmp_path, "02")

    assert decision.decision == "needs_verification"
    assert decision.verification_routing_status == "missing"
    assert decision.primary_command == "gpd:verify-work 02"
    assert decision.primary_owner == "runtime"
    assert decision.lifecycle_class == "needs_verification"
    route = decision.lifecycle_next_up
    assert route is not None
    _assert_route(
        route,
        status_class="needs_verification",
        transition_owner="runtime",
        current_blocking_gate="verification_missing",
        primary_runtime_command="gpd:verify-work 02",
        local_transition_command=None,
        after_local_runtime_command=None,
    )
    assert route.primary.action == "verify-work"
    assert route.stage_stop_next_runtime_command == _command_text(route.primary_runtime_command)
    assert route.rendered_markdown == "## > Next Up\nPrimary: `gpd:verify-work 02`"


def test_lifecycle_decision_verification_opt_out_is_not_mutation_ready(tmp_path: Path) -> None:
    _write_phase_project(tmp_path, verification_status=None, state_status="Phase complete - ready for verification")

    decision = phase_lifecycle_decision(tmp_path, "02", require_verification=False)

    assert decision.decision == "needs_verification"
    assert decision.closeout_ready is False
    assert decision.primary_command == "gpd:verify-work 02"
    assert decision.closeout_readiness.require_verification is False
    assert decision.closeout_readiness.mutation_allowed is False
    assert decision.closeout_readiness.closeout_command is None
    assert any("advisory only" in warning for warning in decision.closeout_warnings)
    route = decision.lifecycle_next_up
    assert route is not None
    _assert_route(
        route,
        status_class="needs_verification",
        transition_owner="runtime",
        current_blocking_gate="verification_missing",
        primary_runtime_command="gpd:verify-work 02",
        local_transition_command=None,
        after_local_runtime_command=None,
    )


def test_lifecycle_decision_non_passing_verification_routes_to_runtime_verify_work(tmp_path: Path) -> None:
    _write_phase_project(tmp_path, verification_status="gaps_found", state_status="Blocked")
    before_roadmap = (tmp_path / "GPD" / "ROADMAP.md").read_text(encoding="utf-8")
    before_state = (tmp_path / "GPD" / "state.json").read_text(encoding="utf-8")
    before_report = (tmp_path / "GPD" / "phases" / "02-analysis" / "02-VERIFICATION.md").read_text(encoding="utf-8")

    decision = phase_lifecycle_decision(tmp_path, "02")

    assert decision.decision == "needs_verification"
    assert decision.verification_status == "gaps_found"
    assert decision.verification_routing_status == "gaps_found"
    assert decision.closeout_ready is False
    assert decision.primary_action == "verify-work"
    assert decision.primary_command == "gpd:verify-work 02"
    assert decision.primary_owner == "runtime"
    assert decision.lifecycle_class == "needs_verification"
    assert decision.closeout_readiness.mutation_allowed is False
    assert decision.closeout_readiness.closeout_command is None
    assert any("must have top-level frontmatter status 'passed'" in blocker for blocker in decision.closeout_blockers)
    route = decision.lifecycle_next_up
    assert route is not None
    _assert_route(
        route,
        status_class="needs_verification",
        transition_owner="runtime",
        current_blocking_gate="verification_not_passed",
        primary_runtime_command="gpd:verify-work 02",
        local_transition_command=None,
        after_local_runtime_command=None,
    )
    assert route.primary.action == "verify-work"
    assert route.stage_stop_next_runtime_command == _command_text(route.primary_runtime_command)
    assert route.rendered_markdown == "## > Next Up\nPrimary: `gpd:verify-work 02`"
    assert (tmp_path / "GPD" / "ROADMAP.md").read_text(encoding="utf-8") == before_roadmap
    assert (tmp_path / "GPD" / "state.json").read_text(encoding="utf-8") == before_state
    assert (tmp_path / "GPD" / "phases" / "02-analysis" / "02-VERIFICATION.md").read_text(
        encoding="utf-8"
    ) == before_report


def test_lifecycle_decision_roadmap_only_closed_missing_verification_stays_on_verification(
    tmp_path: Path,
) -> None:
    _write_phase_project(
        tmp_path,
        roadmap_closed=True,
        verification_status=None,
        state_current_phase="02",
        state_status="Verified",
    )

    decision = phase_lifecycle_decision(tmp_path, "02")

    _assert_not_next_phase_route(decision)
    assert decision.decision == "needs_verification"
    assert decision.lifecycle_class == "needs_verification"
    assert decision.verification_routing_status == "missing"
    assert decision.closeout_blockers == ["canonical verification report missing"]
    route = decision.lifecycle_next_up
    assert route is not None
    _assert_route(
        route,
        status_class="needs_verification",
        transition_owner="runtime",
        current_blocking_gate="verification_missing",
        primary_runtime_command="gpd:verify-work 02",
        local_transition_command=None,
        after_local_runtime_command=None,
    )


def test_lifecycle_decision_roadmap_only_closed_incomplete_summaries_stays_on_execution(
    tmp_path: Path,
) -> None:
    _write_phase_project(
        tmp_path,
        roadmap_closed=True,
        summaries=("02-01-SUMMARY.md",),
        state_current_phase="02",
        state_status="Verified",
    )

    decision = phase_lifecycle_decision(tmp_path, "02")

    _assert_not_next_phase_route(decision)
    assert decision.decision == "needs_execution"
    assert decision.lifecycle_class == "needs_execution"
    assert decision.summary_count == 1
    assert decision.closeout_readiness.all_plans_complete is False
    assert decision.closeout_readiness.incomplete_plans == ["02-02-PLAN.md"]
    route = decision.lifecycle_next_up
    assert route is not None
    _assert_route(
        route,
        status_class="needs_execution",
        transition_owner="runtime",
        current_blocking_gate="summaries_incomplete",
        primary_runtime_command="gpd:execute-phase 02",
        local_transition_command=None,
        after_local_runtime_command=None,
    )


def test_lifecycle_decision_roadmap_only_closed_active_bounded_segment_stays_on_resume(
    tmp_path: Path,
) -> None:
    _write_phase_project(
        tmp_path,
        roadmap_closed=True,
        bounded_segment=True,
        state_current_phase="02",
        state_status="Verified",
    )

    decision = phase_lifecycle_decision(tmp_path, "02")

    _assert_not_next_phase_route(decision)
    assert decision.decision == "blocked_closeout"
    assert decision.lifecycle_class == "blocked_closeout"
    assert decision.closeout_readiness.active_bounded_segment is True
    assert decision.closeout_blockers == ["active bounded segment must be resumed or cleared before phase closeout"]
    route = decision.lifecycle_next_up
    assert route is not None
    _assert_route(
        route,
        status_class="blocked_closeout",
        transition_owner="runtime",
        current_blocking_gate="active_bounded_segment",
        primary_runtime_command="gpd:resume-work",
        local_transition_command=None,
        after_local_runtime_command=None,
    )


def test_lifecycle_decision_proof_redteam_blocker_uses_runtime_verify_work(tmp_path: Path) -> None:
    _write_phase_project(tmp_path, proof_bearing=True)

    decision = phase_lifecycle_decision(tmp_path, "02")

    assert decision.decision == "blocked_closeout"
    assert decision.lifecycle_class == "needs_verification"
    assert decision.closeout_readiness.proof_redteam_required is True
    assert decision.closeout_readiness.proof_redteam_ready is False
    assert "proof-bearing work requires a passed proof-redteam artifact" in decision.closeout_blockers
    route = decision.lifecycle_next_up
    assert route is not None
    _assert_route(
        route,
        status_class="needs_verification",
        transition_owner="runtime",
        current_blocking_gate="proof_redteam_required",
        primary_runtime_command="gpd:verify-work 02",
        local_transition_command=None,
        after_local_runtime_command=None,
    )
    assert route.primary.action == "verify-work"
    assert route.stage_stop_next_runtime_command == _command_text(route.primary_runtime_command)


def test_lifecycle_decision_active_bounded_segment_blocks_with_resume_next_up(tmp_path: Path) -> None:
    _write_phase_project(tmp_path, bounded_segment=True, verification_status=None)

    decision = phase_lifecycle_decision(tmp_path, "02")

    assert decision.decision == "blocked_closeout"
    assert decision.lifecycle_class == "blocked_closeout"
    assert decision.closeout_readiness.active_bounded_segment is True
    assert any("active bounded segment" in blocker for blocker in decision.closeout_blockers)
    assert decision.primary_command == "gpd:resume-work"
    assert decision.primary_owner == "runtime"
    route = decision.lifecycle_next_up
    assert route is not None
    _assert_route(
        route,
        status_class="blocked_closeout",
        transition_owner="runtime",
        current_blocking_gate="active_bounded_segment",
        primary_runtime_command="gpd:resume-work",
        local_transition_command=None,
        after_local_runtime_command=None,
    )
    assert route.primary.action == "resume-work"
    assert route.stage_stop_next_runtime_command == _command_text(route.primary_runtime_command)
    assert route.rendered_markdown == "## > Next Up\nPrimary: `gpd:resume-work`"


def test_lifecycle_decision_preserves_recovery_artifacts_and_suppresses_cleanup(tmp_path: Path) -> None:
    _write_phase_project(tmp_path, recovery=True)

    decision = phase_lifecycle_decision(tmp_path, "02")

    assert decision.decision == "ready_for_closeout"
    assert decision.closeout_readiness.preserve_checkpoint_tags is True
    assert decision.closeout_readiness.cleanup_command is None
    assert decision.closeout_readiness.recovery_artifacts == ["GPD/phases/02-analysis/RECOVERY-02.md"]
    route = decision.lifecycle_next_up
    assert route is not None
    _assert_route(
        route,
        status_class="ready_for_local_closeout",
        transition_owner="local_transition",
        current_blocking_gate="none",
        primary_runtime_command="gpd:suggest-next",
        local_transition_command="gpd phase complete 02",
        after_local_runtime_command="gpd:suggest-next",
    )


def test_lifecycle_decision_closed_phase_without_next_context_routes_to_discuss_first(tmp_path: Path) -> None:
    _write_phase_project(
        tmp_path,
        state_current_phase="03",
        state_status="Ready to plan",
        roadmap_closed=True,
    )

    decision = phase_lifecycle_decision(tmp_path, "02")

    assert decision.decision == "closed_ready_next_phase"
    assert decision.lifecycle_class == "closed_ready_next_phase"
    assert decision.phase_closed is True
    assert decision.roadmap_complete is True
    assert decision.next_phase == "03"
    assert decision.closeout_ready is False
    assert decision.primary_command == "gpd:discuss-phase 03"
    assert decision.primary_owner == "runtime"
    route = decision.lifecycle_next_up
    assert route is not None
    _assert_route(
        route,
        status_class="closed_ready_next_phase",
        transition_owner="runtime",
        current_blocking_gate="none",
        primary_runtime_command="gpd:discuss-phase 03",
        local_transition_command=None,
        after_local_runtime_command=None,
        secondary_runtime_commands=("gpd:plan-phase 03", "gpd:suggest-next"),
        next_phase_context_class="missing_context",
    )
    assert route.primary.action == "discuss-phase"
    assert route.stage_stop_next_runtime_command == _command_text(route.primary_runtime_command)
    assert "gpd phase complete 02" not in route.rendered_markdown


def test_lifecycle_decision_closed_phase_with_planned_next_context_routes_to_execute_first(tmp_path: Path) -> None:
    _write_phase_project(
        tmp_path,
        state_current_phase="03",
        state_status="Ready to plan",
        roadmap_closed=True,
    )
    _write_next_phase_context(tmp_path)

    decision = phase_lifecycle_decision(tmp_path, "02")

    assert decision.decision == "closed_ready_next_phase"
    assert decision.lifecycle_class == "closed_ready_next_phase"
    assert decision.phase_closed is True
    assert decision.roadmap_complete is True
    assert decision.next_phase == "03"
    assert decision.closeout_ready is False
    assert decision.primary_command == "gpd:execute-phase 03"
    assert decision.primary_owner == "runtime"
    route = decision.lifecycle_next_up
    assert route is not None
    _assert_route(
        route,
        status_class="closed_ready_next_phase",
        transition_owner="runtime",
        current_blocking_gate="none",
        primary_runtime_command="gpd:execute-phase 03",
        local_transition_command=None,
        after_local_runtime_command=None,
        secondary_runtime_commands=("gpd:plan-phase 03", "gpd:discuss-phase 03", "gpd:suggest-next"),
        next_phase_context_class="planned",
    )
    assert route.primary.action == "execute-phase"
    assert route.stage_stop_next_runtime_command == _command_text(route.primary_runtime_command)
    assert "gpd phase complete 02" not in route.rendered_markdown


def test_lifecycle_decision_closed_milestone_routes_runtime_audit_not_stale_transition(tmp_path: Path) -> None:
    _write_phase_project(
        tmp_path,
        state_current_phase=None,
        state_status="milestone complete",
        roadmap_closed=True,
    )

    decision = phase_lifecycle_decision(tmp_path, "02")

    assert decision.decision == "closed_milestone_complete"
    assert decision.lifecycle_class == "closed_needs_milestone_audit"
    assert decision.phase_closed is True
    assert decision.primary_command == "gpd:audit-milestone"
    assert decision.primary_owner == "runtime"
    route = decision.lifecycle_next_up
    assert route is not None
    _assert_route(
        route,
        status_class="closed_needs_milestone_audit",
        transition_owner="runtime",
        current_blocking_gate="none",
        primary_runtime_command="gpd:audit-milestone",
        local_transition_command=None,
        after_local_runtime_command=None,
    )
    assert route.stage_stop_next_runtime_command == _command_text(route.primary_runtime_command)
    assert route.rendered_markdown == "## > Next Up\nPrimary: `gpd:audit-milestone`"
    assert "gpd phase complete 02" not in route.rendered_markdown


def test_lifecycle_decision_closed_milestone_routes_archive_only_after_passed_audit(tmp_path: Path) -> None:
    _write_phase_project(
        tmp_path,
        state_current_phase=None,
        state_status="milestone complete",
        roadmap_closed=True,
    )
    (tmp_path / "GPD" / "v1.0-MILESTONE-AUDIT.md").write_text(
        "---\nstatus: passed\n---\n\n# Audit\n",
        encoding="utf-8",
    )

    decision = phase_lifecycle_decision(tmp_path, "02")

    assert decision.decision == "closed_milestone_complete"
    assert decision.lifecycle_class == "closed_ready_for_milestone_archive"
    assert decision.phase_closed is True
    assert decision.primary_action == "complete-milestone"
    assert decision.primary_command == "gpd:complete-milestone v1.0"
    assert decision.primary_owner == "runtime"
    route = decision.lifecycle_next_up
    assert route is not None
    _assert_route(
        route,
        status_class="closed_ready_for_milestone_archive",
        transition_owner="runtime",
        current_blocking_gate="none",
        primary_runtime_command="gpd:complete-milestone v1.0",
        local_transition_command=None,
        after_local_runtime_command=None,
    )
    assert route.stage_stop_next_runtime_command == _command_text(route.primary_runtime_command)
    assert route.rendered_markdown == "## > Next Up\nPrimary: `gpd:complete-milestone v1.0`"
    assert "gpd:audit-milestone" not in route.rendered_markdown


def test_lifecycle_decision_closed_milestone_routes_new_milestone_after_archive(tmp_path: Path) -> None:
    _write_phase_project(
        tmp_path,
        state_current_phase=None,
        state_status="milestone complete",
        roadmap_closed=True,
    )
    archive_dir = tmp_path / "GPD" / "milestones"
    archive_dir.mkdir()
    (archive_dir / "v1.0-ROADMAP.md").write_text("# Archived roadmap\n", encoding="utf-8")

    decision = phase_lifecycle_decision(tmp_path, "02")

    assert decision.decision == "closed_milestone_complete"
    assert decision.lifecycle_class == "archived_ready_for_next_milestone"
    assert decision.phase_closed is True
    assert decision.primary_action == "new-milestone"
    assert decision.primary_command == "gpd:new-milestone"
    assert decision.primary_owner == "runtime"
    route = decision.lifecycle_next_up
    assert route is not None
    _assert_route(
        route,
        status_class="archived_ready_for_next_milestone",
        transition_owner="runtime",
        current_blocking_gate="none",
        primary_runtime_command="gpd:new-milestone",
        local_transition_command=None,
        after_local_runtime_command=None,
    )
    assert route.stage_stop_next_runtime_command == _command_text(route.primary_runtime_command)
    assert route.rendered_markdown == "## > Next Up\nPrimary: `gpd:new-milestone`"
