"""Prompt budget assertions for the `arxiv-submission` startup surface."""

from __future__ import annotations

import json
from pathlib import Path

from gpd.core.workflow_staging import validate_workflow_stage_manifest_payload
from tests.prompt_metrics_support import expanded_prompt_text, measure_prompt_surface

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = REPO_ROOT / "src" / "gpd" / "commands"
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
SOURCE_ROOT = REPO_ROOT / "src" / "gpd"
PATH_PREFIX = "/runtime/"
BOOTSTRAP_AUTHORITY = WORKFLOWS_DIR / "arxiv-submission" / "bootstrap.md"


def _manifest() -> object:
    return validate_workflow_stage_manifest_payload(
        json.loads((WORKFLOWS_DIR / "arxiv-submission-stage-manifest.json").read_text(encoding="utf-8")),
        expected_workflow_id="arxiv-submission",
    )


def _expanded_stage_surface(stage: object, *, selected_conditions: tuple[str, ...] = ()) -> str:
    return "\n\n".join(
        expanded_prompt_text(
            SOURCE_ROOT / "specs" / authority,
            src_root=SOURCE_ROOT,
            path_prefix=PATH_PREFIX,
        )
        for authority in stage.eager_authorities(selected_conditions=selected_conditions)
    )


def test_arxiv_submission_command_stays_thin_and_only_eagerly_loads_bootstrap_authority() -> None:
    command_text = (COMMANDS_DIR / "arxiv-submission.md").read_text(encoding="utf-8")
    metrics = measure_prompt_surface(
        COMMANDS_DIR / "arxiv-submission.md",
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )
    bootstrap = measure_prompt_surface(
        BOOTSTRAP_AUTHORITY,
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )

    assert metrics.raw_include_count == 1
    assert "@{GPD_INSTALL_DIR}/workflows/arxiv-submission/bootstrap.md" in command_text
    assert "@{GPD_INSTALL_DIR}/workflows/arxiv-submission.md" not in command_text
    assert (
        "Keep the wrapper thin and let the workflow own validation, packaging, and submission-gate details."
        in command_text
    )
    assert (
        "Paper target: $ARGUMENTS (optional manuscript root or `.tex` entrypoint; "
        "when omitted, the workflow resolves the active GPD-owned manuscript root)." in command_text
    )
    assert "@{GPD_INSTALL_DIR}/templates/paper/publication-manuscript-root-preflight.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/references/publication/publication-review-round-artifacts.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/references/publication/publication-response-artifacts.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/references/publication/peer-review-reliability.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/references/publication/publication-bootstrap-preflight.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/references/shared/canonical-schema-discipline.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/templates/paper/paper-config-schema.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/templates/paper/artifact-manifest-schema.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/templates/paper/bibliography-audit-schema.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/templates/paper/review-ledger-schema.md" not in command_text
    assert "@{GPD_INSTALL_DIR}/templates/paper/referee-decision-schema.md" not in command_text
    assert metrics.expanded_line_count > bootstrap.expanded_line_count
    assert metrics.expanded_char_count > bootstrap.expanded_char_count
    assert metrics.expanded_line_count < bootstrap.expanded_line_count + 180
    assert metrics.expanded_char_count < bootstrap.expanded_char_count + 9000

    expanded_command = expanded_prompt_text(
        COMMANDS_DIR / "arxiv-submission.md",
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )
    assert '<step name="package">' not in expanded_command
    assert "gpd --raw validate arxiv-package --materialize" not in expanded_command
    assert '<step name="finalize">' not in expanded_command


def test_arxiv_submission_stage_init_fields_keep_review_payloads_on_review_gate() -> None:
    manifest = _manifest()
    review_payload_fields = {
        "latest_review_artifacts",
        "latest_author_response",
        "latest_referee_response",
        "latest_response_artifacts",
    }

    for stage_id in ("bootstrap", "manuscript_preflight", "package", "finalize"):
        assert review_payload_fields.isdisjoint(manifest.stage(stage_id).required_init_fields)

    review_gate_fields = set(manifest.stage("review_gate").required_init_fields)
    assert {
        "latest_review_ledger",
        "latest_referee_decision",
        "latest_review_artifacts",
        "latest_author_response",
        "latest_referee_response",
        "latest_response_artifacts",
        "latest_response_freshness",
        "derived_manuscript_proof_review_status",
    } <= review_gate_fields


def test_arxiv_submission_late_stage_surfaces_avoid_review_authorities() -> None:
    manifest = _manifest()
    review_gate_surface = _expanded_stage_surface(manifest.stage("review_gate"))
    review_gate_recovery_surface = _expanded_stage_surface(
        manifest.stage("review_gate"),
        selected_conditions=("review_integrity_recovery_needed",),
    )
    package_surface = _expanded_stage_surface(manifest.stage("package"))
    finalize_surface = _expanded_stage_surface(manifest.stage("finalize"))

    assert len(review_gate_surface) <= 21_000
    assert "publication-review-round-artifacts.md" in review_gate_surface
    assert "peer-review-reliability.md" in review_gate_surface
    assert "# Peer Review Phase Reliability" not in review_gate_surface
    assert "# Peer Review Phase Reliability" in review_gate_recovery_surface
    assert "publication-review-round-artifacts.md" not in package_surface
    assert "peer-review-reliability.md" not in package_surface
    assert "publication-review-round-artifacts.md" not in finalize_surface
    assert "peer-review-reliability.md" not in finalize_surface
