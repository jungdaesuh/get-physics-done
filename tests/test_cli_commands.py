"""Smoke tests for EVERY `gpd` CLI command.

Ensures every command can be invoked without crashing in a valid project
directory. This catches the class of bug where CLI functions pass a Path to
core functions that expect a domain object (e.g. convention_check receiving
a Path instead of ConventionLock).

Each test invokes the command with minimal valid arguments. If the command
exits 0, the type plumbing is correct. These are NOT functional tests —
they verify the CLI → core function argument wiring works.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import gpd.cli as cli_module
import gpd.registry as registry_module
from gpd.adapters.runtime_catalog import iter_runtime_descriptors, list_runtime_names
from gpd.cli import app
from gpd.command_labels import rewrite_runtime_command_surfaces, runtime_command_surface_pattern
from gpd.core import help_renderer
from gpd.core.artifact_text import PEER_REVIEW_ARTIFACT_SUFFIXES
from gpd.core.command_preflight import _command_managed_output_context_root, _command_managed_output_root
from gpd.core.command_subjects import _command_context_manuscript_check, _command_required_files_override_detail
from gpd.core.recent_projects import record_recent_project
from gpd.core.reproducibility import compute_sha256
from gpd.core.state import StateUpdateResult, default_state_dict, generate_state_markdown
from gpd.registry import _parse_command_file
from scripts.render_help_surface import extract_help_surface_region
from tests.helpers.cli import (
    StableCliRunner,
    assert_check,
    assert_checks_pass,
    assert_no_traceback,
    checks_by_name,
    invoke_cli,
    invoke_help_text,
    invoke_raw_json,
    json_output_from_result,
)
from tests.helpers.cli import (
    fake_pypdf_failure_module as _fake_pypdf_failure_module,
)
from tests.helpers.cli import (
    fake_pypdf_module as _fake_pypdf_module,
)
from tests.helpers.cli import (
    refresh_artifact_manifest_for_manuscript as _refresh_artifact_manifest_for_manuscript,
)
from tests.helpers.cli import (
    write_binary_pdf as _write_binary_pdf,
)
from tests.helpers.cli import (
    write_internal_publication_artifacts as _write_internal_publication_artifacts,
)
from tests.helpers.cli import (
    write_managed_publication_manuscript as _write_managed_publication_manuscript,
)
from tests.helpers.cli import (
    write_minimal_docx as _write_minimal_docx,
)
from tests.helpers.cli import (
    write_minimal_xlsx as _write_minimal_xlsx,
)
from tests.helpers.cli import (
    write_secondary_manuscript_root as _write_secondary_manuscript_root,
)
from tests.helpers.cli import (
    write_write_paper_authoring_input as _write_write_paper_authoring_input,
)
from tests.manuscript_test_support import (
    CANONICAL_MANUSCRIPT_STEM,
    write_proof_review_package,
)
from tests.manuscript_test_support import (
    manuscript_path as canonical_manuscript_path,
)
from tests.manuscript_test_support import (
    manuscript_relpath as canonical_manuscript_relpath,
)
from tests.project_test_support import write_cli_smoke_project
from tests.review_contract_test_support import (
    PEER_REVIEW_COMMON_PREFLIGHT_CHECKS,
    PROJECT_BACKED_PEER_REVIEW_CONDITIONAL,
    THEOREM_BEARING_PEER_REVIEW_CONDITIONAL,
)
from tests.review_test_support import (
    move_publication_review_outcome_to_subject_review as _move_publication_review_outcome_to_subject_review,
)
from tests.review_test_support import (
    prepare_accepted_managed_arxiv_subject as _prepare_accepted_managed_arxiv_subject,
)
from tests.review_test_support import (
    update_claim_index_claim as _update_claim_index_claim,
)
from tests.review_test_support import (
    write_draft_knowledge_document as _write_draft_knowledge_document,
)
from tests.review_test_support import (
    write_managed_arxiv_submission_package as _write_managed_arxiv_submission_package,
)
from tests.review_test_support import (
    write_publication_response_round as _write_publication_response_round,
)
from tests.review_test_support import (
    write_publication_review_outcome as _write_publication_review_outcome,
)
from tests.review_test_support import (
    write_review_stage_artifacts as _write_review_stage_artifacts,
)

runner = StableCliRunner()


def _assert_text_contains(text: str, fragments: tuple[str, ...]) -> None:
    for fragment in fragments:
        assert fragment in text


def _assert_text_excludes(text: str, fragments: tuple[str, ...]) -> None:
    for fragment in fragments:
        assert fragment not in text


def _help_text(*args: str, expect_exit: int = 0, **kwargs) -> str:
    return invoke_help_text(runner, app, args, expect_exit=expect_exit, **kwargs)


def test_runtime_command_surface_pattern_does_not_truncate_markdown_filenames() -> None:
    """Command-label rewriting must not treat command markdown filenames as command invocations."""
    pattern = runtime_command_surface_pattern()

    assert pattern.search("gpd:record-backtrack.md") is None
    assert pattern.search("/gpd:record-backtrack.md") is None
    assert rewrite_runtime_command_surfaces("Read gpd:record-backtrack.md") == "Read gpd:record-backtrack.md"
    assert (
        rewrite_runtime_command_surfaces("Run gpd:record-backtrack now", canonical="command")
        == "Run gpd:record-backtrack now"
    )


def test_route_and_backtrack_public_command_metadata_is_dispatchable() -> None:
    """New runtime commands should advertise the args/tools their workflows actually require."""
    registry_module.invalidate_cache()

    route = registry_module.get_command("route")
    backtrack = registry_module.get_command("record-backtrack")

    assert route.argument_hint == "[--frozen=yes|no] [--change=extend|revise] [--layer=new|change]"
    assert "ask_user" in backtrack.allowed_tools


def test_progress_reconcile_public_metadata_exposes_confirmation_tool() -> None:
    """The runtime reconcile mode must have an executable confirmation path before state writes."""
    registry_module.invalidate_cache()

    command = registry_module.get_command("progress")

    assert "ask_user" in command.allowed_tools


def test_write_paper_public_metadata_only_advertises_intake_manifest() -> None:
    """write-paper should not advertise unsupported title/topic or from-phases inputs."""
    registry_module.invalidate_cache()

    command = registry_module.get_command("write-paper")
    subject_policy = command.command_policy.subject_policy

    assert command.argument_hint == "[--intake path/to/write-paper-authoring-input.json]"
    assert subject_policy.explicit_input_kinds == ["authoring_intake_manifest"]
    assert "paper_title_or_topic" not in command.content
    assert "from_phases_flag" not in command.content


@pytest.mark.parametrize("command_name", ["research-phase", "list-phase-assumptions"])
def test_phase_required_input_command_metadata_is_not_optional(command_name: str) -> None:
    registry_module.invalidate_cache()

    command = registry_module.get_command(command_name)
    subject_policy = command.command_policy.subject_policy

    assert command.argument_hint == "<phase-number>"
    assert subject_policy.subject_kind == "phase"
    assert subject_policy.resolution_mode == "phase_number"
    assert subject_policy.explicit_input_kinds == ["phase-number"]
    assert subject_policy.allow_interactive_without_subject is False


def test_peer_review_public_metadata_uses_canonical_artifact_suffixes() -> None:
    """Peer-review frontmatter must stay aligned with the artifact text/resolver suffix set."""
    registry_module.invalidate_cache()

    command = registry_module.get_command("peer-review")
    subject_policy = command.command_policy.subject_policy

    assert frozenset(subject_policy.allowed_suffixes) == PEER_REVIEW_ARTIFACT_SUFFIXES


def test_health_runtime_wrapper_accepts_unhealthy_json_exit_status() -> None:
    """Runtime prompt must parse raw health JSON even when the CLI uses exit 1 for fail."""
    health_command = (Path(__file__).resolve().parents[1] / "src/gpd/commands/health.md").read_text(encoding="utf-8")

    assert "HEALTH_STATUS=$?" in health_command
    assert "Do not treat a nonzero `HEALTH_STATUS` as a wrapper failure" in health_command
    assert "parses as the valid report JSON" in health_command
    assert 'echo "ERROR: health check failed: $HEALTH"' not in health_command


def _command_with_analysis_output_policy(command_name: str):
    command = registry_module.get_command(command_name)
    command_policy = command.command_policy or registry_module.CommandPolicy()
    return dataclasses.replace(
        command,
        command_policy=dataclasses.replace(
            command_policy,
            output_policy=registry_module.CommandOutputPolicy(
                output_mode="subtree",
                managed_root_kind="gpd_managed_durable",
                default_output_subtree="GPD/analysis",
                stage_artifact_policy="disallowed",
            ),
        ),
    )


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "stage0"
_RUNTIME_DESCRIPTORS = iter_runtime_descriptors()
_PRIMARY_RAW_RUNTIME_DESCRIPTOR = _RUNTIME_DESCRIPTORS[0]
_CANONICAL_MANUSCRIPT_REL = canonical_manuscript_relpath()
_CANONICAL_MANUSCRIPT_BASENAME = f"{CANONICAL_MANUSCRIPT_STEM}.tex"
_CANONICAL_MANUSCRIPT_PDF_BASENAME = f"{CANONICAL_MANUSCRIPT_STEM}.pdf"
_CANONICAL_MARKDOWN_BASENAME = f"{CANONICAL_MANUSCRIPT_STEM}.md"


def _project_contract_fixture() -> dict[str, object]:
    return json.loads((FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"))


def _write_project_contract_to_state(
    project_root: Path,
    *,
    recoverable_schema_drift: bool = False,
) -> dict[str, object]:
    contract = _project_contract_fixture()
    if recoverable_schema_drift:
        contract["claims"][0]["notes"] = "recoverable drift"
    state_path = project_root / "GPD" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["project_contract"] = contract
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return contract


_ALIASABLE_RUNTIME_DESCRIPTOR = next(
    descriptor
    for descriptor in _RUNTIME_DESCRIPTORS
    if any(alias != descriptor.runtime_name for alias in descriptor.selection_aliases)
)
_DOLLAR_COMMAND_DESCRIPTOR = next(
    descriptor
    for descriptor in _RUNTIME_DESCRIPTORS
    if descriptor.validated_command_surface == "public_runtime_dollar_command"
)
_SLASH_COMMAND_DESCRIPTOR = next(
    descriptor
    for descriptor in _RUNTIME_DESCRIPTORS
    if descriptor.validated_command_surface == "public_runtime_slash_command"
    and descriptor.runtime_name != _DOLLAR_COMMAND_DESCRIPTOR.runtime_name
)


@pytest.fixture()
def dollar_command_prefix(monkeypatch: pytest.MonkeyPatch) -> str:
    """Force the CLI preflight helpers to resolve the dollar-command runtime."""
    monkeypatch.setattr("gpd.cli.detect_runtime_for_gpd_use", lambda cwd=None: _DOLLAR_COMMAND_DESCRIPTOR.runtime_name)
    return _DOLLAR_COMMAND_DESCRIPTOR.public_command_surface_prefix


@pytest.fixture()
def slash_command_prefix(monkeypatch: pytest.MonkeyPatch) -> str:
    """Force the CLI preflight helpers to resolve the slash-command runtime."""
    monkeypatch.setattr("gpd.cli.detect_runtime_for_gpd_use", lambda cwd=None: _SLASH_COMMAND_DESCRIPTOR.runtime_name)
    return _SLASH_COMMAND_DESCRIPTOR.public_command_surface_prefix


@pytest.fixture()
def gpd_project(tmp_path: Path) -> Path:
    return write_cli_smoke_project(tmp_path)


@pytest.fixture(autouse=True)
def _chdir(gpd_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """All tests run from the project directory."""
    monkeypatch.chdir(gpd_project)


def _invoke(*args: str, expect_ok: bool = True) -> None:
    """Invoke a gpd CLI command and assert it doesn't crash."""
    invoke_cli(runner, app, args, expect_exit=0 if expect_ok else None, catch_exceptions=False)


def _raw_json(args: list[str], *, expect_exit: int = 0, **kwargs: object) -> dict[str, object]:
    return invoke_raw_json(runner, app, args, expect_exit=expect_exit, catch_exceptions=False, **kwargs)


def _manuscript_entrypoint_path(
    project_root: Path,
    *,
    root_name: str = "paper",
    suffix: str = ".tex",
) -> Path:
    return project_root / root_name / f"{CANONICAL_MANUSCRIPT_STEM}{suffix}"


def _manuscript_entrypoint_relpath(
    *,
    root_name: str = "paper",
    suffix: str = ".tex",
) -> str:
    return f"{root_name}/{CANONICAL_MANUSCRIPT_STEM}{suffix}"


# ═══════════════════════════════════════════════════════════════════════════
# Convention commands — the original bug class
# ═══════════════════════════════════════════════════════════════════════════


class TestConventionCommands:
    def test_set_persists(self, gpd_project: Path) -> None:
        _invoke("convention", "set", "fourier_convention", "physics")
        state = json.loads((gpd_project / "GPD" / "state.json").read_text())
        assert state["convention_lock"]["fourier_convention"] == "physics"


# ═══════════════════════════════════════════════════════════════════════════
# State commands
# ═══════════════════════════════════════════════════════════════════════════


class TestStateCommands:
    def test_set_project_contract(self, gpd_project: Path) -> None:
        contract_path = gpd_project / "contract.json"
        contract_path.write_text(
            (FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        _invoke("state", "set-project-contract", str(contract_path))
        state = json.loads((gpd_project / "GPD" / "state.json").read_text(encoding="utf-8"))
        assert state["project_contract"]["scope"]["question"] == "What benchmark must the project recover?"

    def test_set_project_contract_raw_surfaces_warnings_on_success(self, gpd_project: Path) -> None:
        contract = json.loads((FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"))
        contract["references"][0]["must_surface"] = False
        contract_path = gpd_project / "warning-contract.json"
        contract_path.write_text(json.dumps(contract), encoding="utf-8")

        payload = _raw_json(
            ["--cwd", str(gpd_project), "--raw", "state", "set-project-contract", str(contract_path)],
        )
        assert payload["updated"] is True
        assert any(
            "references must include at least one must_surface=true anchor" in warning
            for warning in payload["warnings"]
        )

    def test_set_project_contract_rejects_semantically_invalid_contract(self, gpd_project: Path) -> None:
        contract = json.loads((FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"))
        contract["uncertainty_markers"]["weakest_anchors"] = []
        contract["uncertainty_markers"]["disconfirming_observations"] = []
        contract_path = gpd_project / "invalid-contract.json"
        contract_path.write_text(json.dumps(contract), encoding="utf-8")

        payload = _raw_json(
            ["--raw", "state", "set-project-contract", str(contract_path)],
            expect_exit=1,
        )
        assert payload["valid"] is False
        assert any("weakest_anchors" in error for error in payload["errors"])

    def test_set_project_contract_rejects_singleton_list_drift_at_write_boundary(self, gpd_project: Path) -> None:
        contract = json.loads((FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"))
        contract["context_intake"]["must_read_refs"] = "ref-benchmark"
        contract_path = gpd_project / "invalid-contract.json"
        contract_path.write_text(json.dumps(contract), encoding="utf-8")

        payload = _raw_json(
            ["--raw", "state", "set-project-contract", str(contract_path)],
            expect_exit=1,
        )
        assert payload["updated"] is False
        assert (
            payload["reason"]
            == "Invalid project contract schema: context_intake.must_read_refs must be a list, not str"
        )
        assert payload["warnings"] == []
        assert payload["schema_reference"] == "templates/project-contract-schema.md"
        state = json.loads((gpd_project / "GPD" / "state.json").read_text(encoding="utf-8"))
        assert state["project_contract"] is None

    def test_set_project_contract_exits_nonzero_on_hard_backend_rejection(
        self,
        gpd_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        contract_path = gpd_project / "contract.json"
        contract_path.write_text(
            (FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        def _reject_contract(cwd: Path, contract_data: object) -> StateUpdateResult:
            return StateUpdateResult(
                updated=False,
                reason="Backend rejected project contract: missing required anchor",
            )

        monkeypatch.setattr("gpd.core.state.state_set_project_contract", _reject_contract)

        payload = _raw_json(
            ["--cwd", str(gpd_project), "--raw", "state", "set-project-contract", str(contract_path)],
            expect_exit=1,
        )
        assert payload["updated"] is False
        assert payload["reason"] == "Backend rejected project contract: missing required anchor"

    def test_set_project_contract_keeps_benign_noop_exit_zero(
        self,
        gpd_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        contract_path = gpd_project / "contract.json"
        contract_path.write_text(
            (FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        def _noop_contract(cwd: Path, contract_data: object) -> StateUpdateResult:
            return StateUpdateResult(
                updated=False,
                unchanged=True,
                reason="Project contract already matches requested value",
            )

        monkeypatch.setattr("gpd.core.state.state_set_project_contract", _noop_contract)

        payload = _raw_json(
            ["--cwd", str(gpd_project), "--raw", "state", "set-project-contract", str(contract_path)],
        )
        assert payload["updated"] is False
        assert payload["reason"] == "Project contract already matches requested value"

    def test_set_project_contract_raw_rejects_schema_valid_contract_with_approval_blockers(
        self,
        gpd_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        contract = json.loads((FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"))
        contract["context_intake"] = {
            "must_read_refs": [],
            "must_include_prior_outputs": [],
            "user_asserted_anchors": [],
            "known_good_baselines": [],
            "context_gaps": ["Need a concrete must-surface anchor before approval."],
            "crucial_inputs": [],
        }
        contract["references"][0]["role"] = "background"
        contract["references"][0]["must_surface"] = False
        contract_path = gpd_project / "draft-contract.json"
        contract_path.write_text(json.dumps(contract), encoding="utf-8")

        def _unexpected_backend_call(*args, **kwargs) -> object:
            raise AssertionError("backend persistence must not run after approved-mode preflight failure")

        monkeypatch.setattr("gpd.core.state.state_set_project_contract", _unexpected_backend_call)

        payload = _raw_json(
            ["--cwd", str(gpd_project), "--raw", "state", "set-project-contract", str(contract_path)],
            expect_exit=1,
        )
        assert payload["valid"] is False
        assert payload["mode"] == "approved"
        assert any("approved project contract requires" in error for error in payload["errors"])
        state = json.loads((gpd_project / "GPD" / "state.json").read_text(encoding="utf-8"))
        assert state["project_contract"] is None


class TestContractCommands:
    def test_lifecycle_contract_gate_accepts_authoritative_project_contract(self, gpd_project: Path) -> None:
        _write_project_contract_to_state(gpd_project)

        payload = _raw_json(
            ["--raw", "--cwd", str(gpd_project), "validate", "lifecycle-contract-gate", "plan-phase", "1"],
        )
        assert payload["passed"] is True
        assert payload["project_contract_gate"]["authoritative"] is True
        assert payload["project_contract_validation"]["valid"] is True

    def test_lifecycle_contract_gate_rejects_recoverably_normalized_contract(self, gpd_project: Path) -> None:
        _write_project_contract_to_state(gpd_project, recoverable_schema_drift=True)

        payload = _raw_json(
            ["--raw", "--cwd", str(gpd_project), "validate", "lifecycle-contract-gate", "execute-phase", "1"],
            expect_exit=1,
        )
        assert payload["passed"] is False
        assert payload["project_contract_load_info"]["status"] == "loaded_with_schema_normalization"
        assert payload["project_contract_validation"]["valid"] is True
        assert payload["project_contract_gate"]["authoritative"] is False
        assert payload["project_contract_gate"]["repair_required"] is True
        assert "project_contract_gate.authoritative is not true" in payload["error"]

    def test_contract_alignment_commands_reject_recoverably_normalized_contract(self, gpd_project: Path) -> None:
        _write_project_contract_to_state(gpd_project, recoverable_schema_drift=True)

        for args in (
            ["contract", "fingerprint"],
            ["--raw", "contract", "alignment-summary"],
            [
                "contract",
                "record-alignment",
                "--contract-hash",
                "sha256:abc",
                "--context-hash",
                "sha256:def",
            ],
        ):
            result = runner.invoke(
                app,
                ["--cwd", str(gpd_project), *args],
                catch_exceptions=False,
            )
            combined_output = result.output + getattr(result, "stderr", "")
            assert result.exit_code == 1, combined_output
            assert "project_contract_gate.authoritative is not true" in combined_output


class TestInitCommands:
    def test_progress_include_rejects_unknown_values(self) -> None:
        payload = _raw_json(
            ["--raw", "init", "progress", "--include", "state, bogus"],
            expect_exit=1,
        )
        assert payload["error"] == (
            "Unknown --include value(s) for gpd init progress: bogus. "
            "Allowed values: config, project, protocols, references, roadmap, state."
        )

    def test_init_resume_resolves_ancestor_project_root_from_nested_workspace(
        self,
        gpd_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        nested = gpd_project / "workspace" / "notes"
        nested.mkdir(parents=True)
        monkeypatch.chdir(nested)

        payload = _raw_json(
            ["--raw", "--cwd", str(nested), "init", "resume"],
        )
        assert payload["planning_exists"] is True
        assert payload["project_exists"] is True
        assert payload["roadmap_exists"] is True
        assert payload["state_exists"] is True

    def test_init_resume_raw_unknown_stage_reports_clean_error(self, gpd_project: Path) -> None:
        result = runner.invoke(
            app,
            ["--raw", "--cwd", str(gpd_project), "init", "resume", "--stage", "bogus"],
            catch_exceptions=False,
        )

        payload = json_output_from_result(result, expect_exit=1)
        assert payload["error"].startswith("Unknown resume-work stage 'bogus'.")
        assert_no_traceback(result)

    def test_init_verify_work_raw_missing_phase_reports_clean_error(self, gpd_project: Path) -> None:
        result = runner.invoke(
            app,
            ["--raw", "--cwd", str(gpd_project), "init", "verify-work"],
            catch_exceptions=False,
        )

        payload = json_output_from_result(result, expect_exit=1)
        assert payload["error"].startswith("phase is required for init verify-work.")
        assert_no_traceback(result)

    def test_init_verify_work_raw_unknown_stage_reports_clean_error(self, gpd_project: Path) -> None:
        result = runner.invoke(
            app,
            ["--raw", "--cwd", str(gpd_project), "init", "verify-work", "1", "--stage", "bogus"],
            catch_exceptions=False,
        )

        payload = json_output_from_result(result, expect_exit=1)
        assert payload["error"].startswith("Unknown verify-work stage 'bogus'.")
        assert_no_traceback(result)

    @pytest.mark.parametrize(
        ("command_args", "expected_keys"),
        [
            (["init", "execute-phase", "1"], {"phase_found": True, "phase_number": "01", "plan_count": 0}),
            (["init", "verify-work", "1"], {"phase_found": True, "phase_number": "01", "has_verification": True}),
        ],
    )
    def test_project_scoped_init_phase_commands_resolve_ancestor_project_root(
        self,
        gpd_project: Path,
        monkeypatch: pytest.MonkeyPatch,
        command_args: list[str],
        expected_keys: dict[str, object],
    ) -> None:
        nested = gpd_project / "workspace" / "notes"
        nested.mkdir(parents=True)
        monkeypatch.chdir(nested)

        payload = _raw_json(
            ["--raw", "--cwd", str(nested), *command_args],
        )
        for key, expected in expected_keys.items():
            assert payload[key] == expected

    def test_init_progress_resolves_ancestor_project_root_from_nested_workspace(
        self,
        gpd_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        nested = gpd_project / "workspace" / "notes"
        nested.mkdir(parents=True)
        monkeypatch.chdir(nested)

        payload = _raw_json(
            ["--raw", "--cwd", str(nested), "init", "progress"],
        )
        assert payload["project_exists"] is True
        assert payload["roadmap_exists"] is True
        assert payload["state_exists"] is True

    def test_init_progress_without_project_reentry_keeps_ancestor_project_resolution(
        self,
        gpd_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        nested = gpd_project / "workspace" / "notes"
        nested.mkdir(parents=True)
        monkeypatch.chdir(nested)

        payload = _raw_json(
            ["--raw", "--cwd", str(nested), "init", "progress", "--no-project-reentry"],
        )
        assert payload["workspace_root"] == nested.resolve().as_posix()
        assert payload["project_root"] == gpd_project.resolve().as_posix()
        assert payload["init_root_policy"] == "project_scoped"
        assert payload["project_exists"] is True
        assert "project_reentry_candidates" not in payload

    def test_init_new_project_scope_intake_is_workspace_bound_inside_nested_checkout(
        self,
        gpd_project: Path,
    ) -> None:
        nested_repo = gpd_project / "nested-unrelated-repo"
        workspace = nested_repo / "analysis"
        (nested_repo / ".git").mkdir(parents=True)
        workspace.mkdir(parents=True)
        (workspace / "notes.py").write_text("print('local notes')\n", encoding="utf-8")

        payload = _raw_json(
            ["--raw", "--cwd", str(workspace), "init", "new-project", "--stage", "scope_intake"],
        )
        assert payload["project_exists"] is False
        assert payload["state_exists"] is False
        assert payload["roadmap_exists"] is False
        assert payload["recoverable_project_exists"] is False
        assert payload["planning_exists"] is False
        assert payload["has_research_files"] is True
        assert payload["needs_research_map"] is True
        assert not (gpd_project / "GPD" / "state.json.lock").exists()

    def test_init_phase_op_resolves_ancestor_project_root_from_nested_workspace(
        self,
        gpd_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        nested = gpd_project / "workspace" / "notes"
        nested.mkdir(parents=True)
        monkeypatch.chdir(nested)

        payload = _raw_json(
            ["--raw", "--cwd", str(nested), "init", "phase-op", "1"],
        )
        assert payload["planning_exists"] is True
        assert payload["roadmap_exists"] is True
        assert payload["state_exists"] is True
        assert payload["phase_found"] is True
        assert payload["phase_number"] == "01"
        assert str(payload["phase_dir"]).startswith("GPD/phases/01-")

    def test_init_new_milestone_stage_resolves_ancestor_project_root_from_nested_workspace(
        self,
        gpd_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        nested = gpd_project / "workspace" / "notes"
        nested.mkdir(parents=True)
        monkeypatch.chdir(nested)

        payload = _raw_json(
            ["--raw", "--cwd", str(nested), "init", "new-milestone", "--stage", "milestone_bootstrap"],
        )
        assert payload["project_exists"] is True
        assert payload["roadmap_exists"] is True
        assert payload["state_exists"] is True
        assert not (nested / "GPD").exists()

    def test_init_milestone_op_resolves_ancestor_project_root_from_nested_workspace(
        self,
        gpd_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        nested = gpd_project / "workspace" / "notes"
        nested.mkdir(parents=True)
        monkeypatch.chdir(nested)

        payload = _raw_json(
            ["--raw", "--cwd", str(nested), "init", "milestone-op"],
        )
        assert payload["init_root_policy"] == "project_scoped"
        assert payload["project_exists"] is True
        assert payload["roadmap_exists"] is True
        assert payload["state_exists"] is True
        assert not (nested / "GPD").exists()

    def test_init_literature_review_resolves_ancestor_project_root_from_nested_workspace(
        self,
        gpd_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        nested = gpd_project / "workspace" / "notes"
        nested.mkdir(parents=True)
        literature_dir = gpd_project / "GPD" / "literature"
        literature_dir.mkdir(parents=True)
        (literature_dir / "benchmark-REVIEW.md").write_text("# Benchmark Review\n", encoding="utf-8")
        monkeypatch.chdir(nested)

        payload = _raw_json(
            ["--raw", "--cwd", str(nested), "init", "literature-review", "Curvature", "flow", "bounds"],
        )
        assert payload["topic"] == "Curvature flow bounds"
        assert payload["slug"] == "curvature-flow-bounds"
        assert payload["project_exists"] is True
        assert payload["roadmap_exists"] is True
        assert payload["state_exists"] is True
        assert "GPD/literature/benchmark-REVIEW.md" in payload["literature_review_files"]

    def test_init_map_research_resolves_ancestor_project_root_from_nested_workspace(
        self,
        gpd_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        nested = gpd_project / "workspace" / "notes"
        nested.mkdir(parents=True)
        map_dir = gpd_project / "GPD" / "research-map"
        map_dir.mkdir(parents=True)
        (map_dir / "theory.md").write_text("# Theory Map\n", encoding="utf-8")
        monkeypatch.chdir(nested)

        payload = _raw_json(
            ["--raw", "--cwd", str(nested), "init", "map-research"],
        )
        assert payload["workspace_root"] == nested.resolve().as_posix()
        assert payload["project_root"] == gpd_project.resolve().as_posix()
        assert payload["project_root_source"] == "workspace"
        assert payload["project_root_auto_selected"] is False
        assert payload["research_map_dir"] == "GPD/research-map"
        assert payload["research_map_dir_absolute"] == map_dir.resolve().as_posix()
        assert payload["planning_exists"] is True
        assert payload["research_map_dir_exists"] is True
        assert payload["has_maps"] is True
        assert "theory.md" in payload["existing_maps"]
        assert not (nested / "GPD").exists()

    def test_init_map_research_stage_exposes_project_rooted_targets_from_nested_workspace(
        self,
        gpd_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        nested = gpd_project / "workspace" / "notes"
        nested.mkdir(parents=True)
        root_map_dir = gpd_project / "GPD" / "research-map"
        monkeypatch.chdir(nested)

        payload = _raw_json(
            ["--raw", "--cwd", str(nested), "init", "map-research", "--stage", "map_bootstrap"],
        )
        assert payload["workspace_root"] == nested.resolve().as_posix()
        assert payload["project_root"] == gpd_project.resolve().as_posix()
        assert payload["project_root_source"] == "workspace"
        assert payload["project_root_auto_selected"] is False
        assert payload["research_map_dir"] == "GPD/research-map"
        assert payload["research_map_dir_absolute"] == root_map_dir.resolve(strict=False).as_posix()
        assert (
            payload["research_map_dir_absolute"] != (nested / "GPD" / "research-map").resolve(strict=False).as_posix()
        )
        assert payload["research_map_dir_exists"] is False
        assert payload["staged_loading"]["stage_id"] == "map_bootstrap"
        assert not (nested / "GPD").exists()

    def test_init_map_research_stage_preserves_focus_argument(self, gpd_project: Path) -> None:
        payload = _raw_json(
            [
                "--raw",
                "--cwd",
                str(gpd_project),
                "init",
                "map-research",
                "Hamiltonian sector",
                "--stage",
                "map_bootstrap",
            ],
        )
        assert payload["map_focus"] == "Hamiltonian sector"
        assert payload["map_focus_provided"] is True
        assert payload["staged_loading"]["stage_id"] == "map_bootstrap"

    def test_init_progress_can_skip_recent_project_reentry_for_projectless_config_bootstrap(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from tempfile import TemporaryDirectory

        from gpd.core.context import init_progress as build_init_progress

        with TemporaryDirectory() as temp_dir:
            sandbox_root = Path(temp_dir)
            workspace = sandbox_root / "workspace"
            candidate = sandbox_root / "recoverable-project"
            data_root = sandbox_root / "data"

            (workspace / "GPD" / "phases").mkdir(parents=True)
            (workspace / "GPD" / "config.json").write_text(
                json.dumps(
                    {
                        "autonomy": "balanced",
                        "review_cadence": "adaptive",
                        "research_mode": "balanced",
                    }
                ),
                encoding="utf-8",
            )

            gpd_dir = candidate / "GPD"
            gpd_dir.mkdir(parents=True)
            (gpd_dir / "STATE.md").write_text("# Research State\n", encoding="utf-8")
            (gpd_dir / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
            (gpd_dir / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
            resume_file = gpd_dir / "phases" / "01" / ".continue-here.md"
            resume_file.parent.mkdir(parents=True, exist_ok=True)
            resume_file.write_text("resume\n", encoding="utf-8")
            monkeypatch.setenv("GPD_DATA_DIR", str(data_root))
            record_recent_project(
                candidate,
                session_data={
                    "last_date": "2026-03-29T12:00:00+00:00",
                    "stopped_at": "Phase 01",
                    "resume_file": "GPD/phases/01/.continue-here.md",
                },
                store_root=data_root,
            )

            payload = build_init_progress(
                workspace,
                includes={"config"},
                data_root=data_root,
                include_project_reentry=False,
            )
            assert payload["workspace_root"] == str(workspace.resolve())
            assert payload["project_root"] == str(workspace.resolve())
            assert payload["project_root_source"] == "workspace"
            assert payload["project_root_auto_selected"] is False
            assert payload["config_content"] is not None
            assert payload["project_exists"] is False
            assert "project_reentry_mode" not in payload
            assert "project_reentry_candidates" not in payload
            assert "project_reentry_selected_candidate" not in payload

    def test_plan_phase_surfaces_artifact_derived_reference_context(self, gpd_project: Path) -> None:
        literature_dir = gpd_project / "GPD" / "literature"
        literature_dir.mkdir(parents=True)
        (literature_dir / "benchmark-REVIEW.md").write_text(
            """# Literature Review: Benchmark Survey

## Active Anchor Registry

| Anchor | Type | Why It Matters | Required Action | Downstream Use |
| ------ | ---- | -------------- | --------------- | -------------- |
| Benchmark Ref 2024 | benchmark | Published benchmark curve for the decisive observable | read/compare/cite | planning/execution |

```yaml
---
review_summary:
  benchmark_values:
    - quantity: "critical slope"
      value: "1.23 +/- 0.04"
      source: "Benchmark Ref 2024"
  active_anchors:
    - anchor: "Benchmark Ref 2024"
      type: "benchmark"
      why_it_matters: "Published benchmark curve for the decisive observable"
      required_action: "read/compare/cite"
      downstream_use: "planning/execution"
---
```
""",
            encoding="utf-8",
        )
        map_dir = gpd_project / "GPD" / "research-map"
        map_dir.mkdir(parents=True)
        (map_dir / "REFERENCES.md").write_text(
            """# Reference and Anchor Map

## Active Anchor Registry

| Anchor | Type | Source / Locator | What It Constrains | Required Action | Carry Forward To |
| ------ | ---- | ---------------- | ------------------ | --------------- | ---------------- |
| prior-baseline | prior artifact | `GPD/phases/01-test-phase/01-SUMMARY.md` | Baseline summary for later comparisons | use | planning/execution |
""",
            encoding="utf-8",
        )

        result = runner.invoke(app, ["--raw", "init", "plan-phase", "1"], catch_exceptions=False)
        payload = json_output_from_result(result)

        assert payload["project_contract"] is None
        assert payload["derived_active_reference_count"] >= 2
        assert "Benchmark Ref 2024" in payload["active_reference_context"]
        assert "GPD/phases/01-test-phase/01-SUMMARY.md" in payload["active_reference_context"]
        assert (
            "GPD/phases/01-test-phase/01-SUMMARY.md"
            in payload["effective_reference_intake"]["must_include_prior_outputs"]
        )

    def test_new_milestone_surfaces_contract_and_effective_reference_context(self, gpd_project: Path) -> None:
        (gpd_project / "GPD" / "ROADMAP.md").write_text(
            "# Roadmap\n\n## Milestone v1.1: Scaling Study\n",
            encoding="utf-8",
        )
        state = json.loads((gpd_project / "GPD" / "state.json").read_text(encoding="utf-8"))
        state["project_contract"] = json.loads((FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"))
        (gpd_project / "GPD" / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")

        literature_dir = gpd_project / "GPD" / "literature"
        literature_dir.mkdir(parents=True)
        (literature_dir / "benchmark-REVIEW.md").write_text(
            "## Active Anchor Registry\n\n"
            "| Anchor | Type | Why It Matters | Required Action | Downstream Use |\n"
            "| ------ | ---- | -------------- | --------------- | -------------- |\n"
            "| Benchmark Ref 2024 | benchmark | Published benchmark curve for the decisive observable | read/compare/cite | planning/execution |\n",
            encoding="utf-8",
        )
        map_dir = gpd_project / "GPD" / "research-map"
        map_dir.mkdir(parents=True)
        (map_dir / "CONCERNS.md").write_text(
            "## Prior Outputs\n\n- `GPD/phases/01-test-phase/01-SUMMARY.md`\n",
            encoding="utf-8",
        )

        result = runner.invoke(app, ["--raw", "init", "new-milestone"], catch_exceptions=False)
        payload = json_output_from_result(result)

        assert payload["current_milestone"] == "v1.1"
        assert payload["project_contract"]["references"][0]["id"] == "ref-benchmark"
        assert "Benchmark Ref 2024" in payload["active_reference_context"]
        assert (
            "GPD/phases/01-test-phase/01-SUMMARY.md"
            in payload["effective_reference_intake"]["must_include_prior_outputs"]
        )
        assert "GPD/research-map/CONCERNS.md" in payload["research_map_reference_files"]

    def test_new_milestone_surfaces_contract_load_and_validation_gates(self, gpd_project: Path) -> None:
        (gpd_project / "GPD" / "ROADMAP.md").write_text(
            "# Roadmap\n\n## Milestone v1.1: Scaling Study\n",
            encoding="utf-8",
        )
        state = json.loads((gpd_project / "GPD" / "state.json").read_text(encoding="utf-8"))
        contract = json.loads((FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"))
        contract["context_intake"] = {
            "must_read_refs": [],
            "must_include_prior_outputs": [],
            "user_asserted_anchors": [],
            "known_good_baselines": [],
            "context_gaps": ["Need a concrete must-surface anchor before approval."],
            "crucial_inputs": [],
        }
        contract["references"][0]["role"] = "background"
        contract["references"][0]["must_surface"] = False
        state["project_contract"] = contract
        (gpd_project / "GPD" / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")

        result = runner.invoke(app, ["--raw", "init", "new-milestone"], catch_exceptions=False)
        payload = json_output_from_result(result)

        assert payload["project_contract"] is not None
        assert payload["project_contract"]["references"][0]["must_surface"] is False
        assert payload["contract_intake"]["context_gaps"] == ["Need a concrete must-surface anchor before approval."]
        assert payload["project_contract_load_info"]["status"] == "loaded_with_approval_blockers"
        assert payload["project_contract_validation"]["valid"] is False
        assert "project_contract_load_info" in payload
        assert "project_contract_validation" in payload

    def test_new_project_init_scope_intake_is_read_only_for_existing_research(self, tmp_path: Path) -> None:
        workspace = tmp_path.parent / f"{tmp_path.name}-candidate-existing-research"
        workspace.mkdir()
        (workspace / "analysis.py").write_text("print('existing result')\n", encoding="utf-8")

        payload = _raw_json(
            ["--raw", "--cwd", str(workspace), "init", "new-project", "--stage", "scope_intake"],
        )
        assert payload["has_git"] is False
        assert payload["has_research_files"] is True
        assert payload["needs_research_map"] is True
        assert "researcher_model" not in payload
        assert "synthesizer_model" not in payload
        assert "roadmapper_model" not in payload
        assert payload["staged_loading"]["loaded_authorities"] == ["workflows/new-project/scope-intake.md"]
        assert payload["staged_loading"]["eager_authorities"] == ["workflows/new-project/scope-intake.md"]
        assert payload["staged_loading"]["writes_allowed"] == []
        assert not (workspace / ".git").exists()
        assert not (workspace / "GPD").exists()

    def test_start_context_is_thin_workspace_classifier_for_existing_research(self, tmp_path: Path) -> None:
        workspace = tmp_path.parent / f"{tmp_path.name}-candidate-start-context"
        workspace.mkdir()
        (workspace / "analysis.py").write_text("print('existing result')\n", encoding="utf-8")

        payload = _raw_json(
            ["--raw", "--cwd", str(workspace), "init", "start-context"],
        )
        assert payload["schema_version"] == "start_context.v1"
        assert payload["folder_state"] == "existing_research"
        assert payload["classification"] == "existing_research"
        assert payload["has_git"] is False
        assert payload["has_research_files"] is True
        assert payload["research_file_samples"] == ["analysis.py"]
        assert payload["needs_research_map"] is True
        assert payload["raw_diagnostics_command"] == "gpd --raw init new-project"
        for omitted_key in (
            "researcher_model",
            "synthesizer_model",
            "roadmapper_model",
            "project_contract",
            "project_contract_gate",
            "project_contract_load_info",
            "project_contract_validation",
            "staged_loading",
            "commit_docs",
            "autonomy",
            "research_mode",
        ):
            assert omitted_key not in payload
        assert not (workspace / ".git").exists()
        assert not (workspace / "GPD").exists()

    def test_start_context_preserves_partial_project_init_progress_diagnostics(self, tmp_path: Path) -> None:
        workspace = tmp_path.parent / f"{tmp_path.name}-start-context-interrupted-init"
        progress_dir = workspace / "GPD"
        progress_dir.mkdir(parents=True)
        (progress_dir / "ROADMAP.md").write_text("# Partial Roadmap\n", encoding="utf-8")
        (progress_dir / "init-progress.json").write_text(
            json.dumps({"step": "M3", "description": "Requirements drafted"}) + "\n",
            encoding="utf-8",
        )

        payload = _raw_json(
            ["--raw", "--cwd", str(workspace), "init", "start-context"],
        )
        assert payload["folder_state"] == "partial_project"
        assert payload["recoverable_project_exists"] is True
        assert payload["partial_project_exists"] is True
        assert payload["project_exists"] is False
        assert payload["roadmap_exists"] is True
        assert payload["init_progress"] == {
            "exists": True,
            "status": "interrupted_init_progress",
            "valid": True,
            "corrupt": False,
            "step": "M3",
            "description": "Requirements drafted",
            "path": "GPD/init-progress.json",
        }
        assert payload["init_progress_exists"] is True
        assert payload["init_progress_valid"] is True
        assert not (progress_dir / "state.json.lock").exists()

        interrupted_only = tmp_path.parent / f"{tmp_path.name}-start-context-init-progress-only"
        interrupted_only_dir = interrupted_only / "GPD"
        interrupted_only_dir.mkdir(parents=True)
        (interrupted_only_dir / "init-progress.json").write_text(
            json.dumps({"step": "M1", "description": "Scope intake started"}) + "\n",
            encoding="utf-8",
        )

        payload = _raw_json(
            ["--raw", "--cwd", str(interrupted_only), "init", "start-context"],
        )
        assert payload["folder_state"] == "partial_project"
        assert payload["recoverable_project_exists"] is False
        assert payload["partial_project_exists"] is False
        assert payload["init_progress"]["exists"] is True

    def test_start_context_matches_new_project_classifier_booleans(self, tmp_path: Path) -> None:
        def make_workspace(name: str) -> Path:
            workspace = tmp_path / name
            workspace.mkdir()
            return workspace

        fresh = make_workspace("fresh")
        existing_research = make_workspace("existing-research")
        (existing_research / "analysis.py").write_text("print('existing result')\n", encoding="utf-8")
        research_map = make_workspace("research-map")
        (research_map / "GPD" / "research-map").mkdir(parents=True)
        partial_project = make_workspace("partial-project")
        (partial_project / "GPD").mkdir()
        (partial_project / "GPD" / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
        initialized_project = make_workspace("initialized-project")
        (initialized_project / "GPD").mkdir()
        (initialized_project / "GPD" / "PROJECT.md").write_text("# Project\n", encoding="utf-8")

        shared_keys = {
            "project_exists",
            "state_exists",
            "roadmap_exists",
            "recoverable_project_exists",
            "partial_project_exists",
            "project_recovery_status",
            "init_progress_exists",
            "init_progress_status",
            "init_progress_valid",
            "init_progress_corrupt",
            "init_progress_step",
            "init_progress_description",
            "init_progress_path",
            "has_research_map",
            "planning_exists",
            "has_research_files",
            "research_file_samples",
            "has_project_manifest",
            "needs_research_map",
            "has_git",
            "platform",
        }

        cases = (
            (fresh, "fresh"),
            (existing_research, "existing_research"),
            (research_map, "research_map"),
            (partial_project, "partial_project"),
            (initialized_project, "initialized_project"),
        )
        for workspace, expected_folder_state in cases:
            start_result = runner.invoke(
                app,
                ["--raw", "--cwd", str(workspace), "init", "start-context"],
                catch_exceptions=False,
            )
            new_project_result = runner.invoke(
                app,
                ["--raw", "--cwd", str(workspace), "init", "new-project", "--stage", "scope_intake"],
                catch_exceptions=False,
            )

            start_payload = json_output_from_result(start_result)
            new_project_payload = json_output_from_result(new_project_result)
            assert start_payload["folder_state"] == expected_folder_state
            assert start_payload["classification"] == expected_folder_state
            for key in shared_keys:
                assert start_payload[key] == new_project_payload[key], (workspace.name, key)
            assert "staged_loading" not in start_payload

    def test_new_project_init_scope_intake_does_not_resolve_late_models(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import gpd.core.context as context_module

        workspace = tmp_path.parent / f"{tmp_path.name}-candidate-scope-intake-models"
        workspace.mkdir()
        resolved_agents: list[str] = []

        def _fail_if_resolved(cwd: Path, agent_type: str, _config: dict | None = None, runtime: str | None = None):
            del cwd, _config, runtime
            resolved_agents.append(agent_type)
            return f"{agent_type}-model"

        monkeypatch.setattr(context_module, "_resolve_model", _fail_if_resolved)

        payload = _raw_json(
            ["--raw", "--cwd", str(workspace), "init", "new-project", "--stage", "scope_intake"],
        )
        assert resolved_agents == []
        assert "researcher_model" not in payload
        assert "synthesizer_model" not in payload
        assert "roadmapper_model" not in payload

    def test_new_project_init_scope_intake_exposes_interrupted_init_progress(self, tmp_path: Path) -> None:
        workspace = tmp_path.parent / f"{tmp_path.name}-interrupted-init"
        progress_dir = workspace / "GPD"
        progress_dir.mkdir(parents=True)
        (progress_dir / "init-progress.json").write_text(
            json.dumps({"step": "M3", "description": "Requirements drafted"}) + "\n",
            encoding="utf-8",
        )
        (progress_dir / "PROJECT.md").write_text("# Partial Project\n", encoding="utf-8")
        (progress_dir / "ROADMAP.md").write_text("# Partial Roadmap\n", encoding="utf-8")

        payload = _raw_json(
            ["--raw", "--cwd", str(workspace), "init", "new-project", "--stage", "scope_intake"],
        )
        assert payload["init_progress_exists"] is True
        assert payload["init_progress_status"] == "interrupted_init_progress"
        assert payload["init_progress_valid"] is True
        assert payload["init_progress_corrupt"] is False
        assert payload["init_progress_step"] == "M3"
        assert payload["init_progress_description"] == "Requirements drafted"
        assert payload["init_progress_path"] == "GPD/init-progress.json"
        assert payload["project_exists"] is True
        assert payload["recoverable_project_exists"] is True
        assert payload["staged_loading"]["writes_allowed"] == []
        assert not (progress_dir / "state.json.lock").exists()

    def test_new_project_init_scope_intake_exposes_corrupt_init_progress(self, tmp_path: Path) -> None:
        workspace = tmp_path.parent / f"{tmp_path.name}-corrupt-init"
        progress_dir = workspace / "GPD"
        progress_dir.mkdir(parents=True)
        (progress_dir / "init-progress.json").write_text("{bad json\n", encoding="utf-8")

        payload = _raw_json(
            ["--raw", "--cwd", str(workspace), "init", "new-project", "--stage", "scope_intake"],
        )
        assert payload["init_progress_exists"] is True
        assert payload["init_progress_status"] == "corrupt_init_progress"
        assert payload["init_progress_valid"] is False
        assert payload["init_progress_corrupt"] is True
        assert payload["init_progress_step"] is None
        assert payload["init_progress_description"] is None
        assert payload["staged_loading"]["writes_allowed"] == []
        assert not (progress_dir / "state.json.lock").exists()

    def test_new_project_init_scope_approval_declares_state_writer_side_effects(self, tmp_path: Path) -> None:
        workspace = tmp_path.parent / f"{tmp_path.name}-candidate-scope-approval"
        workspace.mkdir()

        payload = _raw_json(
            ["--raw", "--cwd", str(workspace), "init", "new-project", "--stage", "scope_approval"],
        )
        assert payload["staged_loading"]["writes_allowed"] == [
            "GPD/state.json",
            "GPD/STATE.md",
            "GPD/state.json.bak",
            "GPD/state.json.lock",
        ]
        assert not (workspace / "GPD").exists()

    def test_new_project_init_stage_literature_survey_filters_payload(self, gpd_project: Path) -> None:
        from gpd.core.workflow_staging import load_workflow_stage_manifest

        state = json.loads((gpd_project / "GPD" / "state.json").read_text(encoding="utf-8"))
        state["project_contract"] = json.loads((FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"))
        (gpd_project / "GPD" / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")

        manifest = load_workflow_stage_manifest("new-project")
        stage = manifest.get_stage("literature_survey")

        payload = _raw_json(
            ["--raw", "--cwd", str(gpd_project), "init", "new-project", "--stage", "literature_survey"],
        )

        assert set(payload) == set(stage.required_init_fields) | {"staged_loading"}
        assert payload["staged_loading"]["workflow_id"] == "new-project"
        assert payload["staged_loading"] == manifest.staged_loading_payload("literature_survey")
        assert payload["staged_loading"]["loaded_authorities"] == ["workflows/new-project/literature-survey.md"]
        assert payload["staged_loading"]["writes_allowed"] == [
            "GPD/literature/PRIOR-WORK.md",
            "GPD/literature/METHODS.md",
            "GPD/literature/COMPUTATIONAL.md",
            "GPD/literature/PITFALLS.md",
            "GPD/literature/SUMMARY.md",
            "GPD/init-progress.json",
        ]
        assert "researcher_model" in payload
        assert "synthesizer_model" in payload
        assert "roadmapper_model" not in payload
        assert "workflows/new-project.md" in payload["staged_loading"]["must_not_eager_load"]

    def test_new_project_init_stage_post_scope_is_unknown(self, gpd_project: Path) -> None:
        result = runner.invoke(
            app,
            ["--raw", "--cwd", str(gpd_project), "init", "new-project", "--stage", "post_scope"],
            catch_exceptions=False,
        )

        assert result.exit_code != 0
        assert "Unknown new-project stage 'post_scope'" in result.output
        assert "minimal_artifacts" in result.output
        assert "workflow_preferences" in result.output

    def test_quick_init_stage_task_authoring_filters_payload(
        self,
        gpd_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from gpd.core.workflow_staging import load_workflow_stage_manifest

        monkeypatch.setenv("GPD_ACTIVE_RUNTIME", "codex")
        state = json.loads((gpd_project / "GPD" / "state.json").read_text(encoding="utf-8"))
        state["project_contract"] = json.loads((FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"))
        (gpd_project / "GPD" / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
        config_path = gpd_project / "GPD" / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["model_overrides"] = {"codex": {"tier-1": "gpt-5", "tier-2": "gpt-5-mini"}}
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        (gpd_project / "GPD" / "PROJECT.md").write_text("# Project\n", encoding="utf-8")

        manifest = load_workflow_stage_manifest("quick")
        stage = manifest.get_stage("task_authoring")

        result = runner.invoke(
            app,
            ["--raw", "init", "quick", "Quick reference check", "--stage", "task_authoring"],
            catch_exceptions=False,
        )
        payload = json_output_from_result(result)

        assert set(payload) == set(stage.required_init_fields) | {"staged_loading"}
        assert payload["staged_loading"]["workflow_id"] == "quick"
        assert payload["staged_loading"]["stage_id"] == "task_authoring"
        assert payload["staged_loading"]["loaded_authorities"] == list(stage.loaded_authorities)
        assert "project_contract_gate" in payload
        assert "active_reference_context" not in payload
        assert "effective_reference_intake" not in payload
        assert "reference_artifacts_content" not in payload
        assert "derived_manuscript_proof_review_status" not in payload

    def test_quick_init_stage_reference_context_loads_reference_payload(
        self,
        gpd_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from gpd.core.workflow_staging import load_workflow_stage_manifest

        monkeypatch.setenv("GPD_ACTIVE_RUNTIME", "codex")
        state = json.loads((gpd_project / "GPD" / "state.json").read_text(encoding="utf-8"))
        state["project_contract"] = json.loads((FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"))
        (gpd_project / "GPD" / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
        config_path = gpd_project / "GPD" / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["model_overrides"] = {"codex": {"tier-1": "gpt-5", "tier-2": "gpt-5-mini"}}
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        (gpd_project / "GPD" / "PROJECT.md").write_text("# Project\n", encoding="utf-8")

        manifest = load_workflow_stage_manifest("quick")
        stage = manifest.get_stage("reference_context")

        result = runner.invoke(
            app,
            ["--raw", "init", "quick", "Quick reference check", "--stage", "reference_context"],
            catch_exceptions=False,
        )
        payload = json_output_from_result(result)

        assert set(payload) == set(stage.required_init_fields) | {"staged_loading"}
        assert payload["staged_loading"]["workflow_id"] == "quick"
        assert payload["staged_loading"]["stage_id"] == "reference_context"
        assert payload["staged_loading"]["loaded_authorities"] == list(stage.loaded_authorities)
        assert "active_reference_context" not in payload
        assert "effective_reference_intake" in payload
        assert "reference_artifacts_content" not in payload
        assert "reference_artifact_files" in payload
        assert "derived_manuscript_proof_review_status" in payload

    def test_quick_init_stage_task_bootstrap_blocks_without_project_file(self, tmp_path: Path) -> None:
        workspace = tmp_path / "quick-without-project"
        (workspace / "GPD").mkdir(parents=True)

        payload = _raw_json(
            [
                "--raw",
                "--cwd",
                str(workspace),
                "init",
                "quick",
                "Quick reference check",
                "--stage",
                "task_bootstrap",
            ],
            expect_exit=1,
        )
        assert "quick staged init requires an initialized GPD project" in payload["error"]

    def test_phase_op_surfaces_contract_load_and_validation_gates(self, gpd_project: Path) -> None:
        state = json.loads((gpd_project / "GPD" / "state.json").read_text(encoding="utf-8"))
        contract = json.loads((FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"))
        contract["context_intake"] = {
            "must_read_refs": [],
            "must_include_prior_outputs": [],
            "user_asserted_anchors": [],
            "known_good_baselines": [],
            "context_gaps": ["Need a concrete must-surface anchor before approval."],
            "crucial_inputs": [],
        }
        contract["references"][0]["role"] = "background"
        contract["references"][0]["must_surface"] = False
        state["project_contract"] = contract
        (gpd_project / "GPD" / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")

        result = runner.invoke(app, ["--raw", "init", "phase-op"], catch_exceptions=False)
        payload = json_output_from_result(result)

        assert payload["project_contract"] is not None
        assert payload["project_contract"]["references"][0]["must_surface"] is False
        assert payload["contract_intake"]["context_gaps"] == ["Need a concrete must-surface anchor before approval."]
        assert payload["project_contract_load_info"]["status"] == "loaded_with_approval_blockers"
        assert payload["project_contract_validation"]["valid"] is False
        assert "project_contract_load_info" in payload
        assert "project_contract_validation" in payload

    def test_write_paper_init_stage_surfaces_bootstrap_payload(self, gpd_project: Path) -> None:
        (gpd_project / "GPD" / "PROJECT.md").write_text("# Project\n\nDraft manuscript.\n", encoding="utf-8")
        state = json.loads((gpd_project / "GPD" / "state.json").read_text(encoding="utf-8"))
        state["project_contract"] = json.loads((FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"))
        (gpd_project / "GPD" / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")

        payload = _raw_json(
            ["--raw", "init", "write-paper", "--stage", "paper_bootstrap"],
        )
        assert payload["staged_loading"]["workflow_id"] == "write-paper"
        assert payload["staged_loading"]["stage_id"] == "paper_bootstrap"
        assert "reference_artifacts_content" not in payload
        assert "state_content" not in payload
        assert "derived_manuscript_reference_status" in payload
        assert payload["publication_subject_status"] == "resolved"
        assert payload["publication_bootstrap_mode"] == "resume_existing_manuscript"
        assert payload["publication_bootstrap_root"] == "paper"


class TestRoadmapCommands:
    def test_roadmap_commands_resolve_project_root_like_progress(
        self,
        gpd_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        nested = gpd_project / "workspace" / "notes"
        nested.mkdir(parents=True)
        monkeypatch.chdir(nested)

        seen: dict[str, object] = {}
        project_root = gpd_project.resolve()

        def _progress_render(cwd: Path, fmt: str) -> dict[str, str]:
            seen["progress"] = cwd
            return {"cwd": str(cwd), "fmt": fmt}

        def _roadmap_analyze(cwd: Path) -> dict[str, str]:
            seen["analyze"] = cwd
            return {"cwd": str(cwd)}

        def _roadmap_get_phase(cwd: Path, phase_num: str) -> dict[str, str]:
            seen["get_phase"] = (cwd, phase_num)
            return {"cwd": str(cwd), "phase_num": phase_num}

        monkeypatch.setattr("gpd.core.phases.progress_render", _progress_render)
        monkeypatch.setattr("gpd.core.phases.roadmap_analyze", _roadmap_analyze)
        monkeypatch.setattr("gpd.core.phases.roadmap_get_phase", _roadmap_get_phase)

        progress_result = runner.invoke(
            app,
            ["--raw", "--cwd", str(nested), "progress"],
            catch_exceptions=False,
        )
        assert json_output_from_result(progress_result) == {"cwd": str(project_root), "fmt": "json"}
        assert seen["progress"] == project_root

        analyze_result = runner.invoke(
            app,
            ["--raw", "--cwd", str(nested), "roadmap", "analyze"],
            catch_exceptions=False,
        )
        assert json_output_from_result(analyze_result) == {"cwd": str(project_root)}
        assert seen["analyze"] == project_root

        get_phase_result = runner.invoke(
            app,
            ["--raw", "--cwd", str(nested), "roadmap", "get-phase", "01"],
            catch_exceptions=False,
        )
        assert json_output_from_result(get_phase_result) == {"cwd": str(project_root), "phase_num": "01"}
        assert seen["get_phase"] == (project_root, "01")


class TestMilestoneCommands:
    def test_milestone_complete_resolves_project_root_like_phase_commands(
        self,
        gpd_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        nested = gpd_project / "workspace" / "notes"
        nested.mkdir(parents=True)
        monkeypatch.chdir(nested)
        project_root = gpd_project.resolve()
        seen: dict[str, object] = {}

        def _milestone_complete(cwd: Path, version: str, *, name: str | None = None) -> dict[str, str | None]:
            seen["cwd"] = cwd
            return {"cwd": str(cwd), "version": version, "name": name}

        monkeypatch.setattr("gpd.core.phases.milestone_complete", _milestone_complete)

        payload = _raw_json(
            ["--raw", "--cwd", str(nested), "milestone", "complete", "v1.0", "--name", "Test"],
        )

        assert payload == {"cwd": str(project_root), "version": "v1.0", "name": "Test"}
        assert seen["cwd"] == project_root
        assert not (nested / "GPD").exists()


class TestReadOnlyCommandRouting:
    @pytest.mark.parametrize(
        ("command_args", "patch_target", "kind"),
        [
            (["--raw", "health"], "gpd.core.health.run_health", "health"),
            (["--raw", "validate", "consistency"], "gpd.core.health.run_health", "health"),
            (["--raw", "query", "search", "--text", "alpha"], "gpd.core.query.query", "query_search"),
            (["--raw", "query", "deps", "R-01"], "gpd.core.query.query_deps", "query_deps"),
            (
                ["--raw", "query", "assumptions", "alpha", "beta"],
                "gpd.core.query.query_assumptions",
                "query_assumptions",
            ),
            (["--raw", "history-digest"], "gpd.core.commands.cmd_history_digest", "history_digest"),
            (["--raw", "regression-check"], "gpd.core.commands.cmd_regression_check", "regression_check"),
        ],
    )
    def test_project_scoped_read_only_commands_use_project_root(
        self,
        gpd_project: Path,
        monkeypatch: pytest.MonkeyPatch,
        command_args: list[str],
        patch_target: str,
        kind: str,
    ) -> None:
        nested = gpd_project / "workspace" / "notes"
        nested.mkdir(parents=True)
        monkeypatch.chdir(nested)
        project_root = gpd_project.resolve()
        seen: dict[str, object] = {}

        monkeypatch.setattr("gpd.cli._project_scoped_cwd", lambda cwd=None: project_root)

        if kind == "health":

            def _fake_run_health(cwd: Path, fix: bool = False):
                seen["cwd"] = cwd
                seen["fix"] = fix
                return SimpleNamespace(
                    overall="ok",
                    model_dump=lambda mode="json", by_alias=True: {
                        "cwd": str(cwd),
                        "fix": fix,
                        "overall": "ok",
                    },
                )

            monkeypatch.setattr(patch_target, _fake_run_health)
        elif kind == "query_search":

            def _fake_query(cwd: Path, **kwargs: object):
                seen["cwd"] = cwd
                seen["kwargs"] = kwargs
                return {"cwd": str(cwd), **kwargs}

            monkeypatch.setattr(patch_target, _fake_query)
        elif kind == "query_deps":

            def _fake_query_deps(cwd: Path, identifier: str):
                seen["cwd"] = cwd
                seen["identifier"] = identifier
                return {"cwd": str(cwd), "identifier": identifier}

            monkeypatch.setattr(patch_target, _fake_query_deps)
        elif kind == "query_assumptions":

            def _fake_query_assumptions(cwd: Path, text: str):
                seen["cwd"] = cwd
                seen["text"] = text
                return {"cwd": str(cwd), "text": text}

            monkeypatch.setattr(patch_target, _fake_query_assumptions)
        elif kind == "history_digest":

            def _fake_history_digest(cwd: Path):
                seen["cwd"] = cwd
                return {"cwd": str(cwd)}

            monkeypatch.setattr(patch_target, _fake_history_digest)
        elif kind == "regression_check":

            def _fake_regression_check(cwd: Path, phase: str | None = None, quick: bool = False):
                seen["cwd"] = cwd
                seen["phase"] = phase
                seen["quick"] = quick
                return SimpleNamespace(
                    passed=True,
                    model_dump=lambda mode="json", by_alias=True: {
                        "cwd": str(cwd),
                        "phase": phase,
                        "quick": quick,
                        "passed": True,
                    },
                )

            monkeypatch.setattr(patch_target, _fake_regression_check)
        else:  # pragma: no cover - guarded by parametrization
            raise AssertionError(kind)

        result = runner.invoke(app, ["--cwd", str(nested), *command_args], catch_exceptions=False)

        payload = json_output_from_result(result)
        assert payload["cwd"] == str(project_root)
        assert seen["cwd"] == project_root
        if kind == "health":
            assert payload["fix"] is False
            assert seen["fix"] is False
        elif kind == "query_search":
            assert payload["text"] == "alpha"
            assert seen["kwargs"]["text"] == "alpha"
        elif kind == "query_deps":
            assert payload["identifier"] == "R-01"
            assert seen["identifier"] == "R-01"
        elif kind == "query_assumptions":
            assert payload["text"] == "alpha beta"
            assert seen["text"] == "alpha beta"
        elif kind == "regression_check":
            assert payload["passed"] is True
            assert seen["quick"] is False

    @pytest.mark.parametrize(
        "command_args",
        [
            ["--raw", "health"],
            ["--raw", "validate", "consistency"],
        ],
    )
    def test_health_read_only_paths_do_not_migrate_root_planning_files(
        self,
        gpd_project: Path,
        monkeypatch: pytest.MonkeyPatch,
        command_args: list[str],
    ) -> None:
        for filename in ("PROJECT.md", "ROADMAP.md"):
            (gpd_project / "GPD" / filename).unlink()
            (gpd_project / filename).write_text(f"# Root {filename}\n", encoding="utf-8")

        seen: dict[str, object] = {}

        def _fake_run_health(cwd: Path, fix: bool = False):
            seen["cwd"] = cwd
            seen["fix"] = fix
            return SimpleNamespace(
                overall="ok",
                model_dump=lambda mode="json", by_alias=True: {
                    "cwd": str(cwd),
                    "fix": fix,
                    "overall": "ok",
                },
            )

        monkeypatch.setattr("gpd.core.health.run_health", _fake_run_health)

        result = runner.invoke(app, ["--cwd", str(gpd_project), *command_args], catch_exceptions=False)

        assert result.exit_code == 0, result.output
        assert seen == {"cwd": gpd_project.resolve(), "fix": False}
        assert not (gpd_project / "GPD" / "PROJECT.md").exists()
        assert not (gpd_project / "GPD" / "ROADMAP.md").exists()

    def test_health_fix_retains_mutating_project_scope(
        self,
        gpd_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        for filename in ("PROJECT.md", "ROADMAP.md"):
            (gpd_project / "GPD" / filename).unlink()
            (gpd_project / filename).write_text(f"# Root {filename}\n", encoding="utf-8")

        seen: dict[str, object] = {}

        def _fake_run_health(cwd: Path, fix: bool = False):
            seen["cwd"] = cwd
            seen["fix"] = fix
            return SimpleNamespace(
                overall="ok",
                model_dump=lambda mode="json", by_alias=True: {
                    "cwd": str(cwd),
                    "fix": fix,
                    "overall": "ok",
                },
            )

        monkeypatch.setattr("gpd.core.health.run_health", _fake_run_health)

        result = runner.invoke(app, ["--cwd", str(gpd_project), "--raw", "health", "--fix"], catch_exceptions=False)

        assert result.exit_code == 0, result.output
        assert seen == {"cwd": gpd_project.resolve(), "fix": True}
        assert (gpd_project / "GPD" / "PROJECT.md").read_text(encoding="utf-8") == "# Root PROJECT.md\n"
        assert (gpd_project / "GPD" / "ROADMAP.md").read_text(encoding="utf-8") == "# Root ROADMAP.md\n"

    def test_raw_health_failure_still_emits_parseable_json(
        self,
        gpd_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def _fake_run_health(cwd: Path, fix: bool = False):
            return SimpleNamespace(
                overall="fail",
                model_dump=lambda mode="json", by_alias=True: {
                    "cwd": str(cwd),
                    "fix": fix,
                    "overall": "fail",
                    "summary": {"ok": 1, "warn": 0, "fail": 1, "total": 2},
                    "checks": [],
                    "fixes_applied": [],
                },
            )

        monkeypatch.setattr("gpd.core.health.run_health", _fake_run_health)

        result = runner.invoke(app, ["--cwd", str(gpd_project), "--raw", "health"], catch_exceptions=False)

        payload = json_output_from_result(result, expect_exit=1)
        assert payload["overall"] == "fail"
        assert payload["summary"]["fail"] == 1


class TestReadOnlyStateBackedLists:
    @pytest.mark.parametrize(
        ("command_args", "patch_target", "kind"),
        [
            (["--raw", "result", "list"], "gpd.core.results.result_list", "result_list"),
            (["--raw", "approximation", "list"], "gpd.core.extras.approximation_list", "approximation_list"),
            (["--raw", "uncertainty", "list"], "gpd.core.extras.uncertainty_list", "uncertainty_list"),
            (["--raw", "question", "list"], "gpd.core.extras.question_list", "question_list"),
            (["--raw", "calculation", "list"], "gpd.core.extras.calculation_list", "calculation_list"),
        ],
    )
    def test_state_backed_read_only_lists_use_non_mutating_loader(
        self,
        gpd_project: Path,
        monkeypatch: pytest.MonkeyPatch,
        command_args: list[str],
        patch_target: str,
        kind: str,
    ) -> None:
        nested = gpd_project / "workspace" / "notes"
        nested.mkdir(parents=True)
        monkeypatch.chdir(nested)
        project_root = gpd_project.resolve()
        seen: dict[str, object] = {}

        monkeypatch.setattr(
            "gpd.cli._project_scoped_cwd",
            lambda cwd=None: (_ for _ in ()).throw(AssertionError("_load_state_dict must stay read-only")),
        )

        def _fake_peek_state_json(
            cwd: Path,
            *,
            integrity_mode: str = "standard",
            recover_intent: bool = True,
            surface_blocked_project_contract: bool = False,
            acquire_lock: bool = True,
        ):
            seen["peek_cwd"] = cwd
            seen["acquire_lock"] = acquire_lock
            seen["recover_intent"] = recover_intent
            seen["surface_blocked_project_contract"] = surface_blocked_project_contract
            return ({"loaded_cwd": str(cwd)}, [], "state.json")

        monkeypatch.setattr("gpd.core.state.peek_state_json", _fake_peek_state_json)

        def _fake_state_reader(state: dict, *args: object, **kwargs: object):
            seen["state"] = state
            seen["args"] = args
            seen["kwargs"] = kwargs
            return {"cwd": state["loaded_cwd"], "kind": kind, "args": list(args), "kwargs": kwargs}

        monkeypatch.setattr(patch_target, _fake_state_reader)

        result = runner.invoke(app, ["--cwd", str(nested), *command_args], catch_exceptions=False)

        payload = json_output_from_result(result)
        assert payload["cwd"] == str(project_root)
        assert payload["kind"] == kind
        assert seen["peek_cwd"] == project_root
        assert seen["acquire_lock"] is False
        assert seen["recover_intent"] is False
        assert seen["surface_blocked_project_contract"] is True


class TestReviewValidationCommands:
    def test_review_contract_uses_typed_registry_surface(self) -> None:
        payload = _raw_json(
            ["--raw", "validate", "review-contract", "write-paper"],
        )
        assert payload["command"] == "gpd:write-paper"
        assert payload["context_mode"] == "project-aware"
        assert payload["review_contract"]["review_mode"] == "publication"
        assert "${PAPER_DIR}/ARTIFACT-MANIFEST.json" in payload["review_contract"]["required_outputs"]
        assert "${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json" in payload["review_contract"]["required_outputs"]
        assert "${PAPER_DIR}/reproducibility-manifest.json" in payload["review_contract"]["required_outputs"]
        assert "GPD/review/REVIEW-LEDGER{round_suffix}.json" in payload["review_contract"]["required_outputs"]
        assert "GPD/review/REFEREE-DECISION{round_suffix}.json" in payload["review_contract"]["required_outputs"]
        assert "GPD/REFEREE-REPORT{round_suffix}.md" in payload["review_contract"]["required_outputs"]
        assert "GPD/REFEREE-REPORT{round_suffix}.tex" in payload["review_contract"]["required_outputs"]
        assert payload["review_contract"]["required_evidence"] == [
            "project-backed lane: research artifacts and verification reports",
            "external-authoring lane: explicit `--intake` manifest with claim-to-evidence bindings",
            "bibliography / citation-source input",
        ]
        assert payload["review_contract"]["preflight_checks"] == [
            "command_context",
            "project_state",
            "roadmap",
            "conventions",
            "research_artifacts",
            "verification_reports",
            "manuscript",
            "artifact_manifest",
            "bibliography_audit",
            "bibliography_audit_clean",
            "reproducibility_manifest",
            "reproducibility_ready",
            "manuscript_proof_review",
        ]
        assert payload["review_contract"]["stage_artifacts"] == []
        assert payload["review_contract"]["conditional_requirements"] == [
            {
                "when": "theorem-bearing claims are present",
                "required_outputs": ["GPD/review/PROOF-REDTEAM{round_suffix}.md"],
                "required_evidence": [],
                "blocking_conditions": [],
                "preflight_checks": [],
                "blocking_preflight_checks": [],
                "stage_artifacts": [],
            }
        ]
        assert payload["review_contract"]["scope_variants"] == [
            {
                "scope": "explicit_intake_manifest",
                "activation": "validated explicit external authoring intake manifest was supplied outside a project",
                "relaxed_preflight_checks": [
                    "project_state",
                    "roadmap",
                    "conventions",
                    "research_artifacts",
                    "verification_reports",
                    "manuscript_proof_review",
                ],
                "optional_preflight_checks": [
                    "artifact_manifest",
                    "bibliography_audit",
                    "bibliography_audit_clean",
                    "reproducibility_manifest",
                    "reproducibility_ready",
                ],
                "required_outputs_override": [
                    "${PAPER_DIR}/{topic_specific_stem}.tex",
                    "${PAPER_DIR}/PAPER-CONFIG.json",
                    "${PAPER_DIR}/ARTIFACT-MANIFEST.json",
                    "${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json",
                    "${PAPER_DIR}/reproducibility-manifest.json",
                ],
                "required_evidence_override": [
                    "validated external authoring intake manifest with explicit claim-to-evidence bindings"
                ],
                "blocking_conditions_override": ["invalid or incomplete external authoring intake manifest"],
            }
        ]

    def test_review_contract_peer_review_uses_typed_registry_surface(self) -> None:
        payload = _raw_json(
            ["--raw", "validate", "review-contract", "peer-review"],
        )
        assert payload["command"] == "gpd:peer-review"
        assert payload["context_mode"] == "project-aware"
        assert payload["review_contract"]["review_mode"] == "publication"
        assert "${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.md" in payload["review_contract"]["required_outputs"]
        assert "${PUBLICATION_ROOT}/REFEREE-REPORT{round_suffix}.tex" in payload["review_contract"]["required_outputs"]
        assert "${REVIEW_ROOT}/CLAIMS{round_suffix}.json" in payload["review_contract"]["required_outputs"]
        assert (
            "${REVIEW_ROOT}/STAGE-interestingness{round_suffix}.json" in payload["review_contract"]["required_outputs"]
        )
        assert "${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json" in payload["review_contract"]["required_outputs"]
        assert "GPD/CONSISTENCY-REPORT.md" not in payload["review_contract"]["required_outputs"]
        assert payload["review_contract"]["preflight_checks"] == PEER_REVIEW_COMMON_PREFLIGHT_CHECKS
        assert payload["review_contract"]["required_evidence"] == [
            "existing manuscript or explicit external artifact target",
        ]
        assert payload["review_contract"]["blocking_conditions"] == [
            "missing manuscript or explicit external artifact target",
            "degraded review integrity",
            "unsupported physical significance claims",
            "collapsed novelty or venue fit",
        ]
        assert payload["review_contract"]["stage_artifacts"] == [
            "${REVIEW_ROOT}/CLAIMS{round_suffix}.json",
            "${REVIEW_ROOT}/STAGE-reader{round_suffix}.json",
            "${REVIEW_ROOT}/STAGE-literature{round_suffix}.json",
            "${REVIEW_ROOT}/STAGE-math{round_suffix}.json",
            "${REVIEW_ROOT}/STAGE-physics{round_suffix}.json",
            "${REVIEW_ROOT}/STAGE-interestingness{round_suffix}.json",
            "${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json",
            "${REVIEW_ROOT}/REFEREE-DECISION{round_suffix}.json",
        ]
        assert payload["review_contract"]["conditional_requirements"] == [
            PROJECT_BACKED_PEER_REVIEW_CONDITIONAL,
            THEOREM_BEARING_PEER_REVIEW_CONDITIONAL,
        ]
        assert "stage_ids" not in payload["review_contract"]
        assert "final_decision_output" not in payload["review_contract"]
        assert "requires_fresh_context_per_stage" not in payload["review_contract"]
        assert "max_review_rounds" not in payload["review_contract"]

    def test_review_contract_review_knowledge_supports_strict_standalone_canonical_targets(self) -> None:
        payload = _raw_json(
            ["--raw", "validate", "review-contract", "review-knowledge"],
        )
        assert payload["command"] == "gpd:review-knowledge"
        assert payload["context_mode"] == "project-aware"
        assert payload["review_contract"]["review_mode"] == "review"
        assert payload["review_contract"]["required_outputs"] == [
            "GPD/knowledge/reviews/{knowledge_id}-R{review_round}-REVIEW.md",
            "GPD/knowledge/{knowledge_id}.md",
        ]
        assert payload["review_contract"]["required_evidence"] == [
            "current-workspace canonical knowledge document",
            "knowledge sources and coverage summary",
            "current knowledge frontmatter/body snapshot",
            "prior review artifact when revisiting a document",
        ]
        assert payload["review_contract"]["preflight_checks"] == [
            "command_context",
            "knowledge_target",
            "knowledge_document",
            "knowledge_review_freshness",
        ]
        assert "missing project state" not in payload["review_contract"]["blocking_conditions"]
        assert "missing knowledge document" in payload["review_contract"]["blocking_conditions"]
        assert "ambiguous knowledge target" in payload["review_contract"]["blocking_conditions"]
        assert "stale approved review evidence" in payload["review_contract"]["blocking_conditions"]

    def test_review_contract_accepts_public_command_label(self) -> None:
        payload = _raw_json(
            ["--raw", "validate", "review-contract", "/gpd:peer-review"],
        )
        assert payload["command"] == "gpd:peer-review"
        assert payload["review_contract"]["review_mode"] == "publication"

    def test_review_contract_respond_to_referees_uses_typed_registry_surface(self) -> None:
        payload = _raw_json(
            ["--raw", "validate", "review-contract", "respond-to-referees"],
        )
        assert payload["command"] == "gpd:respond-to-referees"
        assert payload["context_mode"] == "project-aware"
        assert payload["review_contract"]["review_mode"] == "publication"
        assert "GPD/review/REFEREE_RESPONSE{round_suffix}.md" in payload["review_contract"]["required_outputs"]
        assert "GPD/AUTHOR-RESPONSE{round_suffix}.md" in payload["review_contract"]["required_outputs"]
        assert "existing manuscript" in payload["review_contract"]["required_evidence"]
        assert "referee report source when provided as a path" in payload["review_contract"]["required_evidence"]
        assert (
            "missing referee report source when provided as a path" in payload["review_contract"]["blocking_conditions"]
        )
        assert "command_context" in payload["review_contract"]["preflight_checks"]
        assert "referee_report_source" in payload["review_contract"]["preflight_checks"]
        scope_variants = {variant["scope"]: variant for variant in payload["review_contract"]["scope_variants"]}
        assert "explicit_external_manuscript" in scope_variants
        explicit_external = scope_variants["explicit_external_manuscript"]
        assert (
            explicit_external["activation"]
            == "explicit `--manuscript` subject outside the current project's canonical manuscript roots"
        )
        assert explicit_external["relaxed_preflight_checks"] == ["project_state", "conventions"]
        assert explicit_external["required_evidence_override"] == [
            "explicit manuscript subject",
            "one or more referee report sources",
        ]
        assert explicit_external["blocking_conditions_override"] == [
            "missing manuscript subject",
            "missing referee report source",
            "degraded review integrity",
        ]

    def test_review_contract_arxiv_submission_surfaces_latest_review_outcome_gate(self) -> None:
        command_path = Path(__file__).resolve().parents[1] / "src/gpd/commands/arxiv-submission.md"
        command = _parse_command_file(command_path, source="commands")
        assert command.review_contract is not None

        payload = {
            "command": command.name,
            "context_mode": command.context_mode,
            "review_contract": dataclasses.asdict(command.review_contract),
        }
        assert payload["command"] == "gpd:arxiv-submission"
        assert payload["context_mode"] == "project-aware"
        assert (
            "GPD/publication/{subject_slug}/arxiv/arxiv-submission.tar.gz"
            in payload["review_contract"]["required_outputs"]
        )
        assert "manuscript-root artifact manifest" in payload["review_contract"]["required_evidence"]
        assert "manuscript-root bibliography audit" in payload["review_contract"]["required_evidence"]
        assert "latest peer-review review ledger" in payload["review_contract"]["required_evidence"]
        assert "latest peer-review referee decision" in payload["review_contract"]["required_evidence"]
        assert "missing manuscript-root artifact manifest" in payload["review_contract"]["blocking_conditions"]
        assert "missing manuscript-root bibliography audit" in payload["review_contract"]["blocking_conditions"]
        assert "missing compiled manuscript" in payload["review_contract"]["blocking_conditions"]
        assert (
            "missing latest staged peer-review decision evidence" in payload["review_contract"]["blocking_conditions"]
        )
        assert (
            "latest staged peer-review recommendation blocks submission packaging"
            in payload["review_contract"]["blocking_conditions"]
        )
        assert payload["review_contract"]["preflight_checks"] == [
            "command_context",
            "project_state",
            "manuscript",
            "artifact_manifest",
            "bibliography_audit",
            "bibliography_audit_clean",
            "reproducibility_manifest",
            "reproducibility_ready",
            "compiled_manuscript",
            "conventions",
            "publication_blockers",
            "review_ledger",
            "review_ledger_valid",
            "referee_decision",
            "referee_decision_valid",
            "publication_review_outcome",
            "manuscript_proof_review",
        ]
        assert payload["review_contract"]["scope_variants"] == []
        assert payload["review_contract"]["conditional_requirements"] == [
            {
                "when": "theorem-bearing manuscripts are present",
                "required_outputs": [],
                "required_evidence": ["cleared manuscript proof review for theorem-bearing manuscripts"],
                "blocking_conditions": ["missing or stale manuscript proof review for theorem-bearing manuscripts"],
                "preflight_checks": [],
                "blocking_preflight_checks": ["manuscript_proof_review"],
                "stage_artifacts": [],
            }
        ]

    def test_command_context_project_required_fails_without_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dollar_command_prefix: str
    ) -> None:
        outside_dir = tmp_path.parent / f"{tmp_path.name}-outside"
        outside_dir.mkdir()
        monkeypatch.setenv("GPD_DATA_DIR", str(tmp_path / "data"))
        monkeypatch.chdir(outside_dir)

        payload = _raw_json(
            ["--raw", "--cwd", str(outside_dir), "validate", "command-context", "progress"],
            expect_exit=1,
        )
        assert payload["command"] == "gpd:progress"
        assert payload["context_mode"] == "project-required"
        assert payload["passed"] is False
        assert payload["guidance"] == (
            "This command requires a recoverable GPD workspace. "
            "Open the right project, use `gpd resume --recent` to rediscover it, or initialize a new project with "
            f"`{dollar_command_prefix}new-project` in the runtime surface or `gpd init new-project` in the local CLI."
        )

    def test_command_context_progress_resolves_ancestor_project_root_for_nested_workspace(
        self,
        gpd_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        nested = gpd_project / "workspace" / "notes"
        nested.mkdir(parents=True)
        monkeypatch.chdir(nested)

        payload = _raw_json(
            ["--raw", "--cwd", str(nested), "validate", "command-context", "progress"],
        )
        checks = checks_by_name(payload)
        assert payload["command"] == "gpd:progress"
        assert payload["context_mode"] == "project-required"
        assert payload["passed"] is True
        assert payload["project_exists"] is True
        assert checks["project_exists"]["passed"] is True
        assert "GPD/PROJECT.md" in checks["project_exists"]["detail"]

    def test_command_context_progress_reconcile_surfaces_confirmation_contract(
        self,
        gpd_project: Path,
    ) -> None:
        payload = _raw_json(
            ["--raw", "--cwd", str(gpd_project), "validate", "command-context", "progress", "--reconcile"],
        )
        checks = checks_by_name(payload)
        assert payload["command"] == "gpd:progress"
        assert payload["passed"] is True
        assert checks["reconcile_confirmation"]["passed"] is True
        assert checks["reconcile_confirmation"]["blocking"] is True
        assert "ask_user" in checks["reconcile_confirmation"]["detail"]

    @pytest.mark.parametrize("command_args", [["progress", "--watch"], ["progress", "-w"], ["gpd:progress --watch"]])
    def test_command_context_progress_rejects_runtime_watch_mode(
        self,
        gpd_project: Path,
        command_args: list[str],
    ) -> None:
        payload = _raw_json(
            ["--raw", "--cwd", str(gpd_project), "validate", "command-context", *command_args],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert payload["command"] == "gpd:progress"
        assert payload["passed"] is False
        assert payload["guidance"].endswith("use `gpd progress json --watch` from a terminal.")
        assert checks["runtime_arguments"]["passed"] is False
        assert checks["runtime_arguments"]["blocking"] is True
        assert "local CLI only" in checks["runtime_arguments"]["detail"]

    @pytest.mark.parametrize("command_name", ["research-phase", "list-phase-assumptions"])
    def test_command_context_phase_commands_require_explicit_phase_in_initialized_project(
        self,
        gpd_project: Path,
        command_name: str,
    ) -> None:
        payload = _raw_json(
            ["--raw", "--cwd", str(gpd_project), "validate", "command-context", command_name],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert payload["command"] == f"gpd:{command_name}"
        assert payload["context_mode"] == "project-required"
        assert payload["passed"] is False
        assert checks["project_exists"]["passed"] is True
        assert checks["explicit_inputs"]["passed"] is False
        assert checks["explicit_inputs"]["detail"] == "missing explicit subject (phase-number)"
        assert payload["guidance"] == "missing explicit subject (phase-number)"

    @pytest.mark.parametrize("command_name", ["research-phase", "list-phase-assumptions"])
    def test_command_context_phase_commands_accept_explicit_phase_in_initialized_project(
        self,
        gpd_project: Path,
        command_name: str,
    ) -> None:
        payload = _raw_json(
            ["--raw", "--cwd", str(gpd_project), "validate", "command-context", command_name, "1"],
        )
        checks = checks_by_name(payload)
        assert payload["command"] == f"gpd:{command_name}"
        assert payload["context_mode"] == "project-required"
        assert payload["passed"] is True
        assert checks["project_exists"]["passed"] is True
        assert checks["explicit_inputs"]["passed"] is True
        assert checks["explicit_inputs"]["detail"] == "explicit phase subject 1"

    def test_command_context_resume_work_resolves_ancestor_project_root_for_nested_workspace(
        self,
        gpd_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        nested = gpd_project / "workspace" / "notes"
        nested.mkdir(parents=True)
        monkeypatch.chdir(nested)

        payload = _raw_json(
            ["--raw", "--cwd", str(nested), "validate", "command-context", "resume-work"],
        )
        checks = checks_by_name(payload)
        assert payload["command"] == "gpd:resume-work"
        assert payload["context_mode"] == "project-required"
        assert payload["passed"] is True
        assert checks["project_exists"]["passed"] is True

    def test_command_context_literature_review_resolves_ancestor_project_root_for_nested_workspace(
        self,
        gpd_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        nested = gpd_project / "workspace" / "notes"
        nested.mkdir(parents=True)
        monkeypatch.chdir(nested)

        payload = _raw_json(
            [
                "--raw",
                "--cwd",
                str(nested),
                "validate",
                "command-context",
                "literature-review",
                "Curvature flow bounds",
            ],
        )
        checks = checks_by_name(payload)
        assert payload["command"] == "gpd:literature-review"
        assert payload["context_mode"] == "project-aware"
        assert payload["passed"] is True
        assert payload["project_exists"] is True
        assert checks["project_exists"]["passed"] is True
        assert checks["explicit_inputs"]["passed"] is True

    def test_command_context_resume_work_requires_literal_files_in_project_root(self, gpd_project: Path) -> None:
        (gpd_project / "GPD" / "ROADMAP.md").unlink()

        payload = _raw_json(
            ["--raw", "validate", "command-context", "resume-work"],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert payload["command"] == "gpd:resume-work"
        assert payload["context_mode"] == "project-required"
        assert payload["passed"] is False
        assert checks["project_exists"]["passed"] is True

    def test_command_context_recovery_surfaces_accept_partial_recoverable_workspace(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp_dir:
            sandbox_root = Path(temp_dir)
            project = sandbox_root / "recoverable-project"
            nested = project / "workspace" / "notes"
            gpd_dir = project / "GPD"
            recent = sandbox_root / "recent-project"
            nested.mkdir(parents=True)
            gpd_dir.mkdir()
            (recent / "GPD").mkdir(parents=True)
            (recent / "GPD" / "PROJECT.md").write_text("# Recent\n", encoding="utf-8")
            (gpd_dir / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
            (gpd_dir / "STATE.md").write_text("# Research State\n", encoding="utf-8")
            monkeypatch.setattr(cli_module, "_cwd", nested)
            monkeypatch.setattr(
                "gpd.core.project_reentry.list_recent_projects",
                lambda _data_root=None: [
                    {
                        "project_root": recent.resolve(strict=False).as_posix(),
                        "available": True,
                        "resumable": True,
                        "resume_file": "GPD/phases/01/.continue-here.md",
                        "resume_file_available": True,
                        "last_session_at": "2026-03-28T12:00:00+00:00",
                    }
                ],
            )

            for command_name in ("progress", "resume-work"):
                preflight = cli_module._build_command_context_preflight(command_name)

                checks = {check.name: check for check in preflight.checks}
                assert preflight.passed is (command_name == "resume-work")
                assert preflight.project_exists is False
                assert checks["state_exists"].passed is True
                assert checks["roadmap_exists"].passed is True
                assert checks["project_exists"].passed is False
                assert checks["required_files"].passed is (command_name == "resume-work")
                assert "recent-project" not in checks["roadmap_exists"].detail

    def test_command_context_plan_milestone_gaps_requires_globbed_files_in_project_root(
        self, gpd_project: Path
    ) -> None:
        payload = _raw_json(
            ["--raw", "validate", "command-context", "plan-milestone-gaps"],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert payload["command"] == "gpd:plan-milestone-gaps"
        assert payload["context_mode"] == "project-required"
        assert payload["passed"] is False
        assert checks["project_exists"]["passed"] is True

    def test_command_context_plan_milestone_gaps_resolves_ancestor_project_root_for_nested_workspace(
        self,
        gpd_project: Path,
    ) -> None:
        nested = gpd_project / "workspace" / "notes"
        nested.mkdir(parents=True)
        (gpd_project / "GPD" / "v1-MILESTONE-AUDIT.md").write_text("# Audit\n", encoding="utf-8")

        payload = _raw_json(
            ["--raw", "--cwd", str(nested), "validate", "command-context", "plan-milestone-gaps"],
        )
        checks = checks_by_name(payload)
        assert payload["command"] == "gpd:plan-milestone-gaps"
        assert payload["context_mode"] == "project-required"
        assert payload["passed"] is True
        assert checks["project_exists"]["passed"] is True

    def test_command_context_progress_auto_selects_unique_recoverable_recent_project(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        workspace = tmp_path.parent / f"{tmp_path.name}-outside-unique"
        workspace.mkdir()
        project = tmp_path / "recoverable-project"
        gpd_dir = project / "GPD"
        gpd_dir.mkdir(parents=True)
        (gpd_dir / "STATE.md").write_text("# Research State\n", encoding="utf-8")
        (gpd_dir / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
        (gpd_dir / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
        resume_file = gpd_dir / "phases" / "01" / ".continue-here.md"
        resume_file.parent.mkdir(parents=True, exist_ok=True)
        resume_file.write_text("resume\n", encoding="utf-8")
        data_root = tmp_path / "data"
        monkeypatch.setenv("GPD_DATA_DIR", str(data_root))
        record_recent_project(
            project,
            session_data={
                "last_date": "2026-03-29T12:00:00+00:00",
                "stopped_at": "Phase 01",
                "resume_file": "GPD/phases/01/.continue-here.md",
            },
            store_root=data_root,
        )

        result = runner.invoke(
            app,
            ["--raw", "--cwd", str(workspace), "validate", "command-context", "progress"],
            catch_exceptions=False,
        )

        payload = json_output_from_result(result)
        checks = checks_by_name(payload)
        assert payload["passed"] is True
        assert checks["project_reentry"]["passed"] is True
        assert "auto-selected recoverable recent project" in checks["project_reentry"]["detail"]

        init_result = runner.invoke(
            app,
            ["--raw", "--cwd", str(workspace), "init", "progress"],
            catch_exceptions=False,
        )

        init_payload = json_output_from_result(init_result)
        assert init_payload["project_root"] == project.resolve().as_posix()
        assert init_payload["project_reentry_mode"] == "auto-recent-project"

        def _progress_render(cwd: Path, fmt: str) -> dict[str, str]:
            return {"cwd": cwd.resolve(strict=False).as_posix(), "fmt": fmt}

        monkeypatch.setattr("gpd.core.phases.progress_render", _progress_render)

        progress_result = runner.invoke(
            app,
            ["--raw", "--cwd", str(workspace), "progress"],
            catch_exceptions=False,
        )

        assert json_output_from_result(progress_result) == {
            "cwd": project.resolve().as_posix(),
            "fmt": "json",
        }

    def test_progress_surfaces_keep_local_phase_workspace_over_recent_project(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        workspace = tmp_path.parent / f"{tmp_path.name}-progress-local"
        local_phase = workspace / "GPD" / "phases" / "01-local"
        local_phase.mkdir(parents=True)
        (local_phase / "01-PLAN.md").write_text("local plan\n", encoding="utf-8")
        project = tmp_path / "recoverable-project"
        gpd_dir = project / "GPD"
        gpd_dir.mkdir(parents=True)
        (gpd_dir / "STATE.md").write_text("# Research State\n", encoding="utf-8")
        (gpd_dir / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
        (gpd_dir / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
        resume_file = gpd_dir / "phases" / "02" / ".continue-here.md"
        resume_file.parent.mkdir(parents=True, exist_ok=True)
        resume_file.write_text("resume\n", encoding="utf-8")
        data_root = tmp_path / "data"
        monkeypatch.setenv("GPD_DATA_DIR", str(data_root))
        record_recent_project(
            project,
            session_data={
                "last_date": "2026-03-29T12:00:00+00:00",
                "stopped_at": "Phase 02",
                "resume_file": "GPD/phases/02/.continue-here.md",
            },
            store_root=data_root,
        )

        validate_result = runner.invoke(
            app,
            ["--raw", "--cwd", str(workspace), "validate", "command-context", "progress"],
            catch_exceptions=False,
        )

        validate_payload = json_output_from_result(validate_result, expect_exit=1)
        checks = checks_by_name(validate_payload)
        assert validate_payload["passed"] is False
        assert checks["project_reentry"]["passed"] is True
        assert checks["project_reentry"]["detail"] == "current workspace or ancestor project root is recoverable"
        assert "auto-selected recoverable recent project" not in checks["project_reentry"]["detail"]
        assert "recent-project" not in checks["project_exists"]["detail"]

        init_result = runner.invoke(
            app,
            ["--raw", "--cwd", str(workspace), "init", "progress"],
            catch_exceptions=False,
        )

        init_payload = json_output_from_result(init_result)
        assert init_payload["project_root"] == workspace.resolve().as_posix()
        assert init_payload["project_reentry_mode"] == "current-workspace"
        assert (
            init_payload["project_reentry_selected_candidate"]["reason"]
            == "workspace carries local GPD phase directory"
        )

        def _progress_render(cwd: Path, fmt: str) -> dict[str, str]:
            return {"cwd": cwd.resolve(strict=False).as_posix(), "fmt": fmt}

        monkeypatch.setattr("gpd.core.phases.progress_render", _progress_render)

        progress_result = runner.invoke(
            app,
            ["--raw", "--cwd", str(workspace), "progress"],
            catch_exceptions=False,
        )

        assert json_output_from_result(progress_result) == {
            "cwd": workspace.resolve().as_posix(),
            "fmt": "json",
        }

    def test_command_context_resume_work_requires_reopen_for_unique_recent_project(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        workspace = tmp_path.parent / f"{tmp_path.name}-outside-unique-resume"
        workspace.mkdir()
        project = tmp_path / "recoverable-resume-project"
        gpd_dir = project / "GPD"
        gpd_dir.mkdir(parents=True)
        (gpd_dir / "STATE.md").write_text("# Research State\n", encoding="utf-8")
        (gpd_dir / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
        (gpd_dir / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
        resume_file = gpd_dir / "phases" / "02" / ".continue-here.md"
        resume_file.parent.mkdir(parents=True, exist_ok=True)
        resume_file.write_text("resume\n", encoding="utf-8")
        data_root = tmp_path / "data"
        monkeypatch.setenv("GPD_DATA_DIR", str(data_root))
        record_recent_project(
            project,
            session_data={
                "last_date": "2026-03-29T12:00:00+00:00",
                "stopped_at": "Phase 02",
                "resume_file": "GPD/phases/02/.continue-here.md",
            },
            store_root=data_root,
        )

        payload = _raw_json(
            ["--raw", "--cwd", str(workspace), "validate", "command-context", "resume-work"],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert payload["passed"] is False
        assert checks["project_reentry"]["passed"] is False
        assert "resume-work will not switch runtime workspaces silently" in checks["project_reentry"]["detail"]
        assert "unique recoverable recent GPD project" in payload["guidance"]
        assert "open that project folder in the runtime" in payload["guidance"]
        assert "gpd resume --recent" in payload["guidance"]

    def test_command_context_resume_work_requires_explicit_selection_when_recent_projects_are_ambiguous(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        workspace = tmp_path.parent / f"{tmp_path.name}-outside-ambiguous"
        workspace.mkdir()
        data_root = tmp_path / "data"
        monkeypatch.setenv("GPD_DATA_DIR", str(data_root))

        for name, stopped_at in (("project-a", "Phase 01"), ("project-b", "Phase 02")):
            project = tmp_path / name
            gpd_dir = project / "GPD"
            gpd_dir.mkdir(parents=True)
            (gpd_dir / "STATE.md").write_text("# Research State\n", encoding="utf-8")
            (gpd_dir / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
            (gpd_dir / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
            phase_number = stopped_at.removeprefix("Phase ").strip() or "01"
            resume_file = gpd_dir / "phases" / phase_number / ".continue-here.md"
            resume_file.parent.mkdir(parents=True, exist_ok=True)
            resume_file.write_text("resume\n", encoding="utf-8")
            record_recent_project(
                project,
                session_data={
                    "last_date": "2026-03-29T12:00:00+00:00",
                    "stopped_at": stopped_at,
                    "resume_file": f"GPD/phases/{phase_number}/.continue-here.md",
                },
                store_root=data_root,
            )

        payload = _raw_json(
            ["--raw", "--cwd", str(workspace), "validate", "command-context", "resume-work"],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert payload["passed"] is False
        assert checks["project_reentry"]["passed"] is False
        assert "multiple recoverable recent GPD projects" in payload["guidance"]

    @pytest.mark.parametrize(
        ("command_name", "context_mode", "expects_project_context_check", "expects_runtime_dispatch_note"),
        [
            ("help", "global", True, False),
            ("new-project", "projectless", True, False),
            ("map-research", "projectless", False, True),
            ("start", "projectless", True, True),
            ("tour", "projectless", True, True),
            ("health", "projectless", False, False),
            ("suggest-next", "projectless", False, False),
        ],
    )
    def test_command_context_projectless_and_global_commands_pass_without_project(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        dollar_command_prefix: str,
        command_name: str,
        context_mode: str,
        expects_project_context_check: bool,
        expects_runtime_dispatch_note: bool,
    ) -> None:
        empty_dir = tmp_path / "empty-context"
        empty_dir.mkdir()
        monkeypatch.chdir(empty_dir)

        payload = _raw_json(
            ["--raw", "--cwd", str(empty_dir), "validate", "command-context", command_name],
        )
        assert payload["command"] == f"gpd:{command_name}"
        assert payload["context_mode"] == context_mode
        assert payload["passed"] is True
        if expects_project_context_check:
            checks = checks_by_name(payload)
            assert checks["project_context"]["passed"] is True
        if expects_runtime_dispatch_note:
            assert payload["public_runtime_command_prefix"] == dollar_command_prefix
            assert f"public command surface rooted at `{dollar_command_prefix}`" in payload["dispatch_note"]

    @pytest.mark.parametrize("command_name", ["gpd:settings", "gpd:set-tier-models"])
    def test_command_context_surfaces_runtime_command_dispatch_note(
        self, dollar_command_prefix: str, command_name: str
    ) -> None:
        payload = _raw_json(
            ["--raw", "validate", "command-context", command_name],
        )
        assert payload["command"] == command_name
        assert payload["validated_surface"] == "public_runtime_dollar_command"
        assert payload["public_runtime_command_prefix"] == dollar_command_prefix
        assert payload["local_cli_equivalence_guaranteed"] is False
        assert f"public command surface rooted at `{dollar_command_prefix}`" in payload["dispatch_note"]
        assert "same-name local `gpd` subcommand" in payload["dispatch_note"]

    @pytest.mark.parametrize("command_name", ["gpd:settings", "gpd:set-tier-models"])
    def test_command_context_surfaces_slash_runtime_dispatch_note(
        self, slash_command_prefix: str, monkeypatch: pytest.MonkeyPatch, command_name: str
    ) -> None:
        monkeypatch.setattr(
            "gpd.cli.detect_runtime_for_gpd_use", lambda cwd=None: _SLASH_COMMAND_DESCRIPTOR.runtime_name
        )

        payload = _raw_json(
            ["--raw", "validate", "command-context", command_name],
        )
        assert payload["command"] == command_name
        assert payload["validated_surface"] == "public_runtime_slash_command"
        assert payload["public_runtime_command_prefix"] == slash_command_prefix
        assert payload["local_cli_equivalence_guaranteed"] is False
        assert f"public command surface rooted at `{slash_command_prefix}`" in payload["dispatch_note"]
        assert "same-name local `gpd` subcommand" in payload["dispatch_note"]

    @pytest.mark.parametrize("failure_mode", ["missing-runtime", "runtime-error"])
    @pytest.mark.parametrize("command_name", ["gpd:settings", "gpd:set-tier-models"])
    def test_command_context_falls_back_when_runtime_resolution_fails(
        self, monkeypatch: pytest.MonkeyPatch, command_name: str, failure_mode: str
    ) -> None:
        if failure_mode == "runtime-error":

            def _raise_runtime_error(cwd=None) -> str:
                raise RuntimeError("runtime resolution failed")

            monkeypatch.setattr("gpd.cli.detect_runtime_for_gpd_use", _raise_runtime_error)
        else:
            monkeypatch.setattr("gpd.cli.detect_runtime_for_gpd_use", lambda cwd=None: None)

        payload = _raw_json(
            ["--raw", "validate", "command-context", command_name],
        )
        assert payload["command"] == command_name
        assert payload["validated_surface"] == "public_runtime_command_surface"
        assert payload["public_runtime_command_prefix"] == ""
        assert payload["local_cli_equivalence_guaranteed"] is False
        assert "the active runtime command surface" in payload["dispatch_note"]
        assert "same-name local `gpd` subcommand" in payload["dispatch_note"]

    def test_config_set_autonomy_guided_path_uses_runtime_command_helper(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dollar_command_prefix: str
    ) -> None:
        monkeypatch.chdir(tmp_path)

        payload = _raw_json(
            ["--raw", "config", "set", "autonomy", '"balanced"'],
        )
        assert payload["guided_path"] == (
            f"Use `{dollar_command_prefix}settings` inside the runtime for guided autonomy changes."
        )

    def test_config_commands_use_ancestor_config_from_nested_workspace(self, tmp_path: Path) -> None:
        project_root = tmp_path / "project"
        nested_cwd = project_root / "scratch" / "notes"
        nested_cwd.mkdir(parents=True)
        config_path = project_root / "GPD" / "config.json"
        config_path.parent.mkdir(parents=True)
        config_path.write_text(
            json.dumps({"autonomy": "supervised", "parallelization": False, "research_mode": "adaptive"}),
            encoding="utf-8",
        )
        (project_root / "GPD" / "state.json").write_text(json.dumps(default_state_dict()), encoding="utf-8")
        nested_config_path = nested_cwd / "GPD" / "config.json"
        nested_config_path.parent.mkdir(parents=True)
        nested_config_path.write_text(
            json.dumps({"parallelization": True, "research_mode": "balanced"}),
            encoding="utf-8",
        )

        get_result = runner.invoke(
            app,
            ["--cwd", str(nested_cwd), "--raw", "config", "get", "parallelization"],
            catch_exceptions=False,
        )
        set_result = runner.invoke(
            app,
            ["--cwd", str(nested_cwd), "--raw", "config", "set", "research_mode", '"exploit"'],
            catch_exceptions=False,
        )
        ensure_result = runner.invoke(
            app,
            ["--cwd", str(nested_cwd), "--raw", "config", "ensure-section"],
            catch_exceptions=False,
        )

        get_payload = json_output_from_result(get_result)
        assert get_payload == {"key": "parallelization", "value": False, "found": True}

        set_payload = json_output_from_result(set_result)
        assert set_payload["canonical_key"] == "research_mode"
        assert set_payload["value"] == "exploit"

        ensure_payload = json_output_from_result(ensure_result)
        assert ensure_payload == {"created": False, "path": str(config_path)}

        written = json.loads(config_path.read_text(encoding="utf-8"))
        assert written["parallelization"] is False
        assert written["research_mode"] == "exploit"
        nested_written = json.loads(nested_config_path.read_text(encoding="utf-8"))
        assert nested_written == {"parallelization": True, "research_mode": "balanced"}

    def test_command_context_slides_passes_without_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        empty_dir = tmp_path / "empty-context"
        empty_dir.mkdir()
        monkeypatch.chdir(empty_dir)

        payload = _raw_json(
            ["--raw", "--cwd", str(empty_dir), "validate", "command-context", "slides"],
        )
        assert payload["command"] == "gpd:slides"
        assert payload["context_mode"] == "projectless"
        assert payload["passed"] is True

    def test_command_context_project_aware_requires_explicit_inputs_without_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dollar_command_prefix: str
    ) -> None:
        outside_dir = tmp_path.parent / f"{tmp_path.name}-outside-aware"
        outside_dir.mkdir()
        monkeypatch.chdir(outside_dir)

        payload = _raw_json(
            ["--raw", "--cwd", str(outside_dir), "validate", "command-context", "digest-knowledge"],
            expect_exit=1,
        )
        assert payload["command"] == "gpd:digest-knowledge"
        assert payload["context_mode"] == "project-aware"
        assert payload["passed"] is False
        assert payload["explicit_inputs"] == ["knowledge document path", "source path", "arxiv id", "topic"]
        assert payload["guidance"] == (
            "Either provide knowledge document path, source path, arxiv id, and topic explicitly, or initialize a project with "
            f"`{dollar_command_prefix}new-project` in the runtime surface or `gpd init new-project` in the local CLI."
        )

    def test_review_preflight_propagates_runtime_surface_metadata(self, dollar_command_prefix: str) -> None:
        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "peer-review"],
        )
        assert payload["validated_surface"] == "public_runtime_dollar_command"
        assert payload["public_runtime_command_prefix"] == dollar_command_prefix
        assert payload["local_cli_equivalence_guaranteed"] is False
        assert f"public command surface rooted at `{dollar_command_prefix}`" in payload["dispatch_note"]
        assert payload["conditional_requirements"] == [
            PROJECT_BACKED_PEER_REVIEW_CONDITIONAL,
            THEOREM_BEARING_PEER_REVIEW_CONDITIONAL,
        ]
        checks = checks_by_name(payload)
        assert "same-name local `gpd` subcommand" in checks["command_context"]["detail"]
        assert checks["artifact_manifest"]["passed"] is True
        assert checks["bibliography_audit"]["passed"] is True
        assert checks["reproducibility_manifest"]["passed"] is True
        assert checks["manuscript_proof_review"]["passed"] is True

    def test_review_contract_preflight_helpers_only_follow_explicit_checks(self) -> None:
        contract = SimpleNamespace(
            preflight_checks=["command_context"],
            conditional_requirements=[
                SimpleNamespace(
                    preflight_checks=["artifact_manifest"],
                    blocking_preflight_checks=["artifact_manifest"],
                )
            ],
            required_evidence=[
                "verification reports",
                "manuscript-root artifact manifest",
                "manuscript-root bibliography audit",
            ],
            blocking_conditions=[
                "missing compiled manuscript",
                "missing latest staged peer-review decision evidence",
            ],
        )

        assert cli_module._review_contract_requests_check(contract, "artifact_manifest") is True
        assert cli_module._review_preflight_check_is_blocking(contract, "artifact_manifest") is False
        assert cli_module._review_contract_requests_check(contract, "verification_reports") is False
        assert cli_module._review_preflight_check_is_blocking(contract, "verification_reports") is False
        assert cli_module._review_contract_requests_check(contract, "compiled_manuscript") is False
        assert cli_module._review_preflight_check_is_blocking(contract, "compiled_manuscript") is False
        assert cli_module._review_contract_requests_check(contract, "review_ledger") is False
        assert cli_module._review_preflight_check_is_blocking(contract, "review_ledger") is False
        assert (
            cli_module._review_preflight_check_is_blocking(
                contract,
                "artifact_manifest",
                conditional_blocking_preflight_checks={"artifact_manifest"},
            )
            is True
        )

    def test_validate_review_preflight_help_mentions_manuscript_and_referee_subjects(self) -> None:
        output = _help_text("validate", "review-preflight", catch_exceptions=False)
        assert "Optional phase number, manuscript target" in output
        assert "referee report source" in output

    def test_init_peer_review_help_surfaces_target_argument_and_stage_option(self) -> None:
        output = _help_text("init", "peer-review", catch_exceptions=False)
        assert "[SUBJECT]" in output
        assert "Optional explicit review target path" in output
        assert "--stage" in output

    def test_init_peer_review_accepts_explicit_standalone_target_and_surfaces_mode(
        self,
        gpd_project: Path,
    ) -> None:
        external_txt = gpd_project / "external-review.txt"
        external_txt.write_text("Standalone review surface.\n", encoding="utf-8")

        payload = _raw_json(
            ["--raw", "--cwd", str(gpd_project), "init", "peer-review", external_txt.name],
        )
        assert payload["review_target_input"] == external_txt.name
        assert payload["review_target_mode"] == "standalone explicit-artifact review"
        assert "standalone explicit-artifact intake applies" in payload["review_target_mode_reason"]
        assert payload["resolved_review_target"] == str(external_txt)
        assert payload["resolved_review_root"] == str(gpd_project)
        assert payload["publication_lane_kind"] == "external_artifact"
        assert payload["publication_lane_owner"] == "external_artifact"
        assert payload["publication_subject_slug"]
        managed_root = f"GPD/publication/{payload['publication_subject_slug']}"
        assert payload["managed_publication_root"] == managed_root
        assert payload["selected_publication_root"] == managed_root
        assert payload["selected_review_root"] == f"{managed_root}/review"
        assert payload["manuscript_resolution_status"] == "resolved"
        assert payload["manuscript_entrypoint"] == external_txt.name
        assert payload["project_contract"] is None
        assert payload["artifact_manifest_path"] is None
        assert payload["latest_review_round"] is None
        assert payload["latest_response_round"] is None

    def test_init_peer_review_stage_bootstrap_includes_target_aware_mode_fields(
        self,
        gpd_project: Path,
    ) -> None:
        external_txt = gpd_project / "external-review-stage.txt"
        external_txt.write_text("Standalone stage review surface.\n", encoding="utf-8")

        payload = _raw_json(
            [
                "--raw",
                "--cwd",
                str(gpd_project),
                "init",
                "peer-review",
                external_txt.name,
                "--stage",
                "bootstrap",
            ],
        )
        assert payload["review_target_input"] == external_txt.name
        assert payload["review_target_mode"] == "standalone explicit-artifact review"
        assert payload["resolved_review_target"] == str(external_txt)
        assert payload["resolved_review_root"] == str(gpd_project)
        assert payload["publication_lane_kind"] == "external_artifact"
        assert payload["publication_lane_owner"] == "external_artifact"
        assert payload["publication_subject_slug"]
        managed_root = f"GPD/publication/{payload['publication_subject_slug']}"
        assert payload["managed_publication_root"] == managed_root
        assert payload["selected_publication_root"] == managed_root
        assert payload["selected_review_root"] == f"{managed_root}/review"
        assert payload["staged_loading"]["stage_id"] == "bootstrap"

    @pytest.mark.parametrize(
        "review_target",
        [
            "GPD/publication/curvature-flow",
            "GPD/publication/curvature-flow/manuscript",
            "GPD/publication/curvature-flow/manuscript/managed_manuscript.tex",
        ],
    )
    def test_init_peer_review_treats_explicit_managed_publication_target_as_project_backed(
        self,
        gpd_project: Path,
        review_target: str,
    ) -> None:
        manuscript = _write_managed_publication_manuscript(gpd_project)

        payload = _raw_json(
            [
                "--raw",
                "--cwd",
                str(gpd_project),
                "init",
                "peer-review",
                review_target,
            ],
        )
        assert payload["review_target_mode"] == "project-backed manuscript review"
        assert payload["publication_target_mode"] == "project_explicit_manuscript"
        assert payload["publication_target_project_context_role"] == "authoritative"
        assert payload["publication_lane_kind"] == "managed_publication_manuscript"
        assert payload["publication_lane_owner"] == "project_managed"
        assert payload["publication_subject_slug"] == "curvature-flow"
        assert payload["selected_publication_root"] == "GPD/publication/curvature-flow"
        assert payload["selected_review_root"] == "GPD/publication/curvature-flow/review"
        assert payload["manuscript_root"] == "GPD/publication/curvature-flow/manuscript"
        assert payload["manuscript_entrypoint"] == "GPD/publication/curvature-flow/manuscript/managed_manuscript.tex"
        assert payload["artifact_manifest_path"] == "GPD/publication/curvature-flow/manuscript/ARTIFACT-MANIFEST.json"
        assert payload["bibliography_audit_path"] == "GPD/publication/curvature-flow/manuscript/BIBLIOGRAPHY-AUDIT.json"
        assert payload["resolved_review_target"] == str(manuscript)
        assert payload["resolved_review_root"] == str(manuscript.parent)

    def test_init_respond_to_referees_stage_preserves_external_subject_response_roots(
        self,
        gpd_project: Path,
    ) -> None:
        external_manuscript = gpd_project / "external-response-manuscript.tex"
        external_manuscript.write_text(
            "\\documentclass{article}\n\\begin{document}\nExternal response target.\n\\end{document}\n",
            encoding="utf-8",
        )

        payload = _raw_json(
            [
                "--raw",
                "--cwd",
                str(gpd_project),
                "init",
                "respond-to-referees",
                "--stage",
                "report_triage",
                "--",
                "--manuscript",
                external_manuscript.name,
                "--report",
                "reports/referee-report.md",
            ],
        )
        assert payload["publication_lane_kind"] == "external_artifact"
        assert payload["managed_publication_root"] == f"GPD/publication/{payload['publication_subject_slug']}"
        assert payload["selected_publication_root"] == payload["managed_publication_root"]
        assert payload["selected_review_root"] == f"{payload['managed_publication_root']}/review"

    def test_init_peer_review_proof_review_detail_uses_active_manuscript_wording_without_final_review_artifacts(
        self,
        gpd_project: Path,
    ) -> None:
        package = write_proof_review_package(gpd_project, theorem_bearing=True, review_report=False)
        review_dir = gpd_project / "GPD" / "review"
        (review_dir / "REVIEW-LEDGER.json").unlink()
        (review_dir / "REFEREE-DECISION.json").unlink()
        math_stage_path = review_dir / "STAGE-math.json"
        math_stage_payload = json.loads(math_stage_path.read_text(encoding="utf-8"))
        math_stage_payload["manuscript_path"] = "paper/other.tex"
        math_stage_path.write_text(json.dumps(math_stage_payload), encoding="utf-8")

        payload = _raw_json(
            ["--raw", "--cwd", str(gpd_project), "init", "peer-review", str(package.manuscript_path)],
        )
        detail = payload["derived_manuscript_proof_review_status"]["detail"]
        assert payload["latest_review_artifacts"] is None
        assert "active manuscript" in detail
        assert "referee decision manuscript_path" not in detail

    def test_review_preflight_peer_review_project_backed_mode_surfaces_effective_contract_fields(
        self,
        gpd_project: Path,
    ) -> None:
        payload = _raw_json(
            ["--raw", "--cwd", str(gpd_project), "validate", "review-preflight", "peer-review"],
        )
        assert payload["resolved_mode"] == "project-backed manuscript review"
        assert payload["effective_required_evidence"] == [
            "existing manuscript or explicit external artifact target",
            "phase summaries or milestone digest",
            "verification reports",
            "manuscript-root bibliography audit",
            "manuscript-root artifact manifest",
            "manuscript-root reproducibility manifest",
            "manuscript-root publication artifacts",
        ]
        assert payload["effective_blocking_conditions"] == [
            "missing manuscript or explicit external artifact target",
            "degraded review integrity",
            "unsupported physical significance claims",
            "collapsed novelty or venue fit",
            "missing project state",
            "missing roadmap",
            "missing conventions",
            "no research artifacts",
        ]

    def test_review_preflight_peer_review_standalone_mode_omits_project_backed_effective_contract_fields(
        self,
        gpd_project: Path,
    ) -> None:
        external_txt = gpd_project / "external-review-preflight.txt"
        external_txt.write_text("Standalone review surface.\n", encoding="utf-8")

        payload = _raw_json(
            [
                "--raw",
                "--cwd",
                str(gpd_project),
                "validate",
                "review-preflight",
                "peer-review",
                external_txt.name,
            ],
        )
        assert payload["resolved_mode"] == "standalone explicit-artifact review"
        assert payload["effective_required_evidence"] == [
            "existing manuscript or explicit external artifact target",
        ]
        assert payload["effective_blocking_conditions"] == [
            "missing manuscript or explicit external artifact target",
            "degraded review integrity",
            "unsupported physical significance claims",
            "collapsed novelty or venue fit",
        ]

    def test_command_required_files_override_detail_uses_contract_metadata_not_command_name(
        self, tmp_path: Path
    ) -> None:
        manuscript = canonical_manuscript_path(tmp_path)
        manuscript.parent.mkdir(parents=True, exist_ok=True)
        manuscript.write_text(
            "\\documentclass{article}\n\\begin{document}\nDraft.\n\\end{document}\n",
            encoding="utf-8",
        )
        _refresh_artifact_manifest_for_manuscript(tmp_path, manuscript)
        command = SimpleNamespace(
            name="gpd:custom-review",
            requires={"files": ["paper/*.tex"]},
            review_contract=SimpleNamespace(preflight_checks=["manuscript", "compiled_manuscript"]),
        )

        detail = _command_required_files_override_detail(
            tmp_path,
            command,
            str(manuscript.relative_to(tmp_path)),
            workspace_cwd=tmp_path,
        )

        assert detail is not None
        assert "explicit manuscript target satisfies command context" in detail

    def test_command_required_files_override_detail_skips_referee_source_commands(self, tmp_path: Path) -> None:
        manuscript = canonical_manuscript_path(tmp_path)
        manuscript.parent.mkdir(parents=True, exist_ok=True)
        manuscript.write_text(
            "\\documentclass{article}\n\\begin{document}\nDraft.\n\\end{document}\n",
            encoding="utf-8",
        )
        command = SimpleNamespace(
            name="gpd:custom-referees",
            requires={"files": ["paper/*.tex"]},
            review_contract=SimpleNamespace(preflight_checks=["manuscript", "referee_report_source"]),
        )

        detail = _command_required_files_override_detail(
            tmp_path,
            command,
            str(manuscript.relative_to(tmp_path)),
            workspace_cwd=tmp_path,
        )

        assert detail is None

    def test_command_context_manuscript_check_allows_bootstrap_from_contract_metadata(self, tmp_path: Path) -> None:
        isolated_root = tmp_path / "bootstrap-context"
        isolated_root.mkdir(parents=True, exist_ok=True)
        command = SimpleNamespace(
            name="gpd:custom-write",
            requires={},
            review_contract=SimpleNamespace(preflight_checks=["manuscript"]),
        )

        result = _command_context_manuscript_check(
            isolated_root,
            command,
            arguments=None,
            workspace_cwd=isolated_root,
        )

        assert result is not None
        passed, detail = result
        assert passed is True
        assert "fresh bootstrap is allowed" in detail

    def test_command_context_publication_policy_overrides_removed_required_context_and_suffixes(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        workspace = tmp_path / "publication-policy"
        workspace.mkdir()
        (workspace / "notes.txt").write_text("Standalone publication artifact.\n", encoding="utf-8")
        monkeypatch.chdir(workspace)

        command = SimpleNamespace(
            name="gpd:custom-publication-review",
            context_mode="project-required",
            argument_hint="",
            project_reentry_capable=False,
            requires={"files": ["paper/*.tex"]},
            command_policy=SimpleNamespace(
                subject_policy=SimpleNamespace(
                    subject_kind="publication",
                    resolution_mode="explicit_or_project_manuscript",
                    explicit_input_kinds=["publication_artifact_path"],
                    allow_external_subjects=True,
                    allowed_suffixes=[".txt"],
                ),
                supporting_context_policy=SimpleNamespace(
                    project_context_mode="project-aware",
                    project_reentry_mode="disallowed",
                    required_file_patterns=[],
                ),
            ),
            review_contract=SimpleNamespace(
                review_mode="publication",
                preflight_checks=["command_context", "manuscript"],
                required_outputs=[],
                required_evidence=[],
                blocking_conditions=[],
                conditional_requirements=[],
                scope_variants=[],
            ),
        )

        monkeypatch.setattr(
            cli_module,
            "_resolve_registry_command",
            lambda command_name: (command, "gpd:custom-publication-review"),
        )

        payload = _raw_json(
            ["--raw", "--cwd", str(workspace), "validate", "command-context", "custom-publication-review", "notes.txt"],
        )
        checks = checks_by_name(payload)
        assert payload["command"] == "gpd:custom-publication-review"
        assert payload["context_mode"] == "project-aware"
        assert payload["passed"] is True
        assert checks["explicit_inputs"]["passed"] is True
        assert payload["resolved_subject"]["status"] == "resolved"
        assert payload["resolved_subject"]["ownership_mode"] == "external_artifact"
        assert payload["resolved_subject"]["target_path"].endswith("notes.txt")

    def test_review_preflight_publication_scope_variants_drive_runtime_overrides(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        workspace = tmp_path / "publication-scope-variant"
        workspace.mkdir()
        (workspace / "notes.txt").write_text("Standalone publication artifact.\n", encoding="utf-8")
        monkeypatch.chdir(workspace)

        command = SimpleNamespace(
            name="gpd:custom-publication-review",
            context_mode="project-required",
            argument_hint="",
            project_reentry_capable=False,
            requires={"files": ["paper/*.tex"]},
            command_policy=SimpleNamespace(
                subject_policy=SimpleNamespace(
                    subject_kind="publication",
                    resolution_mode="explicit_or_project_manuscript",
                    explicit_input_kinds=["publication_artifact_path"],
                    allow_external_subjects=True,
                    allowed_suffixes=[".txt"],
                ),
                supporting_context_policy=SimpleNamespace(
                    project_context_mode="project-aware",
                    project_reentry_mode="disallowed",
                    required_file_patterns=[],
                ),
            ),
            review_contract=SimpleNamespace(
                review_mode="publication",
                required_outputs=["GPD/review/DEFAULT-REPORT.md"],
                required_evidence=["project-backed review evidence"],
                blocking_conditions=["missing project state"],
                preflight_checks=[
                    "command_context",
                    "project_state",
                    "roadmap",
                    "conventions",
                    "manuscript",
                    "artifact_manifest",
                    "bibliography_audit",
                ],
                stage_artifacts=[],
                conditional_requirements=[],
                scope_variants=[
                    SimpleNamespace(
                        scope="explicit_artifact",
                        activation="explicit external artifact subject was supplied",
                        relaxed_preflight_checks=["project_state", "roadmap", "conventions"],
                        optional_preflight_checks=["artifact_manifest", "bibliography_audit"],
                        required_outputs_override=["GPD/review/ARTIFACT-REPORT.md"],
                        required_evidence_override=["resolved explicit artifact subject"],
                        blocking_conditions_override=["missing manuscript"],
                    )
                ],
            ),
        )

        monkeypatch.setattr(
            cli_module,
            "_resolve_registry_command",
            lambda command_name: (command, "gpd:custom-publication-review"),
        )

        payload = _raw_json(
            [
                "--raw",
                "--cwd",
                str(workspace),
                "validate",
                "review-preflight",
                "custom-publication-review",
                "notes.txt",
            ],
        )
        checks = checks_by_name(payload)
        assert payload["command"] == "gpd:custom-publication-review"
        assert payload["passed"] is True
        assert payload["required_outputs"] == ["GPD/review/ARTIFACT-REPORT.md"]
        assert payload["required_evidence"] == ["resolved explicit artifact subject"]
        assert payload["blocking_conditions"] == ["missing manuscript"]
        assert checks["project_state"]["passed"] is True
        assert checks["project_state"]["blocking"] is False
        assert checks["roadmap"]["passed"] is True
        assert checks["roadmap"]["blocking"] is False
        assert checks["conventions"]["passed"] is True
        assert checks["conventions"]["blocking"] is False
        assert checks["artifact_manifest"]["passed"] is True
        assert checks["artifact_manifest"]["blocking"] is False
        assert checks["bibliography_audit"]["passed"] is True
        assert checks["bibliography_audit"]["blocking"] is False

    def test_review_preflight_falls_back_when_runtime_resolution_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("gpd.cli.detect_runtime_for_gpd_use", lambda cwd=None: None)

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "peer-review"],
        )
        assert payload["validated_surface"] == "public_runtime_command_surface"
        assert payload["public_runtime_command_prefix"] == ""
        assert payload["local_cli_equivalence_guaranteed"] is False
        assert "the active runtime command surface" in payload["dispatch_note"]

    @pytest.mark.parametrize(
        ("command_name", "args", "explicit_inputs"),
        [
            (
                "compare-experiment",
                ["predictions.csv", "experiment.csv"],
                ["prediction, dataset path, phase identifier, or comparison target"],
            ),
            (
                "compare-results",
                ["results/01-SUMMARY.md"],
                ["comparison target, phase, artifact path, or source-a vs source-b"],
            ),
            ("discover", ["finite-temperature RG flow", "--depth", "deep"], ["phase number or standalone topic"]),
            ("explain", ["Ward identity"], ["concept, result, method, notation, or paper"]),
            ("literature-review", ["Sachdev-Ye-Kitaev model thermodynamics"], ["topic or research question"]),
        ],
    )
    def test_command_context_current_workspace_helpers_accept_explicit_inputs_without_project(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        command_name: str,
        args: list[str],
        explicit_inputs: list[str],
    ) -> None:
        outside_dir = tmp_path.parent / f"{tmp_path.name}-{command_name}-explicit-standalone"
        outside_dir.mkdir()
        monkeypatch.chdir(outside_dir)

        payload = _raw_json(
            ["--raw", "--cwd", str(outside_dir), "validate", "command-context", command_name, *args],
        )
        checks = checks_by_name(payload)
        assert payload["command"] == f"gpd:{command_name}"
        assert payload["context_mode"] == "project-aware"
        assert payload["passed"] is True
        assert payload["explicit_inputs"] == explicit_inputs
        assert checks["project_exists"]["passed"] is False
        assert checks["explicit_inputs"]["passed"] is True
        assert checks["explicit_inputs"]["detail"] == "explicit standalone inputs detected"

    @pytest.mark.parametrize(
        ("command_name", "args", "explicit_inputs"),
        [
            ("derive-equation", ["derive the one-loop beta function"], ["equation or topic to derive"]),
            ("dimensional-analysis", ["results.md"], ["phase number or file path"]),
            ("limiting-cases", ["results.md"], ["phase number or file path"]),
            ("numerical-convergence", ["results.csv"], ["phase number or file path"]),
            (
                "parameter-sweep",
                ["results/mesh-study.py", "--param", "coupling", "--range", "0:1:20"],
                ["computation anchor or file path", "--param name", "--range start:end:steps"],
            ),
            (
                "sensitivity-analysis",
                ["--target", "energy-gap", "--params", "g,m"],
                ["--target quantity", "--params p1,p2,..."],
            ),
        ],
    )
    def test_command_context_project_aware_analysis_wrappers_accept_explicit_inputs_without_project(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        command_name: str,
        args: list[str],
        explicit_inputs: list[str],
    ) -> None:
        outside_dir = tmp_path.parent / f"{tmp_path.name}-{command_name}-explicit"
        outside_dir.mkdir()
        monkeypatch.chdir(outside_dir)

        payload = _raw_json(
            ["--raw", "--cwd", str(outside_dir), "validate", "command-context", command_name, *args],
        )
        checks = checks_by_name(payload)
        assert payload["command"] == f"gpd:{command_name}"
        assert payload["context_mode"] == "project-aware"
        assert payload["passed"] is True
        assert payload["explicit_inputs"] == explicit_inputs
        assert checks["project_exists"]["passed"] is False
        assert checks["explicit_inputs"]["passed"] is True

    @pytest.mark.parametrize(
        ("command_name", "explicit_inputs", "guidance_prefix"),
        [
            (
                "derive-equation",
                ["equation or topic to derive"],
                "Either provide equation or topic to derive explicitly",
            ),
            (
                "dimensional-analysis",
                ["phase number or file path"],
                "Either provide phase number or file path explicitly",
            ),
            (
                "limiting-cases",
                ["phase number or file path"],
                "Either provide phase number or file path explicitly",
            ),
            (
                "numerical-convergence",
                ["phase number or file path"],
                "Either provide phase number or file path explicitly",
            ),
            (
                "parameter-sweep",
                ["computation anchor or file path", "--param name", "--range start:end:steps"],
                "Either provide computation anchor or file path, --param name, and --range start:end:steps explicitly",
            ),
            (
                "sensitivity-analysis",
                ["--target quantity", "--params p1,p2,..."],
                "Either provide --target quantity and --params p1,p2,... explicitly",
            ),
        ],
    )
    def test_command_context_project_aware_analysis_wrappers_require_explicit_inputs_without_project(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        dollar_command_prefix: str,
        command_name: str,
        explicit_inputs: list[str],
        guidance_prefix: str,
    ) -> None:
        outside_dir = tmp_path.parent / f"{tmp_path.name}-{command_name}-missing"
        outside_dir.mkdir()
        monkeypatch.chdir(outside_dir)

        payload = _raw_json(
            ["--raw", "--cwd", str(outside_dir), "validate", "command-context", command_name],
            expect_exit=1,
        )
        assert payload["command"] == f"gpd:{command_name}"
        assert payload["context_mode"] == "project-aware"
        assert payload["passed"] is False
        assert payload["explicit_inputs"] == explicit_inputs
        assert payload["guidance"] == (
            f"{guidance_prefix}, or initialize a project with `{dollar_command_prefix}new-project` "
            "in the runtime surface or `gpd init new-project` in the local CLI."
        )

    def test_command_context_parameter_sweep_rejects_bare_phase_anchor_without_project(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        dollar_command_prefix: str,
    ) -> None:
        outside_dir = tmp_path.parent / f"{tmp_path.name}-parameter-sweep-phase-only"
        outside_dir.mkdir()
        monkeypatch.chdir(outside_dir)

        payload = _raw_json(
            [
                "--raw",
                "--cwd",
                str(outside_dir),
                "validate",
                "command-context",
                "parameter-sweep",
                "3",
                "--param",
                "coupling",
                "--range",
                "0:1:20",
            ],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert payload["command"] == "gpd:parameter-sweep"
        assert payload["context_mode"] == "project-aware"
        assert payload["passed"] is False
        assert payload["explicit_inputs"] == [
            "computation anchor or file path",
            "--param name",
            "--range start:end:steps",
        ]
        assert checks["project_exists"]["passed"] is False
        assert checks["explicit_inputs"]["passed"] is False
        assert checks["explicit_inputs"]["detail"] == (
            "missing explicit standalone inputs (computation anchor or file path, --param name, --range start:end:steps)"
        )
        assert payload["guidance"] == (
            f"Either provide computation anchor or file path, --param name, and --range start:end:steps explicitly, "
            f"or initialize a project with `{dollar_command_prefix}new-project` in the runtime surface or "
            "`gpd init new-project` in the local CLI."
        )

    @pytest.mark.parametrize(
        "command_name",
        [
            "derive-equation",
            "dimensional-analysis",
            "limiting-cases",
            "numerical-convergence",
            "sensitivity-analysis",
        ],
    )
    def test_command_context_analysis_managed_outputs_anchor_to_invoking_workspace_without_initialized_project(
        self,
        tmp_path: Path,
        command_name: str,
    ) -> None:
        ancestor_root = tmp_path / "ancestor-root"
        (ancestor_root / "GPD").mkdir(parents=True)
        workspace = ancestor_root / "scratch" / command_name
        workspace.mkdir(parents=True)
        patched_command = _command_with_analysis_output_policy(command_name)
        managed_output_context_root = _command_managed_output_context_root(
            workspace_root=workspace,
            context_root=ancestor_root,
            project_exists=False,
        )
        managed_output_root = _command_managed_output_root(
            patched_command,
            project_root=managed_output_context_root,
        )

        assert managed_output_root == (workspace / "GPD" / "analysis").resolve(strict=False)
        assert managed_output_root != (ancestor_root / "GPD" / "analysis").resolve(strict=False)

    def test_command_context_analysis_managed_outputs_preserve_project_root_when_initialized_project_exists(
        self,
        tmp_path: Path,
    ) -> None:
        project_root = tmp_path / "project-root"
        (project_root / "GPD").mkdir(parents=True)
        (project_root / "GPD" / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
        workspace = project_root / "notes" / "scratch"
        workspace.mkdir(parents=True)
        patched_command = _command_with_analysis_output_policy("derive-equation")
        managed_output_context_root = _command_managed_output_context_root(
            workspace_root=workspace,
            context_root=project_root,
            project_exists=True,
        )
        managed_output_root = _command_managed_output_root(
            patched_command,
            project_root=managed_output_context_root,
        )

        assert managed_output_root == (project_root / "GPD" / "analysis").resolve(strict=False)

    def test_command_context_parameter_sweep_managed_outputs_anchor_to_invoking_workspace_without_initialized_project(
        self,
        tmp_path: Path,
    ) -> None:
        ancestor_root = tmp_path / "ancestor-root"
        (ancestor_root / "GPD").mkdir(parents=True)
        workspace = ancestor_root / "scratch" / "parameter-sweep"
        workspace.mkdir(parents=True)
        command = registry_module.get_command("parameter-sweep")
        managed_output_context_root = _command_managed_output_context_root(
            workspace_root=workspace,
            context_root=ancestor_root,
            project_exists=False,
        )
        managed_output_root = _command_managed_output_root(
            command,
            project_root=managed_output_context_root,
        )

        assert managed_output_root == (workspace / "GPD" / "sweeps").resolve(strict=False)
        assert managed_output_root != (ancestor_root / "GPD" / "sweeps").resolve(strict=False)

    def test_command_context_parameter_sweep_managed_outputs_preserve_project_root_when_initialized_project_exists(
        self,
        tmp_path: Path,
    ) -> None:
        project_root = tmp_path / "project-root"
        (project_root / "GPD").mkdir(parents=True)
        (project_root / "GPD" / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
        workspace = project_root / "notes" / "scratch"
        workspace.mkdir(parents=True)
        command = registry_module.get_command("parameter-sweep")
        managed_output_context_root = _command_managed_output_context_root(
            workspace_root=workspace,
            context_root=project_root,
            project_exists=True,
        )
        managed_output_root = _command_managed_output_root(
            command,
            project_root=managed_output_context_root,
        )

        assert managed_output_root == (project_root / "GPD" / "sweeps").resolve(strict=False)

    @pytest.mark.parametrize(
        ("command_name", "args", "explicit_inputs"),
        [
            ("compare-experiment", [], ["prediction, dataset path, phase identifier, or comparison target"]),
            ("compare-results", [], ["comparison target, phase, artifact path, or source-a vs source-b"]),
            ("discover", [], ["phase number or standalone topic"]),
            ("discover", ["-d", "deep"], ["phase number or standalone topic"]),
            ("explain", [], ["concept, result, method, notation, or paper"]),
        ],
    )
    def test_command_context_current_workspace_helpers_allow_interactive_standalone_intake_without_project(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        command_name: str,
        args: list[str],
        explicit_inputs: list[str],
    ) -> None:
        outside_dir = tmp_path.parent / f"{tmp_path.name}-{command_name}-interactive-standalone"
        outside_dir.mkdir()
        monkeypatch.chdir(outside_dir)

        payload = _raw_json(
            ["--raw", "--cwd", str(outside_dir), "validate", "command-context", command_name, *args],
        )
        checks = checks_by_name(payload)
        assert payload["command"] == f"gpd:{command_name}"
        assert payload["context_mode"] == "project-aware"
        assert payload["passed"] is True
        assert payload["project_exists"] is False
        assert payload["explicit_inputs"] == explicit_inputs
        assert payload["guidance"] == ""
        assert checks["project_exists"]["passed"] is False
        assert checks["explicit_inputs"]["passed"] is True
        assert checks["explicit_inputs"]["blocking"] is False
        assert "interactive" in checks["explicit_inputs"]["detail"]
        assert "missing explicit standalone inputs" not in checks["explicit_inputs"]["detail"]

    def test_command_context_literature_review_fails_closed_without_project_topic(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        outside_dir = tmp_path.parent / f"{tmp_path.name}-literature-review-empty-standalone"
        outside_dir.mkdir()
        monkeypatch.chdir(outside_dir)

        payload = _raw_json(
            ["--raw", "--cwd", str(outside_dir), "validate", "command-context", "literature-review"],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert payload["command"] == "gpd:literature-review"
        assert payload["passed"] is False
        assert payload["project_exists"] is False
        assert payload["guidance"].startswith("Either provide topic or research question explicitly")
        assert checks["explicit_inputs"]["passed"] is False
        assert checks["explicit_inputs"]["blocking"] is True
        assert checks["explicit_inputs"]["detail"] == "missing explicit standalone inputs (topic or research question)"
        assert payload["resolved_subject"]["status"] == "missing"

    def test_command_context_literature_review_project_backed_empty_allows_topic_clarification(
        self,
        gpd_project: Path,
    ) -> None:
        payload = _raw_json(
            ["--raw", "--cwd", str(gpd_project), "validate", "command-context", "literature-review"],
        )
        checks = checks_by_name(payload)
        assert payload["passed"] is True
        assert payload["project_exists"] is True
        assert checks["explicit_inputs"]["passed"] is True
        assert checks["explicit_inputs"]["blocking"] is False
        assert payload["resolved_subject"]["status"] == "interactive"
        assert "interactive intake can prompt for topic or research question" in checks["explicit_inputs"]["detail"]

    def test_command_context_digest_knowledge_requires_explicit_inputs_without_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        outside_dir = tmp_path.parent / f"{tmp_path.name}-outside-digest-knowledge"
        outside_dir.mkdir()
        monkeypatch.chdir(outside_dir)

        payload = _raw_json(
            ["--raw", "--cwd", str(outside_dir), "validate", "command-context", "digest-knowledge"],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert payload["command"] == "gpd:digest-knowledge"
        assert payload["context_mode"] == "project-aware"
        assert payload["passed"] is False
        assert checks["project_exists"]["passed"] is False
        assert checks["explicit_inputs"]["passed"] is False

    def test_command_context_digest_knowledge_accepts_explicit_topic_without_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        outside_dir = tmp_path.parent / f"{tmp_path.name}-outside-digest-knowledge-topic"
        outside_dir.mkdir()
        monkeypatch.chdir(outside_dir)

        payload = _raw_json(
            [
                "--raw",
                "--cwd",
                str(outside_dir),
                "validate",
                "command-context",
                "digest-knowledge",
                "renormalization group fixed points",
            ],
        )
        checks = checks_by_name(payload)
        assert payload["command"] == "gpd:digest-knowledge"
        assert payload["context_mode"] == "project-aware"
        assert payload["passed"] is True
        assert checks["project_exists"]["passed"] is False
        assert checks["explicit_inputs"]["passed"] is True

    def test_command_context_digest_knowledge_accepts_explicit_file_path_without_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        outside_dir = tmp_path.parent / f"{tmp_path.name}-outside-digest-knowledge-file"
        outside_dir.mkdir()
        knowledge_dir = outside_dir / "GPD" / "knowledge"
        knowledge_dir.mkdir(parents=True)
        knowledge_file = knowledge_dir / "K-renormalization-group-fixed-points.md"
        knowledge_file.write_text("knowledge doc\n", encoding="utf-8")
        monkeypatch.chdir(outside_dir)

        payload = _raw_json(
            [
                "--raw",
                "--cwd",
                str(outside_dir),
                "validate",
                "command-context",
                "digest-knowledge",
                knowledge_file.relative_to(outside_dir).as_posix(),
            ],
        )
        checks = checks_by_name(payload)
        assert payload["command"] == "gpd:digest-knowledge"
        assert payload["context_mode"] == "project-aware"
        assert payload["passed"] is True
        assert checks["project_exists"]["passed"] is False
        assert checks["explicit_inputs"]["passed"] is True

    def test_command_context_digest_knowledge_accepts_explicit_modern_arxiv_without_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        outside_dir = tmp_path.parent / f"{tmp_path.name}-outside-digest-knowledge-arxiv"
        outside_dir.mkdir()
        monkeypatch.chdir(outside_dir)

        payload = _raw_json(
            ["--raw", "--cwd", str(outside_dir), "validate", "command-context", "digest-knowledge", "2401.12345v2"],
        )
        checks = checks_by_name(payload)
        assert payload["command"] == "gpd:digest-knowledge"
        assert payload["context_mode"] == "project-aware"
        assert payload["passed"] is True
        assert checks["project_exists"]["passed"] is False
        assert checks["explicit_inputs"]["passed"] is True

    def test_command_context_digest_knowledge_accepts_explicit_prefixed_arxiv_without_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        outside_dir = tmp_path.parent / f"{tmp_path.name}-outside-digest-knowledge-prefixed-arxiv"
        outside_dir.mkdir()
        monkeypatch.chdir(outside_dir)

        payload = _raw_json(
            ["--raw", "--cwd", str(outside_dir), "validate", "command-context", "digest-knowledge", "hep-th/9901001"],
        )
        checks = checks_by_name(payload)
        assert payload["command"] == "gpd:digest-knowledge"
        assert payload["context_mode"] == "project-aware"
        assert payload["passed"] is True
        assert checks["project_exists"]["passed"] is False
        assert checks["explicit_inputs"]["passed"] is True

    def test_command_context_review_knowledge_requires_explicit_inputs_without_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        outside_dir = tmp_path.parent / f"{tmp_path.name}-outside-review-knowledge"
        outside_dir.mkdir()
        monkeypatch.chdir(outside_dir)

        payload = _raw_json(
            ["--raw", "--cwd", str(outside_dir), "validate", "command-context", "review-knowledge"],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert payload["command"] == "gpd:review-knowledge"
        assert payload["context_mode"] == "project-aware"
        assert payload["passed"] is False
        assert checks["project_exists"]["passed"] is False
        assert checks["explicit_inputs"]["passed"] is False

    def test_command_context_review_knowledge_registry_errors_fail_closed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise_registry_error(command_name: str):
            raise ValueError(f"registry parse failed for {command_name}")

        monkeypatch.setattr(cli_module, "_resolve_registry_command", _raise_registry_error)

        with pytest.raises(ValueError, match="registry parse failed for review-knowledge"):
            cli_module._build_command_context_preflight(
                "review-knowledge",
                arguments="K-renormalization-group-fixed-points",
            )

    def test_command_context_review_knowledge_accepts_explicit_knowledge_path_without_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        outside_dir = tmp_path.parent / f"{tmp_path.name}-outside-review-knowledge-path"
        outside_dir.mkdir()
        knowledge_dir = outside_dir / "GPD" / "knowledge"
        knowledge_dir.mkdir(parents=True)
        knowledge_file = knowledge_dir / "K-renormalization-group-fixed-points.md"
        knowledge_file.write_text("knowledge doc\n", encoding="utf-8")
        monkeypatch.chdir(outside_dir)

        payload = _raw_json(
            [
                "--raw",
                "--cwd",
                str(outside_dir),
                "validate",
                "command-context",
                "review-knowledge",
                knowledge_file.relative_to(outside_dir).as_posix(),
            ],
        )
        checks = checks_by_name(payload)
        assert payload["command"] == "gpd:review-knowledge"
        assert payload["context_mode"] == "project-aware"
        assert payload["passed"] is True
        assert checks["project_exists"]["passed"] is False
        assert checks["explicit_inputs"]["passed"] is True

    def test_command_context_review_knowledge_accepts_explicit_knowledge_id_without_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        outside_dir = tmp_path.parent / f"{tmp_path.name}-outside-review-knowledge-id"
        outside_dir.mkdir()
        knowledge_dir = outside_dir / "GPD" / "knowledge"
        knowledge_dir.mkdir(parents=True)
        knowledge_file = knowledge_dir / "K-renormalization-group-fixed-points.md"
        knowledge_file.write_text("knowledge doc\n", encoding="utf-8")
        monkeypatch.chdir(outside_dir)

        payload = _raw_json(
            [
                "--raw",
                "--cwd",
                str(outside_dir),
                "validate",
                "command-context",
                "review-knowledge",
                "K-renormalization-group-fixed-points",
            ],
        )
        checks = checks_by_name(payload)
        assert payload["command"] == "gpd:review-knowledge"
        assert payload["context_mode"] == "project-aware"
        assert payload["passed"] is True
        assert checks["project_exists"]["passed"] is False
        assert checks["explicit_inputs"]["passed"] is True

    @pytest.mark.parametrize("subject_kind", ["path", "knowledge_id"])
    def test_review_preflight_review_knowledge_strict_accepts_standalone_canonical_targets(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        subject_kind: str,
    ) -> None:
        workspace = tmp_path.parent / f"{tmp_path.name}-standalone-review-knowledge-{subject_kind}"
        workspace.mkdir()
        knowledge_path = _write_draft_knowledge_document(workspace)
        monkeypatch.chdir(workspace)
        subject = knowledge_path.relative_to(workspace).as_posix() if subject_kind == "path" else knowledge_path.stem

        payload = _raw_json(
            ["--raw", "--cwd", str(workspace), "validate", "review-preflight", "review-knowledge", subject, "--strict"],
        )
        checks = checks_by_name(payload)
        assert payload["command"] == "gpd:review-knowledge"
        assert payload["review_mode"] == "review"
        assert payload["strict"] is True
        assert payload["passed"] is True
        assert "missing project state" not in payload["blocking_conditions"]
        assert "GPD/knowledge/reviews/{knowledge_id}-R{review_round}-REVIEW.md" in payload["required_outputs"]
        assert checks["command_context"]["passed"] is True
        assert checks["project_state"]["passed"] is True
        assert checks["project_state"]["blocking"] is False
        assert checks["knowledge_target"]["passed"] is True
        assert "GPD/knowledge/K-renormalization-group-fixed-points.md" in checks["knowledge_target"]["detail"]
        assert checks["knowledge_document"]["passed"] is True
        assert checks["knowledge_review_freshness"]["passed"] is True

    def test_review_preflight_review_knowledge_strict_rejects_malformed_canonical_document(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        workspace = tmp_path.parent / f"{tmp_path.name}-standalone-review-knowledge-malformed"
        workspace.mkdir()
        knowledge_path = _write_draft_knowledge_document(workspace, knowledge_id="K-bad")
        knowledge_path.write_text(
            knowledge_path.read_text(encoding="utf-8").replace("knowledge_id: K-bad", "knowledge_id: K-other"),
            encoding="utf-8",
        )
        monkeypatch.chdir(workspace)

        payload = _raw_json(
            ["--raw", "--cwd", str(workspace), "validate", "review-preflight", "review-knowledge", "K-bad", "--strict"],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert payload["passed"] is False
        assert checks["knowledge_target"]["passed"] is True
        assert checks["knowledge_document"]["passed"] is False
        assert "failed strict parsing" in checks["knowledge_document"]["detail"]

    def test_review_preflight_review_knowledge_strict_rejects_noncanonical_standalone_target(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        workspace = tmp_path.parent / f"{tmp_path.name}-standalone-review-knowledge-noncanonical"
        workspace.mkdir()
        knowledge_path = _write_draft_knowledge_document(workspace, relative_dir="notes")
        monkeypatch.chdir(workspace)

        payload = _raw_json(
            [
                "--raw",
                "--cwd",
                str(workspace),
                "validate",
                "review-preflight",
                "review-knowledge",
                knowledge_path.relative_to(workspace).as_posix(),
                "--strict",
            ],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert payload["command"] == "gpd:review-knowledge"
        assert payload["passed"] is False
        assert checks["knowledge_target"]["passed"] is False
        assert "GPD/knowledge/" in checks["knowledge_target"]["detail"]

    def test_review_preflight_write_paper_strict(self, gpd_project: Path) -> None:
        payload = _raw_json(
            ["--raw", "--cwd", str(gpd_project), "validate", "review-preflight", "write-paper", "--strict"],
        )
        assert payload["command"] == "gpd:write-paper"
        assert payload["passed"] is True
        checks = checks_by_name(payload)
        check_names = set(checks)
        assert {
            "project_state",
            "state_integrity",
            "roadmap",
            "conventions",
            "research_artifacts",
        } <= check_names
        assert checks["reproducibility_manifest"]["passed"] is True
        assert checks["reproducibility_ready"]["passed"] is True

    def test_review_preflight_write_paper_resolves_ancestor_project_from_nested_workspace(
        self,
        gpd_project: Path,
    ) -> None:
        workspace = gpd_project / "nested-write-paper"
        workspace.mkdir()

        payload = _raw_json(
            ["--raw", "--cwd", str(workspace), "validate", "review-preflight", "write-paper", "--strict"],
        )
        checks = checks_by_name(payload)
        assert payload["command"] == "gpd:write-paper"
        assert payload["passed"] is True
        assert checks["command_context"]["passed"] is True
        assert checks["project_state"]["passed"] is True
        assert checks["manuscript"]["passed"] is True
        assert payload["resolved_subject"]["status"] == "resolved"
        assert payload["resolved_subject"]["resolved_project_root"] == gpd_project.resolve().as_posix()
        assert payload["resolved_subject"]["ancestor_walked_up"] is True

    def test_review_preflight_write_paper_bootstraps_manuscript_proof_review_manifest(
        self,
        gpd_project: Path,
    ) -> None:
        _write_review_stage_artifacts(gpd_project, artifact_names=("STAGE-math.json",))

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "write-paper", "--strict"],
        )
        checks = checks_by_name(payload)
        assert checks["manuscript_proof_review"]["passed"] is True
        assert (gpd_project / "paper" / "PROOF-REVIEW-MANIFEST.json").exists()

    def test_review_preflight_arxiv_submission_strict_does_not_bootstrap_manuscript_proof_review_manifest(
        self,
        gpd_project: Path,
    ) -> None:
        _write_review_stage_artifacts(gpd_project, artifact_names=("STAGE-math.json",))

        payload = _raw_json(
            ["--raw", "--cwd", str(gpd_project), "validate", "review-preflight", "arxiv-submission", "--strict"],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert checks["manuscript_proof_review"]["passed"] is True
        assert not (gpd_project / "paper" / "PROOF-REVIEW-MANIFEST.json").exists()

    def test_review_preflight_write_paper_reports_theorem_bearing_proof_review_without_blocking(
        self,
        gpd_project: Path,
    ) -> None:
        write_proof_review_package(gpd_project, theorem_bearing=True, review_report=False)

        payload = _raw_json(
            ["--raw", "--cwd", str(gpd_project), "validate", "review-preflight", "write-paper"],
        )
        checks = checks_by_name(payload)
        assert checks["manuscript_proof_review"]["passed"] is False
        assert checks["manuscript_proof_review"]["blocking"] is False
        assert "PROOF-REDTEAM.md" in checks["manuscript_proof_review"]["detail"]
        assert "write-paper will run its own staged proof-review loop" in checks["manuscript_proof_review"]["detail"]

    def test_review_preflight_peer_review_surfaces_active_conditional_requirements_for_theorem_bearing_manuscript(
        self,
        gpd_project: Path,
    ) -> None:
        write_proof_review_package(gpd_project, theorem_bearing=True, review_report=False)

        payload = _raw_json(
            ["--raw", "--cwd", str(gpd_project), "validate", "review-preflight", "peer-review"],
        )

        assert payload["active_conditional_requirements"] == payload["conditional_requirements"]
        assert payload["active_conditional_requirements"] == [
            PROJECT_BACKED_PEER_REVIEW_CONDITIONAL,
            THEOREM_BEARING_PEER_REVIEW_CONDITIONAL,
        ]

    def test_review_preflight_peer_review_ignores_generic_claim_kind_without_theorem_metadata(
        self,
        gpd_project: Path,
    ) -> None:
        write_proof_review_package(gpd_project, theorem_bearing=False, review_report=False)
        _update_claim_index_claim(
            gpd_project,
            claim_kind="claim",
            text="The manuscript reports a descriptive result.",
            theorem_assumptions=[],
            theorem_parameters=[],
        )

        payload = _raw_json(
            ["--raw", "--cwd", str(gpd_project), "validate", "review-preflight", "peer-review"],
        )
        assert payload["passed"] is True
        assert payload["active_conditional_requirements"] == [PROJECT_BACKED_PEER_REVIEW_CONDITIONAL]

    def test_review_preflight_write_paper_reports_theorem_bearing_claim_inventory_without_blocking(
        self,
        gpd_project: Path,
    ) -> None:
        _write_review_stage_artifacts(
            gpd_project,
            artifact_names=("STAGE-reader.json",),
            proof_bearing=True,
            write_proof_redteam=False,
        )

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "write-paper"],
        )
        checks = checks_by_name(payload)
        assert checks["manuscript_proof_review"]["passed"] is False
        assert checks["manuscript_proof_review"]["blocking"] is False
        assert (
            "no prior staged math review artifact matches the active manuscript"
            in checks["manuscript_proof_review"]["detail"]
        )

    def test_review_preflight_write_paper_reports_theorem_bearing_manuscript_text_without_blocking(
        self,
        gpd_project: Path,
    ) -> None:
        _manuscript_entrypoint_path(gpd_project).write_text(
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "\\begin{theorem}For every r_0 > 0, the orbit intersects the target annulus.\\end{theorem}\n"
            "\\begin{proof}The proof is omitted.\\end{proof}\n"
            "\\end{document}\n",
            encoding="utf-8",
        )
        _refresh_artifact_manifest_for_manuscript(gpd_project)

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "write-paper"],
        )
        checks = checks_by_name(payload)
        assert checks["manuscript_proof_review"]["passed"] is False
        assert checks["manuscript_proof_review"]["blocking"] is False
        assert (
            "no prior staged math review artifact matches the active manuscript"
            in checks["manuscript_proof_review"]["detail"]
        )

    def test_review_preflight_write_paper_reports_theorem_bearing_nested_section_text_without_blocking(
        self,
        gpd_project: Path,
    ) -> None:
        manuscript_path = _manuscript_entrypoint_path(gpd_project)
        manuscript_path.write_text(
            "\\documentclass{article}\n\\begin{document}\n\\input{sections/results}\n\\end{document}\n",
            encoding="utf-8",
        )
        section_path = manuscript_path.parent / "sections" / "results.tex"
        section_path.parent.mkdir(parents=True, exist_ok=True)
        section_path.write_text(
            "\\begin{claim}For every r_0 > 0, the orbit intersects the target annulus.\\end{claim}\n"
            "\\begin{proof}The proof is omitted.\\end{proof}\n",
            encoding="utf-8",
        )
        _refresh_artifact_manifest_for_manuscript(gpd_project, manuscript_path)

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "write-paper"],
        )
        checks = checks_by_name(payload)
        assert checks["manuscript_proof_review"]["passed"] is False
        assert checks["manuscript_proof_review"]["blocking"] is False
        assert (
            "no prior staged math review artifact matches the active manuscript"
            in checks["manuscript_proof_review"]["detail"]
        )

    def test_review_preflight_write_paper_reports_stale_manuscript_proof_review_without_blocking(
        self,
        gpd_project: Path,
    ) -> None:
        _write_review_stage_artifacts(gpd_project, artifact_names=("STAGE-math.json",))

        initial = runner.invoke(
            app,
            ["--raw", "validate", "review-preflight", "write-paper", "--strict"],
            catch_exceptions=False,
        )
        assert initial.exit_code == 0, initial.output

        manuscript = canonical_manuscript_path(gpd_project)
        manuscript.write_text(
            "\\documentclass{article}\n\\begin{document}\nRevised theorem statement.\n\\end{document}\n",
            encoding="utf-8",
        )
        _refresh_artifact_manifest_for_manuscript(gpd_project, manuscript)

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "write-paper", "--strict"],
        )
        checks = checks_by_name(payload)
        assert checks["manuscript_proof_review"]["passed"] is False
        assert checks["manuscript_proof_review"]["blocking"] is False
        assert "stale" in checks["manuscript_proof_review"]["detail"]

    def test_review_preflight_write_paper_reports_missing_proof_redteam_for_proof_bearing_manuscript_without_blocking(
        self,
        gpd_project: Path,
    ) -> None:
        _write_review_stage_artifacts(
            gpd_project,
            artifact_names=("STAGE-math.json",),
            proof_bearing=True,
        )

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "write-paper", "--strict"],
        )
        checks = checks_by_name(payload)
        assert checks["manuscript_proof_review"]["passed"] is False
        assert checks["manuscript_proof_review"]["blocking"] is False
        assert "PROOF-REDTEAM.md" in checks["manuscript_proof_review"]["detail"]

    def test_review_preflight_write_paper_accepts_passed_proof_redteam_for_proof_bearing_manuscript(
        self,
        gpd_project: Path,
    ) -> None:
        _write_review_stage_artifacts(
            gpd_project,
            artifact_names=("STAGE-math.json",),
            proof_bearing=True,
            write_proof_redteam=True,
        )

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "write-paper", "--strict"],
        )
        checks = checks_by_name(payload)
        assert checks["manuscript_proof_review"]["passed"] is True

    def test_review_preflight_peer_review_reports_stale_manuscript_proof_review_without_blocking(
        self,
        gpd_project: Path,
    ) -> None:
        _write_review_stage_artifacts(gpd_project, artifact_names=("STAGE-math.json",))

        initial = runner.invoke(
            app,
            ["--raw", "validate", "review-preflight", "write-paper", "--strict"],
            catch_exceptions=False,
        )
        assert initial.exit_code == 0, initial.output

        manuscript = canonical_manuscript_path(gpd_project)
        manuscript.write_text(
            "\\documentclass{article}\n\\begin{document}\nPeer review should refresh this proof.\n\\end{document}\n",
            encoding="utf-8",
        )
        _refresh_artifact_manifest_for_manuscript(gpd_project, manuscript)

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "peer-review", "--strict"],
        )
        checks = checks_by_name(payload)
        assert checks["manuscript_proof_review"]["passed"] is False
        assert checks["manuscript_proof_review"]["blocking"] is False
        assert payload["passed"] is True

    def test_review_preflight_write_paper_strict_allows_fresh_bootstrap_without_manuscript(
        self, gpd_project: Path
    ) -> None:
        canonical_manuscript_path(gpd_project).unlink()

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "write-paper", "--strict"],
        )
        assert payload["command"] == "gpd:write-paper"
        assert payload["passed"] is True
        assert payload["active_conditional_requirements"] == []
        checks = checks_by_name(payload)
        assert checks["manuscript"]["passed"] is True
        assert "fresh bootstrap is allowed" in checks["manuscript"]["detail"]
        assert "reproducibility_manifest" not in checks
        assert "reproducibility_ready" not in checks

    @pytest.mark.parametrize(
        ("command", "extra_args"),
        [
            ("write-paper", []),
            ("respond-to-referees", ["reports/referee-report.md"]),
            ("peer-review", []),
            ("arxiv-submission", []),
        ],
    )
    def test_review_preflight_fails_closed_on_ambiguous_manuscript_state(
        self,
        gpd_project: Path,
        command: str,
        extra_args: list[str],
    ) -> None:
        _write_secondary_manuscript_root(gpd_project)

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", command, *extra_args, "--strict"],
            expect_exit=1,
        )
        assert payload["passed"] is False
        checks = checks_by_name(payload)
        assert checks["manuscript"]["passed"] is False
        assert "ambiguous or inconsistent manuscript roots" in checks["manuscript"]["detail"]
        if command == "write-paper":
            assert "reproducibility_manifest" not in checks
            assert "reproducibility_ready" not in checks

    @pytest.mark.parametrize(
        ("command", "extra_args"),
        [
            ("write-paper", []),
            ("respond-to-referees", ["reports/referee-report.md"]),
            ("peer-review", []),
            ("arxiv-submission", []),
        ],
    )
    def test_review_preflight_fails_closed_on_inconsistent_manuscript_state(
        self,
        gpd_project: Path,
        command: str,
        extra_args: list[str],
    ) -> None:
        paper_dir = gpd_project / "paper"
        (paper_dir / "PAPER-CONFIG.json").write_text(
            json.dumps(
                {
                    "title": "Alternate Title",
                    "authors": [{"name": "A. Researcher"}],
                    "abstract": "Abstract.",
                    "sections": [{"heading": "Intro", "content": "Hello."}],
                }
            ),
            encoding="utf-8",
        )

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", command, *extra_args, "--strict"],
            expect_exit=1,
        )
        assert payload["passed"] is False
        checks = checks_by_name(payload)
        assert checks["manuscript"]["passed"] is False
        assert "ambiguous or inconsistent manuscript roots" in checks["manuscript"]["detail"]

    def test_review_preflight_write_paper_strict_recognizes_markdown_resume_directory(self, gpd_project: Path) -> None:
        paper_dir = gpd_project / "paper"
        (paper_dir / _CANONICAL_MANUSCRIPT_BASENAME).unlink()
        markdown_manuscript = paper_dir / _CANONICAL_MARKDOWN_BASENAME
        markdown_manuscript.write_text("# Markdown manuscript\n", encoding="utf-8")
        _refresh_artifact_manifest_for_manuscript(gpd_project, markdown_manuscript)

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "write-paper", "--strict"],
        )
        checks = checks_by_name(payload)
        assert checks["manuscript"]["passed"] is True
        assert f"paper/{_CANONICAL_MARKDOWN_BASENAME}" in checks["manuscript"]["detail"]
        assert checks["artifact_manifest"]["passed"] is True
        assert checks["bibliography_audit"]["passed"] is True
        assert checks["reproducibility_manifest"]["passed"] is True

    @pytest.mark.parametrize("resume_dir_name", ["manuscript", "draft"])
    def test_review_preflight_write_paper_strict_uses_resolved_resume_directory(
        self,
        gpd_project: Path,
        resume_dir_name: str,
    ) -> None:
        paper_dir = gpd_project / "paper"
        (paper_dir / _CANONICAL_MANUSCRIPT_BASENAME).unlink()

        resume_dir = gpd_project / resume_dir_name
        resume_dir.mkdir()
        resume_manuscript = resume_dir / _CANONICAL_MANUSCRIPT_BASENAME
        resume_manuscript.write_text(
            "\\documentclass{article}\n\\begin{document}\nResume manuscript.\n\\end{document}\n",
            encoding="utf-8",
        )
        for artifact_name in (
            "PAPER-CONFIG.json",
            "ARTIFACT-MANIFEST.json",
            "BIBLIOGRAPHY-AUDIT.json",
            "reproducibility-manifest.json",
        ):
            (resume_dir / artifact_name).write_text(
                (paper_dir / artifact_name).read_text(encoding="utf-8"), encoding="utf-8"
            )
        (resume_dir / _CANONICAL_MANUSCRIPT_PDF_BASENAME).write_bytes(
            (paper_dir / _CANONICAL_MANUSCRIPT_PDF_BASENAME).read_bytes()
        )
        manifest = json.loads((resume_dir / "ARTIFACT-MANIFEST.json").read_text(encoding="utf-8"))
        manifest["manuscript_sha256"] = compute_sha256(resume_manuscript)
        manifest["manuscript_mtime_ns"] = resume_manuscript.stat().st_mtime_ns
        for artifact in manifest.get("artifacts", []):
            if isinstance(artifact, dict) and artifact.get("category") == "tex":
                artifact["sha256"] = compute_sha256(resume_manuscript)
                artifact["path"] = _CANONICAL_MANUSCRIPT_BASENAME
        (resume_dir / "ARTIFACT-MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "write-paper", "--strict"],
        )
        checks = checks_by_name(payload)
        assert checks["manuscript"]["passed"] is True
        assert f"{resume_dir_name}/{_CANONICAL_MANUSCRIPT_BASENAME}" in checks["manuscript"]["detail"]
        assert checks["artifact_manifest"]["passed"] is True
        assert checks["bibliography_audit"]["passed"] is True
        assert checks["reproducibility_manifest"]["passed"] is True
        assert checks["reproducibility_ready"]["passed"] is True

    def test_review_preflight_write_paper_strict_does_not_fall_back_to_internal_gpd_paper_artifacts(
        self,
        gpd_project: Path,
    ) -> None:
        canonical_manuscript_path(gpd_project).unlink()

        resume_dir = gpd_project / "manuscript"
        resume_dir.mkdir()
        (resume_dir / _CANONICAL_MANUSCRIPT_BASENAME).write_text(
            "\\documentclass{article}\n\\begin{document}\nResume manuscript.\n\\end{document}\n",
            encoding="utf-8",
        )
        _write_internal_publication_artifacts(
            gpd_project,
            ("PAPER-CONFIG.json", "ARTIFACT-MANIFEST.json", "BIBLIOGRAPHY-AUDIT.json", "reproducibility-manifest.json"),
        )

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "write-paper", "--strict"],
        )
        checks = checks_by_name(payload)
        assert checks["manuscript"]["passed"] is True
        assert "fresh bootstrap is allowed" in checks["manuscript"]["detail"]
        assert "artifact_manifest" not in checks
        assert "bibliography_audit" not in checks
        assert "reproducibility_manifest" not in checks

    def test_raw_help_bridge_default_and_all_are_machine_readable(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("gpd.cli.detect_runtime_for_gpd_use", lambda cwd=None: None)

        payload = _raw_json(
            ["--raw", "--cwd", str(tmp_path), "help"],
        )
        assert payload["command"] == "gpd:help"
        assert payload["ok"] is True
        assert payload["default_sections"] == ["quick_start_extract", "wrapper_owned_all_hint"]
        assert payload["quick_start"]["heading"] == "Quick Start"
        _assert_text_contains(payload["quick_start"]["markdown"], ("gpd:start", "Existing research folder"))
        _assert_text_excludes(payload["quick_start"]["markdown"], ("gpd:progress", "gpd cost"))
        fallback_default = extract_help_surface_region(
            (Path(__file__).resolve().parents[1] / "src/gpd/specs/workflows/help.md").read_text(encoding="utf-8"),
            "default",
        ).strip()
        assert payload["quick_start"]["markdown"] == fallback_default
        assert payload["quick_start"]["canonical_markdown"] == help_renderer.render_default_help_markdown()
        assert payload["quick_start"]["canonical_markdown"] == fallback_default
        _assert_text_excludes(payload["quick_start"]["markdown"], ("<!--",))
        assert payload["recommended_commands"] == ["gpd:help --all"]
        assert payload["canonical_recommended_commands"] == ["gpd:help --all"]
        assert payload["local_cli_equivalence_guaranteed"] is False

        payload = _raw_json(
            ["--raw", "--cwd", str(tmp_path), "help", "--all"],
        )
        commands = {entry["command"] for entry in payload["command_index"]}
        assert {"gpd:new-project", "gpd:help"} <= commands
        assert payload["rendered_sections"] == ["quick_start", "command_index", "detailed_help_follow_up"]
        assert payload["quick_start"]["markdown"] == help_renderer.render_quick_start_markdown()
        assert payload["quick_start"]["canonical_markdown"] == help_renderer.render_quick_start_markdown()
        assert payload["command_index_markdown"] == help_renderer.render_command_index_markdown()
        assert payload["canonical_command_index_markdown"] == help_renderer.render_command_index_markdown()
        _assert_text_contains(payload["command_index_markdown"], ("## Command Index",))
        _assert_text_excludes(payload["command_index_markdown"], ("<!--",))
        assert payload["command_groups"] == help_renderer.command_groups_payload()
        assert payload["command_groups"][0]["name"] == "Starter commands"
        starter_commands = {entry["command"] for entry in payload["command_groups"][0]["commands"]}
        assert {"gpd:help", "gpd:new-project --minimal"} <= starter_commands
        assert payload["detailed_help_follow_up"] == help_renderer.DETAILED_HELP_FOLLOW_UP
        assert payload["canonical_detailed_help_follow_up"] == help_renderer.DETAILED_HELP_FOLLOW_UP

    def test_raw_help_bridge_display_markdown_uses_active_runtime_prefix(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        descriptor = _DOLLAR_COMMAND_DESCRIPTOR
        monkeypatch.setattr("gpd.cli.detect_runtime_for_gpd_use", lambda cwd=None: descriptor.runtime_name)

        payload = _raw_json(
            ["--raw", "--cwd", str(tmp_path), "help"],
        )
        assert payload["public_runtime_command_prefix"] == "$gpd-"
        _assert_text_contains(
            payload["quick_start"]["markdown"],
            ("`$gpd-start`", "`$gpd-new-project --minimal`", "`$gpd-map-research`"),
        )
        _assert_text_excludes(payload["quick_start"]["markdown"], ("`$gpd-progress`",))
        _assert_text_contains(payload["quick_start"]["canonical_markdown"], ("`gpd:start`",))
        assert payload["recommended_commands"] == ["$gpd-help --all"]
        assert payload["canonical_recommended_commands"] == ["gpd:help --all"]

        payload = _raw_json(
            ["--raw", "--cwd", str(tmp_path), "help", "--all"],
        )
        _assert_text_contains(
            payload["command_index_markdown"],
            ("`$gpd-help`", "`$gpd-new-project --minimal`", "`gpd --help`"),
        )
        _assert_text_contains(payload["canonical_command_index_markdown"], ("`gpd:help`",))
        assert payload["detailed_help_follow_up"] == (
            "Use `$gpd-help --command <name>` when you want detailed notes for one runtime command."
        )
        assert payload["canonical_detailed_help_follow_up"] == help_renderer.DETAILED_HELP_FOLLOW_UP

    @pytest.mark.parametrize(
        "descriptor",
        _RUNTIME_DESCRIPTORS,
        ids=[descriptor.runtime_name for descriptor in _RUNTIME_DESCRIPTORS],
    )
    def test_raw_help_bridge_top_level_metadata_uses_active_runtime(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        descriptor,
    ) -> None:
        monkeypatch.setattr("gpd.cli.detect_runtime_for_gpd_use", lambda cwd=None: descriptor.runtime_name)

        payload = _raw_json(
            ["--raw", "--cwd", str(tmp_path), "help", "--command", "progress", "--minimal"],
        )
        assert payload["validated_surface"] == descriptor.validated_command_surface
        assert payload["public_runtime_command_prefix"] == descriptor.public_command_surface_prefix
        _assert_text_contains(payload["detail_markdown"], (f"`{descriptor.public_command_surface_prefix}progress",))
        _assert_text_contains(payload["canonical_detail_markdown"], ("`gpd:progress",))
        assert payload["command_context"]["validated_surface"] == descriptor.validated_command_surface
        assert payload["command_context"]["public_runtime_command_prefix"] == descriptor.public_command_surface_prefix

    def test_raw_help_bridge_command_specific_payload(self, tmp_path: Path) -> None:
        payload = _raw_json(
            ["--raw", "--cwd", str(tmp_path), "help", "--command", "new-project", "--minimal"],
        )
        assert payload["ok"] is True
        assert payload["canonical_command"] == "gpd:new-project"
        assert payload["context_mode"] == "projectless"
        assert payload["command_context"]["passed"] is True
        assert payload["command_context"]["command"] == "gpd:new-project"

        payload = _raw_json(
            ["--raw", "--cwd", str(tmp_path), "help", "--command", "gpd:new-project --minimal", "--minimal"],
        )
        assert payload["ok"] is True
        assert payload["requested_command"] == "gpd:new-project --minimal"
        assert payload["canonical_command"] == "gpd:new-project"
        assert payload["command_context"]["command"] == "gpd:new-project"

    def test_raw_help_bridge_unknown_command_fails_closed(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("gpd.cli.detect_runtime_for_gpd_use", lambda cwd=None: None)
        payload = _raw_json(
            ["--raw", "--cwd", str(tmp_path), "help", "--command", "does-not-exist"],
            expect_exit=1,
        )
        assert payload["ok"] is False
        assert payload["passed"] is False
        assert payload["error"] == "unknown_command"
        assert payload["requested_command"] == "does-not-exist"
        assert payload["normalized_command"] == "does-not-exist"
        assert payload["canonical_command"] == "gpd:does-not-exist"
        assert payload["known_command"] is False
        assert "gpd:help" in payload["allowed_preview"]
        assert isinstance(payload["primary_action"], dict)
        assert "primary_actions" not in payload
        assert payload["primary_action"]["command"] == "gpd --raw help --all"
        assert payload["safe_alternatives"]
        assert payload["debug_actions"]

    def test_raw_help_bridge_unknown_command_uses_active_runtime_prefix(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        descriptor = _DOLLAR_COMMAND_DESCRIPTOR
        monkeypatch.setattr("gpd.cli.detect_runtime_for_gpd_use", lambda cwd=None: descriptor.runtime_name)

        payload = _raw_json(
            ["--raw", "--cwd", str(tmp_path), "help", "--command", "verfy-work"],
            expect_exit=1,
        )
        assert payload["error"] == "unknown_command"
        assert payload["public_runtime_command_prefix"] == "$gpd-"
        assert payload["primary_action"]["command"] == "$gpd-help --all"
        assert any(suggestion["command"] == "$gpd-verify-work" for suggestion in payload["suggestions"])

    def test_command_context_unknown_command_preserves_inline_request(self, tmp_path: Path) -> None:
        payload = _raw_json(
            [
                "--raw",
                "--cwd",
                str(tmp_path),
                "validate",
                "command-context",
                "gpd:verfy-work --phase 2",
            ],
            expect_exit=1,
        )
        assert payload["error"] == "unknown_command"
        assert payload["requested_command"] == "gpd:verfy-work --phase 2"
        assert payload["normalized_command"] == "gpd:verfy-work"
        assert payload["canonical_command"] == "gpd:verfy-work"
        assert any(suggestion["canonical_command"] == "gpd:verify-work" for suggestion in payload["suggestions"])

    def test_command_context_project_aware_command_accepts_explicit_inputs(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        outside_dir = tmp_path.parent / f"{tmp_path.name}-outside-aware-explicit"
        outside_dir.mkdir()
        monkeypatch.chdir(outside_dir)
        payload = _raw_json(
            ["--raw", "--cwd", str(outside_dir), "validate", "command-context", "discover", "7"],
        )
        checks = checks_by_name(payload)
        assert payload["command"] == "gpd:discover"
        assert payload["context_mode"] == "project-aware"
        assert payload["passed"] is True
        assert checks["project_exists"]["passed"] is False
        assert checks["explicit_inputs"]["passed"] is True

    def test_command_context_project_required_command_fails_without_project(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        outside_dir = tmp_path.parent / f"{tmp_path.name}-outside-required"
        outside_dir.mkdir()
        monkeypatch.chdir(outside_dir)
        payload = _raw_json(
            ["--raw", "--cwd", str(outside_dir), "validate", "command-context", "quick"],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert payload["command"] == "gpd:quick"
        assert payload["context_mode"] == "project-required"
        assert payload["passed"] is False
        assert checks["project_exists"]["passed"] is False

    def test_review_preflight_peer_review_strict(self) -> None:
        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "peer-review", "--strict"],
        )
        assert payload["command"] == "gpd:peer-review"
        assert payload["passed"] is True
        checks = checks_by_name(payload)
        assert checks["project_state"]["passed"] is True
        assert checks["state_integrity"]["passed"] is True
        assert checks["roadmap"]["passed"] is True
        assert checks["research_artifacts"]["passed"] is True
        assert checks["manuscript"]["passed"] is True
        assert checks["conventions"]["passed"] is True
        assert checks["artifact_manifest"]["passed"] is True
        assert checks["bibliography_audit"]["passed"] is True
        assert checks["bibliography_audit_clean"]["passed"] is True
        assert checks["reproducibility_manifest"]["passed"] is True
        assert checks["reproducibility_ready"]["passed"] is True

    def test_review_preflight_peer_review_without_subject_accepts_markdown_entrypoint(self, gpd_project: Path) -> None:
        paper_dir = gpd_project / "paper"
        (paper_dir / _CANONICAL_MANUSCRIPT_BASENAME).unlink()
        markdown_manuscript = paper_dir / _CANONICAL_MARKDOWN_BASENAME
        markdown_manuscript.write_text("# Markdown manuscript\n", encoding="utf-8")
        _refresh_artifact_manifest_for_manuscript(gpd_project, markdown_manuscript)

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "peer-review", "--strict"],
        )
        assert payload["command"] == "gpd:peer-review"
        assert payload["passed"] is True
        checks = checks_by_name(payload)
        assert checks["manuscript"]["passed"] is True
        assert f"paper/{_CANONICAL_MARKDOWN_BASENAME}" in checks["manuscript"]["detail"]
        assert checks["artifact_manifest"]["passed"] is True
        assert checks["bibliography_audit"]["passed"] is True
        assert checks["reproducibility_manifest"]["passed"] is True

    def test_review_preflight_strict_blocks_review_integrity_failures(self, gpd_project: Path) -> None:
        planning = gpd_project / "GPD"
        state = json.loads((planning / "state.json").read_text(encoding="utf-8"))
        state["intermediate_results"] = [
            {
                "id": "R-01",
                "description": "Unbacked claim",
                "depends_on": [],
                "verified": True,
                "verification_records": [],
            }
        ]
        (planning / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "write-paper", "--strict"],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert checks["state_integrity"]["passed"] is False

    def test_review_preflight_strict_blocks_semantically_invalid_project_contract(self, gpd_project: Path) -> None:
        planning = gpd_project / "GPD"
        state = json.loads((planning / "state.json").read_text(encoding="utf-8"))
        contract = json.loads((FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"))
        contract["uncertainty_markers"]["weakest_anchors"] = []
        contract["uncertainty_markers"]["disconfirming_observations"] = []
        state["project_contract"] = contract
        (planning / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "write-paper", "--strict"],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert checks["state_integrity"]["passed"] is False
        assert "project_contract:" in checks["state_integrity"]["detail"]

    def test_review_preflight_strict_blocks_invalid_phase_artifact_frontmatter(self, gpd_project: Path) -> None:
        planning = gpd_project / "GPD"
        phase_dir = planning / "phases" / "01-test-phase"
        (phase_dir / "01-SUMMARY.md").write_text("# Summary\n\nMissing frontmatter.\n", encoding="utf-8")
        (phase_dir / "01-VERIFICATION.md").write_text("# Verification\n\nMissing frontmatter.\n", encoding="utf-8")

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "write-paper", "--strict"],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert checks["summary_frontmatter"]["passed"] is False
        assert checks["verification_frontmatter"]["passed"] is False

    def test_review_preflight_verify_work_for_phase(self, gpd_project: Path) -> None:
        planning = gpd_project / "GPD"
        state = json.loads((planning / "state.json").read_text(encoding="utf-8"))
        state["position"]["status"] = "Phase complete — ready for verification"
        (planning / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
        (planning / "STATE.md").write_text(generate_state_markdown(state), encoding="utf-8")

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "verify-work", "1"],
        )
        assert payload["command"] == "gpd:verify-work"
        assert payload["passed"] is True
        checks = checks_by_name(payload)
        assert checks["phase_lookup"]["passed"] is True
        assert checks["phase_summaries"]["passed"] is True
        assert checks["required_state"]["passed"] is True

    def test_review_preflight_verify_work_fails_from_planning_state(self) -> None:
        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "verify-work", "1"],
            expect_exit=1,
        )
        assert payload["command"] == "gpd:verify-work"
        assert payload["passed"] is False
        checks = checks_by_name(payload)
        assert checks["phase_lookup"]["passed"] is True
        assert checks["phase_summaries"]["passed"] is True
        assert checks["required_state"]["passed"] is False
        assert checks["required_state"]["blocking"] is True
        assert 'found "Planning"' in checks["required_state"]["detail"]

    def test_review_preflight_verify_work_strict_is_read_only_when_blocked(self, gpd_project: Path) -> None:
        lock_path = gpd_project / "GPD" / "state.json.lock"
        assert not lock_path.exists()

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "verify-work", "1", "--strict"],
            expect_exit=1,
        )
        assert payload["passed"] is False
        checks = checks_by_name(payload)
        assert checks["required_state"]["passed"] is False
        assert not lock_path.exists()

    def test_review_preflight_verify_work_without_subject_uses_current_phase_artifacts(self, gpd_project: Path) -> None:
        planning = gpd_project / "GPD"
        state = json.loads((planning / "state.json").read_text(encoding="utf-8"))
        state["position"]["current_phase"] = "02"
        state["position"]["status"] = "Phase complete — ready for verification"
        (planning / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
        (planning / "STATE.md").write_text(generate_state_markdown(state), encoding="utf-8")

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "verify-work"],
            expect_exit=1,
        )
        assert payload["command"] == "gpd:verify-work"
        assert payload["passed"] is False
        checks = checks_by_name(payload)
        assert checks["phase_summaries"]["passed"] is False
        assert 'current phase "02" has no SUMMARY artifacts' in checks["phase_summaries"]["detail"]
        assert checks["required_state"]["passed"] is True

    def test_review_preflight_respond_to_referees_checks_report_path(self) -> None:
        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "respond-to-referees", "reports/referee-report.md"],
        )
        assert payload["command"] == "gpd:respond-to-referees"
        assert payload["passed"] is True
        checks = checks_by_name(payload)
        assert checks["manuscript"]["passed"] is True
        assert checks["referee_report_source"]["passed"] is True
        assert "artifact_manifest" not in checks
        assert "bibliography_audit" not in checks

    def test_review_preflight_respond_to_referees_resolves_positional_report_from_nested_launch_cwd(
        self,
        gpd_project: Path,
    ) -> None:
        nested = gpd_project / "workspace" / "nested-review"
        nested.mkdir(parents=True)
        (nested / "local-referee-report.md").write_text("# Local Report\n\nClarify the proof.\n", encoding="utf-8")

        payload = _raw_json(
            [
                "--raw",
                "--cwd",
                str(nested),
                "validate",
                "review-preflight",
                "respond-to-referees",
                "local-referee-report.md",
            ],
        )
        checks = checks_by_name(payload)
        assert checks["referee_report_source"]["passed"] is True
        assert "./local-referee-report.md present" in checks["referee_report_source"]["detail"]

    def test_review_preflight_respond_to_referees_resolves_flagged_report_from_nested_launch_cwd(
        self,
        gpd_project: Path,
    ) -> None:
        nested = gpd_project / "workspace" / "flagged-review"
        nested.mkdir(parents=True)
        (nested / "flagged-referee-report.md").write_text("# Flagged Report\n\nClarify notation.\n", encoding="utf-8")

        payload = _raw_json(
            [
                "--raw",
                "--cwd",
                str(nested),
                "validate",
                "review-preflight",
                "respond-to-referees",
                "--",
                "--report",
                "flagged-referee-report.md",
            ],
        )
        checks = checks_by_name(payload)
        assert checks["referee_report_source"]["passed"] is True
        assert "./flagged-referee-report.md present" in checks["referee_report_source"]["detail"]

    def test_review_preflight_respond_to_referees_accepts_markdown_manuscript(self, gpd_project: Path) -> None:
        paper_dir = gpd_project / "paper"
        (paper_dir / _CANONICAL_MANUSCRIPT_BASENAME).unlink()
        (paper_dir / _CANONICAL_MARKDOWN_BASENAME).write_text("# Markdown manuscript\n", encoding="utf-8")

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "respond-to-referees", "reports/referee-report.md"],
        )
        checks = checks_by_name(payload)
        assert checks["manuscript"]["passed"] is True
        assert f"paper/{_CANONICAL_MARKDOWN_BASENAME}" in checks["manuscript"]["detail"]

    def test_review_preflight_peer_review_fails_without_manuscript(self, gpd_project: Path) -> None:
        canonical_manuscript_path(gpd_project).unlink()

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "peer-review", "--strict"],
            expect_exit=1,
        )
        assert payload["command"] == "gpd:peer-review"
        assert payload["passed"] is False
        checks = checks_by_name(payload)
        assert checks["manuscript"]["passed"] is False

    def test_review_preflight_fails_without_manuscript(self, gpd_project: Path) -> None:
        canonical_manuscript_path(gpd_project).unlink()

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "respond-to-referees", "reports/referee-report.md"],
            expect_exit=1,
        )
        assert payload["command"] == "gpd:respond-to-referees"
        assert payload["passed"] is False
        checks = checks_by_name(payload)
        assert checks["command_context"]["passed"] is False
        assert checks["referee_report_source"]["passed"] is True
        assert checks["manuscript"]["passed"] is False
        assert checks["command_context"]["detail"]

    def test_review_preflight_peer_review_resolves_ancestor_project_root_for_nested_workspace(
        self,
        gpd_project: Path,
    ) -> None:
        nested = gpd_project / "workspace" / "notes"
        nested.mkdir(parents=True)

        payload = _raw_json(
            ["--raw", "--cwd", str(nested), "validate", "review-preflight", "peer-review", "--strict"],
        )
        checks = checks_by_name(payload)
        resolved_subject = payload["resolved_subject"]
        assert payload["command"] == "gpd:peer-review"
        assert payload["passed"] is True
        assert checks["manuscript"]["passed"] is True
        assert _CANONICAL_MANUSCRIPT_REL in checks["manuscript"]["detail"]
        assert resolved_subject["status"] == "resolved"
        assert resolved_subject["ownership_mode"] == "project_backed"
        assert resolved_subject["ancestor_walked_up"] is True
        assert resolved_subject["explicit_input"] is False

    def test_review_preflight_peer_review_does_not_leak_ancestor_context_into_nested_checkout(
        self,
        gpd_project: Path,
    ) -> None:
        nested_repo = gpd_project / "nested-standalone-review"
        (nested_repo / ".git").mkdir(parents=True)
        target = nested_repo / "standalone-review.txt"
        target.write_text("Standalone manuscript surface.\n", encoding="utf-8")

        payload = _raw_json(
            [
                "--raw",
                "--cwd",
                str(nested_repo),
                "validate",
                "review-preflight",
                "peer-review",
                target.name,
                "--strict",
            ],
        )
        checks = checks_by_name(payload)
        resolved_subject = payload["resolved_subject"]
        assert payload["resolved_mode"] == "standalone explicit-artifact review"
        assert checks["command_context"]["passed"] is True
        assert "project_state" not in checks
        assert checks["manuscript"]["passed"] is True
        assert resolved_subject["context_root"] == nested_repo.resolve(strict=False).as_posix()
        assert resolved_subject["resolved_project_root"] is None
        assert resolved_subject["ownership_mode"] == "external_artifact"
        assert resolved_subject["ancestor_walked_up"] is False

    def test_review_preflight_peer_review_strict_requires_artifact_audits(self, gpd_project: Path) -> None:
        paper_dir = gpd_project / "paper"
        (paper_dir / "ARTIFACT-MANIFEST.json").unlink()

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "peer-review", "--strict"],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert checks["artifact_manifest"]["passed"] is False

    def test_review_preflight_peer_review_strict_rejects_invalid_artifact_manifest(self, gpd_project: Path) -> None:
        paper_dir = gpd_project / "paper"
        (paper_dir / "ARTIFACT-MANIFEST.json").write_text("{not json", encoding="utf-8")

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "peer-review", "--strict"],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert checks["manuscript"]["passed"] is False
        assert "ARTIFACT-MANIFEST.json is invalid" in checks["manuscript"]["detail"]

    def test_review_preflight_peer_review_strict_rejects_blank_artifact_manifest_title(self, gpd_project: Path) -> None:
        paper_dir = gpd_project / "paper"
        manifest = json.loads((paper_dir / "ARTIFACT-MANIFEST.json").read_text(encoding="utf-8"))
        manifest["paper_title"] = "   "
        (paper_dir / "ARTIFACT-MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "peer-review", "--strict"],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert checks["manuscript"]["passed"] is False
        assert "ARTIFACT-MANIFEST.json is invalid" in checks["manuscript"]["detail"]
        assert "paper_title" in checks["manuscript"]["detail"]

    @pytest.mark.parametrize(
        ("case", "expected_fragments"),
        [
            (
                "stale_checksum",
                (
                    "artifact manifest is stale",
                    "manuscript_sha256 does not match the active manuscript snapshot",
                ),
            ),
            ("missing_checksum", ("artifact manifest is stale", "manifest is missing manuscript_sha256")),
            (
                "tex_path_mismatch",
                (
                    "artifact manifest integrity failed",
                    "tex artifact path does not resolve to the selected manuscript",
                ),
            ),
            ("duplicate_tex", ("artifact manifest integrity failed", "must contain exactly one tex artifact")),
        ],
    )
    def test_review_preflight_peer_review_strict_rejects_artifact_manifest_semantic_drift(
        self,
        gpd_project: Path,
        case: str,
        expected_fragments: tuple[str, ...],
    ) -> None:
        paper_dir = gpd_project / "paper"
        manuscript = canonical_manuscript_path(gpd_project)
        manifest_path = paper_dir / "ARTIFACT-MANIFEST.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if case == "stale_checksum":
            manifest["manuscript_sha256"] = "0" * 64
        elif case == "missing_checksum":
            manifest.pop("manuscript_sha256", None)
            manifest.pop("manuscript_mtime_ns", None)
        else:
            alternate_manuscript = paper_dir / "alternate-manuscript.tex"
            alternate_manuscript.write_text(manuscript.read_text(encoding="utf-8"), encoding="utf-8")
            tex_artifact = next(artifact for artifact in manifest["artifacts"] if artifact["category"] == "tex")
            if case == "tex_path_mismatch":
                tex_artifact["path"] = alternate_manuscript.name
                tex_artifact["sha256"] = compute_sha256(alternate_manuscript)
            else:
                manifest["artifacts"].append(
                    dict(
                        tex_artifact,
                        artifact_id="tex-duplicate",
                        path=alternate_manuscript.name,
                        sha256=compute_sha256(alternate_manuscript),
                    )
                )
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        passed, detail = cli_module._validate_artifact_manifest_semantics(manifest_path, manuscript)

        assert passed is False
        _assert_text_contains(detail, expected_fragments)

    @pytest.mark.parametrize(
        ("category", "artifact_path"),
        [
            ("tex", _CANONICAL_MANUSCRIPT_BASENAME),
            ("bib", "references.bib"),
            ("audit", "BIBLIOGRAPHY-AUDIT.json"),
            ("figure", "figures/test-figure.png"),
            ("pdf", _CANONICAL_MANUSCRIPT_PDF_BASENAME),
        ],
    )
    def test_review_preflight_peer_review_strict_rejects_manifest_artifact_sha256_mismatch(
        self,
        gpd_project: Path,
        category: str,
        artifact_path: str,
    ) -> None:
        paper_dir = gpd_project / "paper"
        manuscript = canonical_manuscript_path(gpd_project)
        manifest_path = paper_dir / "ARTIFACT-MANIFEST.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifact_file = paper_dir / artifact_path
        artifact_file.parent.mkdir(parents=True, exist_ok=True)
        if category == "bib":
            artifact_file.write_text(
                "@article{ref2026,\n  title={Reference},\n  author={Doe, Jane},\n  year={2026}\n}\n",
                encoding="utf-8",
            )
        elif category == "figure":
            artifact_file.write_bytes(b"\x89PNG\r\n\x1a\nfake")
        artifact = next(
            (record for record in manifest["artifacts"] if record["category"] == category),
            None,
        )
        if artifact is None:
            artifact = {
                "artifact_id": f"{category}-test",
                "category": category,
                "path": artifact_path,
                "produced_by": "tests.test_cli_commands",
                "sources": [],
                "metadata": {},
            }
            manifest["artifacts"].append(artifact)
        artifact["path"] = artifact_path
        artifact["sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        passed, detail = cli_module._validate_artifact_manifest_semantics(manifest_path, manuscript)

        assert passed is False
        assert f"sha256 mismatch for {category} artifact" in detail

    def test_review_preflight_peer_review_strict_rejects_failed_build_manifest(
        self,
        gpd_project: Path,
    ) -> None:
        paper_dir = gpd_project / "paper"
        manuscript = canonical_manuscript_path(gpd_project)
        manifest_path = paper_dir / "ARTIFACT-MANIFEST.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        failure_artifact = dict(manifest["artifacts"][0])
        failure_artifact.update(
            {
                "artifact_id": "build-failure-compile",
                "category": "audit",
                "produced_by": "build_paper:compile",
                "metadata": {
                    "build_success": False,
                    "failure_stage": "compile",
                    "errors": "pdflatex exited with code 1",
                },
            }
        )
        manifest["artifacts"].append(failure_artifact)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        passed, detail = cli_module._validate_artifact_manifest_semantics(manifest_path, manuscript)

        assert passed is False
        assert "artifact manifest records failed paper build at compile stage" in detail

    def test_review_preflight_peer_review_accepts_explicit_manuscript_path_outside_supported_roots(
        self,
        gpd_project: Path,
    ) -> None:
        canonical_manuscript_path(gpd_project).unlink()

        paper_dir = gpd_project / "paper"
        review_dir = gpd_project / "submission"
        review_dir.mkdir()
        (_manuscript_entrypoint_path(gpd_project, root_name="submission")).write_text(
            "\\documentclass{article}\n\\begin{document}\nSubmission manuscript.\n\\end{document}\n",
            encoding="utf-8",
        )
        for artifact_name in ("PAPER-CONFIG.json",):
            (review_dir / artifact_name).write_text(
                (paper_dir / artifact_name).read_text(encoding="utf-8"), encoding="utf-8"
            )

        payload = _raw_json(
            [
                "--raw",
                "validate",
                "review-preflight",
                "peer-review",
                _manuscript_entrypoint_relpath(root_name="submission"),
                "--strict",
            ],
        )
        assert payload["command"] == "gpd:peer-review"
        assert payload["passed"] is True
        checks = checks_by_name(payload)
        assert checks["manuscript"]["passed"] is True
        assert checks["manuscript"]["detail"] == f"./submission/{_CANONICAL_MANUSCRIPT_BASENAME} present"
        assert "artifact_manifest" not in checks
        assert "bibliography_audit" not in checks
        assert "reproducibility_manifest" not in checks
        assert payload["resolved_mode"] == "standalone explicit-artifact review"
        assert payload["effective_required_evidence"] == ["existing manuscript or explicit external artifact target"]

    def test_review_preflight_peer_review_strict_does_not_fall_back_to_gpd_paper_for_explicit_manuscript(
        self,
        gpd_project: Path,
    ) -> None:
        review_dir = gpd_project / "submission"
        review_dir.mkdir()
        (_manuscript_entrypoint_path(gpd_project, root_name="submission")).write_text(
            "\\documentclass{article}\n\\begin{document}\nSubmission manuscript.\n\\end{document}\n",
            encoding="utf-8",
        )

        payload = _raw_json(
            [
                "--raw",
                "validate",
                "review-preflight",
                "peer-review",
                _manuscript_entrypoint_relpath(root_name="submission"),
                "--strict",
            ],
        )
        assert payload["passed"] is True
        checks = checks_by_name(payload)
        assert checks["manuscript"]["passed"] is True
        assert "artifact_manifest" not in checks
        assert "bibliography_audit" not in checks
        assert "reproducibility_manifest" not in checks
        assert payload["resolved_mode"] == "standalone explicit-artifact review"

    @pytest.mark.parametrize(
        "review_target",
        [
            "GPD/publication/curvature-flow",
            "GPD/publication/curvature-flow/manuscript",
            "GPD/publication/curvature-flow/manuscript/managed_manuscript.tex",
        ],
    )
    def test_review_preflight_peer_review_keeps_managed_publication_subject_project_backed(
        self,
        gpd_project: Path,
        review_target: str,
    ) -> None:
        manuscript = _write_managed_publication_manuscript(gpd_project)

        payload = _raw_json(
            [
                "--raw",
                "validate",
                "review-preflight",
                "peer-review",
                review_target,
                "--strict",
            ],
        )
        checks = checks_by_name(payload)
        assert payload["resolved_mode"] == "project-backed manuscript review"
        assert checks["manuscript"]["passed"] is True
        assert cli_module._format_display_path(manuscript) in checks["manuscript"]["detail"]
        assert checks["artifact_manifest"]["passed"] is True
        assert checks["bibliography_audit"]["passed"] is True
        assert checks["reproducibility_manifest"]["passed"] is True
        assert "manuscript-root publication artifacts" in payload["effective_required_evidence"]

    def test_review_preflight_peer_review_accepts_explicit_manuscript_directory(self, gpd_project: Path) -> None:
        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "peer-review", "paper", "--strict"],
        )
        checks = checks_by_name(payload)
        assert checks["manuscript"]["passed"] is True
        assert "resolved to" in checks["manuscript"]["detail"]

    @pytest.mark.parametrize(("command", "extra_args"), [("peer-review", ["paper"]), ("arxiv-submission", ["paper"])])
    def test_review_preflight_explicit_manuscript_path_disambiguates_supported_root(
        self,
        gpd_project: Path,
        command: str,
        extra_args: list[str],
    ) -> None:
        _write_secondary_manuscript_root(gpd_project)

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", command, *extra_args, "--strict"],
            expect_exit=1 if command == "arxiv-submission" else 0,
        )

        checks = checks_by_name(payload)
        assert checks["manuscript"]["passed"] is True
        assert "resolved to ./paper/curvature_flow_bounds.tex" in checks["manuscript"]["detail"]

    def test_review_preflight_explicit_nested_manuscript_keeps_owning_supported_root(
        self,
        gpd_project: Path,
    ) -> None:
        paper_dir = gpd_project / "paper"
        nested_dir = paper_dir / "sections"
        nested_dir.mkdir()
        manuscript = canonical_manuscript_path(gpd_project)
        nested_manuscript = nested_dir / manuscript.name
        nested_manuscript.write_text(manuscript.read_text(encoding="utf-8"), encoding="utf-8")
        manuscript.unlink()
        (paper_dir / "PAPER-CONFIG.json").unlink()
        manifest = json.loads((paper_dir / "ARTIFACT-MANIFEST.json").read_text(encoding="utf-8"))
        for artifact in manifest["artifacts"]:
            if artifact["artifact_id"] == "manuscript":
                artifact["path"] = f"sections/{manuscript.name}"
                artifact["sha256"] = compute_sha256(nested_manuscript)
            if artifact["artifact_id"] == "compiled-manuscript":
                artifact["sources"] = [{"path": f"sections/{manuscript.name}", "role": "compiled_from"}]
        (paper_dir / "ARTIFACT-MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")

        payload = _raw_json(
            [
                "--raw",
                "validate",
                "review-preflight",
                "peer-review",
                f"paper/sections/{manuscript.name}",
                "--strict",
            ],
        )
        checks = checks_by_name(payload)
        resolved_subject = payload["resolved_subject"]
        assert checks["manuscript"]["passed"] is True
        assert checks["artifact_manifest"]["passed"] is True
        assert resolved_subject["status"] == "resolved"
        assert resolved_subject["target_path"].endswith(f"paper/sections/{manuscript.name}")
        assert resolved_subject["target_root"].endswith("paper")

    def test_review_preflight_peer_review_directory_rejects_missing_main_entrypoint(
        self,
        gpd_project: Path,
    ) -> None:
        paper_dir = gpd_project / "paper"
        (paper_dir / _CANONICAL_MANUSCRIPT_BASENAME).unlink()
        (paper_dir / "z-notes.tex").write_text("\\section{Notes}\n", encoding="utf-8")
        (paper_dir / "a-appendix.md").write_text("# Appendix\n", encoding="utf-8")

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "peer-review", "paper", "--strict"],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert checks["manuscript"]["passed"] is False
        assert "no manuscript entry point found under ./paper" == checks["manuscript"]["detail"]

    def test_review_preflight_peer_review_strict_blocks_dirty_bibliography_audit(self, gpd_project: Path) -> None:
        paper_dir = gpd_project / "paper"
        (paper_dir / "BIBLIOGRAPHY-AUDIT.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-03-10T00:00:00+00:00",
                    "total_sources": 2,
                    "resolved_sources": 1,
                    "partial_sources": 1,
                    "unverified_sources": 0,
                    "failed_sources": 0,
                    "entries": [
                        {
                            "key": "einstein1905",
                            "source_type": "paper",
                            "reference_id": "ref-einstein",
                            "title": "Relativity",
                            "resolution_status": "provided",
                            "verification_status": "verified",
                        },
                        {
                            "key": "pending2026",
                            "source_type": "paper",
                            "reference_id": "ref-pending",
                            "title": "Pending Reference",
                            "resolution_status": "incomplete",
                            "verification_status": "partial",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "peer-review", "--strict"],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert checks["bibliography_audit"]["passed"] is True
        assert checks["bibliography_audit_clean"]["passed"] is False

    def test_review_preflight_peer_review_strict_rejects_incoherent_clean_bibliography_audit(
        self, gpd_project: Path
    ) -> None:
        paper_dir = gpd_project / "paper"
        (paper_dir / "BIBLIOGRAPHY-AUDIT.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-03-10T00:00:00+00:00",
                    "total_sources": 1,
                    "resolved_sources": 1,
                    "partial_sources": 0,
                    "unverified_sources": 0,
                    "failed_sources": 0,
                    "entries": [
                        {
                            "key": "doe2024",
                            "source_type": "paper",
                            "reference_id": "ref-doe",
                            "title": "Unverified Reference",
                            "resolution_status": "provided",
                            "verification_status": "unverified",
                            "verification_sources": [],
                            "canonical_identifiers": [],
                            "missing_core_fields": [],
                            "enriched_fields": [],
                            "warnings": [],
                            "errors": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "peer-review", "--strict"],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert checks["bibliography_audit_clean"]["passed"] is False
        assert "bibliography audit is invalid" in checks["bibliography_audit_clean"]["detail"]
        assert "summary counts do not match entries" in checks["bibliography_audit_clean"]["detail"]

    def test_review_preflight_peer_review_strict_rejects_invalid_bibliography_audit_shape(
        self, gpd_project: Path
    ) -> None:
        paper_dir = gpd_project / "paper"
        (paper_dir / "BIBLIOGRAPHY-AUDIT.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-03-10T00:00:00+00:00",
                    "total_sources": "oops",
                    "resolved_sources": 1,
                    "partial_sources": 0,
                    "unverified_sources": 0,
                    "failed_sources": 0,
                    "entries": [],
                }
            ),
            encoding="utf-8",
        )

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "peer-review", "--strict"],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert checks["bibliography_audit"]["passed"] is True
        assert checks["bibliography_audit_clean"]["passed"] is False
        assert "bibliography audit is invalid" in checks["bibliography_audit_clean"]["detail"]

    def test_review_preflight_peer_review_strict_blocks_non_ready_reproducibility_manifest(
        self, gpd_project: Path
    ) -> None:
        paper_dir = gpd_project / "paper"
        manifest = json.loads((paper_dir / "reproducibility-manifest.json").read_text(encoding="utf-8"))
        manifest["last_verified"] = ""
        manifest["last_verified_platform"] = ""
        (paper_dir / "reproducibility-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "peer-review", "--strict"],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert checks["reproducibility_manifest"]["passed"] is True
        assert checks["reproducibility_ready"]["passed"] is False

    def test_review_preflight_peer_review_strict_does_not_swallow_reproducibility_validator_bugs(
        self,
        gpd_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import gpd.core.reproducibility as reproducibility_module

        def _raise_validator_bug(payload: object):
            raise RuntimeError("validator bug")

        monkeypatch.setattr(reproducibility_module, "validate_reproducibility_manifest", _raise_validator_bug)

        with pytest.raises(RuntimeError, match="validator bug"):
            runner.invoke(
                app,
                ["--raw", "validate", "review-preflight", "peer-review", "--strict"],
                catch_exceptions=False,
            )

    def test_review_preflight_arxiv_submission_strict_requires_artifact_audits(self, gpd_project: Path) -> None:
        paper_dir = gpd_project / "paper"
        (paper_dir / "ARTIFACT-MANIFEST.json").unlink()

        payload = _raw_json(["--raw", "validate", "review-preflight", "arxiv-submission"], expect_exit=1)
        checks = checks_by_name(payload)
        assert checks["artifact_manifest"]["passed"] is False
        assert checks["bibliography_audit"]["passed"] is True
        assert checks["compiled_manuscript"]["passed"] is True

    def test_review_preflight_arxiv_submission_strict_requires_bibliography_audit(self, gpd_project: Path) -> None:
        paper_dir = gpd_project / "paper"
        (paper_dir / "BIBLIOGRAPHY-AUDIT.json").unlink()

        payload = _raw_json(["--raw", "validate", "review-preflight", "arxiv-submission"], expect_exit=1)
        checks = checks_by_name(payload)
        assert checks["artifact_manifest"]["passed"] is True
        assert checks["bibliography_audit"]["passed"] is False
        assert checks["compiled_manuscript"]["passed"] is True

    def test_review_preflight_arxiv_submission_enforces_theorem_bearing_proof_review_without_strict(
        self,
        gpd_project: Path,
    ) -> None:
        _write_publication_review_outcome(
            gpd_project,
            final_recommendation="accept",
            proof_bearing=True,
            write_proof_redteam=False,
        )

        payload = _raw_json(["--raw", "validate", "review-preflight", "arxiv-submission"], expect_exit=1)
        checks = checks_by_name(payload)
        assert checks["artifact_manifest"]["passed"] is True
        assert checks["bibliography_audit"]["passed"] is True
        assert checks["review_ledger"]["passed"] is True
        assert checks["referee_decision"]["passed"] is True
        assert checks["manuscript_proof_review"]["passed"] is False
        assert checks["manuscript_proof_review"]["blocking"] is True
        assert "PROOF-REDTEAM.md" in checks["manuscript_proof_review"]["detail"]

    @pytest.mark.parametrize(
        ("claim_updates", "expect_exit", "proof_check_passed", "forbidden_detail"),
        [
            (None, 0, True, "PROOF-REDTEAM"),
            (
                {
                    "claim_kind": "claim",
                    "text": "The manuscript reports a descriptive result.",
                    "theorem_assumptions": [],
                    "theorem_parameters": [],
                },
                0,
                True,
                "PROOF-REDTEAM",
            ),
            (
                {
                    "claim_kind": "claim",
                    "text": "The manuscript reports a descriptive result.",
                    "theorem_assumptions": ["chi > 0"],
                    "theorem_parameters": ["r_0"],
                },
                1,
                False,
                "not required",
            ),
            (
                {
                    "claim_kind": "claim",
                    "text": "For every r_0 > 0, the orbit intersects the target annulus.",
                    "theorem_assumptions": [],
                    "theorem_parameters": [],
                },
                1,
                False,
                "not required",
            ),
            (
                {
                    "claim_kind": "theorem",
                    "text": "For every r_0 > 0, the orbit intersects the target annulus.",
                    "theorem_assumptions": ["chi > 0"],
                    "theorem_parameters": ["r_0"],
                },
                1,
                False,
                "not required",
            ),
        ],
    )
    def test_review_preflight_arxiv_submission_classifies_theorem_bearing_claim_inventory(
        self,
        gpd_project: Path,
        claim_updates: dict[str, object] | None,
        expect_exit: int,
        proof_check_passed: bool,
        forbidden_detail: str,
    ) -> None:
        _write_publication_review_outcome(
            gpd_project,
            final_recommendation="accept",
            proof_bearing=False,
            write_proof_redteam=False,
        )
        if claim_updates is not None:
            _update_claim_index_claim(gpd_project, **claim_updates)

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "arxiv-submission"],
            expect_exit=expect_exit,
        )

        if claim_updates is not None:
            assert_checks_pass(payload, "review_ledger", "referee_decision")
        check = assert_check(payload, "manuscript_proof_review", passed=proof_check_passed)
        assert check["blocking"] is (not proof_check_passed)
        assert forbidden_detail not in check["detail"]

    def test_review_preflight_arxiv_submission_detects_theorem_bearing_manuscript_text_without_theorem_claim_inventory(
        self,
        gpd_project: Path,
    ) -> None:
        _write_publication_review_outcome(
            gpd_project,
            final_recommendation="accept",
            proof_bearing=False,
            write_proof_redteam=False,
        )
        manuscript = _manuscript_entrypoint_path(gpd_project)
        manuscript.write_text(
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "\\begin{lemma}For every r_0 > 0, the orbit intersects the target annulus.\\end{lemma}\n"
            "\\begin{proof}The proof is omitted.\\end{proof}\n"
            "\\end{document}\n",
            encoding="utf-8",
        )
        manifest_path = manuscript.parent / "ARTIFACT-MANIFEST.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["manuscript_sha256"] = compute_sha256(manuscript)
        manifest["manuscript_mtime_ns"] = manuscript.stat().st_mtime_ns
        for artifact in manifest.get("artifacts", []):
            if isinstance(artifact, dict) and artifact.get("category") == "tex":
                artifact["sha256"] = compute_sha256(manuscript)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        payload = _raw_json(["--raw", "validate", "review-preflight", "arxiv-submission"], expect_exit=1)
        checks = checks_by_name(payload)
        assert checks["manuscript_proof_review"]["passed"] is False
        assert checks["manuscript_proof_review"]["blocking"] is True
        assert "not required" not in checks["manuscript_proof_review"]["detail"]

    def test_review_preflight_arxiv_submission_rejects_theorem_claim_inventory_omitted_from_math_review(
        self,
        gpd_project: Path,
    ) -> None:
        _write_publication_review_outcome(
            gpd_project,
            final_recommendation="accept",
            proof_bearing=False,
            write_proof_redteam=False,
        )
        claims_path = gpd_project / "GPD" / "review" / "CLAIMS.json"
        claims_payload = json.loads(claims_path.read_text(encoding="utf-8"))
        claims_payload["claims"][0]["claim_kind"] = "theorem"
        claims_payload["claims"][0]["text"] = "For every r_0 > 0, the orbit intersects the target annulus."
        claims_payload["claims"][0]["theorem_assumptions"] = ["chi > 0"]
        claims_payload["claims"][0]["theorem_parameters"] = ["r_0"]
        claims_path.write_text(json.dumps(claims_payload), encoding="utf-8")
        math_stage_path = gpd_project / "GPD" / "review" / "STAGE-math.json"
        math_stage_payload = json.loads(math_stage_path.read_text(encoding="utf-8"))
        math_stage_payload["claims_reviewed"] = []
        math_stage_payload["proof_audits"] = []
        math_stage_path.write_text(json.dumps(math_stage_payload), encoding="utf-8")

        payload = _raw_json(["--raw", "validate", "review-preflight", "arxiv-submission"], expect_exit=1)
        checks = checks_by_name(payload)
        assert checks["manuscript_proof_review"]["passed"] is False
        assert checks["manuscript_proof_review"]["blocking"] is True
        assert "claims_reviewed" in checks["manuscript_proof_review"]["detail"]

    def test_review_preflight_arxiv_submission_uses_latest_round_specific_theorem_proof_review(
        self,
        gpd_project: Path,
    ) -> None:
        _write_publication_review_outcome(
            gpd_project,
            final_recommendation="accept",
            round_number=1,
            proof_bearing=True,
            write_proof_redteam=True,
        )
        _write_publication_review_outcome(
            gpd_project,
            final_recommendation="accept",
            round_number=2,
            proof_bearing=True,
            write_proof_redteam=False,
        )

        payload = _raw_json(["--raw", "validate", "review-preflight", "arxiv-submission"], expect_exit=1)
        checks = checks_by_name(payload)
        assert "round 2" in checks["review_ledger"]["detail"]
        assert "round 2" in checks["referee_decision"]["detail"]
        assert checks["manuscript_proof_review"]["passed"] is False
        assert checks["manuscript_proof_review"]["blocking"] is True
        assert "PROOF-REDTEAM-R2.md" in checks["manuscript_proof_review"]["detail"]

    def test_review_preflight_arxiv_submission_rejects_accepted_review_after_manuscript_edit(
        self,
        gpd_project: Path,
    ) -> None:
        _write_publication_review_outcome(
            gpd_project,
            final_recommendation="accept",
            proof_bearing=False,
        )
        manuscript_path = canonical_manuscript_path(gpd_project)
        manuscript_path.write_text(
            "\\documentclass{article}\n\\begin{document}\nEdited after review.\n\\end{document}\n",
            encoding="utf-8",
        )
        _refresh_artifact_manifest_for_manuscript(gpd_project, manuscript_path)

        payload = _raw_json(["--raw", "validate", "review-preflight", "arxiv-submission", "--strict"], expect_exit=1)
        checks = checks_by_name(payload)
        assert checks["referee_decision_valid"]["passed"] is False
        assert (
            "manuscript_sha256 does not match the active manuscript snapshot"
            in checks["referee_decision_valid"]["detail"]
        )

    def test_review_preflight_arxiv_submission_strict_blocks_semantically_dirty_bibliography_audit(
        self,
        gpd_project: Path,
    ) -> None:
        paper_dir = gpd_project / "paper"
        (paper_dir / "BIBLIOGRAPHY-AUDIT.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-03-10T00:00:00+00:00",
                    "total_sources": 2,
                    "resolved_sources": 1,
                    "partial_sources": 1,
                    "unverified_sources": 0,
                    "failed_sources": 0,
                    "entries": [
                        {
                            "key": "einstein1905",
                            "source_type": "paper",
                            "reference_id": "ref-einstein",
                            "title": "Relativity",
                            "resolution_status": "provided",
                            "verification_status": "verified",
                        },
                        {
                            "key": "pending2026",
                            "source_type": "paper",
                            "reference_id": "ref-pending",
                            "title": "Pending Reference",
                            "resolution_status": "incomplete",
                            "verification_status": "partial",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

        payload = _raw_json(["--raw", "validate", "review-preflight", "arxiv-submission", "--strict"], expect_exit=1)
        checks = checks_by_name(payload)
        assert checks["bibliography_audit"]["passed"] is True
        assert checks["bibliography_audit_clean"]["passed"] is False
        assert "bibliography audit still has unresolved" in checks["bibliography_audit_clean"]["detail"]

    def test_review_preflight_arxiv_submission_strict_blocks_publication_blockers(self, gpd_project: Path) -> None:
        planning = gpd_project / "GPD"
        state = json.loads((planning / "state.json").read_text(encoding="utf-8"))
        state["blockers"] = ["Publication blocker: unresolved venue fit"]
        (planning / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
        (planning / "STATE.md").write_text(generate_state_markdown(state), encoding="utf-8")

        payload = _raw_json(["--raw", "validate", "review-preflight", "arxiv-submission", "--strict"], expect_exit=1)
        checks = checks_by_name(payload)
        assert checks["compiled_manuscript"]["passed"] is True
        assert checks["publication_blockers"]["passed"] is False
        assert checks["publication_blockers"]["blocking"] is True

    def test_review_preflight_arxiv_submission_strict_blocks_latest_major_revision_decision(
        self,
        gpd_project: Path,
    ) -> None:
        _write_publication_review_outcome(gpd_project, final_recommendation="major_revision")

        payload = _raw_json(["--raw", "validate", "review-preflight", "arxiv-submission", "--strict"], expect_exit=1)
        checks = checks_by_name(payload)
        assert checks["review_ledger"]["passed"] is True
        assert checks["referee_decision"]["passed"] is True
        assert checks["review_ledger_valid"]["passed"] is True
        assert checks["referee_decision_valid"]["passed"] is True
        assert checks["publication_review_outcome"]["passed"] is False
        assert checks["publication_review_outcome"]["blocking"] is True

    def test_review_preflight_arxiv_submission_strict_blocks_latest_open_blocking_review_issues(
        self,
        gpd_project: Path,
    ) -> None:
        _write_publication_review_outcome(
            gpd_project,
            final_recommendation="minor_revision",
            blocking_issue_ids=["REF-001"],
        )

        payload = _raw_json(["--raw", "validate", "review-preflight", "arxiv-submission", "--strict"], expect_exit=1)
        checks = checks_by_name(payload)
        assert checks["review_ledger_valid"]["passed"] is True
        assert checks["referee_decision_valid"]["passed"] is False
        assert "publication_review_outcome" not in checks

    def test_review_preflight_arxiv_submission_strict_uses_latest_review_round_when_review_artifacts_exist(
        self,
        gpd_project: Path,
    ) -> None:
        _write_publication_review_outcome(gpd_project, final_recommendation="accept", round_number=1)
        _write_publication_review_outcome(gpd_project, final_recommendation="major_revision", round_number=2)

        payload = _raw_json(["--raw", "validate", "review-preflight", "arxiv-submission", "--strict"], expect_exit=1)
        checks = checks_by_name(payload)
        assert "round 2" in checks["review_ledger"]["detail"]
        assert "round 2" in checks["referee_decision"]["detail"]
        assert checks["publication_review_outcome"]["passed"] is False

    def test_review_preflight_arxiv_submission_strict_requires_matching_latest_review_pair(
        self,
        gpd_project: Path,
    ) -> None:
        _write_publication_review_outcome(gpd_project, final_recommendation="accept", round_number=1)
        _write_publication_review_outcome(gpd_project, final_recommendation="accept", round_number=2)
        (gpd_project / "GPD" / "review" / "REVIEW-LEDGER-R2.json").unlink()

        payload = _raw_json(["--raw", "validate", "review-preflight", "arxiv-submission", "--strict"], expect_exit=1)
        checks = checks_by_name(payload)
        assert checks["review_ledger"]["passed"] is False
        assert "round 2" in checks["review_ledger"]["detail"]

    def test_review_preflight_arxiv_submission_strict_requires_new_review_after_same_round_response(
        self,
        gpd_project: Path,
    ) -> None:
        _write_publication_review_outcome(gpd_project, final_recommendation="accept", round_number=1)
        (gpd_project / "GPD" / "AUTHOR-RESPONSE.md").write_text("# Author Response\n", encoding="utf-8")
        (gpd_project / "GPD" / "review" / "REFEREE_RESPONSE.md").write_text(
            "# Referee Response\n",
            encoding="utf-8",
        )

        payload = _raw_json(["--raw", "validate", "review-preflight", "arxiv-submission", "--strict"], expect_exit=1)
        checks = checks_by_name(payload)
        assert checks["response_freshness"]["passed"] is False
        assert checks["response_freshness"]["blocking"] is True
        assert "checkpoint=response_gate" in checks["response_freshness"]["detail"]
        assert checks["review_ledger"]["passed"] is False
        assert "REVIEW-LEDGER-R2.json" in checks["review_ledger"]["detail"]
        assert "latest response artifacts already reached round 1" in checks["review_ledger"]["detail"]
        assert "requires newer staged review clearance in round 2" in checks["review_ledger"]["detail"]
        assert checks["referee_decision"]["passed"] is False
        assert "REFEREE-DECISION-R2.json" in checks["referee_decision"]["detail"]

    def test_review_preflight_arxiv_submission_strict_requires_fresh_review_after_newer_managed_lane_response_round(
        self,
        gpd_project: Path,
    ) -> None:
        manuscript = _write_managed_publication_manuscript(gpd_project)
        _write_publication_review_outcome(
            gpd_project,
            final_recommendation="accept",
            round_number=1,
            manuscript_path="GPD/publication/curvature-flow/manuscript/managed_manuscript.tex",
        )
        _write_publication_response_round(gpd_project, round_number=2)

        payload = _raw_json(
            [
                "--raw",
                "validate",
                "review-preflight",
                "arxiv-submission",
                "GPD/publication/curvature-flow/manuscript/managed_manuscript.tex",
                "--strict",
            ],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert payload["publication_subject_slug"] == "curvature-flow"
        assert payload["publication_lane_kind"] == "managed_publication_manuscript"
        assert payload["managed_publication_root"] == "GPD/publication/curvature-flow"
        assert payload["selected_publication_root"] == "GPD/publication/curvature-flow"
        assert payload["selected_review_root"] == "GPD/publication/curvature-flow/review"
        assert payload["manuscript_root"] == "GPD/publication/curvature-flow/manuscript"
        assert payload["manuscript_entrypoint"] == "GPD/publication/curvature-flow/manuscript/managed_manuscript.tex"
        assert checks["manuscript"]["passed"] is True
        assert checks["manuscript"]["detail"] == f"{cli_module._format_display_path(manuscript)} present"
        assert checks["review_ledger"]["passed"] is False
        assert "REVIEW-LEDGER-R3.json" in checks["review_ledger"]["detail"]
        assert "latest response artifacts already reached round 2" in checks["review_ledger"]["detail"]
        assert "requires newer staged review clearance in round 3" in checks["review_ledger"]["detail"]
        assert checks["referee_decision"]["passed"] is False
        assert "REFEREE-DECISION-R3.json" in checks["referee_decision"]["detail"]

    def test_review_preflight_arxiv_submission_strict_rejects_stale_review_artifact_manuscript_paths(
        self,
        gpd_project: Path,
    ) -> None:
        _write_publication_review_outcome(
            gpd_project,
            final_recommendation="accept",
            manuscript_path=_manuscript_entrypoint_relpath(root_name="submission"),
        )

        payload = _raw_json(["--raw", "validate", "review-preflight", "arxiv-submission", "--strict"], expect_exit=1)
        checks = checks_by_name(payload)
        assert checks["review_ledger_valid"]["passed"] is False
        assert checks["referee_decision_valid"]["passed"] is False

    def test_review_preflight_arxiv_submission_ignores_generic_non_publication_blockers(
        self, gpd_project: Path
    ) -> None:
        planning = gpd_project / "GPD"
        state = json.loads((planning / "state.json").read_text(encoding="utf-8"))
        state["blockers"] = ["IR divergence in loop integral"]
        (planning / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
        (planning / "STATE.md").write_text(generate_state_markdown(state), encoding="utf-8")

        payload = _raw_json(["--raw", "validate", "review-preflight", "arxiv-submission", "--strict"], expect_exit=1)
        checks = checks_by_name(payload)
        assert checks["publication_blockers"]["passed"] is True
        assert checks["review_ledger"]["passed"] is False
        assert checks["referee_decision"]["passed"] is False

    def test_review_preflight_arxiv_submission_rejects_explicit_directory_outside_supported_roots(
        self,
        gpd_project: Path,
    ) -> None:
        submission_dir = gpd_project / "submission"
        submission_dir.mkdir()
        (submission_dir / _CANONICAL_MANUSCRIPT_BASENAME).write_text(
            "\\documentclass{article}\n\\begin{document}\nSubmission manuscript.\n\\end{document}\n",
            encoding="utf-8",
        )

        payload = _raw_json(
            ["--raw", "validate", "review-preflight", "arxiv-submission", "submission", "--strict"],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert checks["manuscript"]["passed"] is False
        assert (
            checks["manuscript"]["detail"]
            == "explicit manuscript target must stay under `paper/`, `manuscript/`, `draft/`, or `GPD/publication/<subject_slug>[/manuscript/]` inside the current project"
        )

    @pytest.mark.parametrize(
        "review_target",
        [
            "GPD/publication/curvature-flow",
            "GPD/publication/curvature-flow/manuscript",
            "GPD/publication/curvature-flow/manuscript/managed_manuscript.tex",
        ],
    )
    def test_review_preflight_arxiv_submission_accepts_explicit_managed_publication_manuscript_subject(
        self, gpd_project: Path, review_target: str
    ) -> None:
        manuscript = _write_managed_publication_manuscript(gpd_project)

        payload = _raw_json(
            [
                "--raw",
                "validate",
                "review-preflight",
                "arxiv-submission",
                review_target,
                "--strict",
            ],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert checks["manuscript"]["passed"] is True
        assert checks["artifact_manifest"]["passed"] is True
        assert checks["bibliography_audit"]["passed"] is True
        assert checks["reproducibility_manifest"]["passed"] is True
        assert checks["review_ledger"]["passed"] is False
        assert checks["referee_decision"]["passed"] is False
        assert cli_module._format_display_path(manuscript) in checks["manuscript"]["detail"]

    def test_review_preflight_arxiv_submission_prefers_managed_subject_review_over_stale_global_rounds(
        self,
        gpd_project: Path,
    ) -> None:
        manuscript = _write_managed_publication_manuscript(gpd_project)
        managed_manuscript_path = "GPD/publication/curvature-flow/manuscript/managed_manuscript.tex"
        _write_publication_review_outcome(
            gpd_project,
            final_recommendation="accept",
            round_number=1,
            manuscript_path=managed_manuscript_path,
        )
        _move_publication_review_outcome_to_subject_review(
            gpd_project,
            subject_slug="curvature-flow",
            round_number=1,
        )
        _write_publication_review_outcome(
            gpd_project,
            final_recommendation="major_revision",
            round_number=2,
            manuscript_path=_CANONICAL_MANUSCRIPT_REL,
        )

        payload = _raw_json(
            [
                "--raw",
                "validate",
                "review-preflight",
                "arxiv-submission",
                managed_manuscript_path,
                "--strict",
            ],
        )
        checks = checks_by_name(payload)
        assert checks["manuscript"]["passed"] is True
        assert checks["manuscript"]["detail"] == f"{cli_module._format_display_path(manuscript)} present"
        assert checks["review_ledger"]["passed"] is True
        assert "round 1" in checks["review_ledger"]["detail"]
        assert "REVIEW-LEDGER-R2.json" not in checks["review_ledger"]["detail"]
        assert checks["publication_review_outcome"]["passed"] is True

    def test_validate_arxiv_package_accepts_managed_root_tarball_after_strict_preflight(
        self,
        gpd_project: Path,
    ) -> None:
        managed_manuscript_path, _manuscript = _prepare_accepted_managed_arxiv_subject(gpd_project)
        _write_managed_arxiv_submission_package(gpd_project)

        payload = _raw_json(
            ["--raw", "validate", "arxiv-package", managed_manuscript_path],
        )
        checks = checks_by_name(payload)
        assert payload["passed"] is True
        assert payload["preflight_passed"] is True
        assert payload["subject_slug"] == "curvature-flow"
        assert payload["package_root"] == "GPD/publication/curvature-flow/arxiv"
        assert payload["submission_dir"] == "GPD/publication/curvature-flow/arxiv/submission"
        assert payload["tarball"] == "GPD/publication/curvature-flow/arxiv/arxiv-submission.tar.gz"
        assert payload["root_entrypoint"] == "managed_manuscript.tex"
        assert "managed_manuscript.tex" in payload["tarball_entries"]
        assert checks["tarball_under_managed_arxiv_root"]["passed"] is True
        assert checks["tarball_entrypoint_at_root"]["passed"] is True
        assert checks["tarball_tex_ready"]["passed"] is True

    def test_validate_arxiv_package_materializes_tarball_from_valid_submission_tree(
        self,
        gpd_project: Path,
    ) -> None:
        managed_manuscript_path, _manuscript = _prepare_accepted_managed_arxiv_subject(gpd_project)
        submission_dir, tarball = _write_managed_arxiv_submission_package(gpd_project)
        tarball.unlink()

        payload = _raw_json(
            [
                "--raw",
                "validate",
                "arxiv-package",
                managed_manuscript_path,
                "--materialize",
                "--submission-dir",
                str(submission_dir),
                "--tarball",
                str(tarball),
            ],
        )
        checks = checks_by_name(payload)
        assert payload["materialized"] is True
        assert tarball.exists()
        assert checks["tarball_materialized"]["passed"] is True
        assert checks["tarball_exists"]["passed"] is True

    def test_validate_arxiv_package_rejects_tarball_outside_managed_arxiv_root(
        self,
        gpd_project: Path,
    ) -> None:
        managed_manuscript_path, _manuscript = _prepare_accepted_managed_arxiv_subject(gpd_project)
        _submission_dir, tarball = _write_managed_arxiv_submission_package(gpd_project)
        escaped_tarball = gpd_project / "arxiv-submission.tar.gz"
        escaped_tarball.write_bytes(tarball.read_bytes())

        payload = _raw_json(
            [
                "--raw",
                "validate",
                "arxiv-package",
                managed_manuscript_path,
                "--tarball",
                str(escaped_tarball),
            ],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert checks["tarball_under_managed_arxiv_root"]["passed"] is False
        assert "escapes managed arXiv root" in checks["tarball_under_managed_arxiv_root"]["detail"]

    def test_validate_arxiv_package_accepts_packaged_bib_source_material(
        self,
        gpd_project: Path,
    ) -> None:
        managed_manuscript_path, _manuscript = _prepare_accepted_managed_arxiv_subject(gpd_project)
        _write_managed_arxiv_submission_package(
            gpd_project,
            tex_body=(
                "\\documentclass{article}\n"
                "\\begin{document}\n"
                "Citation \\cite{einstein1905}.\\bibliography{refs}\n"
                "\\end{document}\n"
            ),
            extra_files={"refs.bib": "@article{einstein1905,title={Relativity}}\n"},
        )

        payload = _raw_json(
            ["--raw", "validate", "arxiv-package", managed_manuscript_path],
        )
        checks = checks_by_name(payload)
        assert checks["submission_tree_excludes_auxiliary_files"]["passed"] is True
        assert checks["submission_tex_ready"]["passed"] is True
        assert checks["tarball_entries_safe"]["passed"] is True
        assert checks["tarball_tex_ready"]["passed"] is True
        assert "refs.bib" in payload["tarball_entries"]

    def test_validate_arxiv_package_reuses_strict_preflight_response_freshness(
        self,
        gpd_project: Path,
    ) -> None:
        managed_manuscript_path = "GPD/publication/curvature-flow/manuscript/managed_manuscript.tex"
        _write_managed_publication_manuscript(gpd_project)
        _write_publication_review_outcome(
            gpd_project,
            final_recommendation="accept",
            round_number=1,
            manuscript_path=managed_manuscript_path,
        )
        _move_publication_review_outcome_to_subject_review(gpd_project, subject_slug="curvature-flow")
        _write_publication_response_round(gpd_project, round_number=2)
        _write_managed_arxiv_submission_package(gpd_project)

        payload = _raw_json(
            ["--raw", "validate", "arxiv-package", managed_manuscript_path],
            expect_exit=1,
        )
        assert payload["preflight_passed"] is False
        assert payload["checks"][0]["name"] == "strict_review_preflight"
        review_checks = checks_by_name(payload["review_preflight"])
        assert review_checks["response_freshness"]["passed"] is False
        assert "checkpoint=response_gate" in review_checks["response_freshness"]["detail"]
        assert review_checks["review_ledger"]["passed"] is False
        assert "latest response artifacts already reached round 2" in review_checks["review_ledger"]["detail"]
        assert "requires newer staged review clearance" in review_checks["review_ledger"]["detail"]

    def test_command_context_arxiv_submission_rejects_explicit_target_outside_supported_roots(
        self,
        gpd_project: Path,
    ) -> None:
        submission_dir = gpd_project / "submission"
        submission_dir.mkdir()
        (submission_dir / _CANONICAL_MANUSCRIPT_BASENAME).write_text(
            "\\documentclass{article}\n\\begin{document}\nSubmission manuscript.\n\\end{document}\n",
            encoding="utf-8",
        )

        payload = _raw_json(
            ["--raw", "validate", "command-context", "arxiv-submission", "submission"],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert payload["context_mode"] == "project-aware"
        assert payload["passed"] is False
        assert payload["guidance"] == (
            "explicit manuscript target must stay under `paper/`, `manuscript/`, `draft/`, or "
            "`GPD/publication/<subject_slug>[/manuscript/]` inside the current project"
        )
        assert checks["explicit_inputs"]["passed"] is False
        assert checks["explicit_inputs"]["blocking"] is True
        assert checks["explicit_inputs"]["detail"] == payload["guidance"]
        assert payload["resolved_subject"]["status"] == "invalid"
        assert payload["resolved_subject"]["ownership_mode"] == "external_artifact"
        assert payload["resolved_subject"]["explicit_input"] is True
        assert payload["resolved_subject"]["target_path"].endswith("submission")
        assert (
            payload["resolved_subject"]["detail"]
            == "explicit manuscript target must stay under `paper/`, `manuscript/`, `draft/`, or `GPD/publication/<subject_slug>[/manuscript/]` inside the current project"
        )

    def test_command_context_arxiv_submission_rejects_standalone_publication_artifact(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        workspace = tmp_path.parent / f"{tmp_path.name}-standalone-arxiv"
        workspace.mkdir()
        manuscript = _write_managed_publication_manuscript(workspace, subject_slug="standalone", stem="standalone")
        monkeypatch.chdir(workspace)

        result = runner.invoke(
            app,
            [
                "--raw",
                "--cwd",
                str(workspace),
                "validate",
                "command-context",
                "arxiv-submission",
                manuscript.relative_to(workspace).as_posix(),
            ],
            catch_exceptions=False,
        )

        payload = json_output_from_result(result, expect_exit=1)
        checks = checks_by_name(payload)
        assert payload["context_mode"] == "project-aware"
        assert payload["passed"] is False
        assert (
            payload["guidance"]
            == "explicit manuscript target must resolve inside an initialized GPD project for this command"
        ), result.output
        assert checks["project_exists"]["passed"] is False
        assert checks["explicit_inputs"]["passed"] is False
        assert checks["explicit_inputs"]["blocking"] is True
        assert checks["explicit_inputs"]["detail"] == payload["guidance"]
        assert payload["resolved_subject"]["status"] == "resolved"
        assert payload["resolved_subject"]["ownership_mode"] == "external_artifact"
        assert payload["resolved_subject"]["explicit_input"] is True
        assert payload["resolved_subject"]["target_path"].endswith(
            "GPD/publication/standalone/manuscript/standalone.tex"
        )

    def test_command_context_arxiv_submission_resolves_managed_publication_lane_without_arguments(
        self,
        gpd_project: Path,
    ) -> None:
        paper_dir = gpd_project / "paper"
        for artifact_name in (
            _CANONICAL_MANUSCRIPT_BASENAME,
            _CANONICAL_MANUSCRIPT_PDF_BASENAME,
            "PAPER-CONFIG.json",
            "ARTIFACT-MANIFEST.json",
            "BIBLIOGRAPHY-AUDIT.json",
            "reproducibility-manifest.json",
        ):
            artifact_path = paper_dir / artifact_name
            if artifact_path.exists():
                artifact_path.unlink()

        manuscript = _write_managed_publication_manuscript(gpd_project)

        payload = _raw_json(
            ["--raw", "validate", "command-context", "arxiv-submission"],
        )
        checks = checks_by_name(payload)
        resolved_subject = payload["resolved_subject"]
        assert payload["passed"] is True
        assert checks["project_exists"]["passed"] is True
        assert checks["explicit_inputs"]["passed"] is False
        assert resolved_subject["status"] == "resolved"
        assert resolved_subject["ownership_mode"] == "project_backed"
        assert resolved_subject["explicit_input"] is False
        assert resolved_subject["target_path"].endswith(
            "GPD/publication/curvature-flow/manuscript/managed_manuscript.tex"
        )
        assert resolved_subject["detail"] == f"{cli_module._format_display_path(manuscript)} present"

    def test_command_context_respond_to_referees_exposes_managed_response_roots(
        self,
        gpd_project: Path,
    ) -> None:
        manuscript = _write_managed_publication_manuscript(gpd_project)
        report = gpd_project / "reviews" / "referee-1.md"
        report.parent.mkdir()
        report.write_text("# Referee 1\n\nPlease clarify the proof.\n", encoding="utf-8")

        payload = _raw_json(
            [
                "--raw",
                "--cwd",
                str(gpd_project),
                "validate",
                "command-context",
                "respond-to-referees",
                "--",
                "--manuscript",
                manuscript.relative_to(gpd_project).as_posix(),
                "--report",
                report.relative_to(gpd_project).as_posix(),
            ],
        )
        assert payload["selected_publication_root"] == "GPD/publication/curvature-flow"
        assert payload["selected_review_root"] == "GPD/publication/curvature-flow/review"

    def test_review_preflight_respond_to_referees_uses_managed_response_outputs(
        self,
        gpd_project: Path,
    ) -> None:
        manuscript = _write_managed_publication_manuscript(gpd_project)
        report = gpd_project / "reviews" / "referee-1.md"
        report.parent.mkdir()
        report.write_text("# Referee 1\n\nPlease clarify the proof.\n", encoding="utf-8")

        payload = _raw_json(
            [
                "--raw",
                "--cwd",
                str(gpd_project),
                "validate",
                "review-preflight",
                "respond-to-referees",
                "--strict",
                "--",
                "--manuscript",
                manuscript.relative_to(gpd_project).as_posix(),
                "--report",
                report.relative_to(gpd_project).as_posix(),
            ],
        )
        assert payload["required_outputs"] == [
            "GPD/publication/{subject_slug}/review/REFEREE_RESPONSE{round_suffix}.md",
            "GPD/publication/{subject_slug}/AUTHOR-RESPONSE{round_suffix}.md",
        ]

    def test_command_context_peer_review_resolves_relative_manuscript_from_nested_workspace(
        self,
        gpd_project: Path,
    ) -> None:
        nested = gpd_project / "notes"
        nested.mkdir()

        payload = _raw_json(
            [
                "--raw",
                "--cwd",
                str(nested),
                "validate",
                "command-context",
                "peer-review",
                f"../paper/{_CANONICAL_MANUSCRIPT_BASENAME}",
            ],
        )
        checks = checks_by_name(payload)
        resolved_subject = payload["resolved_subject"]
        assert payload["passed"] is True
        assert checks["project_exists"]["passed"] is True
        assert checks["explicit_inputs"]["passed"] is True
        assert resolved_subject["status"] == "resolved"
        assert resolved_subject["ownership_mode"] == "project_backed"
        assert resolved_subject["ancestor_walked_up"] is True
        assert resolved_subject["explicit_input"] is True
        assert resolved_subject["target_path"].endswith(f"paper/{_CANONICAL_MANUSCRIPT_BASENAME}")

    def test_command_context_peer_review_accepts_explicit_manuscript_outside_supported_roots(
        self,
        gpd_project: Path,
    ) -> None:
        submission_dir = gpd_project / "submission"
        submission_dir.mkdir()
        (_manuscript_entrypoint_path(gpd_project, root_name="submission")).write_text(
            "\\documentclass{article}\n\\begin{document}\nSubmission manuscript.\n\\end{document}\n",
            encoding="utf-8",
        )

        payload = _raw_json(
            [
                "--raw",
                "validate",
                "command-context",
                "peer-review",
                _manuscript_entrypoint_relpath(root_name="submission"),
            ],
        )
        checks = checks_by_name(payload)
        resolved_subject = payload["resolved_subject"]
        assert payload["passed"] is True
        assert checks["project_exists"]["passed"] is True
        assert checks["explicit_inputs"]["passed"] is True
        assert resolved_subject["status"] == "resolved"
        assert resolved_subject["ownership_mode"] == "external_artifact"
        assert resolved_subject["explicit_input"] is True
        assert resolved_subject["target_path"].endswith(f"submission/{_CANONICAL_MANUSCRIPT_BASENAME}")

    def test_command_context_peer_review_without_arguments_allows_interactive_intake(
        self,
        tmp_path: Path,
    ) -> None:
        workspace = tmp_path / "standalone-review"
        workspace.mkdir()

        payload = _raw_json(
            ["--raw", "--cwd", str(workspace), "validate", "command-context", "peer-review"],
        )
        checks = checks_by_name(payload)
        assert payload["passed"] is True
        assert checks["project_exists"]["blocking"] is False
        assert checks["explicit_inputs"]["passed"] is True
        assert checks["explicit_inputs"]["detail"] == (
            "no explicit review target supplied; interactive intake can prompt for a specific artifact path "
            "or use the current GPD project when available"
        )

    def test_command_context_peer_review_accepts_external_xlsm_artifact(
        self,
        tmp_path: Path,
    ) -> None:
        workspace = tmp_path / "standalone-review"
        workspace.mkdir()
        _write_minimal_xlsx(workspace / "standalone.xlsm")

        payload = _raw_json(
            ["--raw", "--cwd", str(workspace), "validate", "command-context", "peer-review", "standalone.xlsm"],
        )
        checks = checks_by_name(payload)
        resolved_subject = payload["resolved_subject"]
        assert payload["passed"] is True
        assert payload["resolved_mode"] == "standalone explicit-artifact review"
        assert "standalone explicit-artifact" in payload["mode_reason"]
        assert checks["explicit_inputs"]["passed"] is True
        assert resolved_subject["status"] == "resolved"
        assert resolved_subject["ownership_mode"] == "external_artifact"
        assert resolved_subject["target_path"].endswith("standalone.xlsm")

    def test_command_context_write_paper_fails_closed_outside_project_without_intake(
        self,
        tmp_path: Path,
    ) -> None:
        workspace = tmp_path.parent / f"{tmp_path.name}-standalone-write-paper"
        workspace.mkdir()

        payload = _raw_json(
            ["--raw", "--cwd", str(workspace), "validate", "command-context", "write-paper"],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert payload["command"] == "gpd:write-paper"
        assert payload["context_mode"] == "project-aware"
        assert payload["passed"] is False
        assert payload["explicit_inputs"] == ["--intake path/to/write-paper-authoring-input.json"]
        assert checks["project_exists"]["passed"] is False
        assert checks["explicit_inputs"]["passed"] is False
        assert checks["explicit_inputs"]["detail"] == (
            "missing explicit standalone inputs (--intake path/to/write-paper-authoring-input.json)"
        )
        assert payload["resolved_subject"]["status"] == "missing"
        assert payload["resolved_subject"]["detail"] == (
            "external authoring outside a project requires `--intake path/to/write-paper-authoring-input.json`"
        )

    def test_command_context_write_paper_does_not_migrate_nested_project_notes_under_ancestor(
        self,
        gpd_project: Path,
    ) -> None:
        nested = gpd_project / "notes" / "nested"
        nested.mkdir(parents=True)
        (nested / "PROJECT.md").write_text("# Nested note\n", encoding="utf-8")

        payload = _raw_json(
            ["--raw", "--cwd", str(nested), "validate", "command-context", "write-paper"],
        )
        checks = checks_by_name(payload)
        assert payload["command"] == "gpd:write-paper"
        assert checks["project_exists"]["passed"] is True
        assert payload["resolved_subject"]["status"] == "resolved"
        assert payload["resolved_subject"]["resolved_project_root"] == gpd_project.resolve().as_posix()
        assert not (nested / "GPD").exists()

    def test_command_context_write_paper_accepts_valid_external_authoring_intake(
        self,
        tmp_path: Path,
    ) -> None:
        workspace = tmp_path.parent / f"{tmp_path.name}-standalone-write-paper-intake"
        workspace.mkdir()
        intake_path = _write_write_paper_authoring_input(workspace)

        payload = _raw_json(
            [
                "--raw",
                "--cwd",
                str(workspace),
                "validate",
                "command-context",
                "write-paper",
                f"--intake {intake_path.name}",
            ],
        )
        checks = checks_by_name(payload)
        resolved_subject = payload["resolved_subject"]
        assert payload["command"] == "gpd:write-paper"
        assert payload["context_mode"] == "project-aware"
        assert payload["passed"] is True
        assert payload["explicit_inputs"] == ["--intake path/to/write-paper-authoring-input.json"]
        assert checks["project_exists"]["passed"] is False
        assert checks["explicit_inputs"]["passed"] is True
        assert checks["explicit_inputs"]["detail"] == "validated external authoring intake manifest"
        assert resolved_subject["status"] == "bootstrap"
        assert resolved_subject["ownership_mode"] == "external_authoring_intake"
        assert resolved_subject["explicit_input"] is True
        assert resolved_subject["target_path"].endswith(intake_path.name)
        assert resolved_subject["target_root"].endswith("GPD/publication/external-authoring-test/manuscript")
        assert payload["selected_publication_root"] == "GPD/publication/external-authoring-test"
        assert payload["selected_review_root"] == "GPD/publication/external-authoring-test/review"
        assert "managed manuscript bootstrap will use" in resolved_subject["detail"]

    def test_command_context_write_paper_rejects_external_authoring_intake_inside_project(
        self,
        gpd_project: Path,
    ) -> None:
        intake_path = _write_write_paper_authoring_input(gpd_project)

        payload = _raw_json(
            [
                "--raw",
                "--cwd",
                str(gpd_project),
                "validate",
                "command-context",
                "write-paper",
                f"--intake {intake_path.name}",
            ],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        resolved_subject = payload["resolved_subject"]
        assert payload["passed"] is False
        assert payload["selected_publication_root"] is None
        assert payload["selected_review_root"] is None
        assert checks["explicit_inputs"]["passed"] is False
        assert "only allowed from a workspace without an initialized GPD project" in checks["explicit_inputs"]["detail"]
        assert resolved_subject["status"] == "invalid"
        assert resolved_subject["ownership_mode"] == "external_authoring_intake"
        assert resolved_subject["target_path"].endswith(intake_path.name)

    def test_command_context_write_paper_rejects_invalid_external_authoring_intake(
        self,
        tmp_path: Path,
    ) -> None:
        workspace = tmp_path.parent / f"{tmp_path.name}-standalone-write-paper-invalid-intake"
        workspace.mkdir()
        intake_path = workspace / "write-paper-authoring-input.json"
        intake_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "title": "Broken intake",
                    "authors": [{"name": "A. Researcher"}],
                    "target_journal": "prl",
                    "claims": [],
                    "source_notes": [],
                    "citation_sources": [],
                }
            ),
            encoding="utf-8",
        )

        payload = _raw_json(
            [
                "--raw",
                "--cwd",
                str(workspace),
                "validate",
                "command-context",
                "write-paper",
                f"--intake {intake_path.name}",
            ],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        resolved_subject = payload["resolved_subject"]
        assert payload["passed"] is False
        assert checks["explicit_inputs"]["passed"] is False
        assert "write-paper intake manifest is invalid" in checks["explicit_inputs"]["detail"]
        assert resolved_subject["status"] == "invalid"
        assert resolved_subject["ownership_mode"] == "external_authoring_intake"
        assert "write_paper_authoring_input.central_claim is required" in resolved_subject["detail"]

    def test_command_context_respond_to_referees_rejects_report_only_outside_project_without_manuscript(
        self,
        tmp_path: Path,
    ) -> None:
        workspace = tmp_path.parent / f"{tmp_path.name}-standalone-respond-report-only"
        report = workspace / "reports" / "referee-1.md"
        report.parent.mkdir(parents=True)
        report.write_text("# Referee 1\n\nPlease clarify the proof.\n", encoding="utf-8")

        payload = _raw_json(
            [
                "--raw",
                "--cwd",
                str(workspace),
                "validate",
                "command-context",
                "respond-to-referees",
                "--",
                "--report",
                report.relative_to(workspace).as_posix(),
            ],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert payload["command"] == "gpd:respond-to-referees"
        assert payload["passed"] is False
        assert checks["project_exists"]["passed"] is False
        assert checks["manuscript"]["passed"] is False
        assert checks["explicit_inputs"]["passed"] is False
        assert checks["manuscript"]["detail"].startswith("respond-to-referees outside a project requires")
        assert payload["resolved_subject"]["status"] == "missing"

    def test_command_context_respond_to_referees_requires_explicit_manuscript_outside_project(
        self,
        tmp_path: Path,
    ) -> None:
        workspace = tmp_path.parent / f"{tmp_path.name}-standalone-respond-with-default-manuscript"
        manuscript = _manuscript_entrypoint_path(workspace)
        manuscript.parent.mkdir(parents=True)
        manuscript.write_text(
            "\\documentclass{article}\n\\begin{document}\nStandalone draft.\n\\end{document}\n",
            encoding="utf-8",
        )
        report = workspace / "reports" / "referee-1.md"
        report.parent.mkdir()
        report.write_text("# Referee 1\n\nPlease clarify notation.\n", encoding="utf-8")

        payload = _raw_json(
            [
                "--raw",
                "--cwd",
                str(workspace),
                "validate",
                "command-context",
                "respond-to-referees",
                report.relative_to(workspace).as_posix(),
            ],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        resolved_subject = payload["resolved_subject"]
        assert payload["passed"] is False
        assert checks["manuscript"]["passed"] is False
        assert checks["manuscript"]["detail"].startswith("respond-to-referees outside a project requires")
        assert resolved_subject["status"] == "missing"
        assert resolved_subject["explicit_input"] is False

    def test_command_context_respond_to_referees_accepts_valid_external_manuscript_and_report(
        self,
        tmp_path: Path,
    ) -> None:
        workspace = tmp_path.parent / f"{tmp_path.name}-standalone-respond"
        workspace.mkdir()
        manuscript = workspace / "submission" / _CANONICAL_MANUSCRIPT_BASENAME
        manuscript.parent.mkdir()
        manuscript.write_text(
            "\\documentclass{article}\n\\begin{document}\nExternal response target.\n\\end{document}\n",
            encoding="utf-8",
        )
        first_report = workspace / "reports" / "referee-1.md"
        second_report = workspace / "reports" / "referee-2.md"
        first_report.parent.mkdir()
        first_report.write_text("# Referee 1\n\nClarify the proof.\n", encoding="utf-8")
        second_report.write_text("# Referee 2\n\nCompare with prior work.\n", encoding="utf-8")
        explicit_intake = (
            f"--manuscript submission/{_CANONICAL_MANUSCRIPT_BASENAME} "
            "--report reports/referee-1.md --report reports/referee-2.md"
        )

        payload = _raw_json(
            ["--raw", "--cwd", str(workspace), "validate", "command-context", "respond-to-referees", explicit_intake],
        )
        checks = checks_by_name(payload)
        assert payload["command"] == "gpd:respond-to-referees"
        assert payload["passed"] is True
        assert payload["explicit_inputs"] == ["manuscript path", "path to referee report", "`paste`"]
        assert checks["manuscript"]["passed"] is True
        assert checks["explicit_inputs"]["passed"] is True
        assert checks["explicit_inputs"]["detail"] == "explicit standalone inputs detected"
        assert payload["resolved_subject"]["ownership_mode"] == "external_artifact"
        assert payload["resolved_subject"]["explicit_input"] is True
        assert payload["resolved_subject"]["target_path"].endswith(f"submission/{_CANONICAL_MANUSCRIPT_BASENAME}")

    def test_review_preflight_peer_review_accepts_external_txt_artifact(self, tmp_path: Path) -> None:
        workspace = tmp_path / "standalone-review"
        workspace.mkdir()
        artifact = workspace / "notes.txt"
        artifact.write_text("Standalone manuscript notes.\n", encoding="utf-8")

        payload = _raw_json(
            ["--raw", "--cwd", str(workspace), "validate", "review-preflight", "peer-review", "notes.txt", "--strict"],
        )
        checks = checks_by_name(payload)
        resolved_subject = payload["resolved_subject"]
        assert payload["passed"] is True
        assert "project_state" not in checks
        assert checks["manuscript"]["passed"] is True
        assert checks["manuscript"]["detail"] == "./notes.txt present"
        assert resolved_subject["status"] == "resolved"
        assert resolved_subject["ownership_mode"] == "external_artifact"
        assert resolved_subject["explicit_input"] is True
        assert resolved_subject["target_path"].endswith("notes.txt")

    def test_review_preflight_write_paper_accepts_external_authoring_intake_outside_project(
        self,
        tmp_path: Path,
    ) -> None:
        workspace = tmp_path.parent / f"{tmp_path.name}-standalone-write-paper-preflight"
        workspace.mkdir()
        intake_path = _write_write_paper_authoring_input(workspace)

        payload = _raw_json(
            [
                "--raw",
                "--cwd",
                str(workspace),
                "validate",
                "review-preflight",
                "write-paper",
                f"--intake {intake_path.name}",
                "--strict",
            ],
        )
        checks = checks_by_name(payload)
        resolved_subject = payload["resolved_subject"]
        assert payload["command"] == "gpd:write-paper"
        assert payload["passed"] is True
        assert payload["required_outputs"] == [
            "${PAPER_DIR}/{topic_specific_stem}.tex",
            "${PAPER_DIR}/PAPER-CONFIG.json",
            "${PAPER_DIR}/ARTIFACT-MANIFEST.json",
            "${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json",
            "${PAPER_DIR}/reproducibility-manifest.json",
        ]
        assert payload["required_evidence"] == [
            "validated external authoring intake manifest with explicit claim-to-evidence bindings"
        ]
        assert payload["blocking_conditions"] == ["invalid or incomplete external authoring intake manifest"]
        assert checks["command_context"]["passed"] is True
        assert checks["project_state"]["passed"] is True
        assert checks["project_state"]["blocking"] is False
        assert "intake manifest is authoritative" in checks["project_state"]["detail"]
        assert checks["roadmap"]["passed"] is True
        assert checks["roadmap"]["blocking"] is False
        assert checks["conventions"]["passed"] is True
        assert checks["conventions"]["blocking"] is False
        assert checks["research_artifacts"]["passed"] is True
        assert checks["research_artifacts"]["blocking"] is False
        assert checks["verification_reports"]["passed"] is True
        assert checks["verification_reports"]["blocking"] is False
        assert checks["manuscript"]["passed"] is True
        assert "validated external authoring intake" in checks["manuscript"]["detail"]
        assert "artifact_manifest" not in checks
        assert "bibliography_audit" not in checks
        assert "reproducibility_manifest" not in checks
        assert "manuscript_proof_review" not in checks
        assert resolved_subject["status"] == "bootstrap"
        assert resolved_subject["ownership_mode"] == "external_authoring_intake"
        assert payload["publication_subject_slug"] == "external-authoring-test"
        assert payload["publication_lane_kind"] == "managed_publication_manuscript"
        assert payload["managed_publication_root"] == "GPD/publication/external-authoring-test"
        assert payload["selected_publication_root"] == "GPD/publication/external-authoring-test"
        assert payload["selected_review_root"] == "GPD/publication/external-authoring-test/review"
        assert payload["manuscript_root"] == "GPD/publication/external-authoring-test/manuscript"
        assert payload["manuscript_entrypoint"] is None
        assert checks["project_state"]["detail"] == (
            "external authoring intake: project state is optional because the intake manifest is authoritative"
        )
        assert checks["roadmap"]["detail"] == (
            "external authoring intake: roadmap is optional because the intake manifest supplies the draft scope"
        )
        assert checks["conventions"]["detail"] == (
            "external authoring intake: project conventions are optional before the manuscript exists"
        )
        assert checks["research_artifacts"]["detail"] == (
            "external authoring intake: milestone digests and phase summaries are optional because claims and evidence "
            "come from the intake manifest"
        )
        assert checks["verification_reports"]["detail"] == (
            "external authoring intake: project verification reports are optional because claim-to-evidence bindings "
            "come from the intake manifest"
        )

    def test_init_write_paper_stage_external_intake_matches_command_context_and_review_preflight_roots(
        self,
        tmp_path: Path,
    ) -> None:
        workspace = tmp_path.parent / f"{tmp_path.name}-standalone-write-paper-root-parity"
        workspace.mkdir()
        intake_path = _write_write_paper_authoring_input(workspace)
        intake_arg = f"--intake {intake_path.name}"

        command_context_result = runner.invoke(
            app,
            [
                "--raw",
                "--cwd",
                str(workspace),
                "validate",
                "command-context",
                "write-paper",
                intake_arg,
            ],
            catch_exceptions=False,
        )
        review_preflight_result = runner.invoke(
            app,
            [
                "--raw",
                "--cwd",
                str(workspace),
                "validate",
                "review-preflight",
                "write-paper",
                intake_arg,
                "--strict",
            ],
            catch_exceptions=False,
        )
        staged_init_result = runner.invoke(
            app,
            [
                "--raw",
                "--cwd",
                str(workspace),
                "init",
                "write-paper",
                "--stage",
                "paper_bootstrap",
                "--",
                "--intake",
                intake_path.name,
            ],
            catch_exceptions=False,
        )

        command_context = json_output_from_result(command_context_result)
        review_preflight = json_output_from_result(review_preflight_result)
        staged_init = json_output_from_result(staged_init_result)
        managed_root = "GPD/publication/external-authoring-test"

        assert command_context["selected_publication_root"] == managed_root
        assert command_context["selected_review_root"] == f"{managed_root}/review"
        assert command_context["resolved_subject"]["target_root"].endswith(f"{managed_root}/manuscript")
        assert review_preflight["publication_subject_slug"] == "external-authoring-test"
        assert review_preflight["managed_publication_root"] == managed_root
        assert review_preflight["selected_publication_root"] == command_context["selected_publication_root"]
        assert review_preflight["selected_review_root"] == command_context["selected_review_root"]
        assert review_preflight["manuscript_root"] == f"{managed_root}/manuscript"
        assert review_preflight["manuscript_entrypoint"] is None
        assert staged_init["publication_subject_slug"] == review_preflight["publication_subject_slug"]
        assert staged_init["managed_publication_root"] == review_preflight["managed_publication_root"]
        assert staged_init["managed_manuscript_root"] == review_preflight["manuscript_root"]
        assert staged_init["selected_publication_root"] == review_preflight["selected_publication_root"]
        assert staged_init["selected_review_root"] == review_preflight["selected_review_root"]
        assert staged_init["publication_intake_root"] == f"{managed_root}/intake"
        assert staged_init["publication_bootstrap_root"] == f"{managed_root}/manuscript"

    def test_init_peer_review_stage_projectless_manuscript_matches_strict_preflight_roots(
        self,
        tmp_path: Path,
    ) -> None:
        workspace = tmp_path / "standalone-review-root-parity"
        manuscript_dir = workspace / "manuscript"
        manuscript_dir.mkdir(parents=True)
        (manuscript_dir / "standalone.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\nStandalone draft.\n\\end{document}\n",
            encoding="utf-8",
        )
        target = "manuscript/standalone.tex"

        command_context_result = runner.invoke(
            app,
            ["--raw", "--cwd", str(workspace), "validate", "command-context", "peer-review", target],
            catch_exceptions=False,
        )
        review_preflight_result = runner.invoke(
            app,
            ["--raw", "--cwd", str(workspace), "validate", "review-preflight", "peer-review", target, "--strict"],
            catch_exceptions=False,
        )
        staged_bootstrap_result = runner.invoke(
            app,
            ["--raw", "--cwd", str(workspace), "init", "peer-review", target, "--stage", "bootstrap"],
            catch_exceptions=False,
        )
        staged_preflight_result = runner.invoke(
            app,
            ["--raw", "--cwd", str(workspace), "init", "peer-review", target, "--stage", "preflight"],
            catch_exceptions=False,
        )

        command_context = json_output_from_result(command_context_result)
        review_preflight = json_output_from_result(review_preflight_result)
        staged_bootstrap = json_output_from_result(staged_bootstrap_result)
        staged_preflight = json_output_from_result(staged_preflight_result)
        managed_root = review_preflight["managed_publication_root"]

        assert review_preflight["publication_lane_kind"] == "external_artifact"
        assert managed_root == f"GPD/publication/{review_preflight['publication_subject_slug']}"
        assert review_preflight["selected_publication_root"] == managed_root
        assert review_preflight["selected_review_root"] == f"{managed_root}/review"
        assert command_context["selected_publication_root"] == review_preflight["selected_publication_root"]
        assert command_context["selected_review_root"] == review_preflight["selected_review_root"]
        for staged_init in (staged_bootstrap, staged_preflight):
            assert staged_init["review_target_mode"] == "standalone explicit-artifact review"
            assert staged_init["publication_lane_kind"] == review_preflight["publication_lane_kind"]
            assert staged_init["managed_publication_root"] == managed_root
            assert staged_init["selected_publication_root"] == review_preflight["selected_publication_root"]
            assert staged_init["selected_review_root"] == review_preflight["selected_review_root"]

    @pytest.mark.parametrize(
        ("artifact_name", "content"),
        [
            ("draft.tex", "\\documentclass{article}\n\\begin{document}\nStandalone draft.\n\\end{document}\n"),
            ("draft.md", "# Standalone draft\n"),
        ],
    )
    def test_review_preflight_peer_review_accepts_external_tex_and_markdown_artifacts(
        self,
        tmp_path: Path,
        artifact_name: str,
        content: str,
    ) -> None:
        workspace = tmp_path / "standalone-review"
        workspace.mkdir()
        (workspace / artifact_name).write_text(content, encoding="utf-8")

        payload = _raw_json(
            [
                "--raw",
                "--cwd",
                str(workspace),
                "validate",
                "review-preflight",
                "peer-review",
                artifact_name,
                "--strict",
            ],
        )
        checks = checks_by_name(payload)
        assert payload["passed"] is True
        assert "project_state" not in checks
        assert checks["manuscript"]["passed"] is True
        assert checks["manuscript"]["detail"] == f"./{artifact_name} present"

    @pytest.mark.parametrize(
        ("suffix", "writer", "expected_detail"),
        [
            (
                ".docx",
                _write_minimal_docx,
                "DOCX review target can be converted using built-in OOXML text extraction",
            ),
            (
                ".csv",
                lambda path: path.write_text("claim,evidence\nmain,table\n", encoding="utf-8"),
                "CSV review target can be read directly as delimited text",
            ),
            (
                ".tsv",
                lambda path: path.write_text("claim\tevidence\nmain\ttable\n", encoding="utf-8"),
                "TSV review target can be read directly as delimited text",
            ),
            (
                ".xlsx",
                _write_minimal_xlsx,
                "XLSX review target can be converted using built-in OOXML spreadsheet extraction",
            ),
            (
                ".xlsm",
                _write_minimal_xlsx,
                "XLSX review target can be converted using built-in OOXML spreadsheet extraction",
            ),
        ],
    )
    def test_review_preflight_peer_review_accepts_expanded_external_artifacts(
        self,
        tmp_path: Path,
        suffix: str,
        writer,
        expected_detail: str,
    ) -> None:
        workspace = tmp_path / "standalone-review"
        workspace.mkdir()
        artifact = workspace / f"standalone{suffix}"
        maybe_path = writer(artifact)
        if isinstance(maybe_path, Path):
            artifact = maybe_path

        payload = _raw_json(
            [
                "--raw",
                "--cwd",
                str(workspace),
                "validate",
                "review-preflight",
                "peer-review",
                artifact.name,
                "--strict",
            ],
        )
        checks = checks_by_name(payload)
        assert payload["passed"] is True
        assert "project_state" not in checks
        assert checks["manuscript"]["passed"] is True
        assert checks["manuscript"]["detail"] == f"./{artifact.name} present; {expected_detail}"

    def test_review_preflight_peer_review_accepts_external_manuscript_directory_with_manifest(
        self, tmp_path: Path
    ) -> None:
        workspace = tmp_path / "standalone-review"
        manuscript_root = workspace / "submission"
        manuscript_root.mkdir(parents=True)
        manuscript = manuscript_root / _CANONICAL_MANUSCRIPT_BASENAME
        manuscript.write_text(
            "\\documentclass{article}\n\\begin{document}\nStandalone directory manuscript.\n\\end{document}\n",
            encoding="utf-8",
        )
        (manuscript_root / "ARTIFACT-MANIFEST.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "paper_title": "Standalone directory review",
                    "journal": "jhep",
                    "created_at": "2026-03-10T00:00:00+00:00",
                    "manuscript_sha256": compute_sha256(manuscript),
                    "manuscript_mtime_ns": manuscript.stat().st_mtime_ns,
                    "artifacts": [
                        {
                            "artifact_id": "manuscript",
                            "category": "tex",
                            "path": _CANONICAL_MANUSCRIPT_BASENAME,
                            "sha256": compute_sha256(manuscript),
                            "produced_by": "tests.test_cli_commands",
                            "sources": [],
                            "metadata": {"role": "manuscript"},
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        payload = _raw_json(
            ["--raw", "--cwd", str(workspace), "validate", "review-preflight", "peer-review", "submission", "--strict"],
        )
        checks = checks_by_name(payload)
        assert payload["passed"] is True
        assert checks["manuscript"]["passed"] is True
        assert (
            checks["manuscript"]["detail"] == f"./submission resolved to ./submission/{_CANONICAL_MANUSCRIPT_BASENAME}"
        )
        if "artifact_manifest" in checks:
            assert checks["artifact_manifest"]["detail"] == "./submission/ARTIFACT-MANIFEST.json present"
        for optional_check in (
            "project_state",
            "roadmap",
            "conventions",
            "research_artifacts",
            "verification_reports",
            "bibliography_audit",
            "reproducibility_manifest",
            "manuscript_proof_review",
        ):
            if optional_check in checks:
                assert checks[optional_check]["blocking"] is False

    def test_review_preflight_peer_review_rejects_external_manifest_with_failed_build(self, tmp_path: Path) -> None:
        workspace = tmp_path / "standalone-review"
        manuscript_root = workspace / "submission"
        manuscript_root.mkdir(parents=True)
        manuscript = manuscript_root / _CANONICAL_MANUSCRIPT_BASENAME
        manuscript.write_text(
            "\\documentclass{article}\n\\begin{document}\nStandalone directory manuscript.\n\\end{document}\n",
            encoding="utf-8",
        )
        manuscript_sha256 = compute_sha256(manuscript)
        (manuscript_root / "ARTIFACT-MANIFEST.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "paper_title": "Standalone directory review",
                    "journal": "jhep",
                    "created_at": "2026-03-10T00:00:00+00:00",
                    "manuscript_sha256": manuscript_sha256,
                    "manuscript_mtime_ns": manuscript.stat().st_mtime_ns,
                    "artifacts": [
                        {
                            "artifact_id": "manuscript",
                            "category": "tex",
                            "path": _CANONICAL_MANUSCRIPT_BASENAME,
                            "sha256": manuscript_sha256,
                            "produced_by": "tests.test_cli_commands",
                            "sources": [],
                            "metadata": {"role": "manuscript"},
                        },
                        {
                            "artifact_id": "build-failure-compile",
                            "category": "audit",
                            "path": "build-failure-compile.log",
                            "sha256": manuscript_sha256,
                            "produced_by": "build_paper:compile",
                            "sources": [],
                            "metadata": {
                                "build_success": False,
                                "failure_stage": "compile",
                                "errors": "pdflatex exited with code 1",
                            },
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

        payload = _raw_json(
            ["--raw", "--cwd", str(workspace), "validate", "review-preflight", "peer-review", "submission", "--strict"],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert payload["passed"] is False
        assert checks["artifact_manifest"]["passed"] is False
        assert checks["artifact_manifest"]["blocking"] is True
        assert "artifact manifest records failed paper build at compile stage" in checks["artifact_manifest"]["detail"]

    def test_review_preflight_peer_review_accepts_external_pdf_artifact_with_companion_text(
        self, tmp_path: Path
    ) -> None:
        workspace = tmp_path / "standalone-review"
        workspace.mkdir()
        artifact = workspace / "draft.pdf"
        _write_binary_pdf(artifact)
        (workspace / "draft.txt").write_text("Extracted PDF text.\n", encoding="utf-8")

        payload = _raw_json(
            ["--raw", "--cwd", str(workspace), "validate", "review-preflight", "peer-review", "draft.pdf", "--strict"],
        )
        checks = checks_by_name(payload)
        assert payload["passed"] is True
        assert checks["manuscript"]["passed"] is True
        assert (
            checks["manuscript"]["detail"] == "./draft.pdf present; PDF intake can use companion text file ./draft.txt"
        )

    def test_review_preflight_peer_review_rejects_external_pdf_without_text_support(self, tmp_path: Path) -> None:
        workspace = tmp_path / "standalone-review"
        workspace.mkdir()
        artifact = workspace / "draft.pdf"
        _write_binary_pdf(artifact)

        # Simulate pypdf being unavailable (no PDF extraction support at all).
        import importlib.abc as _abc
        import sys as _sys

        _original_pypdf = _sys.modules.pop("pypdf", None)

        class _BlockPypdf(_abc.MetaPathFinder):
            def find_spec(self, fullname: str, path, target=None):
                if fullname == "pypdf" or fullname.startswith("pypdf."):
                    raise ImportError("pypdf is disabled for this test")
                return None

        blocker = _BlockPypdf()
        _sys.meta_path.insert(0, blocker)
        try:
            result = runner.invoke(
                app,
                [
                    "--raw",
                    "--cwd",
                    str(workspace),
                    "validate",
                    "review-preflight",
                    "peer-review",
                    "draft.pdf",
                    "--strict",
                ],
                catch_exceptions=False,
            )
        finally:
            _sys.meta_path.remove(blocker)
            if _original_pypdf is not None:
                _sys.modules["pypdf"] = _original_pypdf

        payload = json_output_from_result(result, expect_exit=1)
        checks = checks_by_name(payload)
        assert payload["passed"] is False
        assert checks["manuscript"]["passed"] is False
        detail = checks["manuscript"]["detail"]
        assert "pypdf" in detail.lower() or "companion" in detail

    def test_review_preflight_peer_review_rejects_external_pdf_when_pypdf_extraction_fails(
        self,
        tmp_path: Path,
    ) -> None:
        workspace = tmp_path / "standalone-review"
        workspace.mkdir()
        artifact = workspace / "draft.pdf"
        _write_binary_pdf(artifact)

        _fake_mod, install, uninstall = _fake_pypdf_failure_module("malformed trailer")
        install()
        try:
            result = runner.invoke(
                app,
                [
                    "--raw",
                    "--cwd",
                    str(workspace),
                    "validate",
                    "review-preflight",
                    "peer-review",
                    "draft.pdf",
                    "--strict",
                ],
                catch_exceptions=False,
            )
        finally:
            uninstall()

        payload = json_output_from_result(result, expect_exit=1)
        checks = checks_by_name(payload)
        assert payload["passed"] is False
        assert checks["manuscript"]["passed"] is False
        assert "malformed trailer" in checks["manuscript"]["detail"]

    def test_review_preflight_peer_review_strict_materializes_generated_pdf_surface_with_validate_artifact_text(
        self,
        tmp_path: Path,
    ) -> None:
        workspace = tmp_path / "standalone-review"
        workspace.mkdir()
        artifact = workspace / "draft.pdf"
        _write_binary_pdf(artifact)
        output_path = workspace / "artifact-text.txt"
        extracted_text = (
            "Theorem. Every admissible orbit reaches the annulus.\n"
            "Proof. The extracted text keeps the theorem body intact.\n"
        )

        _fake_mod, install, uninstall = _fake_pypdf_module(extracted_text)
        install()
        try:
            preflight = runner.invoke(
                app,
                [
                    "--raw",
                    "--cwd",
                    str(workspace),
                    "validate",
                    "review-preflight",
                    "peer-review",
                    "draft.pdf",
                    "--strict",
                ],
                catch_exceptions=False,
            )
            materialized = runner.invoke(
                app,
                [
                    "--raw",
                    "--cwd",
                    str(workspace),
                    "validate",
                    "artifact-text",
                    artifact.name,
                    "--output",
                    output_path.name,
                ],
                catch_exceptions=False,
            )
        finally:
            uninstall()

        assert preflight.exit_code == 0, preflight.output
        assert materialized.exit_code == 0, materialized.output

        preflight_payload = json_output_from_result(preflight)
        materialized_payload = json_output_from_result(materialized)
        checks = checks_by_name(preflight_payload)

        assert preflight_payload["passed"] is True
        assert checks["manuscript"]["passed"] is True
        assert checks["manuscript"]["detail"] == f"./draft.pdf present; {materialized_payload['detail']}"
        assert "pypdf" in materialized_payload["detail"]
        assert materialized_payload["surface_kind"] == "generated"
        assert materialized_payload["text_length"] == len(extracted_text)
        assert output_path.read_text(encoding="utf-8").strip() == extracted_text.strip()

    def test_validate_artifact_text_uses_companion_text_for_binary_pdf(self, tmp_path: Path) -> None:
        workspace = tmp_path / "standalone-review"
        workspace.mkdir()
        artifact = _write_binary_pdf(workspace / "draft.pdf")
        companion_text = (
            "Theorem. For every r_0 > 0, the orbit intersects the target annulus.\n"
            "Proof. Carry r_0 through the argument.\n"
        )
        artifact.with_suffix(".txt").write_text(companion_text, encoding="utf-8")
        output_path = workspace / "artifact-text.txt"

        result = runner.invoke(
            app,
            [
                "--cwd",
                str(workspace),
                "validate",
                "artifact-text",
                artifact.name,
                "--output",
                output_path.name,
            ],
            catch_exceptions=False,
        )

        assert result.exit_code == 0, result.output
        assert output_path.read_text(encoding="utf-8").strip() == companion_text.strip()

    def test_validate_artifact_text_uses_pypdf_for_binary_pdf(self, tmp_path: Path) -> None:
        workspace = tmp_path / "standalone-review"
        workspace.mkdir()
        artifact = _write_binary_pdf(workspace / "draft.pdf")
        output_path = workspace / "artifact-text.txt"
        extracted_text = (
            "Theorem. Every admissible orbit reaches the annulus.\n"
            "Proof. The extracted text keeps the theorem body intact.\n"
        )

        _fake_mod, install, uninstall = _fake_pypdf_module(extracted_text)
        install()
        try:
            result = runner.invoke(
                app,
                [
                    "--cwd",
                    str(workspace),
                    "validate",
                    "artifact-text",
                    artifact.name,
                    "--output",
                    output_path.name,
                ],
                catch_exceptions=False,
            )
        finally:
            uninstall()

        assert result.exit_code == 0, result.output
        assert output_path.read_text(encoding="utf-8").strip() == extracted_text.strip()

    def test_validate_artifact_text_reports_clean_pdf_support_error_for_binary_pdf(self, tmp_path: Path) -> None:
        workspace = tmp_path / "standalone-review"
        workspace.mkdir()
        artifact = _write_binary_pdf(workspace / "draft.pdf")

        import sys as _sys

        # Simulate pypdf being unavailable by removing it from sys.modules and
        # blocking its import via a finder.
        _original_pypdf = _sys.modules.pop("pypdf", None)
        try:
            import importlib.abc
            import importlib.util

            class _BlockPypdf(importlib.abc.MetaPathFinder):
                def find_spec(self, fullname: str, path, target=None):
                    if fullname == "pypdf" or fullname.startswith("pypdf."):
                        raise ImportError("pypdf is disabled for this test")
                    return None

            blocker = _BlockPypdf()
            _sys.meta_path.insert(0, blocker)
            try:
                result = runner.invoke(
                    app,
                    [
                        "--raw",
                        "--cwd",
                        str(workspace),
                        "validate",
                        "artifact-text",
                        artifact.name,
                    ],
                    catch_exceptions=False,
                )
            finally:
                _sys.meta_path.remove(blocker)
        finally:
            if _original_pypdf is not None:
                _sys.modules["pypdf"] = _original_pypdf

        payload = json_output_from_result(result, expect_exit=1)
        assert "pypdf" in payload["error"]
        assert "companion" in payload["error"] or "get-physics-done[paper]" in payload["error"]
        assert "get-physics-done[arxiv]" not in payload["error"]

    def test_review_preflight_arxiv_submission_strict_does_not_fall_back_to_internal_gpd_paper_artifacts(
        self,
        gpd_project: Path,
    ) -> None:
        manuscript = _write_managed_publication_manuscript(gpd_project)
        managed_dir = manuscript.parent
        (managed_dir / "ARTIFACT-MANIFEST.json").unlink()
        (managed_dir / "BIBLIOGRAPHY-AUDIT.json").unlink()
        (managed_dir / "reproducibility-manifest.json").unlink()
        _write_internal_publication_artifacts(
            gpd_project,
            ("PAPER-CONFIG.json", "ARTIFACT-MANIFEST.json", "BIBLIOGRAPHY-AUDIT.json"),
        )

        payload = _raw_json(
            [
                "--raw",
                "validate",
                "review-preflight",
                "arxiv-submission",
                "GPD/publication/curvature-flow/manuscript/managed_manuscript.tex",
                "--strict",
            ],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert checks["manuscript"]["passed"] is True
        assert checks["manuscript"]["detail"] == f"{cli_module._format_display_path(manuscript)} present"
        assert checks["artifact_manifest"]["detail"].startswith("no ARTIFACT-MANIFEST.json found near the manuscript")
        assert checks["artifact_manifest"]["blocking"] is True
        assert checks["bibliography_audit"]["detail"].startswith("no BIBLIOGRAPHY-AUDIT.json found near the manuscript")
        assert checks["bibliography_audit"]["blocking"] is True
        assert checks["reproducibility_manifest"]["blocking"] is True
        assert checks["review_ledger"]["passed"] is False
        assert checks["referee_decision"]["passed"] is False

    def test_review_preflight_arxiv_submission_rejects_explicit_markdown_manuscript_file(
        self,
        gpd_project: Path,
    ) -> None:
        manuscript_dir = gpd_project / "GPD" / "publication" / "curvature-flow" / "manuscript"
        manuscript_dir.mkdir(parents=True, exist_ok=True)
        (manuscript_dir / _CANONICAL_MARKDOWN_BASENAME).write_text("# Markdown manuscript\n", encoding="utf-8")

        payload = _raw_json(
            [
                "--raw",
                "validate",
                "review-preflight",
                "arxiv-submission",
                f"GPD/publication/curvature-flow/manuscript/{_CANONICAL_MARKDOWN_BASENAME}",
                "--strict",
            ],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert checks["manuscript"]["passed"] is False
        assert (
            checks["manuscript"]["detail"]
            == f"explicit manuscript target must be a .tex file: ./GPD/publication/curvature-flow/manuscript/{_CANONICAL_MARKDOWN_BASENAME}"
        )

    def test_review_preflight_arxiv_submission_rejects_directory_with_markdown_entrypoint(
        self,
        gpd_project: Path,
    ) -> None:
        manuscript_dir = gpd_project / "GPD" / "publication" / "curvature-flow" / "manuscript"
        manuscript_dir.mkdir(parents=True, exist_ok=True)
        (manuscript_dir / _CANONICAL_MARKDOWN_BASENAME).write_text("# Markdown manuscript\n", encoding="utf-8")

        payload = _raw_json(
            [
                "--raw",
                "validate",
                "review-preflight",
                "arxiv-submission",
                "GPD/publication/curvature-flow/manuscript",
                "--strict",
            ],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert checks["manuscript"]["passed"] is False
        assert checks["manuscript"]["detail"] == (
            "no manuscript entry point found under ./GPD/publication/curvature-flow/manuscript"
        )

    def test_review_preflight_arxiv_submission_rejects_explicit_directory_without_main_entrypoint(
        self,
        gpd_project: Path,
    ) -> None:
        manuscript_dir = gpd_project / "GPD" / "publication" / "curvature-flow" / "manuscript"
        manuscript_dir.mkdir(parents=True, exist_ok=True)
        (manuscript_dir / "alt.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\nSubmission manuscript.\n\\end{document}\n",
            encoding="utf-8",
        )
        (manuscript_dir / "alt.pdf").write_bytes(b"%PDF-1.4\n% fake arxiv submission pdf\n")

        payload = _raw_json(
            [
                "--raw",
                "validate",
                "review-preflight",
                "arxiv-submission",
                "GPD/publication/curvature-flow/manuscript",
                "--strict",
            ],
            expect_exit=1,
        )
        checks = checks_by_name(payload)
        assert checks["manuscript"]["passed"] is False
        assert checks["manuscript"]["detail"] == (
            "no manuscript entry point found under ./GPD/publication/curvature-flow/manuscript"
        )

    def test_review_preflight_arxiv_submission_default_markdown_only_project_fails_manuscript_check(
        self,
        gpd_project: Path,
    ) -> None:
        paper_dir = gpd_project / "paper"
        (paper_dir / _CANONICAL_MANUSCRIPT_BASENAME).unlink()
        (paper_dir / _CANONICAL_MARKDOWN_BASENAME).write_text("# Markdown manuscript\n", encoding="utf-8")

        payload = _raw_json(["--raw", "validate", "review-preflight", "arxiv-submission", "--strict"], expect_exit=1)
        checks = checks_by_name(payload)
        assert checks["manuscript"]["passed"] is False
        assert (
            "no LaTeX manuscript entrypoint found under paper/, manuscript/, or draft/"
            in checks["manuscript"]["detail"]
        )

    def test_validate_plan_contract_command_accepts_valid_plan(self, gpd_project: Path) -> None:
        phase_dir = gpd_project / "GPD" / "phases" / "01-benchmark"
        phase_dir.mkdir(parents=True, exist_ok=True)
        plan_path = phase_dir / "01-01-PLAN.md"
        plan_path.write_text(
            (FIXTURES_DIR / "plan_with_contract.md").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        payload = _raw_json(
            ["--raw", "validate", "plan-contract", str(plan_path)],
        )
        assert payload["valid"] is True

    def test_validate_plan_contract_command_rejects_ambiguous_contract_target_ids(self, gpd_project: Path) -> None:
        phase_dir = gpd_project / "GPD" / "phases" / "01-benchmark"
        phase_dir.mkdir(parents=True, exist_ok=True)
        plan_path = phase_dir / "01-01-PLAN.md"
        plan_path.write_text(
            (FIXTURES_DIR / "plan_with_contract.md")
            .read_text(encoding="utf-8")
            .replace("deliverables: [deliv-figure]", "deliverables: [claim-benchmark]", 1)
            .replace("    - id: deliv-figure", "    - id: claim-benchmark", 1)
            .replace(
                "      evidence_required: [deliv-figure, ref-benchmark]",
                "      evidence_required: [claim-benchmark, ref-benchmark]",
                1,
            ),
            encoding="utf-8",
        )

        payload = _raw_json(
            ["--raw", "validate", "plan-contract", str(plan_path)],
            expect_exit=1,
        )
        assert payload["valid"] is False
        assert any(
            "contract: contract id claim-benchmark is reused across claim, deliverable; "
            "target resolution is ambiguous" in error
            for error in payload["errors"]
        )

    @pytest.mark.parametrize(("command_args"), [("integrations", "status", "wolfram")])
    def test_integrations_surface_smoke(self, command_args: tuple[str, ...]) -> None:
        _invoke(*command_args)

    @pytest.mark.parametrize("server_name", ["wolfram", "gpd-wolfram"])
    def test_mcp_serve_dispatches_managed_integration_aliases_from_registry(
        self,
        monkeypatch: pytest.MonkeyPatch,
        server_name: str,
    ) -> None:
        import importlib.metadata as importlib_metadata

        called: list[str] = []
        fake_module = SimpleNamespace(main=lambda: called.append("main"))
        original_import_module = importlib.import_module

        def _unexpected_entry_points(*_args, **_kwargs):
            raise AssertionError("managed mcp-serve dispatch must not inspect console-script metadata")

        def _fake_import_module(module_name: str, package: str | None = None):
            if module_name == "gpd.mcp.integrations.wolfram_bridge":
                called.append(module_name)
                return fake_module
            return original_import_module(module_name, package)

        monkeypatch.setattr(importlib_metadata, "entry_points", _unexpected_entry_points)
        monkeypatch.setattr(importlib, "import_module", _fake_import_module)

        result = runner.invoke(app, ["mcp-serve", server_name], catch_exceptions=False)

        assert result.exit_code == 0, result.output
        assert called == ["gpd.mcp.integrations.wolfram_bridge", "main"]

    def test_mcp_serve_requires_managed_integration_bridge_module_from_registry(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from gpd.mcp import managed_integrations

        descriptor = SimpleNamespace(
            integration_id="wolfram",
            managed_server_key="gpd-wolfram",
            bridge_command="gpd-mcp-wolfram",
            bridge_module="",
        )
        monkeypatch.setattr(managed_integrations, "list_managed_integrations", lambda: {"wolfram": descriptor})

        result = runner.invoke(app, ["mcp-serve", "wolfram"])

        assert result.exit_code != 0
        assert "has no descriptor module path" in result.output

    def test_list_servers_json_uses_resolved_install_config_and_managed_integrations(
        self,
        gpd_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from gpd.mcp.managed_integrations import (
            WOLFRAM_BRIDGE_MODULE,
            WOLFRAM_MANAGED_INTEGRATION,
            WOLFRAM_MANAGED_SERVER_KEY,
            WOLFRAM_MCP_API_KEY_ENV_VAR,
            WOLFRAM_MCP_ENDPOINT_ENV_VAR,
        )

        monkeypatch.delenv("LOG_LEVEL", raising=False)
        monkeypatch.setenv(WOLFRAM_MCP_API_KEY_ENV_VAR, "test-secret")
        monkeypatch.setenv(WOLFRAM_MCP_ENDPOINT_ENV_VAR, "https://example.invalid/mcp")
        (gpd_project / "GPD" / "integrations.json").write_text(
            json.dumps({WOLFRAM_MANAGED_INTEGRATION.integration_id: {"enabled": True}}),
            encoding="utf-8",
        )

        payload = _raw_json(
            ["--cwd", str(gpd_project), "list-servers", "--json"],
        )
        serialized = json.dumps(payload)
        assert "${" not in serialized
        assert "test-secret" not in serialized
        assert payload["gpd-conventions"] == {
            "command": sys.executable,
            "args": ["-m", "gpd.mcp.servers.conventions_server"],
            "env": {"LOG_LEVEL": "WARNING"},
        }
        assert payload[WOLFRAM_MANAGED_SERVER_KEY] == {
            "command": sys.executable,
            "args": ["-m", WOLFRAM_BRIDGE_MODULE],
            "env": {WOLFRAM_MCP_ENDPOINT_ENV_VAR: "https://example.invalid/mcp"},
        }

    def test_list_servers_binary_rewrites_managed_integrations_to_sidecar_dispatch(
        self,
        gpd_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from gpd.mcp.managed_integrations import (
            WOLFRAM_MANAGED_INTEGRATION,
            WOLFRAM_MANAGED_SERVER_KEY,
            WOLFRAM_MCP_API_KEY_ENV_VAR,
            WOLFRAM_MCP_ENDPOINT_ENV_VAR,
        )

        monkeypatch.setenv(WOLFRAM_MCP_API_KEY_ENV_VAR, "test-secret")
        monkeypatch.setenv(WOLFRAM_MCP_ENDPOINT_ENV_VAR, "https://example.invalid/mcp")
        (gpd_project / "GPD" / "integrations.json").write_text(
            json.dumps({WOLFRAM_MANAGED_INTEGRATION.integration_id: {"enabled": True}}),
            encoding="utf-8",
        )

        payload = _raw_json(
            ["--cwd", str(gpd_project), "list-servers", "--json", "--binary", "/opt/gpd"],
        )
        assert payload[WOLFRAM_MANAGED_SERVER_KEY] == {
            "command": "/opt/gpd",
            "args": ["mcp-serve", "wolfram"],
            "env": {WOLFRAM_MCP_ENDPOINT_ENV_VAR: "https://example.invalid/mcp"},
        }

    def test_validate_summary_contract_command_rejects_unknown_contract_ids(self, gpd_project: Path) -> None:
        phase_dir = gpd_project / "GPD" / "phases" / "01-benchmark"
        phase_dir.mkdir(parents=True, exist_ok=True)
        (phase_dir / "01-01-PLAN.md").write_text(
            (FIXTURES_DIR / "plan_with_contract.md").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        summary_path = phase_dir / "01-SUMMARY.md"
        summary_path.write_text(
            (FIXTURES_DIR.parent / "stage4" / "summary_with_contract_results.md")
            .read_text(encoding="utf-8")
            .replace("claim-benchmark:", "claim-unknown:", 1),
            encoding="utf-8",
        )

        payload = _raw_json(
            ["--raw", "validate", "summary-contract", str(summary_path)],
            expect_exit=1,
        )
        assert any("Unknown claim contract_results entry: claim-unknown" in error for error in payload["errors"])

    def test_validate_summary_contract_command_reports_unresolved_plan_contract_ref(self, gpd_project: Path) -> None:
        phase_dir = gpd_project / "GPD" / "phases" / "01-benchmark"
        phase_dir.mkdir(parents=True, exist_ok=True)
        summary_path = phase_dir / "01-SUMMARY.md"
        summary_path.write_text(
            (FIXTURES_DIR.parent / "stage4" / "summary_with_contract_results.md").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        payload = _raw_json(
            ["--raw", "validate", "summary-contract", str(summary_path)],
            expect_exit=1,
        )
        assert "plan_contract_ref: could not resolve matching plan contract" in payload["errors"]

    def test_validate_verification_contract_command_requires_contract_results(self, gpd_project: Path) -> None:
        phase_dir = gpd_project / "GPD" / "phases" / "01-benchmark"
        phase_dir.mkdir(parents=True, exist_ok=True)
        (phase_dir / "01-01-PLAN.md").write_text(
            (FIXTURES_DIR / "plan_with_contract.md").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        verification_path = phase_dir / "01-VERIFICATION.md"
        verification_path.write_text(
            "---\n"
            "phase: 01-benchmark\n"
            "verified: 2026-03-13T00:00:00Z\n"
            "status: passed\n"
            "score: 1/1 contract targets verified\n"
            "plan_contract_ref: GPD/phases/01-benchmark/01-01-PLAN.md#/contract\n"
            "---\n\n"
            "# Verification\n",
            encoding="utf-8",
        )

        payload = _raw_json(
            ["--raw", "validate", "verification-contract", str(verification_path)],
            expect_exit=1,
        )
        assert "contract_results: required for contract-backed plan" in payload["errors"]


def test_cli_import_and_help_lookup_failure_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    import gpd as gpd_package
    import gpd.adapters as adapters_module

    def _raise_runtime_catalog() -> list[str]:
        raise RuntimeError("catalog offline")

    original_cli = sys.modules.get("gpd.cli")
    monkeypatch.setattr(adapters_module, "list_runtimes", _raise_runtime_catalog)
    sys.modules.pop("gpd.cli", None)

    try:
        reloaded = importlib.import_module("gpd.cli")
        assert reloaded._runtime_override_help() == "Runtime name override"
    finally:
        if original_cli is not None:
            sys.modules["gpd.cli"] = original_cli
            gpd_package.cli = original_cli

    def _raise_programmer_error() -> list[str]:
        raise TypeError("catalog bug")

    original_cli = sys.modules.get("gpd.cli")
    monkeypatch.setattr(adapters_module, "list_runtimes", _raise_programmer_error)
    sys.modules.pop("gpd.cli", None)

    try:
        with pytest.raises(TypeError, match="catalog bug"):
            importlib.import_module("gpd.cli")
    finally:
        if original_cli is not None:
            sys.modules["gpd.cli"] = original_cli
            gpd_package.cli = original_cli


def test_install_command_smoke_error_paths_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    gpd_project: Path,
) -> None:
    import gpd.adapters as adapters_module

    def _raise_runtime_catalog() -> list[str]:
        raise RuntimeError("catalog offline")

    monkeypatch.setattr(adapters_module, "list_runtimes", _raise_runtime_catalog)

    result = runner.invoke(
        app,
        ["--raw", "--cwd", str(gpd_project), "install", "--all"],
        catch_exceptions=False,
    )

    payload = json_output_from_result(result, expect_exit=1)
    assert payload["error"] == "Runtime catalog unavailable during install: catalog offline"
    assert_no_traceback(result)

    def assert_raw_install_error(argv: list[str], expected_error: str, setup=None) -> None:
        if setup is not None:
            setup()
        result = runner.invoke(app, ["--raw", "--cwd", str(gpd_project), *argv], catch_exceptions=False)
        payload = json_output_from_result(result, expect_exit=1)
        assert payload["error"] == expected_error
        assert_no_traceback(result)

    assert_raw_install_error(
        ["install"],
        "Raw install requires one or more runtimes or --all",
    )
    assert_raw_install_error(
        ["install", _PRIMARY_RAW_RUNTIME_DESCRIPTOR.runtime_name],
        "Raw install requires --local, --global, or --target-dir",
        setup=lambda: (
            monkeypatch.setattr(
                adapters_module, "list_runtimes", lambda: [_PRIMARY_RAW_RUNTIME_DESCRIPTOR.runtime_name]
            ),
            monkeypatch.setattr(adapters_module, "get_adapter", lambda runtime_name: object()),
        ),
    )
    assert_raw_install_error(
        ["uninstall", "--all", "--global"],
        "Runtime catalog unavailable during uninstall: catalog offline",
        setup=lambda: monkeypatch.setattr(adapters_module, "list_runtimes", _raise_runtime_catalog),
    )


def test_cli_uninstall_and_resolution_paths(monkeypatch: pytest.MonkeyPatch, gpd_project: Path, tmp_path: Path) -> None:
    import gpd.adapters as adapters_module
    import gpd.cli as cli_module
    import gpd.core.config as config_module

    monkeypatch.setattr(adapters_module, "list_runtimes", lambda: [_PRIMARY_RAW_RUNTIME_DESCRIPTOR.runtime_name])
    monkeypatch.setattr(adapters_module, "get_adapter", lambda runtime_name: object())

    result = runner.invoke(
        app,
        ["--raw", "--cwd", str(gpd_project), "uninstall", _PRIMARY_RAW_RUNTIME_DESCRIPTOR.runtime_name],
        catch_exceptions=False,
    )
    payload = json_output_from_result(result, expect_exit=1)
    assert payload["error"] == "Raw uninstall requires --local, --global, or --target-dir"
    assert_no_traceback(result)

    monkeypatch.setattr(
        adapters_module,
        "get_adapter",
        lambda runtime_name: (_ for _ in ()).throw(RuntimeError("adapter offline")),
    )
    result = runner.invoke(
        app,
        [
            "--raw",
            "--cwd",
            str(gpd_project),
            "uninstall",
            _PRIMARY_RAW_RUNTIME_DESCRIPTOR.runtime_name,
            "--target-dir",
            str(gpd_project / _PRIMARY_RAW_RUNTIME_DESCRIPTOR.config_dir_name),
        ],
        catch_exceptions=False,
    )
    payload = json_output_from_result(result, expect_exit=1)
    assert (
        payload["error"]
        == f"Runtime adapter unavailable for '{_PRIMARY_RAW_RUNTIME_DESCRIPTOR.runtime_name}' during uninstall: adapter offline"
    )
    assert_no_traceback(result)

    alias = next(
        value
        for value in _ALIASABLE_RUNTIME_DESCRIPTOR.selection_aliases
        if value != _ALIASABLE_RUNTIME_DESCRIPTOR.runtime_name
    )
    monkeypatch.setattr(cli_module, "_supported_runtime_names", list_runtime_names)
    monkeypatch.setattr(config_module, "validate_agent_name", lambda agent_name: None)
    monkeypatch.setattr(config_module, "resolve_model", lambda cwd, agent_name, runtime=None: runtime)
    result = runner.invoke(app, ["resolve-model", "gpd-executor", "--runtime", alias], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert _ALIASABLE_RUNTIME_DESCRIPTOR.runtime_name in result.output

    cwd = tmp_path / "workspace"
    cwd.mkdir()
    global_dir = tmp_path / "global"
    global_dir.mkdir()
    canonical_target = global_dir / _PRIMARY_RAW_RUNTIME_DESCRIPTOR.config_dir_name
    canonical_target.mkdir()
    tricky_target = global_dir / "nested" / ".." / _PRIMARY_RAW_RUNTIME_DESCRIPTOR.config_dir_name

    class _FakeAdapter:
        def resolve_target_dir(self, is_global: bool, cwd: Path | None = None) -> Path:
            del cwd
            return (
                canonical_target
                if is_global
                else tmp_path / "workspace" / _PRIMARY_RAW_RUNTIME_DESCRIPTOR.config_dir_name
            )

    monkeypatch.setattr(cli_module, "_get_cwd", lambda: cwd)
    monkeypatch.setattr(cli_module, "_get_adapter_or_error", lambda runtime_name, action: _FakeAdapter())
    assert (
        cli_module._target_dir_matches_global(
            _PRIMARY_RAW_RUNTIME_DESCRIPTOR.runtime_name, str(tricky_target), action="install"
        )
        is True
    )


def test_resolve_model_explain_surfaces_runtime_default_reason(
    monkeypatch: pytest.MonkeyPatch,
    gpd_project: Path,
) -> None:
    import gpd.core.config as config_module
    import gpd.core.context as context_module

    monkeypatch.setattr(config_module, "validate_agent_name", lambda agent_name: None)
    monkeypatch.setattr(config_module, "resolve_tier", lambda cwd, agent_name: config_module.ModelTier.TIER_1)
    monkeypatch.setattr(context_module, "_resolve_model", lambda cwd, agent_name: None)
    monkeypatch.setattr(
        context_module, "_detect_platform", lambda cwd=None: _PRIMARY_RAW_RUNTIME_DESCRIPTOR.runtime_name
    )

    result = runner.invoke(
        app,
        ["--raw", "--cwd", str(gpd_project), "resolve-model", "gpd-referee", "--explain"],
        catch_exceptions=False,
    )

    payload = json_output_from_result(result)
    assert payload["agent_name"] == "gpd-referee"
    assert payload["tier"] == "tier-1"
    assert payload["runtime"] == _PRIMARY_RAW_RUNTIME_DESCRIPTOR.runtime_name
    assert payload["runtime_source"] == "detected"
    assert payload["resolved_model"] is None
    assert payload["override_configured"] is False
    assert payload["uses_runtime_default"] is True
    assert "No explicit model override is configured" in payload["detail"]


def test_resolve_model_keeps_blank_stdout_by_default_when_no_override(
    monkeypatch: pytest.MonkeyPatch,
    gpd_project: Path,
) -> None:
    import gpd.cli as cli_module
    import gpd.core.config as config_module
    import gpd.core.context as context_module

    monkeypatch.setattr(cli_module, "_stdout_is_interactive", lambda: False)
    monkeypatch.setattr(config_module, "validate_agent_name", lambda agent_name: None)
    monkeypatch.setattr(context_module, "_resolve_model", lambda cwd, agent_name: None)
    monkeypatch.setattr(
        context_module, "_detect_platform", lambda cwd=None: _PRIMARY_RAW_RUNTIME_DESCRIPTOR.runtime_name
    )

    result = runner.invoke(
        app,
        ["--cwd", str(gpd_project), "resolve-model", "gpd-referee"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    assert result.output == ""


@pytest.mark.parametrize(
    "command_name",
    ["new-project", "verify-work", "plan-phase", "quick", "execute-phase"],
)
def test_init_help_surfaces_stage_option(command_name: str) -> None:
    output = _help_text("init", command_name)
    assert "--stage" in output
    assert f"Load the staged {command_name} context for a specific" in output
    assert "stage id." in output


class TestNoDuplicateTestMethods:
    """Assert no duplicate test method names (duplicates silently hide tests in Python)."""

    def test_no_duplicate_test_method_in_review_validation(self) -> None:
        import ast

        source = Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "TestReviewValidationCommands":
                method_names = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                duplicates = [name for name in method_names if method_names.count(name) > 1]
                assert duplicates == [], f"Duplicate test methods in TestReviewValidationCommands: {set(duplicates)}"
                break
