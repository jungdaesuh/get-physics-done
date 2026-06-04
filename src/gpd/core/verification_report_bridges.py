"""Shared verification report bridge payload builders."""

from __future__ import annotations

import shlex
from collections.abc import Mapping
from pathlib import Path

from gpd.core.constants import PLAN_SUFFIX, VERIFICATION_SUFFIX
from gpd.core.verification_report import VERIFICATION_REPORT_BODY_CONTRACT

__all__ = [
    "build_proof_redteam_finalizer_bridge",
    "build_verification_report_finalizer_bridge",
    "build_verification_report_skeleton_bridge",
    "expected_phase_plan_path",
    "expected_phase_proof_redteam_path",
    "expected_phase_verification_path",
    "verification_report_schema_sources",
]


def _phase_info_value(phase_info: Mapping[str, object] | None, key: str) -> object | None:
    if not phase_info:
        return None
    if isinstance(phase_info, Mapping):
        return phase_info.get(key)
    return getattr(phase_info, key, None)


def expected_phase_plan_path(cwd: Path, phase_info: Mapping[str, object] | None) -> str | None:
    """Return the plan path used to seed phase-level verification reports."""

    phase_dir = _phase_info_value(phase_info, "directory")
    phase_number = _phase_info_value(phase_info, "phase_number")
    if not phase_dir or not phase_number:
        return None

    fallback_plan = f"{phase_number}{PLAN_SUFFIX}"
    plans = _phase_info_value(phase_info, "plans")
    plan_name = fallback_plan
    if isinstance(plans, (list, tuple)) and plans:
        plan_name = fallback_plan if fallback_plan in plans else str(plans[0])
    return (cwd / str(phase_dir) / plan_name).as_posix()


def expected_phase_verification_path(cwd: Path, phase_info: Mapping[str, object] | None) -> str | None:
    """Return the canonical phase verification report path."""

    phase_dir = _phase_info_value(phase_info, "directory")
    phase_number = _phase_info_value(phase_info, "phase_number")
    if not phase_dir or not phase_number:
        return None
    return (cwd / str(phase_dir) / f"{phase_number}{VERIFICATION_SUFFIX}").as_posix()


def expected_phase_proof_redteam_path(cwd: Path, phase_info: Mapping[str, object] | None) -> str | None:
    """Return the phase-level proof-redteam path used by verify-work bridges."""

    phase_dir = _phase_info_value(phase_info, "directory")
    phase_number = _phase_info_value(phase_info, "phase_number")
    if not phase_dir or not phase_number:
        return None
    return (cwd / str(phase_dir) / f"{phase_number}-PROOF-REDTEAM.md").as_posix()


def verification_report_schema_sources() -> list[dict[str, str]]:
    """Return source references needed when verification report helpers fail."""

    package_root = Path(__file__).resolve().parents[1]
    return [
        {
            "name": "verifier_agent",
            "runtime_ref": "{GPD_AGENTS_DIR}/gpd-verifier.md",
            "source_path": (package_root / "agents" / "gpd-verifier.md").as_posix(),
        },
        {
            "name": "verification_report_template",
            "runtime_ref": "{GPD_INSTALL_DIR}/templates/verification-report.md",
            "source_path": (package_root / "specs" / "templates" / "verification-report.md").as_posix(),
        },
        {
            "name": "contract_results_schema",
            "runtime_ref": "{GPD_INSTALL_DIR}/templates/contract-results-schema.md",
            "source_path": (package_root / "specs" / "templates" / "contract-results-schema.md").as_posix(),
        },
    ]


def build_verification_report_skeleton_bridge(
    cwd: Path,
    phase_info: Mapping[str, object] | None,
) -> dict[str, object]:
    """Return the copy-safe gap-report skeleton bridge payload."""

    plan_path = expected_phase_plan_path(cwd, phase_info)
    verification_path = expected_phase_verification_path(cwd, phase_info)
    gap_report_status = "gaps_found"
    skeleton_command = (
        f"gpd verification-report skeleton {shlex.quote(plan_path)} --format markdown" if plan_path else None
    )
    writer_command = (
        f"gpd verification-report skeleton {shlex.quote(plan_path)} --write "
        f"--output {shlex.quote(verification_path)} --force --body-file BODY.md --validate contract"
        if plan_path and verification_path
        else None
    )
    validation_command = (
        f"gpd validate verification-contract {shlex.quote(verification_path)}" if verification_path else None
    )
    return {
        "command_name": "gpd verification-report skeleton",
        "supported_statuses": [gap_report_status],
        "status_policy": (
            "Bridge-generated skeletons are gap-report-only; stronger statuses require verifier evidence and "
            "contract validation."
        ),
        "skeleton_command": skeleton_command,
        "writer_command": writer_command,
        "gap_report_skeleton_command": skeleton_command,
        "gap_report_writer_command": writer_command,
        "body_contract": VERIFICATION_REPORT_BODY_CONTRACT,
        "schema_sources": verification_report_schema_sources(),
        "expected_target_plan_path": plan_path,
        "expected_verification_path": verification_path,
        "validation_command": validation_command,
        "fallback_rule": (
            "Fallback verifier execution must write body-only evidence to BODY.md that satisfies body_contract, "
            "run writer_command, and accept expected_verification_path only when writer validation passes. "
            "Use skeleton_command as preview context only; do not hand-author or reflow VERIFICATION.md frontmatter."
        ),
    }


def build_verification_report_finalizer_bridge(
    cwd: Path,
    phase_info: Mapping[str, object] | None,
) -> dict[str, object]:
    """Return the typed verification report finalizer bridge payload."""

    plan_path = expected_phase_plan_path(cwd, phase_info)
    verification_path = expected_phase_verification_path(cwd, phase_info)
    writer_command_template = (
        f"gpd verification-report finalize {shlex.quote(plan_path)} --patch PATCH.json "
        f"--body-file BODY.md --output {shlex.quote(verification_path)} --validate contract --force"
        if plan_path and verification_path
        else None
    )
    validation_command = (
        f"gpd validate verification-contract {shlex.quote(verification_path)}" if verification_path else None
    )
    return {
        "command_name": "gpd verification-report finalize",
        "supported_statuses": ["passed", "gaps_found", "expert_needed", "human_needed"],
        "writer_command_template": writer_command_template,
        "patch_contract": (
            "PATCH.json is a typed verification outcome patch consumed by the finalizer. It carries "
            "target status, contract results, comparison verdicts, proof-audit linkage, suggested contract "
            "checks, and status rationale; body evidence stays in BODY.md."
        ),
        "body_contract": "BODY.md is body-only Markdown; do not include YAML frontmatter.",
        "status_policy": (
            "Use the finalizer for passed, human_needed, expert_needed, and typed non-gap outcomes. "
            "Do not hand-author VERIFICATION.md YAML; route on finalizer validation output."
        ),
        "expected_target_plan_path": plan_path,
        "expected_verification_path": verification_path,
        "validation_command": validation_command,
    }


def build_proof_redteam_finalizer_bridge(
    cwd: Path,
    phase_info: Mapping[str, object] | None,
) -> dict[str, object]:
    """Return the proof-redteam finalizer bridge payload."""

    proof_redteam_path = expected_phase_proof_redteam_path(cwd, phase_info)
    validation_command = f"gpd validate proof-redteam {shlex.quote(proof_redteam_path)}" if proof_redteam_path else None
    writer_command_template = (
        f"gpd proof-redteam finalize {shlex.quote(proof_redteam_path)} --claim-id CLAIM_ID "
        "--claim-text CLAIM_TEXT --proof-artifact-path PROOF_ARTIFACT_PATH"
        if proof_redteam_path
        else None
    )
    return {
        "command_name": "gpd proof-redteam finalize",
        "supported_statuses": ["passed"],
        "writer_command_template": writer_command_template,
        "status_policy": (
            "Passed proof-redteam frontmatter is finalizer-owned. Non-passing proof audits use "
            "gpd proof-redteam skeleton; passed audits must run this finalizer before validation."
        ),
        "expected_proof_redteam_path": proof_redteam_path,
        "validation_command": validation_command,
    }
