"""Assertions for arxiv submission prompt/workflow alignment."""

from __future__ import annotations

import json
import re
import tarfile
from pathlib import Path

from typer.testing import CliRunner

from gpd.cli import app
from gpd.core.arxiv_package import ARXIV_TARBALL_NAME, validate_arxiv_package
from gpd.core.workflow_staging import resolve_workflow_stage_manifest_path, validate_workflow_stage_manifest_payload
from tests.lifecycle_contract_test_support import (
    assert_forbidden_lifecycle_prose as _assert_forbidden_semantic,
)
from tests.lifecycle_contract_test_support import (
    assert_semantic_contract as _assert_semantic,
)
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = REPO_ROOT / "src/gpd/commands"
WORKFLOWS_DIR = REPO_ROOT / "src/gpd/specs/workflows"
runner = CliRunner()

_SHELL_VAR_REFERENCE_RE = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)(?::-[^}]*)?\}|([A-Za-z_][A-Za-z0-9_]*))")
_SHELL_ASSIGNMENT_RE = re.compile(r"(?:^\s*|[;&]\s*|then\s+)(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=")
_ARXIV_STAGE_SHELL_AMBIENT = frozenset(
    {
        "ARGUMENTS",
    }
)


def _check_by_name(result: object, name: str) -> object:
    return next(check for check in result.checks if check.name == name)


def _make_arxiv_submission_fixture(
    tmp_path: Path,
    *,
    files: dict[str, str],
    subject_slug: str = "paper",
) -> Path:
    submission_dir = tmp_path / "GPD" / "publication" / subject_slug / "arxiv" / "submission"
    submission_dir.mkdir(parents=True)
    for rel_path, content in files.items():
        target = submission_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return submission_dir


def _validate_paper_arxiv_submission(tmp_path: Path):
    return validate_arxiv_package(
        project_root=tmp_path,
        subject_slug="paper",
        manuscript_entrypoint="paper/main.tex",
    )


def _assert_arxiv_command_wrapper_semantics(command: str) -> None:
    _assert_semantic(
        command,
        "arxiv command wrapper delegates to staged bootstrap",
        "included arxiv-submission bootstrap authority",
        "workflow resolves the active GPD-owned manuscript root",
        "standalone interactive intake",
        "arbitrary external directories",
    )


def _assert_arxiv_manuscript_root_semantics(workflow: str) -> None:
    _assert_semantic(
        workflow,
        "arxiv workflow resolves manuscript root from preflight without globbing",
        "shared publication bootstrap reference",
        "source of truth",
        "STOP",
        "explicit manuscript path",
        "repaired manuscript-root state",
        "supported roots",
        "arbitrary external directories",
        "standalone `.tex` entrypoints",
        "wildcard matching",
    )


def _assert_arxiv_package_gate_semantics(workflow: str) -> None:
    _assert_semantic(
        workflow,
        "arxiv executable package gate preserves review and manuscript boundaries",
        "executable package boundary",
        "reruns strict",
        "validator must pass",
        "strict manuscript preflight",
        "review_gate latest-round checks",
        "response freshness",
        "gpd:peer-review",
        "proof-review manifests",
        "tarballs beside the manuscript root",
    )


def _assert_missing_bibliography_material(tex_check: object) -> None:
    assert tex_check.name == "submission_tex_ready"
    assert tex_check.passed is False
    detail = tex_check.detail
    assert ".bib" in detail
    assert ".bbl" in detail
    assert "inlined bibliography" in detail


def _shell_variables_referenced(source: str) -> set[str]:
    return {braced or bare for braced, bare in _SHELL_VAR_REFERENCE_RE.findall(source) if (braced or bare)}


def _shell_variables_assigned(source: str) -> set[str]:
    return {match.group(1) for line in source.splitlines() for match in _SHELL_ASSIGNMENT_RE.finditer(line)}


def test_arxiv_submission_command_declares_manuscript_root_gates_without_first_match_discovery() -> None:
    command = (COMMANDS_DIR / "arxiv-submission.md").read_text(encoding="utf-8")

    assert "context_mode: project-aware" in command
    assert "command-policy:" in command
    assert "allow_external_subjects: false" in command
    assert "allow_interactive_without_subject: false" in command
    assert "bootstrap_allowed: false" in command
    assert "default_output_subtree: GPD/publication/{subject_slug}/arxiv" in command
    assert "paper/*.tex" in command
    assert "manuscript/*.tex" in command
    assert "draft/*.tex" in command
    assert "GPD/publication/*/manuscript/*.tex" in command
    assert "manuscript-root artifact manifest" in command
    assert "manuscript-root bibliography audit" in command
    _assert_arxiv_command_wrapper_semantics(command)
    assert "artifact_manifest" in command
    assert "bibliography_audit" in command
    assert "bibliography_audit_clean" in command
    assert "$ARGUMENTS" in command
    assert ".tex" in command
    assert "scope_variants:" not in command
    assert "@{GPD_INSTALL_DIR}/templates/paper/publication-manuscript-root-preflight.md" not in command
    assert "@{GPD_INSTALL_DIR}/references/publication/publication-review-round-artifacts.md" not in command
    assert "@{GPD_INSTALL_DIR}/references/publication/publication-response-artifacts.md" not in command
    assert "@{GPD_INSTALL_DIR}/references/publication/publication-bootstrap-preflight.md" not in command


def test_arxiv_submission_workflow_resolves_manifest_based_manuscript_root_without_globbing() -> None:
    workflow = workflow_authority_text(WORKFLOWS_DIR, "arxiv-submission")

    assert "gpd --raw init arxiv-submission --stage bootstrap" in workflow
    assert 'gpd --raw init arxiv-submission --stage bootstrap -- "$ARGUMENTS"' in workflow
    assert 'gpd --raw init arxiv-submission --stage manuscript_preflight -- "$ARGUMENTS"' in workflow
    assert 'gpd --raw init arxiv-submission --stage review_gate -- "$ARGUMENTS"' in workflow
    assert 'gpd --raw init arxiv-submission --stage package -- "$ARGUMENTS"' in workflow
    assert 'gpd --raw init arxiv-submission --stage finalize -- "$ARGUMENTS"' in workflow
    assert "metadata-only" not in workflow
    _assert_arxiv_manuscript_root_semantics(workflow)
    assert "{GPD_INSTALL_DIR}/references/publication/publication-bootstrap-preflight.md" in workflow
    assert "{GPD_INSTALL_DIR}/references/publication/publication-review-round-artifacts.md" in workflow
    assert "{GPD_INSTALL_DIR}/references/publication/peer-review-reliability.md" not in workflow
    assert "staged `peer-review-reliability.md` reference" in workflow
    assert "@{GPD_INSTALL_DIR}/references/publication/publication-response-artifacts.md" not in workflow
    assert "@{GPD_INSTALL_DIR}/references/publication/publication-response-writer-handoff.md" not in workflow
    assert "ARTIFACT-MANIFEST.json" in workflow
    assert "BIBLIOGRAPHY-AUDIT.json" in workflow
    assert "bibliography_audit_clean" in workflow
    assert "gpd paper-build" in workflow
    assert "manuscript_entrypoint" in workflow
    assert "manuscript_root" in workflow
    assert "GPD/publication/<subject_slug>/manuscript/" in workflow
    assert 'PACKAGE_ROOT="${PUBLICATION_ROOT}/arxiv"' in workflow
    assert 'PACKAGE_TARBALL="${PACKAGE_ROOT}/arxiv-submission.tar.gz"' in workflow
    assert "executable_gate:" in workflow
    assert "id: arxiv_package_validator" in workflow
    assert "role: arxiv-package-validator" in workflow
    assert "GPD/publication/${SUBJECT_SLUG}/arxiv/arxiv-submission.tar.gz" in workflow
    _assert_arxiv_package_gate_semantics(workflow)
    assert (
        'gpd --raw validate arxiv-package --materialize --submission-dir "$SUBMISSION_DIR" --tarball "$PACKAGE_TARBALL"'
        in workflow
    )
    assert (
        'gpd --raw validate arxiv-package --submission-dir "$SUBMISSION_DIR" --tarball "$PACKAGE_TARBALL"'
        in workflow
    )
    assert "latest-response discovery" in workflow
    _assert_forbidden_semantic(
        workflow,
        "arxiv workflow avoids stale latest-response clearance prose",
        "latest response artifacts already reached",
    )
    assert "must not persist `PROOF-REVIEW-MANIFEST.json` beside the manuscript root" in workflow
    assert "failed `response_freshness` check" in workflow
    assert "checkpoint as `response_gate`" in workflow
    _assert_forbidden_semantic(
        workflow,
        "arxiv workflow avoids explicit external manuscript subject mode",
        "Even for an explicit external manuscript subject",
    )
    assert 'ls "${DIR}"/*.tex' not in workflow


def test_arxiv_submission_stage_files_bind_shell_variables_locally() -> None:
    offenders: list[str] = []

    for stage_path in sorted((WORKFLOWS_DIR / "arxiv-submission").glob("*.md")):
        source = stage_path.read_text(encoding="utf-8")
        allowed = _shell_variables_assigned(source) | _ARXIV_STAGE_SHELL_AMBIENT
        for variable in sorted(_shell_variables_referenced(source) - allowed):
            offenders.append(f"{stage_path.name}:${variable}")

    assert offenders == []


def test_arxiv_submission_stage_manifest_path_is_resolved_and_loadable() -> None:
    manifest_path = resolve_workflow_stage_manifest_path("arxiv-submission")

    assert manifest_path == WORKFLOWS_DIR / "arxiv-submission-stage-manifest.json"
    assert manifest_path.exists()

    manifest = validate_workflow_stage_manifest_payload(
        json.loads(manifest_path.read_text(encoding="utf-8")),
        expected_workflow_id="arxiv-submission",
    )

    assert manifest.prompt_usage == "staged_init"
    assert manifest.stage_ids() == (
        "bootstrap",
        "manuscript_preflight",
        "review_gate",
        "package",
        "finalize",
    )
    for stage_id in manifest.stage_ids():
        assert "arxiv_submission_argument_input" in manifest.stage(stage_id).required_init_fields
    assert manifest.stage("bootstrap").loaded_authorities[0] == "workflows/arxiv-submission/bootstrap.md"
    assert "workflows/arxiv-submission.md" in manifest.stage("bootstrap").must_not_eager_load
    assert "workflows/arxiv-submission/manuscript-preflight.md" in manifest.stage("bootstrap").must_not_eager_load
    assert "references/publication/publication-bootstrap-preflight.md" in manifest.stage("bootstrap").loaded_authorities
    assert "managed publication output root state" in manifest.stage("bootstrap").produced_state
    assert manifest.stage("manuscript_preflight").loaded_authorities[0] == (
        "workflows/arxiv-submission/manuscript-preflight.md"
    )
    assert (
        "references/publication/publication-review-round-artifacts.md"
        in manifest.stage("review_gate").loaded_authorities
    )
    assert manifest.stage("review_gate").loaded_authorities[0] == "workflows/arxiv-submission/review-gate.md"
    assert "references/publication/peer-review-reliability.md" not in manifest.stage("review_gate").loaded_authorities
    assert {
        conditional.when: conditional.authorities
        for conditional in manifest.stage("review_gate").conditional_authorities
    } == {
        "review_integrity_recovery_needed": ("references/publication/peer-review-reliability.md",),
    }
    assert "references/publication/peer-review-reliability.md" in manifest.stage("review_gate").must_not_eager_load
    assert (
        "references/publication/publication-response-writer-handoff.md"
        not in manifest.stage("review_gate").loaded_authorities
    )
    assert manifest.stage("package").loaded_authorities == ("workflows/arxiv-submission/package.md",)
    assert manifest.stage("finalize").loaded_authorities == ("workflows/arxiv-submission/finalize.md",)
    assert manifest.stage("package").writes_allowed == ("GPD/publication/{subject_slug}/arxiv",)
    assert manifest.stage("finalize").writes_allowed == ("GPD/publication/{subject_slug}/arxiv",)


def test_arxiv_submission_staged_init_marks_external_target_invalid(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "GPD").mkdir()
    (tmp_path / "GPD" / "PROJECT.md").write_text("# Project\n\nSubmission target.\n", encoding="utf-8")
    external_dir = tmp_path / "external-paper"
    external_dir.mkdir()
    (external_dir / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}External draft.\\end{document}\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "--raw",
            "init",
            "arxiv-submission",
            "--stage",
            "bootstrap",
            "--",
            "external-paper/main.tex",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["manuscript_resolution_status"] == "invalid"
    assert "explicit manuscript target must stay under" in payload["manuscript_resolution_detail"]
    assert payload["manuscript_root"] is None
    assert payload["manuscript_entrypoint"] is None
    assert payload["publication_subject_slug"] is None
    assert payload["selected_publication_root"] is None
    assert payload["selected_review_root"] is None


def test_arxiv_package_validator_detects_citations_in_included_tex_files(tmp_path: Path) -> None:
    _make_arxiv_submission_fixture(
        tmp_path,
        files={
            "main.tex": "\\documentclass{article}\\begin{document}\\input{section}\\end{document}\n",
            "section.tex": "The result follows prior work \\cite{known-result}.\n",
        },
    )

    result = _validate_paper_arxiv_submission(tmp_path)

    tex_check = _check_by_name(result, "submission_tex_ready")
    _assert_missing_bibliography_material(tex_check)


def test_arxiv_package_validator_fails_tex_ready_when_root_entrypoint_is_not_packaged_tex(
    tmp_path: Path,
) -> None:
    _make_arxiv_submission_fixture(
        tmp_path,
        files={
            "unrelated.tex": "\\documentclass{article}\\begin{document}Unrelated.\\end{document}\n",
        },
    )

    result = _validate_paper_arxiv_submission(tmp_path)

    entrypoint_check = _check_by_name(result, "submission_entrypoint_at_root")
    tex_check = _check_by_name(result, "submission_tex_ready")
    assert entrypoint_check.passed is False
    assert tex_check.passed is False
    assert "main.tex is not a packaged root-level TeX entrypoint" in tex_check.detail


def test_arxiv_package_validator_rejects_unreferenced_bib_source_material(tmp_path: Path) -> None:
    _make_arxiv_submission_fixture(
        tmp_path,
        files={
            "main.tex": (
                "\\documentclass{article}\\begin{document}\n"
                "Citation \\cite{known-result}.\\bibliographystyle{plain}\\bibliography{refs}\n"
                "\\end{document}\n"
            ),
            "stale.bib": "@article{known-result,title={Known Result}}\n",
        },
    )

    result = _validate_paper_arxiv_submission(tmp_path)

    tex_check = _check_by_name(result, "submission_tex_ready")
    _assert_missing_bibliography_material(tex_check)


def test_arxiv_package_validator_rejects_bibliography_only_in_unreachable_tex(tmp_path: Path) -> None:
    _make_arxiv_submission_fixture(
        tmp_path,
        files={
            "main.tex": "\\documentclass{article}\\begin{document}Citation \\cite{known-result}.\\end{document}\n",
            "unused.tex": "\\begin{thebibliography}{1}\n\\bibitem{known-result} Known Result.\n\\end{thebibliography}\n",
        },
    )

    result = _validate_paper_arxiv_submission(tmp_path)

    tex_check = _check_by_name(result, "submission_tex_ready")
    _assert_missing_bibliography_material(tex_check)


def test_arxiv_package_validator_accepts_included_tex_bibliography_material(tmp_path: Path) -> None:
    _make_arxiv_submission_fixture(
        tmp_path,
        files={
            "main.tex": "\\documentclass{article}\\begin{document}\\input{section}\\end{document}\n",
            "section.tex": (
                "The result follows prior work \\cite{known-result}.\n"
                "\\begin{thebibliography}{1}\n"
                "\\bibitem{known-result} Known Result.\n"
                "\\end{thebibliography}\n"
            ),
        },
    )

    result = _validate_paper_arxiv_submission(tmp_path)

    assert _check_by_name(result, "submission_tex_ready").passed is True


def test_arxiv_package_validator_accepts_packaged_bib_source_material(tmp_path: Path) -> None:
    _make_arxiv_submission_fixture(
        tmp_path,
        files={
            "main.tex": (
                "\\documentclass{article}\\begin{document}\n"
                "Citation \\cite{known-result}.\\bibliographystyle{plain}\\bibliography{refs}\n"
                "\\end{document}\n"
            ),
            "refs.bib": "@article{known-result,title={Known Result}}\n",
        },
    )

    result = _validate_paper_arxiv_submission(tmp_path)

    assert _check_by_name(result, "submission_tree_excludes_auxiliary_files").passed is True
    assert _check_by_name(result, "submission_tex_ready").passed is True


def test_arxiv_package_validator_accepts_root_jobname_bbl_for_bibtex_bibliography(
    tmp_path: Path,
) -> None:
    _make_arxiv_submission_fixture(
        tmp_path,
        files={
            "main.tex": (
                "\\documentclass{article}\\begin{document}\n"
                "Citation \\cite{known-result}.\\bibliographystyle{plain}\\bibliography{refs}\n"
                "\\end{document}\n"
            ),
            "main.bbl": "\\begin{thebibliography}{1}\\bibitem{known-result} Known Result.\\end{thebibliography}\n",
        },
    )

    result = _validate_paper_arxiv_submission(tmp_path)

    assert _check_by_name(result, "submission_tex_ready").passed is True


def test_arxiv_package_validator_rejects_bibliography_target_bbl_without_root_jobname_bbl(
    tmp_path: Path,
) -> None:
    _make_arxiv_submission_fixture(
        tmp_path,
        files={
            "main.tex": (
                "\\documentclass{article}\\begin{document}\n"
                "Citation \\cite{known-result}.\\bibliographystyle{plain}\\bibliography{refs}\n"
                "\\end{document}\n"
            ),
            "refs.bbl": "\\begin{thebibliography}{1}\\bibitem{known-result} Known Result.\\end{thebibliography}\n",
        },
    )

    result = _validate_paper_arxiv_submission(tmp_path)

    tex_check = _check_by_name(result, "submission_tex_ready")
    assert tex_check.passed is False
    assert "citation commands but no packaged .bib, packaged .bbl, or inlined bibliography material" in tex_check.detail


def test_arxiv_package_materialize_refuses_submission_tree_outside_managed_root(tmp_path: Path) -> None:
    outside_submission_dir = tmp_path / "outside-submission"
    outside_submission_dir.mkdir()
    (outside_submission_dir / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}Ready.\\end{document}\n",
        encoding="utf-8",
    )
    tarball = tmp_path / "GPD" / "publication" / "paper" / "arxiv" / ARXIV_TARBALL_NAME

    result = validate_arxiv_package(
        project_root=tmp_path,
        subject_slug="paper",
        manuscript_entrypoint="paper/main.tex",
        submission_dir=outside_submission_dir,
        tarball=tarball,
        materialize=True,
    )

    assert result.materialized is False
    assert not tarball.exists()
    assert _check_by_name(result, "submission_dir_under_managed_arxiv_root").passed is False
    assert _check_by_name(result, "tarball_materialized").passed is False


def test_arxiv_package_validator_rejects_unsafe_publication_subject_slug(tmp_path: Path) -> None:
    submission_dir = tmp_path / "GPD" / "escape" / "arxiv" / "submission"
    submission_dir.mkdir(parents=True)
    (submission_dir / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}Ready.\\end{document}\n",
        encoding="utf-8",
    )
    tarball = tmp_path / "GPD" / "escape" / "arxiv" / ARXIV_TARBALL_NAME
    with tarfile.open(tarball, "w:gz") as archive:
        archive.add(submission_dir / "main.tex", arcname="main.tex", recursive=False)

    result = validate_arxiv_package(
        project_root=tmp_path,
        subject_slug="../escape",
        manuscript_entrypoint="paper/main.tex",
        submission_dir=submission_dir,
        tarball=tarball,
    )

    check = _check_by_name(result, "managed_arxiv_root")
    assert check.passed is False
    assert "publication subject slug" in check.detail


def test_arxiv_package_materialize_refuses_invalid_in_tree_subject_slug(tmp_path: Path) -> None:
    submission_dir = tmp_path / "GPD" / "publication" / "bad slug" / "arxiv" / "submission"
    submission_dir.mkdir(parents=True)
    (submission_dir / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}Ready.\\end{document}\n",
        encoding="utf-8",
    )
    tarball = tmp_path / "GPD" / "publication" / "bad slug" / "arxiv" / ARXIV_TARBALL_NAME

    result = validate_arxiv_package(
        project_root=tmp_path,
        subject_slug="bad slug",
        manuscript_entrypoint="paper/main.tex",
        submission_dir=submission_dir,
        tarball=tarball,
        materialize=True,
    )

    assert result.materialized is False
    assert not tarball.exists()
    assert _check_by_name(result, "managed_arxiv_root").passed is False
    assert _check_by_name(result, "tarball_materialized").passed is False
