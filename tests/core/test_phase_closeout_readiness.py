"""Read-only closeout readiness checks for phase lifecycle helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gpd.cli import app
from gpd.core.phase_closeout import phase_closeout_readiness, phase_closeout_readiness_payload
from gpd.core.proof_redteam import build_proof_redteam_skeleton
from gpd.core.state import default_state_dict
from tests.assertion_taxonomy_support import assert_prompt_contracts, machine_exact, semantic_concept


class _StableCliRunner(CliRunner):
    def invoke(self, *args, **kwargs):
        kwargs.setdefault("color", False)
        return super().invoke(*args, **kwargs)


RUNNER = _StableCliRunner()
REPO_ROOT = Path(__file__).resolve().parents[2]
EXECUTE_PHASE_STAGE_DIR = REPO_ROOT / "src/gpd/specs/workflows/execute-phase"
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
) -> None:
    assert route.status_class == status_class
    assert route.transition_owner == transition_owner
    assert route.current_blocking_gate == current_blocking_gate
    assert _command_text(route.primary_runtime_command) == primary_runtime_command
    assert _command_text(route.local_transition_command) == local_transition_command
    assert _command_text(route.after_local_runtime_command) == after_local_runtime_command
    assert _command_texts(route.secondary_runtime_commands) == secondary_runtime_commands
    assert _command_texts(route.secondary_local_commands) == secondary_local_commands


def _assert_legacy_projection(payload: dict[str, object], route: object) -> None:
    assert payload == route.to_legacy_payload()


def _write_phase_project(
    root: Path,
    *,
    summaries: int = 2,
    verification_status: str | None = "passed",
    malformed_verification: bool = False,
    proof_bearing: bool = False,
    recovery: bool = False,
) -> Path:
    gpd_dir = root / "GPD"
    phase_dir = gpd_dir / "phases" / "02-analysis"
    phase_dir.mkdir(parents=True)
    (gpd_dir / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
    (gpd_dir / "ROADMAP.md").write_text("# Roadmap\n\n## Phase 2: Analysis\n", encoding="utf-8")
    for index in range(1, 3):
        proof_flag = "proof_bearing: true\n" if proof_bearing and index == 1 else ""
        (phase_dir / f"02-{index:02d}-PLAN.md").write_text(
            f"---\nwave: {index}\n{proof_flag}---\n\n# Plan {index}\n",
            encoding="utf-8",
        )
    for index in range(1, summaries + 1):
        (phase_dir / f"02-{index:02d}-SUMMARY.md").write_text(f"# Summary {index}\n", encoding="utf-8")
    if malformed_verification:
        (phase_dir / "02-VERIFICATION.md").write_text("---\nstatus: [\n---\n\n# Bad\n", encoding="utf-8")
    elif verification_status is not None:
        (phase_dir / "02-VERIFICATION.md").write_text(
            f"---\nstatus: {verification_status}\nscore: closeout test\n---\n\n# Verification\n",
            encoding="utf-8",
        )
    if recovery:
        (phase_dir / "RECOVERY-02.md").write_text("# Recovery\n", encoding="utf-8")
    return phase_dir


def _write_state(root: Path, *, bounded_segment: bool = False) -> None:
    state = default_state_dict()
    if bounded_segment:
        state["continuation"]["bounded_segment"] = {
            "resume_file": "GPD/phases/02-analysis/.continue-here.md",
            "phase": "02",
            "plan": "01",
            "segment_id": "seg-02-01",
            "segment_status": "paused",
            "waiting_for_review": True,
        }
    (root / "GPD" / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def _write_closed_milestone_state(root: Path) -> None:
    state = default_state_dict()
    state["position"]["current_phase"] = None
    state["position"]["current_phase_name"] = None
    state["position"]["current_plan"] = None
    state["position"]["total_plans_in_phase"] = None
    state["position"]["status"] = "milestone complete"
    (root / "GPD" / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def test_closeout_readiness_all_summaries_and_passed_verification_is_ready(tmp_path: Path) -> None:
    _write_phase_project(tmp_path)
    _write_state(tmp_path)
    before_roadmap = (tmp_path / "GPD" / "ROADMAP.md").read_text(encoding="utf-8")
    before_state = (tmp_path / "GPD" / "state.json").read_text(encoding="utf-8")

    result = phase_closeout_readiness(tmp_path, "2", require_verification=True)

    assert result.ready is True
    assert result.mutation_allowed is True
    assert result.read_only is True
    assert result.mutated is False
    assert result.plan_count == 2
    assert result.summary_count == 2
    assert result.verification_status == "passed"
    assert result.closeout_command == "gpd phase complete 02"
    assert (
        result.cleanup_command
        == "gpd --raw phase checkpoint cleanup --phase 02 --namespace phase --policy successful-closeout"
    )
    route = result.lifecycle_next_up
    assert route is not None
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
    assert route.stage_stop_next_runtime_command == _command_text(route.after_local_runtime_command)
    rendered = route.rendered_markdown
    assert rendered.startswith("## > Next Up\nPrimary local transition:")
    assert "**After this completes:** `gpd:suggest-next`" in rendered
    assert "Secondary local helper:" in rendered
    assert all(fragment not in rendered for fragment in _FORBIDDEN_NEXT_UP_RELOAD_FRAGMENTS)
    _assert_legacy_projection(result.next_up, route)
    assert result.closeout_command_hint is not None
    assert result.closeout_command_hint["owner"] == "local_transition"
    assert result.cleanup_command_hint is not None
    assert result.cleanup_command_hint["owner"] == "local_helper"
    assert (tmp_path / "GPD" / "ROADMAP.md").read_text(encoding="utf-8") == before_roadmap
    assert (tmp_path / "GPD" / "state.json").read_text(encoding="utf-8") == before_state


def test_phase_closeout_readiness_payload_milestone_archive_does_not_project_version_as_next_phase(
    tmp_path: Path,
) -> None:
    _write_phase_project(tmp_path)
    _write_closed_milestone_state(tmp_path)
    (tmp_path / "GPD" / "v1.0-MILESTONE-AUDIT.md").write_text(
        "---\nstatus: passed\n---\n\n# Audit\n",
        encoding="utf-8",
    )

    readiness = phase_closeout_readiness(tmp_path, "02", require_verification=True)
    payload = phase_closeout_readiness_payload(readiness)

    assert payload["ready"] is False
    assert payload["lifecycle_next_up"]["primary"]["command"] == "gpd:complete-milestone v1.0"
    assert payload["next_up"]["primary_command"]["command"] == "gpd:complete-milestone v1.0"
    route = payload["lifecycle_route"]
    assert route["status"] == "closed"
    assert route["status_class"] == "closed_ready_for_milestone_archive"
    assert route["transition_owner"] == "runtime"
    assert route["next_phase"] is None
    assert route["next_phase_context_class"] == "not_applicable"
    assert route["primary_runtime_command"]["command"] == "gpd:complete-milestone v1.0"
    assert route["primary_runtime_command_text"] == "gpd:complete-milestone v1.0"
    assert route["stage_stop_next_runtime_command"] == "gpd:complete-milestone v1.0"


def test_closeout_readiness_missing_summary_blocks_closeout(tmp_path: Path) -> None:
    _write_phase_project(tmp_path, summaries=1)

    result = phase_closeout_readiness(tmp_path, "02", require_verification=True)

    assert result.ready is False
    assert result.mutation_allowed is False
    assert result.all_plans_complete is False
    assert "02-02-PLAN.md" in result.incomplete_plans
    assert any("summaries incomplete" in blocker for blocker in result.blockers)
    route = result.lifecycle_next_up
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


def test_closeout_readiness_missing_verification_blocks_required_closeout(tmp_path: Path) -> None:
    _write_phase_project(tmp_path, verification_status=None)
    (tmp_path / "GPD" / "CHECKPOINTS.md").write_text("# Generated checkpoint shelf\n", encoding="utf-8")

    result = phase_closeout_readiness(tmp_path, "02", require_verification=True)

    assert result.ready is False
    assert result.verification_routing_status == "missing"
    assert "canonical verification report missing" in result.blockers
    route = result.lifecycle_next_up
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


def test_closeout_readiness_missing_verification_blocks_by_default(tmp_path: Path) -> None:
    _write_phase_project(tmp_path, verification_status=None)

    result = phase_closeout_readiness(tmp_path, "02")

    assert result.ready is False
    assert result.mutation_allowed is False
    assert result.require_verification is True
    assert result.closeout_command is None
    assert result.verification_routing_status == "missing"
    assert result.blockers == ["canonical verification report missing"]
    route = result.lifecycle_next_up
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


def test_closeout_readiness_explicit_verification_opt_out_does_not_allow_mutation(tmp_path: Path) -> None:
    _write_phase_project(tmp_path, verification_status=None)

    result = phase_closeout_readiness(tmp_path, "02", require_verification=False)

    assert result.ready is False
    assert result.mutation_allowed is False
    assert result.require_verification is False
    assert result.closeout_command is None
    assert result.warnings[:1] == ["canonical verification status is 'missing'"]
    assert any("advisory only" in warning for warning in result.warnings)
    route = result.lifecycle_next_up
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


@pytest.mark.parametrize("status", ["gaps_found", "human_needed", "expert_needed"])
def test_closeout_readiness_non_passing_verification_blocks_required_closeout(
    tmp_path: Path,
    status: str,
) -> None:
    _write_phase_project(tmp_path, verification_status=status)

    result = phase_closeout_readiness(tmp_path, "02", require_verification=True)

    assert result.ready is False
    assert result.verification_status == status
    assert any("must have top-level frontmatter status 'passed'" in blocker for blocker in result.blockers)
    route = result.lifecycle_next_up
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


def test_closeout_readiness_malformed_verification_blocks_closeout(tmp_path: Path) -> None:
    _write_phase_project(tmp_path, malformed_verification=True)

    result = phase_closeout_readiness(tmp_path, "02", require_verification=True)

    assert result.ready is False
    assert result.verification_routing_status == "unparseable"
    assert any("canonical verification report blocked" in blocker for blocker in result.blockers)


def test_closeout_readiness_uses_top_level_verification_frontmatter_only(tmp_path: Path) -> None:
    phase_dir = _write_phase_project(tmp_path)
    (phase_dir / "02-VERIFICATION.md").write_text(
        "---\n"
        "status: passed\n"
        "score: closeout test\n"
        "---\n\n"
        "contract_results:\n"
        "  claims:\n"
        "    claim-a:\n"
        "      status: gaps_found\n",
        encoding="utf-8",
    )

    result = phase_closeout_readiness(tmp_path, "02", require_verification=True)

    assert result.ready is True
    assert result.verification_status == "passed"
    assert result.verification_routing_status == "passed"
    assert not any("canonical verification report" in blocker for blocker in result.blockers)


def test_closeout_readiness_active_bounded_segment_blocks_closeout(tmp_path: Path) -> None:
    _write_phase_project(tmp_path)
    _write_state(tmp_path, bounded_segment=True)

    result = phase_closeout_readiness(tmp_path, "02", require_verification=True)

    assert result.ready is False
    assert result.active_bounded_segment is True
    assert any("active bounded segment" in blocker for blocker in result.blockers)
    route = result.lifecycle_next_up
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


def test_closeout_readiness_preserves_checkpoint_tags_when_recovery_artifacts_exist(tmp_path: Path) -> None:
    _write_phase_project(tmp_path, recovery=True)

    result = phase_closeout_readiness(tmp_path, "02", require_verification=True)

    assert result.ready is True
    assert result.preserve_checkpoint_tags is True
    assert result.cleanup_command is None
    assert result.recovery_artifacts == ["GPD/phases/02-analysis/RECOVERY-02.md"]
    route = result.lifecycle_next_up
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


def test_closeout_readiness_blocks_proof_bearing_work_without_passed_proof_redteam(tmp_path: Path) -> None:
    _write_phase_project(tmp_path, proof_bearing=True)

    result = phase_closeout_readiness(tmp_path, "02", require_verification=True)

    assert result.ready is False
    assert result.proof_redteam_required is True
    assert result.proof_redteam_ready is False
    assert_prompt_contracts(
        "\n".join(result.blockers),
        *semantic_concept(
            "closeout readiness blocks proof-bearing work without passed proof-redteam",
            required=("proof-bearing work requires a passed proof-redteam artifact",),
        ),
    )
    route = result.lifecycle_next_up
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


def test_closeout_readiness_blocks_non_passed_proof_redteam_artifact(tmp_path: Path) -> None:
    phase_dir = _write_phase_project(tmp_path, proof_bearing=True)
    skeleton = build_proof_redteam_skeleton(
        claim_id="claim-a",
        proof_artifact_paths=["GPD/phases/02-analysis/02-01-PLAN.md"],
        status="gaps_found",
    )
    (phase_dir / "02-01-PROOF-REDTEAM.md").write_text(skeleton.markdown_draft, encoding="utf-8")

    result = phase_closeout_readiness(tmp_path, "02", require_verification=True)

    assert result.ready is False
    assert result.proof_redteam_required is True
    assert result.proof_redteam_ready is False
    assert result.proof_redteam_artifacts == ["GPD/phases/02-analysis/02-01-PROOF-REDTEAM.md"]
    assert any("reports status 'gaps_found'; expected 'passed'" in blocker for blocker in result.blockers)


def test_phase_closeout_readiness_cli_blocks_missing_verification_by_default(tmp_path: Path) -> None:
    _write_phase_project(tmp_path, verification_status=None)

    result = RUNNER.invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "phase",
            "closeout-readiness",
            "02",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["ready"] is False
    assert payload["read_only"] is True
    assert payload["mutated"] is False
    assert payload["require_verification"] is True
    assert payload["closeout_command"] is None
    assert payload["blockers"] == ["canonical verification report missing"]


def test_phase_closeout_readiness_cli_opt_out_does_not_advertise_mutation(tmp_path: Path) -> None:
    _write_phase_project(tmp_path, verification_status=None)

    result = RUNNER.invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "phase",
            "closeout-readiness",
            "02",
            "--no-require-verification",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["ready"] is False
    assert payload["mutation_allowed"] is False
    assert payload["require_verification"] is False
    assert payload["closeout_command"] is None
    assert payload["lifecycle_next_up"]["primary"]["command"] == "gpd:verify-work 02"


def test_phase_help_lists_closeout_readiness_not_removed_verification_summary() -> None:
    result = RUNNER.invoke(app, ["phase", "--help"])

    assert result.exit_code == 0
    assert "closeout-readiness" in result.output
    assert "verification-summary" not in result.output


def test_execute_phase_closeout_spec_is_readiness_transition_only() -> None:
    workflow = (EXECUTE_PHASE_STAGE_DIR / "closeout.md").read_text(encoding="utf-8")
    manifest = json.loads((EXECUTE_PHASE_STAGE_DIR.parent / "execute-phase-stage-manifest.json").read_text())
    closeout_stage = next(stage for stage in manifest["stages"] if stage["id"] == "closeout")
    conditional_authorities = {
        authority for condition in closeout_stage["conditional_authorities"] for authority in condition["authorities"]
    }

    assert_prompt_contracts(
        workflow,
        *semantic_concept(
            "execute-phase closeout stage remains readiness transition only",
            required=(
                "does not spawn verifiers, close gaps, run consistency checks, or decide scientific status",
                "It is the authority for verification, proof-redteam, consistency, bounded-segment, and closeout readiness",
            ),
        ),
        machine_exact(
            "execute-phase closeout readiness statuses stay distinct",
            "`ready-to-execute` and `ready-for-verification` are not `ready-for-closeout`",
        ),
    )
    assert "gpd --raw phase closeout-readiness" in workflow
    assert "--require-verification" in workflow
    assert 'gpd phase complete "${phase_number}"' in workflow
    assert workflow.index("gpd --raw phase closeout-readiness") < workflow.index('gpd phase complete "${phase_number}"')
    assert 'CLOSEOUT_READY=$(echo "$CLOSEOUT_READINESS" | gpd json get .ready --default false)' in workflow
    assert workflow.index('if [ "$CLOSEOUT_READY" != "true" ]; then') < workflow.index(
        'gpd phase complete "${phase_number}"'
    )
    assert "Do not repair blockers, update roadmap/state, or clean checkpoints from this stage." in workflow
    assert closeout_stage["loaded_authorities"] == ["workflows/execute-phase/closeout.md"]
    assert {"workflows/transition.md", "templates/state-machine.md"} <= conditional_authorities
