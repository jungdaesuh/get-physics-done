"""Focused assertions for the verify-work command wrapper surface."""

from __future__ import annotations

from pathlib import Path

from gpd.core.frontmatter import extract_frontmatter
from gpd.core.prompt_diagnostics import build_prompt_surface_report, report_to_dict
from gpd.core.workflow_staging import load_workflow_stage_manifest
from tests.assertion_taxonomy_support import MatchMode, assert_prompt_contracts, semantic_concept
from tests.lifecycle_contract_test_support import artifact_paths, child_gate_from_text
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMAND_PATH = REPO_ROOT / "src/gpd/commands/verify-work.md"
WORKFLOW_PATH = REPO_ROOT / "src/gpd/specs/workflows/verify-work.md"
WORKFLOW_STAGE_DIR = REPO_ROOT / "src/gpd/specs/workflows/verify-work"
SESSION_ROUTER_AUTHORITY = "workflows/verify-work/session-router.md"


def _command_body_lines(text: str) -> list[str]:
    if text.startswith("---\n"):
        _frontmatter, separator, body = text[4:].partition("\n---\n")
        assert separator
        return body.splitlines()
    return text.splitlines()


def _assert_semantic_contract(
    text: str,
    label: str,
    *,
    required: tuple[str, ...] = (),
    forbidden: tuple[str, ...] = (),
) -> None:
    assert_prompt_contracts(
        text,
        *semantic_concept(
            label,
            required=required or None,
            forbidden=forbidden or None,
            match=MatchMode.CASEFOLD_NORMALIZED,
            context=label,
        ),
    )


def _verify_work_stage_diagnostic() -> tuple[dict[str, object], dict[str, object]]:
    report = build_prompt_surface_report(
        REPO_ROOT,
        surfaces=("command",),
        runtime_names=(),
        include_tests=False,
        include_runtime_projections=False,
    )
    payload = report_to_dict(report)
    stage_diagnostics = payload["stage_diagnostics"]
    assert isinstance(stage_diagnostics, list)
    matches = [
        diagnostic
        for diagnostic in stage_diagnostics
        if isinstance(diagnostic, dict) and diagnostic.get("workflow_id") == "verify-work"
    ]
    assert len(matches) == 1
    return payload, matches[0]


def _stage_diagnostic_by_id(workflow_diagnostic: dict[str, object], stage_id: str) -> dict[str, object]:
    stages = workflow_diagnostic["stages"]
    assert isinstance(stages, list)
    matches = [stage for stage in stages if isinstance(stage, dict) and stage.get("stage_id") == stage_id]
    assert len(matches) == 1
    return matches[0]


def _dict_rows(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _session_router_residue_evidence(
    payload: dict[str, object],
    stage: dict[str, object],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for key in (
        "top_authority_metrics",
        "authority_usage_metrics",
        "prior_stage_residue_authority_metrics",
        "must_not_eager_load_violations",
    ):
        rows.extend(row for row in _dict_rows(stage.get(key)) if row.get("authority") == SESSION_ROUTER_AUTHORITY)

    for key in ("stage_top_authorities", "stage_authority_top_prompts"):
        rows.extend(
            row
            for row in _dict_rows(payload.get(key))
            if row.get("workflow_id") == "verify-work"
            and row.get("stage_id") == "phase_bootstrap"
            and row.get("authority") == SESSION_ROUTER_AUTHORITY
        )
    return rows


def _row_reports_prior_stage_residue(row: dict[str, object]) -> bool:
    return (
        row.get("classification") == "prior_stage_residue"
        or row.get("violation_source") == "prior_stage_residue"
        or row.get("first_turn_role") == "prior_stage_residue"
        or row.get("bucket") == "prior_stage_residue"
    )


def test_verify_work_command_wrapper_stays_thin_and_delegates_policy_to_workflow() -> None:
    text = COMMAND_PATH.read_text(encoding="utf-8")
    metadata, _body = extract_frontmatter(text)
    body_include_lines = [line.strip() for line in _command_body_lines(text) if line.strip().startswith("@")]

    first_stage_include = "@{GPD_INSTALL_DIR}/workflows/verify-work/session-router.md"
    assert body_include_lines.count(first_stage_include) == 1
    assert "@{GPD_INSTALL_DIR}/workflows/verify-work.md" not in text
    requires = metadata.get("requires")
    assert isinstance(requires, dict)
    assert requires.get("files") == ["GPD/ROADMAP.md"]
    assert "@GPD/STATE.md" not in body_include_lines
    assert "@GPD/ROADMAP.md" not in body_include_lines
    _assert_semantic_contract(
        text,
        "verify-work command wrapper stays thin",
        required=("staged workflow authorities", "detailed check taxonomy", "wrapper", "delegates"),
        forbidden=(
            "One check at a time, plain text responses, no interrogation.",
            "Physics verification is not binary:",
        ),
    )
    assert "Severity Classification" not in text
    assert "For deeper focused analysis" not in text


def test_verify_work_session_router_owns_state_and_roadmap_routing() -> None:
    command = COMMAND_PATH.read_text(encoding="utf-8")
    body_include_lines = [line.strip() for line in _command_body_lines(command) if line.strip().startswith("@")]
    session_router = (WORKFLOW_STAGE_DIR / "session-router.md").read_text(encoding="utf-8")

    assert "@GPD/STATE.md" not in body_include_lines
    assert "@GPD/ROADMAP.md" not in body_include_lines
    _assert_semantic_contract(
        session_router,
        "session router owns state and roadmap routing",
        required=(
            "SESSION_ROUTER_INIT",
            "gpd --raw init verify-work",
            "stage session_router",
            "active_verification_sessions",
            "canonical verification-status reader",
            "status` / `routing_status",
            "centralized review preflight",
            "lifecycle authority gate",
            "artifact discovery helpers",
            "fail-closed",
        ),
    )


def test_verify_work_workflow_loads_staged_init_payloads_on_demand() -> None:
    text = workflow_authority_text(WORKFLOW_PATH.parent, "verify-work")

    assert 'PHASE_ARG=""' in text
    assert "VERIFY_FLAGS=()" in text
    assert '*) [ -z "$PHASE_ARG" ] && PHASE_ARG="$token" ;;' in text
    assert text.index('PHASE_ARG=""') < text.index(
        'SESSION_ROUTER_INIT=$(gpd --raw init verify-work "${PHASE_ARG}" --stage session_router)'
    )
    assert 'SESSION_ROUTER_INIT=$(gpd --raw init verify-work "${PHASE_ARG}" --stage session_router)' in text
    assert 'PROJECT_ROOT=$(echo "$SESSION_ROUTER_INIT" | gpd json get .project_root)' in text
    assert 'PHASE_DIR_ABS=$(echo "$SESSION_ROUTER_INIT" | gpd json get .phase_dir_abs --default "")' in text
    assert 'VERIFY_FLAG_TEXT="${VERIFY_FLAGS[*]}"' in text
    _assert_semantic_contract(
        text,
        "verify-work routes normalized flags",
        required=("verification flags", "normalized parser", "VERIFY_FLAG_TEXT"),
        forbidden=("verification flags from the invoking wrapper",),
    )
    assert 'PHASE_BOOTSTRAP_INIT=$(gpd --raw init verify-work "${PHASE_ARG}" --stage phase_bootstrap)' in text
    assert 'INVENTORY_BUILD_INIT=$(gpd --raw init verify-work "${PHASE_ARG}" --stage inventory_build)' in text
    assert (
        'INTERACTIVE_VALIDATION_INIT=$(gpd --raw init verify-work "${PHASE_ARG}" --stage interactive_validation)'
        in text
    )
    assert 'GAP_REPAIR_INIT=$(gpd --raw init verify-work "${PHASE_ARG}" --stage gap_repair)' in text
    assert 'INIT=$(gpd --raw init verify-work "${PHASE_ARG}")' not in text
    _assert_semantic_contract(
        text,
        "verify-work stages load phase payloads on demand",
        required=(
            "reference ledgers",
            "protocol bundles",
            "report schemas",
            "non-empty `${PHASE_ARG}`",
            "user response",
            "phase-only stages",
        ),
    )


def test_verify_work_root_is_stage_index_not_active_authority() -> None:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    manifest = load_workflow_stage_manifest("verify-work")

    _assert_semantic_contract(
        text,
        "verify-work root is only a staged index",
        required=("compatibility index", "staged", "verify-work", "workflow", "index only"),
    )
    assert "<boundary_summary>" not in text
    for stage in manifest.stages:
        assert f"`{stage.id}`" in text
        assert stage.mode_paths[0] in text
    assert "@{GPD_INSTALL_DIR}/references/verification/core/proof-redteam-workflow-gate.md" not in text
    _assert_semantic_contract(
        text,
        "verify-work root excludes session-router procedure",
        forbidden=(
            "gpd --raw init verify-work",
            "active_verification_sessions",
            "status` / `routing_status",
            "artifact discovery helpers",
            "shell-loop over `GPD/phases`",
        ),
    )
    assert "verification_report_skeleton_bridge" not in text
    assert "verify_work_gap_planner" not in text


def test_verify_work_stage_authorities_are_lazy_by_stage() -> None:
    session_router = (WORKFLOW_STAGE_DIR / "session-router.md").read_text(encoding="utf-8")
    phase_bootstrap = (WORKFLOW_STAGE_DIR / "phase-bootstrap.md").read_text(encoding="utf-8")
    inventory_build = (WORKFLOW_STAGE_DIR / "inventory-build.md").read_text(encoding="utf-8")
    interactive_validation = (WORKFLOW_STAGE_DIR / "interactive-validation.md").read_text(encoding="utf-8")
    gap_repair = (WORKFLOW_STAGE_DIR / "gap-repair.md").read_text(encoding="utf-8")

    _assert_semantic_contract(
        session_router,
        "session router excludes phase-local authorities",
        forbidden=(
            "@{GPD_INSTALL_DIR}/references/verification/core/proof-redteam-workflow-gate.md",
            "verification_report_skeleton_bridge",
            "verification_report_finalizer_bridge",
            "GAP_REPAIR_INIT",
            "templates/planner-subagent-prompt.md",
            "verify_work_gap_planner",
        ),
    )

    assert "@{GPD_INSTALL_DIR}/references/verification/core/proof-redteam-workflow-gate.md" in phase_bootstrap
    _assert_semantic_contract(
        phase_bootstrap,
        "phase bootstrap owns proof-redteam finalizer only",
        required=("proof_redteam_finalizer_bridge", "helper-owned", "passed-audit bridge"),
        forbidden=("verification_report_skeleton_bridge", "verify_work_gap_planner"),
    )

    verifier_gate = child_gate_from_text(inventory_build, "verify_work_verifier_report")
    assert artifact_paths(verifier_gate) == ("${PHASE_DIR_ABS}/${phase_number}-VERIFICATION.md",)
    _assert_semantic_contract(
        inventory_build,
        "inventory build owns verifier report bridges",
        required=("verification_report_skeleton_bridge", "verification_report_finalizer_bridge"),
        forbidden=("GAP_REPAIR_INIT", "verify_work_gap_planner"),
    )

    assert "GAP_REPAIR_INIT=$(gpd --raw init verify-work" in interactive_validation
    _assert_semantic_contract(
        interactive_validation,
        "interactive validation excludes gap planner",
        forbidden=("verify_work_gap_planner",),
    )

    assert "templates/planner-subagent-prompt.md" in gap_repair
    gap_planner_gate = child_gate_from_text(gap_repair, "verify_work_gap_planner")
    assert gap_planner_gate.role == "gpd-planner"


def test_verify_work_manifest_eager_authorities_follow_stage_boundaries() -> None:
    manifest = load_workflow_stage_manifest("verify-work")

    session_router = manifest.stage("session_router")
    phase_bootstrap = manifest.stage("phase_bootstrap")
    inventory_build = manifest.stage("inventory_build")
    interactive_validation = manifest.stage("interactive_validation")
    gap_repair = manifest.stage("gap_repair")

    assert session_router.mode_paths == ("workflows/verify-work/session-router.md",)
    assert session_router.loaded_authorities == ("workflows/verify-work/session-router.md",)
    assert "references/verification/core/proof-redteam-workflow-gate.md" not in session_router.eager_authorities()
    assert "workflows/verify-work/inventory-build.md" not in session_router.eager_authorities()
    assert "workflows/verify-work/gap-repair.md" not in session_router.eager_authorities()
    assert "templates/verification-report.md" not in session_router.eager_authorities()

    assert phase_bootstrap.mode_paths == ("workflows/verify-work/phase-bootstrap.md",)
    assert "references/verification/core/proof-redteam-workflow-gate.md" in phase_bootstrap.eager_authorities()
    assert SESSION_ROUTER_AUTHORITY in phase_bootstrap.must_not_eager_load
    assert SESSION_ROUTER_AUTHORITY not in phase_bootstrap.eager_authorities()
    assert "templates/verification-report.md" not in phase_bootstrap.eager_authorities()
    assert "workflows/verify-work/gap-repair.md" not in phase_bootstrap.eager_authorities()

    assert inventory_build.mode_paths == ("workflows/verify-work/inventory-build.md",)
    assert "verification_report_skeleton_bridge" in inventory_build.required_init_fields
    assert "templates/verification-report.md" not in inventory_build.eager_authorities()
    assert "workflows/verify-work/gap-repair.md" not in inventory_build.eager_authorities()

    assert interactive_validation.mode_paths == ("workflows/verify-work/interactive-validation.md",)
    assert {"templates/verification-report.md"}.isdisjoint(interactive_validation.eager_authorities())
    assert {"templates/verification-report.md"} <= set(
        interactive_validation.eager_authorities(selected_conditions=("session_overlay_write_or_repair",))
    )
    assert {"templates/contract-results-schema.md"} <= set(interactive_validation.must_not_eager_load)
    assert "workflows/verify-work/gap-repair.md" not in interactive_validation.eager_authorities()

    assert gap_repair.mode_paths == ("workflows/verify-work/gap-repair.md",)
    assert {
        "templates/verification-report.md",
        "references/protocols/error-propagation-protocol.md",
    }.isdisjoint(gap_repair.eager_authorities())
    assert {"templates/verification-report.md"} <= set(
        gap_repair.eager_authorities(selected_conditions=("gap_report_write_or_schema_repair",))
    )
    assert {"references/protocols/error-propagation-protocol.md"} <= set(
        gap_repair.eager_authorities(selected_conditions=("error_propagation_gap",))
    )


def test_verify_work_phase_bootstrap_session_router_is_prior_stage_residue() -> None:
    payload, verify_work = _verify_work_stage_diagnostic()
    phase_bootstrap = _stage_diagnostic_by_id(verify_work, "phase_bootstrap")
    evidence_rows = _session_router_residue_evidence(payload, phase_bootstrap)

    assert any(_row_reports_prior_stage_residue(row) for row in evidence_rows), (
        "verify-work.phase_bootstrap must report workflows/verify-work/session-router.md "
        "as prior_stage_residue, not hide it or count it as a true eager-load violation"
    )

    true_violation_rows = [
        row
        for row in _dict_rows(phase_bootstrap.get("must_not_eager_load_violations"))
        if row.get("authority") == SESSION_ROUTER_AUTHORITY
        and row.get("classification", "eager_load_violation") == "eager_load_violation"
    ]
    assert true_violation_rows == []
