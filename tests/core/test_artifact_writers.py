"""Tests for Typer-free artifact writer helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from gpd.core import artifact_writers
from gpd.core.errors import GPDError


def _mark_project_root(project_root: Path) -> None:
    (project_root / "GPD").mkdir(parents=True)
    (project_root / "GPD" / "state.json").write_text("{}\n", encoding="utf-8")
    (project_root / "GPD" / "PROJECT.md").write_text("# Project\n", encoding="utf-8")


def _angle_name(path: str | Path | None) -> str:
    return f"<{Path(str(path)).name}>"


def test_verification_report_output_target_resolves_payload_relative_paths_by_scope(tmp_path: Path) -> None:
    _mark_project_root(tmp_path)
    phase_dir = tmp_path / "GPD" / "phases" / "01-baseline"
    phase_dir.mkdir(parents=True)
    plan_path = phase_dir / "01-PLAN.md"
    launch_dir = tmp_path / "launch"
    launch_dir.mkdir()

    builder_target = artifact_writers.verification_report_output_target(
        None,
        payload={"target_report_path": "custom-VERIFICATION.md"},
        plan_path=plan_path,
        launch_cwd=launch_dir,
    )
    explicit_target = artifact_writers.verification_report_output_target(
        "explicit-VERIFICATION.md",
        payload={"target_report_path": "custom-VERIFICATION.md"},
        plan_path=plan_path,
        launch_cwd=launch_dir,
    )
    project_target = artifact_writers.verification_report_output_target(
        None,
        payload={"target_report_path": "GPD/phases/01-baseline/01-VERIFICATION.md"},
        plan_path=plan_path,
        launch_cwd=launch_dir,
    )

    assert builder_target == (phase_dir / "custom-VERIFICATION.md").resolve(strict=False)
    assert explicit_target == (launch_dir / "explicit-VERIFICATION.md").resolve(strict=False)
    assert project_target == (tmp_path / "GPD" / "phases" / "01-baseline" / "01-VERIFICATION.md").resolve(strict=False)


def test_proof_redteam_targets_resolve_against_launch_cwd(tmp_path: Path) -> None:
    launch_dir = tmp_path / "launch"
    launch_dir.mkdir()
    draft_path = tmp_path / "GPD" / "review" / "PROOF-REDTEAM-DRAFT.md"

    assert artifact_writers.proof_redteam_output_target(
        "review/PROOF-REDTEAM.md",
        launch_cwd=launch_dir,
    ) == (launch_dir / "review" / "PROOF-REDTEAM.md").resolve(strict=False)
    assert artifact_writers.proof_redteam_finalize_output_target(
        draft_path,
        None,
        launch_cwd=launch_dir,
    ) == draft_path.resolve(strict=False)
    assert artifact_writers.proof_redteam_finalize_output_target(
        draft_path,
        "review/final.md",
        launch_cwd=launch_dir,
    ) == (launch_dir / "review" / "final.md").resolve(strict=False)

    with pytest.raises(GPDError, match="requires --output PATH"):
        artifact_writers.proof_redteam_output_target(None, launch_cwd=launch_dir)


def test_artifact_write_blocker_preserves_force_and_parent_errors(tmp_path: Path) -> None:
    target_path = tmp_path / "artifact.md"
    target_path.write_text("existing\n", encoding="utf-8")

    assert artifact_writers.artifact_write_blocker(target_path, force=False, display_path=_angle_name) == (
        "target exists; pass --force to overwrite: <artifact.md>"
    )
    assert artifact_writers.artifact_write_blocker(target_path, force=True, display_path=_angle_name) is None

    missing_parent_target = tmp_path / "missing" / "artifact.md"
    assert (
        artifact_writers.artifact_write_blocker(
            missing_parent_target,
            force=True,
            display_path=_angle_name,
        )
        == "target parent directory does not exist: <missing>"
    )

    parent_file = tmp_path / "parent-file"
    parent_file.write_text("not a directory\n", encoding="utf-8")
    assert (
        artifact_writers.artifact_write_blocker(
            parent_file / "artifact.md",
            force=True,
            display_path=_angle_name,
        )
        == "target parent is not a directory: <parent-file>"
    )


def test_atomic_write_artifact_error_returns_payload_string_without_mutating(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target_path = tmp_path / "artifact.md"
    target_path.write_text("original\n", encoding="utf-8")

    def raise_os_error(path: Path, content: str) -> None:
        del path, content
        raise OSError("disk full")

    monkeypatch.setattr(artifact_writers, "atomic_write", raise_os_error)

    error = artifact_writers.atomic_write_artifact_error(target_path, "replacement\n")

    assert error == "failed to write target atomically: disk full"
    assert target_path.read_text(encoding="utf-8") == "original\n"


def test_verification_report_validation_payloads_keep_skip_and_parse_error_shape(tmp_path: Path) -> None:
    source_path = tmp_path / "VERIFICATION.md"

    skipped = artifact_writers.validate_verification_report_candidate(
        "not parsed in none mode",
        source_path=source_path,
        mode="none",
    )
    assert skipped["status"] == "skipped"
    assert skipped["valid"] is True
    assert skipped["errors"] == []
    assert skipped["oracle_evidence_count"] is None

    invalid = artifact_writers.validate_verification_report_candidate(
        "not frontmatter\n",
        source_path=source_path,
        mode="frontmatter",
    )
    assert invalid["status"] == "invalid"
    assert invalid["valid"] is False
    assert invalid["schema_name"] == "verification"
    assert invalid["oracle_evidence_count"] is None
    assert invalid["missing"] or invalid["errors"]


def test_recovery_payloads_preserve_body_contract_and_rerun_commands(tmp_path: Path) -> None:
    plan_path = tmp_path / "01-PLAN.md"
    target_path = tmp_path / "01-VERIFICATION.md"
    body_path = tmp_path / "BODY.md"
    patch_path = tmp_path / "patch.json"

    skeleton_recovery = artifact_writers.verification_report_write_recovery(
        plan_path=plan_path,
        target_path=target_path,
        body_path=body_path,
        validate_mode="contract",
        force=True,
        status="gaps_found",
        verified="2026-05-13T00:00:00Z",
        score="0/1 verified",
        display_path=_angle_name,
    )
    assert skeleton_recovery["safe_next_step"] == "Edit only the Markdown body file, then rerun the writer command."
    assert any("body-only Markdown" in rule for rule in skeleton_recovery["body_file_contract"])
    assert skeleton_recovery["rerun_command"] == (
        "gpd verification-report skeleton '<01-PLAN.md>' --status gaps_found --force --write --output "
        "'<01-VERIFICATION.md>' --body-file '<BODY.md>' --validate contract --verified "
        "2026-05-13T00:00:00Z --score '0/1 verified'"
    )

    finalize_recovery = artifact_writers.verification_report_finalize_recovery(
        plan_path=plan_path,
        patch_path=patch_path,
        target_path=target_path,
        body_path=body_path,
        validate_mode="contract",
        force=True,
        display_path=_angle_name,
    )
    assert (
        finalize_recovery["safe_next_step"]
        == "Edit only the typed patch or body file, then rerun the finalizer command."
    )
    assert any("canonical report" in rule for rule in finalize_recovery["body_file_contract"])
    assert finalize_recovery["rerun_command"].endswith("--validate contract --force")


def test_write_payload_builders_preserve_paths_refs_and_validation_commands(tmp_path: Path) -> None:
    verification_target = tmp_path / "GPD" / "phases" / "01" / "01-VERIFICATION.md"
    verification_payload = artifact_writers.verification_report_write_payload(
        target_path=verification_target,
        target_ref="GPD/phases/01/01-VERIFICATION.md",
        force=True,
        body_path=tmp_path / "BODY.md",
        warnings=["frontmatter-only"],
        validation_commands=["gpd validate verification-contract GPD/phases/01/01-VERIFICATION.md"],
        patch_file_path=tmp_path / "patch.json",
    )

    assert verification_payload["written"] is False
    assert verification_payload["target_report_path"] == str(verification_target)
    assert verification_payload["target_report_ref"] == "GPD/phases/01/01-VERIFICATION.md"
    assert verification_payload["force"] is True
    assert verification_payload["patch_file"] == str(tmp_path / "patch.json")
    not_run = artifact_writers.verification_report_validation_not_run(
        "contract",
        "failed to write target atomically: disk full",
    )
    assert not_run["valid"] is False
    assert not_run["errors"] == ["failed to write target atomically: disk full"]

    proof_target = tmp_path / "PROOF-REDTEAM.md"
    proof_payload = artifact_writers.proof_redteam_write_not_run(
        "failed to write target atomically: disk full",
        target_path=proof_target,
        force=False,
    )
    assert proof_payload["written"] is False
    assert proof_payload["target_path"] == str(proof_target)
    assert proof_payload["error"] == "failed to write target atomically: disk full"
    assert proof_payload["validation_commands"] == [f"gpd validate proof-redteam {proof_target}"]
