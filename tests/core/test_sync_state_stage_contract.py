"""Assertions for the staged `sync-state` contract."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from gpd.core.workflow_staging import load_workflow_stage_manifest, validate_workflow_stage_manifest_payload
from tests.assertion_taxonomy_support import assert_prompt_contracts, machine_exact, semantic_anchor
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"


def test_sync_state_stage_manifest_loads_and_preserves_stage_order() -> None:
    manifest = load_workflow_stage_manifest("sync-state")

    assert manifest.workflow_id == "sync-state"
    assert manifest.stage_ids() == (
        "sync_bootstrap",
        "single_source_recovery",
        "conflict_analysis",
        "reconcile_and_validate",
    )

    bootstrap = manifest.get_stage("sync_bootstrap")
    recovery = manifest.get_stage("single_source_recovery")
    conflict = manifest.get_stage("conflict_analysis")
    reconcile = manifest.get_stage("reconcile_and_validate")

    assert bootstrap.loaded_authorities == ("workflows/sync-state/sync-bootstrap.md",)
    assert bootstrap.required_init_fields[0] == "workspace_root"
    assert bootstrap.required_init_fields[-1] == "platform"
    assert "project_reentry_guidance" in bootstrap.required_init_fields
    assert bootstrap.required_init_fields.index("state_json_backup_exists") < bootstrap.required_init_fields.index(
        "state_recovery_guidance"
    )
    assert "templates/state-json-schema.md" in bootstrap.must_not_eager_load

    assert recovery.loaded_authorities == ("workflows/sync-state/single-source-recovery.md",)
    assert recovery.conditional_authorities[0].when == "backend_validation_failed_needs_schema_context"
    assert recovery.conditional_authorities[0].authorities == ("templates/state-json-schema.md",)
    assert "templates/state-json-schema.md" in recovery.must_not_eager_load
    assert "state_recovery_guidance" in recovery.required_init_fields
    assert "state_load_source" in recovery.required_init_fields
    assert "state_integrity_issues" in recovery.required_init_fields
    assert "state_md_content" not in recovery.required_init_fields
    assert "state_json_content" not in recovery.required_init_fields
    assert "state_json_backup_content" not in recovery.required_init_fields
    assert "project_contract_gate" not in recovery.required_init_fields

    assert conflict.loaded_authorities == ("workflows/sync-state/conflict-analysis.md",)
    assert conflict.conditional_authorities[0].when == "manual_schema_drift_analysis"
    assert conflict.conditional_authorities[0].authorities == ("templates/state-json-schema.md",)
    assert "templates/state-json-schema.md" in conflict.must_not_eager_load
    assert "project_contract_validation" in conflict.required_init_fields
    assert "state_md_content" in conflict.required_init_fields
    assert "state_json_content" in conflict.required_init_fields
    assert "state_json_backup_content" in conflict.required_init_fields

    assert reconcile.loaded_authorities == ("workflows/sync-state/reconcile-and-validate.md",)
    assert reconcile.conditional_authorities[0].when == "backend_validation_failed_needs_schema_context"
    assert reconcile.conditional_authorities[0].authorities == ("templates/state-json-schema.md",)
    assert "templates/state-json-schema.md" in reconcile.must_not_eager_load
    assert "state_recovery_guidance" in reconcile.required_init_fields
    assert "state_load_source" in reconcile.required_init_fields
    assert "state_integrity_issues" in reconcile.required_init_fields
    assert "state_md_content" not in reconcile.required_init_fields
    assert "state_json_content" not in reconcile.required_init_fields
    assert "state_json_backup_content" not in reconcile.required_init_fields
    assert "project_contract_validation" not in reconcile.required_init_fields
    assert reconcile.writes_allowed == (
        "GPD/STATE.md",
        "GPD/state.json",
        "GPD/state.json.bak",
    )


def test_sync_state_stage_manifest_rejects_invalid_field_drift() -> None:
    payload = json.loads((WORKFLOWS_DIR / "sync-state-stage-manifest.json").read_text(encoding="utf-8"))
    payload["stages"][0]["required_init_fields"] = ["bogus_field"]

    with pytest.raises(ValueError, match="unknown field name"):
        validate_workflow_stage_manifest_payload(payload, expected_workflow_id="sync-state")


def test_sync_state_workflow_uses_staged_fields_instead_of_manual_state_probing() -> None:
    text = workflow_authority_text(WORKFLOWS_DIR, "sync-state")

    assert "SYNC_BOOTSTRAP_INIT=$(gpd --raw init sync-state --stage sync_bootstrap)" in text
    assert "SINGLE_SOURCE_RECOVERY_INIT=$(gpd --raw init sync-state --stage single_source_recovery)" in text
    assert "CONFLICT_ANALYSIS_INIT=$(gpd --raw init sync-state --stage conflict_analysis)" in text
    assert "RECONCILE_INIT=$(gpd --raw init sync-state --stage reconcile_and_validate)" in text
    assert 'PROJECT_ROOT=$(echo "$SYNC_BOOTSTRAP_INIT" | gpd json get .project_root)' in text
    assert_prompt_contracts(
        text,
        semantic_anchor(
            "sync-state stays current-workspace-only and stops on backup-only recovery",
            (
                "current-workspace-only",
                "must not inspect or repair a recent project",
                "Backup-only state found",
                "state_recovery_guidance",
                "stop",
            ),
        ),
    )
    assert 'cwd = Path(".")' not in text
    assert 'gpd --raw --cwd "$PROJECT_ROOT" state repair-sync' in text
    assert 'gpd --raw --cwd "$PROJECT_ROOT" state validate' in text
    assert "gpd --raw state validate" not in text
    assert "json.loads" not in text
    assert "save_state_markdown" not in text
    assert "save_state_json" not in text
    assert "--prefer" not in text
    assert_prompt_contracts(
        text,
        machine_exact(
            "sync-state mirrored state paths stay exact",
            ("`GPD/STATE.md`", "`GPD/state.json`", "`GPD/state.json.bak`"),
            owner="sync-state staged contract",
            rationale="state routing protects these exact mirrored file paths",
        ),
        semantic_anchor(
            "sync-state routing avoids manual mirrored-file probes",
            ("Do not re-probe", "by hand during routing", "Do not re-read", "by hand for comparison"),
        ),
        semantic_anchor(
            "sync-state raw bodies are limited to conflict analysis",
            ("Raw state bodies", "`conflict_analysis`", "read-only drift reporting"),
        ),
    )
    assert re.search(r"Do not request raw\s+`STATE\.md`, `state\.json`, or `state\.json\.bak` bodies", text)
    assert "backend_validation_failed_needs_schema_context" in text
    assert "manual_schema_drift_analysis" in text
    assert "@{GPD_INSTALL_DIR}/templates/state-json-schema.md" not in text
    assert "MD_EXISTS=$(test -f" not in text
    assert "JSON_EXISTS=$(test -f" not in text
    assert "cat GPD/STATE.md" not in text
    assert "cat GPD/state.json" not in text


def test_sync_state_workflow_has_fail_closed_bad_backup_branch() -> None:
    text = workflow_authority_text(WORKFLOWS_DIR, "sync-state")

    marker = "corrupt_state_bad_backup"
    assert marker in text
    start = text.index(marker)
    next_branch = text.find("\n\n**If `state_md_exists` and `state_json_exists` are both false", start)
    assert next_branch != -1, "Expected bad-backup branch boundary was not found"
    end = next_branch
    bad_backup_branch = text[start:end]
    for required in (
        "corrupt_state_bad_backup",
        "unrecoverable_state_pair",
        "gpd:health",
        "manual repair",
        "gpd:export-logs",
    ):
        assert required in bad_backup_branch

    branch_lower = bad_backup_branch.lower()
    assert_prompt_contracts(
        branch_lower,
        machine_exact(
            "bad-backup branch keeps repair-sync prohibition exact",
            "no `state repair-sync`",
            owner="sync-state staged contract",
            rationale="bad backup recovery must not run repair-sync",
        ),
        semantic_anchor(
            "bad-backup branch is read-only and write-free",
            ("stop in read-only diagnosis", "writes"),
        ),
    )
    assert re.search(r"writes:?\s+none", branch_lower)
    assert re.search(r"\b(no|not|never|must not|do not)\b[^\n.]*backup promotion", branch_lower)
    assert re.search(r"\b(no|not|never|must not|do not)\b[^\n.]*state rewrite", branch_lower)
