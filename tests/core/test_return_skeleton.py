"""Focused tests for role-aware ``gpd_return`` skeleton rendering."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from gpd.cli import app
from gpd.core.commands import cmd_apply_return_updates
from gpd.core.prompt_semantic_duplicate_diagnostics import status_handling_terms
from gpd.core.return_contract import (
    ALLOWED_RETURN_EXTENSION_FIELDS,
    KNOWN_RETURN_FIELD_NAMES,
    REQUIRED_RETURN_FIELDS,
    RETURN_STATUS_ORDER,
    VALID_RETURN_STATUSES,
    GpdReturnEnvelope,
    normalize_return_status,
    return_field_allowed_for_status,
    return_field_allowed_source,
    return_fields_allowed_for_status,
    validate_gpd_return_markdown,
)
from gpd.core.return_fields import has_return_field_default
from gpd.core.return_skeleton import (
    APPLICATOR_OWNED_METADATA_FIELDS,
    GPD_RETURN_ROLE_PROFILES,
    build_gpd_return_skeleton,
    list_gpd_return_profiles,
    render_gpd_return_markdown,
    render_gpd_return_yaml,
)
from gpd.core.state import default_state_dict, generate_state_markdown

DURABLE_CHECKPOINT_CONTEXT_FIELDS = {
    "last_result_id",
    "recorded_at",
    "recorded_by",
    "resume_file",
    "source_session_id",
    "updated_at",
}


def test_return_profiles_cover_core_roles() -> None:
    assert set(GPD_RETURN_ROLE_PROFILES) == {
        "bibliographer",
        "debugger",
        "executor",
        "experiment_designer",
        "paper_writer",
        "planner",
        "checker",
        "verifier",
        "referee",
        "notation",
        "researcher",
        "reviewer",
        "synthesizer",
        "roadmapper",
    }
    assert set(RETURN_STATUS_ORDER) == VALID_RETURN_STATUSES


def test_return_profile_fields_are_allowed_by_return_contract() -> None:
    known_fields = set(GpdReturnEnvelope.model_fields) | set(ALLOWED_RETURN_EXTENSION_FIELDS)
    assert KNOWN_RETURN_FIELD_NAMES == known_fields
    assert return_field_allowed_source("status") == "base"
    assert return_field_allowed_source("confidence") == "extension"
    assert return_field_allowed_source("statuss") == "unknown"

    for profile in GPD_RETURN_ROLE_PROFILES.values():
        assert profile.required_fields == REQUIRED_RETURN_FIELDS
        for status in VALID_RETURN_STATUSES:
            assert status in profile.role_fields_by_status
            assert set(profile.role_fields_by_status[status]) <= known_fields
            assert set(profile.default_render_fields_by_status[status]) <= known_fields


def test_return_profile_status_fields_obey_status_contract() -> None:
    registry_payload = list_gpd_return_profiles()["field_registry"]
    assert set(registry_payload["known_fields"]) == KNOWN_RETURN_FIELD_NAMES
    assert registry_payload["status_allowed_fields"] == {
        status: list(return_fields_allowed_for_status(status)) for status in RETURN_STATUS_ORDER
    }

    for profile in GPD_RETURN_ROLE_PROFILES.values():
        for status, fields in profile.role_fields_by_status.items():
            disallowed = sorted(
                field_name for field_name in fields if not return_field_allowed_for_status(field_name, status)
            )
            assert disallowed == []
            assert ("blockers" in profile.default_render_fields_by_status[status]) is return_field_allowed_for_status(
                "blockers",
                status,
            )
            for field_name in fields:
                assert field_name in registry_payload["status_allowed_fields"][status]
            for field_name in profile.default_render_fields_by_status[status]:
                assert field_name in registry_payload["status_allowed_fields"][status]
                if field_name != "checkpoint_intent":
                    assert has_return_field_default(field_name)

    executor = GPD_RETURN_ROLE_PROFILES["executor"]
    assert "blockers" not in executor.role_fields_by_status["completed"]
    assert "blockers" in executor.role_fields_by_status["checkpoint"]
    assert "checkpoint_intent" not in executor.role_fields_by_status["completed"]
    assert "checkpoint_intent" in executor.role_fields_by_status["checkpoint"]
    assert "checkpoint_intent" in executor.default_render_fields_by_status["checkpoint"]
    assert "checkpoint_intent" not in return_fields_allowed_for_status("completed")
    assert "checkpoint_intent" in return_fields_allowed_for_status("checkpoint")


def test_return_status_helper_normalizes_callsite_status_selectors() -> None:
    assert normalize_return_status(" CHECKPOINT ") == "checkpoint"

    with pytest.raises(ValueError, match="unknown gpd_return status"):
        normalize_return_status("waiting")


def test_semantic_duplicate_status_vocab_term_uses_return_contract_order() -> None:
    status_pipe = " | ".join(RETURN_STATUS_ORDER)

    assert status_handling_terms(status_pipe) == (status_pipe,)


def test_list_gpd_return_profiles_matches_profile_registry_and_filters() -> None:
    all_payload = list_gpd_return_profiles()

    assert all_payload["mutated"] is False
    assert all_payload["mutates"] is False
    assert all_payload["roles"] == sorted(GPD_RETURN_ROLE_PROFILES)
    assert all_payload["statuses"] == list(RETURN_STATUS_ORDER)
    assert {profile["profile_id"] for profile in all_payload["profiles"]} == set(GPD_RETURN_ROLE_PROFILES)

    executor_payload = list_gpd_return_profiles(role="executor", status="checkpoint")

    assert [profile["profile_id"] for profile in executor_payload["profiles"]] == ["executor"]
    assert set(executor_payload["profiles"][0]["statuses"]) == {"checkpoint"}
    assert "blockers" in executor_payload["profiles"][0]["statuses"]["checkpoint"]["role_fields"]

    with pytest.raises(ValueError, match="unknown gpd_return role profile"):
        list_gpd_return_profiles(role="observer")

    with pytest.raises(ValueError, match="unknown gpd_return status"):
        list_gpd_return_profiles(status="done")


@pytest.mark.parametrize(
    ("alias", "profile_id"),
    [
        ("paper_writer", "paper_writer"),
        ("gpd-paper-writer", "paper_writer"),
        ("bibliographer", "bibliographer"),
        ("gpd-bibliographer", "bibliographer"),
        ("debug", "debugger"),
        ("debugger", "debugger"),
        ("gpd-debugger", "debugger"),
        ("research_mapper", "researcher"),
        ("gpd-research-mapper", "researcher"),
        ("notation_coordinator", "notation"),
        ("gpd-notation-coordinator", "notation"),
        ("experiment_designer", "experiment_designer"),
        ("gpd-experiment-designer", "experiment_designer"),
        ("proof_redteam", "verifier"),
        ("consistency_checker", "checker"),
        ("gpd-review-reader", "reviewer"),
    ],
)
def test_return_profile_aliases_are_shared_with_skeleton_builder(alias: str, profile_id: str) -> None:
    skeleton = build_gpd_return_skeleton(role=alias, status="completed")
    profiles = list_gpd_return_profiles(role=alias, status="completed")

    assert skeleton.profile_id == profile_id
    assert [profile["profile_id"] for profile in profiles["profiles"]] == [profile_id]
    assert validate_gpd_return_markdown(skeleton.markdown).passed is True


def test_new_project_role_profiles_use_conservative_existing_defaults() -> None:
    assert (
        GPD_RETURN_ROLE_PROFILES["reviewer"].default_render_fields_by_status["completed"]
        == GPD_RETURN_ROLE_PROFILES["referee"].default_render_fields_by_status["completed"]
    )
    assert (
        GPD_RETURN_ROLE_PROFILES["synthesizer"].default_render_fields_by_status["completed"]
        == GPD_RETURN_ROLE_PROFILES["researcher"].default_render_fields_by_status["completed"]
    )
    assert (
        GPD_RETURN_ROLE_PROFILES["roadmapper"].default_render_fields_by_status["completed"]
        == GPD_RETURN_ROLE_PROFILES["planner"].default_render_fields_by_status["completed"]
    )


def test_phase5_prompt_worker_profiles_expose_local_fields_without_path_defaults() -> None:
    bibliographer = GPD_RETURN_ROLE_PROFILES["bibliographer"]
    assert set(bibliographer.agent_names) == {"gpd-bibliographer"}
    assert {
        "entries_added",
        "citations_added",
        "papers_reviewed",
        "reference_maps",
    } <= set(bibliographer.role_fields_by_status["completed"])

    debugger = GPD_RETURN_ROLE_PROFILES["debugger"]
    assert set(debugger.agent_names) == {"gpd-debugger"}
    assert {
        "session_file",
        "checks_performed",
        "issues_found",
    } <= set(debugger.role_fields_by_status["completed"])
    assert "session_file" not in debugger.default_render_fields_by_status["completed"]

    paper_writer = GPD_RETURN_ROLE_PROFILES["paper_writer"]
    assert set(paper_writer.agent_names) == {"gpd-paper-writer"}
    assert {
        "section_name",
        "equations_added",
        "figures_added",
        "citations_added",
        "journal_calibration",
        "framing_strategy",
    } <= set(paper_writer.role_fields_by_status["completed"])

    notation = GPD_RETURN_ROLE_PROFILES["notation"]
    assert set(notation.agent_names) == {"gpd-notation-coordinator"}
    assert {
        "conventions_file",
        "categories_defined",
        "test_values_defined",
        "cross_convention_checks",
        "reference_maps",
        "conflicts",
        "severity",
    } <= set(notation.role_fields_by_status["completed"])
    assert "conventions_file" not in notation.default_render_fields_by_status["completed"]

    experiment_designer = GPD_RETURN_ROLE_PROFILES["experiment_designer"]
    assert set(experiment_designer.agent_names) == {"gpd-experiment-designer"}
    assert "design_file" in experiment_designer.role_fields_by_status["completed"]
    assert "design_file" not in experiment_designer.default_render_fields_by_status["completed"]

    researcher = GPD_RETURN_ROLE_PROFILES["researcher"]
    assert "gpd-research-mapper" in researcher.agent_names


def test_phase5_prompt_worker_checkpoint_profiles_keep_child_boundary() -> None:
    for role, artifact_field in (
        ("paper_writer", None),
        ("notation_coordinator", "conventions_file"),
        ("experiment_designer", "design_file"),
        ("research_mapper", None),
    ):
        skeleton = build_gpd_return_skeleton(role=role, status="checkpoint")

        assert skeleton.envelope["status"] == "checkpoint"
        assert skeleton.envelope["files_written"] == []
        assert "checkpoint_intent" in skeleton.envelope
        assert "continuation_update" not in skeleton.envelope
        assert skeleton.applicator_ready is False
        if artifact_field is not None:
            assert artifact_field not in skeleton.envelope


@pytest.mark.parametrize("role", sorted(GPD_RETURN_ROLE_PROFILES))
@pytest.mark.parametrize("status", RETURN_STATUS_ORDER)
def test_return_skeleton_validates_for_each_role_status(role: str, status: str) -> None:
    skeleton = build_gpd_return_skeleton(role=role, status=status)

    result = validate_gpd_return_markdown(skeleton.markdown)

    assert result.passed is True
    assert result.fields == skeleton.envelope
    assert result.fields["status"] == status
    for field_name in REQUIRED_RETURN_FIELDS:
        assert field_name in result.fields

    payload_text = json.dumps(skeleton.model_dump(mode="json"), sort_keys=True)
    for field_name in APPLICATOR_OWNED_METADATA_FIELDS:
        assert field_name not in payload_text
    if status == "checkpoint":
        assert "checkpoint_intent" in result.fields
        assert "continuation_update" not in result.fields
        assert result.fields["checkpoint_intent"]["checkpoint_reason"] == "checkpoint"
        assert skeleton.applicator_ready is False
        for field_name in DURABLE_CHECKPOINT_CONTEXT_FIELDS:
            assert field_name not in json.dumps(result.fields, sort_keys=True)


def test_return_skeleton_renders_yaml_markdown_and_json_payload() -> None:
    skeleton = build_gpd_return_skeleton(
        role="planner",
        status="completed",
        files_written=("GPD/roadmap.md",),
        issues=("needs verifier review",),
        next_actions=("gpd plan-phase 01",),
        phase="01",
    )

    assert yaml.safe_load(skeleton.yaml_payload) == {"gpd_return": skeleton.envelope}
    assert render_gpd_return_yaml(skeleton.envelope) == skeleton.yaml_payload
    assert render_gpd_return_markdown(skeleton.envelope) == skeleton.markdown
    assert json.loads(skeleton.model_dump_json())["envelope"] == skeleton.envelope
    assert skeleton.envelope["files_written"] == ["GPD/roadmap.md"]
    assert skeleton.envelope["phase"] == "01"


def test_return_skeleton_cli_reads_files_from_stdin(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "return",
            "skeleton",
            "--role",
            "paper_writer",
            "--status",
            "completed",
            "--files-from",
            "-",
        ],
        input="GPD/phases/01/01-01-PLAN.md\n\nGPD/ROADMAP.md\n",
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["profile_id"] == "paper_writer"
    assert payload["envelope"]["files_written"] == [
        "GPD/phases/01/01-01-PLAN.md",
        "GPD/ROADMAP.md",
    ]
    assert validate_gpd_return_markdown(payload["markdown"]).passed is True


def test_return_skeleton_cli_defaults_checkpoint_to_child_checkpoint_intent(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(tmp_path),
            "return",
            "skeleton",
            "--role",
            "executor",
            "--status",
            "checkpoint",
            "--phase",
            "01",
            "--plan",
            "02",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    envelope = payload["envelope"]
    assert envelope["checkpoint_intent"] == {
        "checkpoint_reason": "checkpoint",
        "waiting_reason": "Parent/applicator resume context required.",
        "phase": "01",
        "plan": "02",
    }
    assert "continuation_update" not in envelope
    assert payload["applicator_ready"] is False
    assert "gpd apply-return-updates <return-file.md>" not in payload["validation_commands"]


def test_checker_checkpoint_skeleton_contains_partial_approval_fields() -> None:
    skeleton = build_gpd_return_skeleton(role="checker", status="checkpoint")

    assert skeleton.envelope["approved_plans"] == []
    assert skeleton.envelope["blocked_plans"] == []
    assert skeleton.envelope["revision_round"] == 1
    assert "blockers" in skeleton.envelope
    assert skeleton.envelope["checkpoint_intent"]["checkpoint_reason"] == "checkpoint"
    assert any("checkpoint_intent" in warning for warning in skeleton.warnings)


def test_verifier_skeleton_keeps_verification_status_distinct() -> None:
    skeleton = build_gpd_return_skeleton(role="verifier", status="completed")

    assert skeleton.envelope["status"] == "completed"
    assert skeleton.envelope["verification_status"] == "gaps_found"
    assert "verified" not in skeleton.envelope


@pytest.mark.parametrize(
    ("role", "field_name"),
    [
        ("roadmapper", "phases_created"),
        ("bibliographer", "entries_added"),
        ("debugger", "session_file"),
    ],
)
def test_prompt_visible_role_extensions_are_skeleton_profile_visible(role: str, field_name: str) -> None:
    skeleton = build_gpd_return_skeleton(role=role, status="completed")
    profile = GPD_RETURN_ROLE_PROFILES[role]

    assert field_name in skeleton.role_fields
    assert field_name in profile.role_fields_by_status["completed"]
    assert field_name not in profile.default_render_fields_by_status["completed"]
    assert field_name not in skeleton.envelope
    assert return_field_allowed_source(field_name) == "extension"
    assert return_field_allowed_for_status(field_name, "completed")


def test_return_skeleton_rejects_unknown_role_status_and_fields() -> None:
    with pytest.raises(ValueError, match="unknown gpd_return role profile"):
        build_gpd_return_skeleton(role="observer", status="completed")

    with pytest.raises(ValueError, match="unknown gpd_return status"):
        build_gpd_return_skeleton(role="executor", status="done")

    with pytest.raises(ValueError, match="Unknown gpd_return top-level field"):
        build_gpd_return_skeleton(role="executor", status="completed", extra_fields={"file_written": []})


def test_return_skeleton_rejects_status_disallowed_extra_fields() -> None:
    with pytest.raises(ValueError, match="status 'blocked' does not allow gpd_return field\\(s\\): state_updates"):
        build_gpd_return_skeleton(
            role="executor",
            status="blocked",
            extra_fields={"state_updates": {"advance_plan": True}},
        )


def test_checkpoint_applicator_fields_require_explicit_resume_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="resume_file"):
        build_gpd_return_skeleton(role="executor", status="checkpoint", include_applicator_fields=True)

    with pytest.raises(ValueError, match="existing project file"):
        build_gpd_return_skeleton(
            role="executor",
            status="checkpoint",
            include_applicator_fields=True,
            resume_file="GPD/phases/01-test-phase/.continue-here.md",
            project_root=tmp_path,
        )

    resume_file = tmp_path / "GPD" / "phases" / "01-test-phase" / ".continue-here.md"
    resume_file.parent.mkdir(parents=True)
    resume_file.write_text("resume\n", encoding="utf-8")

    skeleton = build_gpd_return_skeleton(
        role="executor",
        status="checkpoint",
        include_applicator_fields=True,
        resume_file="GPD/phases/01-test-phase/.continue-here.md",
        project_root=tmp_path,
        phase="01",
        plan="01",
    )

    bounded_segment = skeleton.envelope["continuation_update"]["bounded_segment"]
    assert bounded_segment == {
        "resume_file": "GPD/phases/01-test-phase/.continue-here.md",
        "segment_status": "paused",
        "phase": "01",
        "plan": "01",
    }
    assert skeleton.applicator_ready is True
    assert "gpd apply-return-updates <return-file.md>" in skeleton.validation_commands


def test_default_checkpoint_skeleton_is_child_pause_intent_not_applicator_context() -> None:
    skeleton = build_gpd_return_skeleton(
        role="executor",
        status="checkpoint",
        checkpoint_reason="pre_fanout",
        checkpoint_waiting_reason="Review the first result before dependent fanout.",
        phase="01",
        plan="02",
    )

    assert skeleton.envelope["checkpoint_intent"] == {
        "checkpoint_reason": "pre_fanout",
        "waiting_reason": "Review the first result before dependent fanout.",
        "phase": "01",
        "plan": "02",
    }
    assert "continuation_update" not in skeleton.envelope
    assert skeleton.applicator_ready is False
    assert "gpd apply-return-updates <return-file.md>" not in skeleton.validation_commands
    payload_text = json.dumps(skeleton.envelope, sort_keys=True)
    for field_name in DURABLE_CHECKPOINT_CONTEXT_FIELDS:
        assert field_name not in payload_text
    assert any("durable resume context must be supplied to the applicator" in warning for warning in skeleton.warnings)


def test_checkpoint_intent_skeleton_uses_child_owned_fields_when_contract_allows() -> None:
    if "checkpoint_intent" not in KNOWN_RETURN_FIELD_NAMES:
        with pytest.raises(ValueError, match="checkpoint_intent skeletons require canonical return contract support"):
            build_gpd_return_skeleton(
                role="executor",
                status="checkpoint",
                include_checkpoint_intent=True,
            )
        return

    skeleton = build_gpd_return_skeleton(
        role="executor",
        status="checkpoint",
        include_checkpoint_intent=True,
        checkpoint_reason="pre_fanout",
        checkpoint_waiting_reason="Review the first result before dependent fanout.",
        phase="01",
        plan="02",
    )

    checkpoint_intent = skeleton.envelope["checkpoint_intent"]
    assert checkpoint_intent == {
        "checkpoint_reason": "pre_fanout",
        "waiting_reason": "Review the first result before dependent fanout.",
        "phase": "01",
        "plan": "02",
    }
    assert "continuation_update" not in skeleton.envelope
    assert "resume_file" not in json.dumps(skeleton.envelope, sort_keys=True)
    assert skeleton.applicator_ready is False
    assert "gpd apply-return-updates <return-file.md>" not in skeleton.validation_commands
    assert any("durable resume context" in warning for warning in skeleton.warnings)


def test_checkpoint_applicator_skeleton_applies_with_existing_resume_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GPD_DATA_DIR", str(tmp_path / "gpd-data"))
    gpd_dir = tmp_path / "GPD"
    gpd_dir.mkdir()
    state = default_state_dict()
    (gpd_dir / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    (gpd_dir / "STATE.md").write_text(generate_state_markdown(state), encoding="utf-8")
    resume_file = gpd_dir / "phases" / "01-test-phase" / ".continue-here.md"
    resume_file.parent.mkdir(parents=True)
    resume_file.write_text("resume\n", encoding="utf-8")

    skeleton = build_gpd_return_skeleton(
        role="executor",
        status="checkpoint",
        include_applicator_fields=True,
        resume_file="GPD/phases/01-test-phase/.continue-here.md",
        project_root=tmp_path,
        phase="01",
        plan="01",
    )
    return_file = tmp_path / "return.md"
    return_file.write_text(skeleton.markdown, encoding="utf-8")

    result = cmd_apply_return_updates(tmp_path, return_file)

    assert result.passed is True
    assert result.applied_continuation_operations == ["set_bounded_segment"]
