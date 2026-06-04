"""Typer-free write-envelope helpers for generated GPD artifacts."""

from __future__ import annotations

import shlex
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path

from gpd.core.artifact_command_payloads import (
    callable_accepts_kwarg,
    mapping_payload,
    markdown_payload_value,
)
from gpd.core.constants import PLANNING_DIR_NAME
from gpd.core.errors import GPDError
from gpd.core.root_resolution import resolve_project_root
from gpd.core.utils import atomic_write

DisplayPath = Callable[[str | Path | None], str]

__all__ = [
    "artifact_target_ref",
    "artifact_write_blocker",
    "atomic_write_artifact_error",
    "body_markdown_starts_with_frontmatter",
    "ensure_frontmatter_block",
    "normalize_optional_proof_redteam_claim_text",
    "normalize_proof_redteam_claim_id",
    "normalize_proof_redteam_proof_artifact_paths",
    "normalize_proof_redteam_reviewed_at",
    "normalize_proof_redteam_skeleton_output",
    "normalize_proof_redteam_skeleton_status",
    "normalize_required_proof_redteam_claim_text",
    "normalize_single_proof_redteam_artifact_path",
    "normalize_verification_report_finalize_validate_mode",
    "normalize_verification_report_score",
    "normalize_verification_report_skeleton_format",
    "normalize_verification_report_skeleton_output",
    "normalize_verification_report_skeleton_status",
    "normalize_verification_report_validate_mode",
    "normalize_verification_report_verified",
    "project_local_artifact_ref",
    "project_local_gpd_ref",
    "proof_redteam_artifact_ref_from_payload",
    "proof_redteam_finalize_not_run",
    "proof_redteam_finalize_output_target",
    "proof_redteam_finalize_validation_commands_for_ref",
    "proof_redteam_finalized_markdown",
    "proof_redteam_output_target",
    "proof_redteam_validation_commands_for_ref",
    "proof_redteam_write_not_run",
    "render_verification_report_candidate",
    "render_verification_report_frontmatter_yaml",
    "render_verification_report_markdown_candidate",
    "render_verification_report_markdown_draft",
    "resolve_proof_redteam_proof_artifact_path",
    "validate_verification_report_candidate",
    "verification_report_artifact_ref",
    "verification_report_authoring_rules",
    "verification_report_finalize_recovery",
    "verification_report_finalized_markdown",
    "verification_report_output_target",
    "verification_report_plan_contract_ref",
    "verification_report_validation_commands",
    "verification_report_validation_commands_for_ref",
    "verification_report_validation_not_run",
    "verification_report_warning_list",
    "verification_report_write_payload",
    "verification_report_write_recovery",
]


def _default_display_path(target: str | Path | None) -> str:
    if target is None:
        return ""
    return Path(str(target)).expanduser().as_posix()


def _format(display_path: DisplayPath | None, target: str | Path | None) -> str:
    formatter = display_path or _default_display_path
    return formatter(target)


def project_local_artifact_ref(path: Path, *, planning_dir_name: str = PLANNING_DIR_NAME) -> str | None:
    resolved = path.resolve(strict=False)
    project_root = resolve_project_root(resolved.parent, require_layout=True)
    if project_root is not None:
        try:
            relative = resolved.relative_to(project_root.resolve(strict=False))
        except ValueError:
            pass
        else:
            if relative.parts and relative.parts[0] == planning_dir_name:
                return relative.as_posix()

    gpd_indexes = [index for index, part in enumerate(resolved.parts) if part == planning_dir_name]
    if gpd_indexes:
        return Path(*resolved.parts[gpd_indexes[-1] :]).as_posix()
    return None


def verification_report_plan_contract_ref(plan_path: Path) -> str:
    """Return the canonical project-local contract ref for a PLAN path."""

    resolved = plan_path.resolve(strict=False)
    artifact_ref = project_local_artifact_ref(plan_path)
    return f"{artifact_ref}#/contract" if artifact_ref is not None else f"{resolved.name}#/contract"


def normalize_verification_report_skeleton_status(status: str) -> str:
    normalized = status.strip()
    if normalized != "gaps_found":
        raise GPDError("verification-report skeleton currently supports only --status gaps_found")
    return normalized


def normalize_verification_report_skeleton_output(
    raw_payload: object,
    *,
    plan_path: Path,
    plan_contract_ref: str,
    target_status: str,
) -> dict[str, object]:
    normalized = mapping_payload(raw_payload, label="verification-report skeleton builder")
    normalized.setdefault("plan_path", str(plan_path))
    normalized.setdefault("plan_contract_ref", plan_contract_ref)
    normalized.setdefault("target_status", target_status)
    if "validation_commands" not in normalized:
        normalized["validation_commands"] = verification_report_validation_commands(normalized)
    if "authoring_rules" not in normalized:
        normalized["authoring_rules"] = verification_report_authoring_rules()
    if "warnings" not in normalized:
        normalized["warnings"] = []
    if "frontmatter_yaml" not in normalized:
        normalized["frontmatter_yaml"] = render_verification_report_frontmatter_yaml(
            normalized.get("frontmatter"),
            target_report_ref=verification_report_artifact_ref(normalized),
        )
    if "markdown_draft" not in normalized:
        normalized["markdown_draft"] = render_verification_report_markdown_draft(normalized)
    return normalized


def normalize_verification_report_skeleton_format(output_format: str) -> str:
    normalized = output_format.strip().lower()
    if normalized not in {"markdown", "frontmatter", "json"}:
        raise GPDError("verification-report skeleton --format must be one of: markdown, frontmatter, json")
    return normalized


def project_local_gpd_ref(path_value: object) -> str | None:
    if not isinstance(path_value, str) or not path_value.strip():
        return None
    return project_local_artifact_ref(Path(path_value).expanduser()) or path_value


def render_verification_report_frontmatter_yaml(
    frontmatter: object,
    *,
    target_report_ref: str | None = None,
) -> str:
    if not isinstance(frontmatter, Mapping):
        raise GPDError("verification-report skeleton payload is missing frontmatter")

    from gpd.core.verification_report import render_verification_report_frontmatter_yaml as render_frontmatter_yaml

    kwargs: dict[str, object] = {}
    if target_report_ref is not None and callable_accepts_kwarg(
        render_frontmatter_yaml,
        "target_report_ref",
    ):
        kwargs["target_report_ref"] = target_report_ref
    return render_frontmatter_yaml(dict(frontmatter), **kwargs)


def ensure_frontmatter_block(frontmatter_yaml: object) -> str:
    if not isinstance(frontmatter_yaml, str) or not frontmatter_yaml.strip():
        raise GPDError("verification-report skeleton payload is missing frontmatter_yaml")
    rendered = frontmatter_yaml.strip()
    if rendered.startswith("---"):
        return f"{rendered}\n"
    return f"---\n{rendered}\n---\n"


def body_markdown_starts_with_frontmatter(body_markdown: str) -> bool:
    stripped = body_markdown.lstrip("\ufeff \t\r\n")
    return stripped == "---" or stripped.startswith("---\n") or stripped.startswith("---\r\n")


def verification_report_artifact_ref(payload: Mapping[str, object]) -> str:
    for key in ("target_report_ref", "target_report_path"):
        rendered = project_local_gpd_ref(payload.get(key))
        if rendered:
            return rendered
    return "GPD/phases/<phase>/<plan>-VERIFICATION.md"


def verification_report_validation_commands(payload: Mapping[str, object]) -> list[str]:
    existing = payload.get("validation_commands")
    if isinstance(existing, list) and all(isinstance(item, str) for item in existing):
        return list(existing)
    report_ref = verification_report_artifact_ref(payload)
    return verification_report_validation_commands_for_ref(report_ref)


def verification_report_authoring_rules() -> list[str]:
    return [
        "Use this generated frontmatter as the starting YAML, not as a loose example.",
        "Do not add prose strings to contract_results.*.evidence; put prose in summary, notes, or the Markdown body.",
        "Keep top-level status as gaps_found until a validated report can support a stronger result.",
        "Run the validation commands before treating the report as canonical.",
    ]


def render_verification_report_markdown_draft(payload: Mapping[str, object]) -> str:
    from gpd.core.verification_report import render_verification_report_markdown

    frontmatter_block = ensure_frontmatter_block(payload.get("frontmatter_yaml"))
    validation_commands = verification_report_validation_commands(payload)
    authoring_rules = payload.get("authoring_rules")
    rules = authoring_rules if isinstance(authoring_rules, list) else verification_report_authoring_rules()
    validation_block = "\n".join(validation_commands)
    rules_block = "\n".join(f"- {rule}" for rule in rules if isinstance(rule, str))
    body_stub = (
        "# Verification\n\n"
        "## Evidence\n\n"
        "Add the independent verification commands, exact outputs, and PASS/FAIL/INCONCLUSIVE verdict here.\n\n"
        "## Gap Notes\n\n"
        "Explain unresolved contract gaps without changing schema-only fields into prose evidence.\n\n"
        "## Validation Commands\n\n"
        "```bash\n"
        f"{validation_block}\n"
        "```\n\n"
        "## Authoring Rules\n\n"
        f"{rules_block}\n"
    )
    return render_verification_report_markdown(frontmatter_block, body_stub)


def normalize_verification_report_validate_mode(validate_mode: str | None, *, has_body_file: bool) -> str:
    if validate_mode is None:
        return "contract" if has_body_file else "frontmatter"
    normalized = validate_mode.strip().lower()
    if normalized not in {"none", "frontmatter", "contract"}:
        raise GPDError("verification-report skeleton --validate must be one of: none, frontmatter, contract")
    return normalized


def normalize_verification_report_finalize_validate_mode(validate_mode: str | None) -> str:
    if validate_mode is None:
        return "contract"
    normalized = validate_mode.strip().lower()
    if normalized != "contract":
        raise GPDError("verification-report finalize --validate must be contract")
    return normalized


def normalize_verification_report_verified(verified: str | None) -> str | None:
    if verified is None:
        return None
    normalized = verified.strip()
    if not normalized:
        raise GPDError("verification-report skeleton --verified cannot be empty")
    if normalized.lower() == "now":
        return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return normalized


def normalize_verification_report_score(score: str | None) -> str | None:
    if score is None:
        return None
    normalized = score.strip()
    if not normalized:
        raise GPDError("verification-report skeleton --score cannot be empty")
    return normalized


def verification_report_output_target(
    output_path: str | None,
    *,
    payload: Mapping[str, object],
    plan_path: Path,
    launch_cwd: Path,
) -> Path:
    target_base = launch_cwd
    if output_path is not None:
        raw_target = output_path
    else:
        raw_target = None
        payload_target = payload.get("target_report_path")
        if isinstance(payload_target, str) and payload_target.strip():
            raw_target = payload_target
            payload_path = Path(payload_target).expanduser()
            if payload_path.parts and payload_path.parts[0] == PLANNING_DIR_NAME:
                target_base = resolve_project_root(plan_path.parent, require_layout=True) or plan_path.parent
            else:
                target_base = plan_path.parent
        else:
            name = plan_path.name
            raw_target = str(
                plan_path.with_name(
                    name.replace("PLAN.md", "VERIFICATION.md") if "PLAN.md" in name else "VERIFICATION.md"
                )
            )

    target = Path(raw_target).expanduser()
    if not target.is_absolute():
        target = target_base / target
    return target.resolve(strict=False)


def verification_report_validation_commands_for_ref(report_ref: str) -> list[str]:
    quoted_ref = shlex.quote(report_ref)
    return [
        f"gpd frontmatter validate {quoted_ref} --schema verification",
        f"gpd validate verification-contract {quoted_ref}",
    ]


def verification_report_warning_list(payload: Mapping[str, object], *, validate_mode: str) -> list[str]:
    warnings: list[str] = []
    raw_warnings = payload.get("warnings")
    if isinstance(raw_warnings, list):
        warnings.extend(str(item) for item in raw_warnings if str(item).strip())
    if validate_mode == "none":
        warnings.append("Validation skipped because --validate none was requested.")
    return warnings


def render_verification_report_markdown_candidate(frontmatter_yaml: str, body_markdown: str) -> str:
    from gpd.core.verification_report import render_verification_report_markdown

    return render_verification_report_markdown(frontmatter_yaml, body_markdown)


def render_verification_report_candidate(
    payload: Mapping[str, object],
    *,
    target_report_ref: str,
    body_markdown: str | None,
    verified: str | None,
    score: str | None,
) -> tuple[str, dict[str, object]]:
    frontmatter = payload.get("frontmatter")
    if not isinstance(frontmatter, Mapping):
        raise GPDError("verification-report skeleton payload is missing frontmatter")

    rendered_payload = dict(payload)
    rendered_frontmatter = dict(frontmatter)
    if verified is not None:
        rendered_frontmatter["verified"] = verified
    if score is not None:
        rendered_frontmatter["score"] = score

    frontmatter_yaml = render_verification_report_frontmatter_yaml(
        rendered_frontmatter,
        target_report_ref=target_report_ref,
    )
    body = body_markdown
    if body is None:
        body_candidate = rendered_payload.get("body_stub")
        body = body_candidate if isinstance(body_candidate, str) else ""
    candidate = render_verification_report_markdown_candidate(frontmatter_yaml, body)

    rendered_payload["frontmatter"] = rendered_frontmatter
    rendered_payload["frontmatter_yaml"] = frontmatter_yaml
    rendered_payload["markdown_draft"] = candidate
    return candidate, rendered_payload


def verification_report_validation_not_run(mode: str, error: str) -> dict[str, object]:
    return {
        "mode": mode,
        "status": "not_run",
        "valid": False,
        "missing": [],
        "present": [],
        "errors": [error],
        "schema_name": "verification",
        "oracle_evidence_count": None,
    }


def artifact_target_ref(target_path: Path) -> str:
    return project_local_gpd_ref(str(target_path)) or target_path.as_posix()


def artifact_write_blocker(
    target_path: Path,
    *,
    force: bool,
    target_exists: bool | None = None,
    existing_requires_force: bool = True,
    display_path: DisplayPath | None = None,
) -> str | None:
    exists = target_path.exists() if target_exists is None else target_exists
    if exists and existing_requires_force and not force:
        return f"target exists; pass --force to overwrite: {_format(display_path, target_path)}"
    if not target_path.parent.exists():
        return f"target parent directory does not exist: {_format(display_path, target_path.parent)}"
    if not target_path.parent.is_dir():
        return f"target parent is not a directory: {_format(display_path, target_path.parent)}"
    return None


def atomic_write_artifact_error(target_path: Path, content: str) -> str | None:
    try:
        atomic_write(target_path, content)
    except OSError as exc:
        return f"failed to write target atomically: {exc}"
    return None


def verification_report_write_payload(
    *,
    target_path: Path,
    target_ref: str,
    force: bool,
    body_path: Path | None,
    warnings: list[str],
    validation_commands: list[str],
    patch_file_path: Path | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "written": False,
        "target_report_path": str(target_path),
        "target_report_ref": target_ref,
        "replaced": False,
        "force": force,
        "body_file": str(body_path) if body_path is not None else None,
        "validation": {},
        "warnings": warnings,
        "validation_commands": validation_commands,
    }
    if patch_file_path is not None:
        payload["patch_file"] = str(patch_file_path)
    return payload


def verification_report_write_recovery(
    *,
    plan_path: Path,
    target_path: Path,
    body_path: Path | None,
    validate_mode: str,
    force: bool,
    status: str,
    verified: str | None,
    score: str | None,
    display_path: DisplayPath | None = None,
) -> dict[str, object]:
    from gpd.core.verification_report import VERIFICATION_REPORT_BODY_CONTRACT

    body_display = _format(display_path, body_path) if body_path is not None else "BODY.md"
    command_parts = [
        "gpd",
        "verification-report",
        "skeleton",
        _format(display_path, plan_path),
        "--status",
        status,
        "--write",
        "--output",
        _format(display_path, target_path),
        "--body-file",
        body_display,
        "--validate",
        validate_mode,
    ]
    if force:
        command_parts.insert(6, "--force")
    if verified is not None:
        command_parts.extend(["--verified", verified])
    if score is not None:
        command_parts.extend(["--score", score])

    if body_path is None:
        safe_next_step = (
            "Create a Markdown body file with executed oracle evidence, then rerun the writer with --body-file."
        )
    else:
        safe_next_step = "Edit only the Markdown body file, then rerun the writer command."

    return {
        "safe_next_step": safe_next_step,
        "body_file_contract": [
            VERIFICATION_REPORT_BODY_CONTRACT,
            "Do not include YAML frontmatter in the body file.",
            "Keep generated frontmatter unchanged; the canonical report is written only after validation passes.",
        ],
        "rerun_command": " ".join(shlex.quote(part) for part in command_parts),
    }


def verification_report_finalize_recovery(
    *,
    plan_path: Path,
    patch_path: Path,
    target_path: Path,
    body_path: Path,
    validate_mode: str,
    force: bool,
    display_path: DisplayPath | None = None,
) -> dict[str, object]:
    from gpd.core.verification_report import VERIFICATION_REPORT_BODY_CONTRACT

    command_parts = [
        "gpd",
        "verification-report",
        "finalize",
        _format(display_path, plan_path),
        "--patch",
        _format(display_path, patch_path),
        "--body-file",
        _format(display_path, body_path),
        "--output",
        _format(display_path, target_path),
        "--validate",
        validate_mode,
    ]
    if force:
        command_parts.append("--force")

    return {
        "safe_next_step": "Edit only the typed patch or body file, then rerun the finalizer command.",
        "body_file_contract": [
            VERIFICATION_REPORT_BODY_CONTRACT,
            "Do not include YAML frontmatter in the body file.",
            "The finalizer writes the canonical report only after contract validation passes.",
        ],
        "rerun_command": " ".join(shlex.quote(part) for part in command_parts),
    }


def validate_verification_report_candidate(
    content: str,
    *,
    source_path: Path,
    mode: str,
) -> dict[str, object]:
    if mode == "none":
        return {
            "mode": mode,
            "status": "skipped",
            "valid": True,
            "missing": [],
            "present": [],
            "errors": [],
            "schema_name": "verification",
            "oracle_evidence_count": None,
        }

    from gpd.core.correctness_validators import validate_verification_oracle_evidence
    from gpd.core.frontmatter import FrontmatterParseError, FrontmatterValidationError, validate_frontmatter

    try:
        schema_result = validate_frontmatter(content, "verification", source_path=source_path)
    except (FrontmatterParseError, FrontmatterValidationError) as exc:
        return {
            "mode": mode,
            "status": "invalid",
            "valid": False,
            "missing": [],
            "present": [],
            "errors": [f"{type(exc).__name__}: {exc}"],
            "schema_name": "verification",
            "oracle_evidence_count": None,
        }

    errors = list(schema_result.errors)
    oracle_evidence_count: int | None = None
    if mode == "contract":
        oracle_result = validate_verification_oracle_evidence(content, source_path=source_path)
        oracle_evidence_count = oracle_result.evidence_count
        errors.extend(oracle_result.errors)

    valid = len(schema_result.missing) == 0 and not errors
    return {
        "mode": mode,
        "status": "valid" if valid else "invalid",
        "valid": valid,
        "missing": list(schema_result.missing),
        "present": list(schema_result.present),
        "errors": errors,
        "schema_name": schema_result.schema_name,
        "oracle_evidence_count": oracle_evidence_count,
    }


def verification_report_finalized_markdown(payload: Mapping[str, object]) -> str:
    markdown = markdown_payload_value(
        payload,
        keys=("markdown", "markdown_draft", "content", "report_markdown"),
        label="verification-report finalizer",
        required=True,
    )
    assert markdown is not None
    return markdown


def normalize_proof_redteam_skeleton_status(status: str) -> str:
    normalized = status.strip().lower()
    if normalized not in {"gaps_found", "human_needed"}:
        raise GPDError("proof-redteam skeleton --status must be one of: gaps_found, human_needed")
    return normalized


def normalize_proof_redteam_claim_id(claim_id: str) -> str:
    normalized = claim_id.strip()
    if not normalized:
        raise GPDError("proof-redteam skeleton --claim-id cannot be empty")
    return normalized


def normalize_optional_proof_redteam_claim_text(claim_text: str | None) -> str | None:
    if claim_text is None:
        return None
    normalized = claim_text.strip()
    if not normalized:
        raise GPDError("proof-redteam skeleton --claim-text cannot be empty when provided")
    return normalized


def normalize_proof_redteam_proof_artifact_paths(proof_artifact_paths: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_path in proof_artifact_paths or []:
        path = raw_path.strip()
        if not path:
            raise GPDError("proof-redteam skeleton --proof-artifact-path cannot be empty")
        if path in seen:
            continue
        seen.add(path)
        normalized.append(path)
    return normalized


def normalize_required_proof_redteam_claim_text(claim_text: str) -> str:
    normalized = claim_text.strip()
    if not normalized:
        raise GPDError("proof-redteam finalize --claim-text cannot be empty")
    return normalized


def normalize_proof_redteam_reviewed_at(reviewed_at: str | None) -> str | None:
    if reviewed_at is None:
        return None
    normalized = reviewed_at.strip()
    if not normalized:
        raise GPDError("proof-redteam finalize --reviewed-at cannot be empty")
    return normalized


def normalize_single_proof_redteam_artifact_path(proof_artifact_path: str) -> str:
    normalized = proof_artifact_path.strip()
    if not normalized:
        raise GPDError("proof-redteam finalize --proof-artifact-path cannot be empty")
    return normalized


def resolve_proof_redteam_proof_artifact_path(
    proof_artifact_path: str,
    *,
    project_root: Path,
    artifact_dir: Path,
) -> Path | None:
    target = Path(proof_artifact_path).expanduser()
    if target.is_absolute():
        candidates = [target.resolve(strict=False)]
    else:
        candidates = [
            (project_root / target).resolve(strict=False),
            (artifact_dir / target).resolve(strict=False),
        ]
    return next((candidate for candidate in candidates if candidate.exists() and candidate.is_file()), None)


def proof_redteam_validation_commands_for_ref(artifact_ref: str) -> list[str]:
    return [f"gpd validate proof-redteam {shlex.quote(artifact_ref)}"]


def proof_redteam_finalize_validation_commands_for_ref(artifact_ref: str) -> list[str]:
    return [
        f"gpd validate proof-redteam {shlex.quote(artifact_ref)}",
        "gpd validate verification-contract VERIFICATION.md",
    ]


def proof_redteam_artifact_ref_from_payload(payload: Mapping[str, object]) -> str:
    for key in ("target_artifact_ref", "target_report_ref", "target_artifact_path", "target_path"):
        rendered = project_local_gpd_ref(payload.get(key))
        if rendered:
            return rendered
    return "PROOF-REDTEAM.md"


def normalize_proof_redteam_skeleton_output(
    raw_payload: object,
    *,
    claim_id: str,
    claim_text: str | None,
    target_status: str,
) -> dict[str, object]:
    if isinstance(raw_payload, str):
        normalized = {"markdown_draft": raw_payload}
    else:
        normalized = mapping_payload(raw_payload, label="proof-redteam skeleton builder")

    normalized.setdefault("claim_id", claim_id)
    if claim_text is not None:
        normalized.setdefault("claim_text", claim_text)
    normalized.setdefault("status", target_status)
    normalized.setdefault("target_status", target_status)
    if "validation_commands" not in normalized:
        normalized["validation_commands"] = proof_redteam_validation_commands_for_ref(
            proof_redteam_artifact_ref_from_payload(normalized)
        )
    if "warnings" not in normalized:
        normalized["warnings"] = []
    markdown_draft = normalized.get("markdown_draft")
    if not isinstance(markdown_draft, str) or not markdown_draft.strip():
        raise GPDError("proof-redteam skeleton payload is missing markdown_draft")
    return normalized


def proof_redteam_finalize_output_target(input_path: Path, output_path: str | None, *, launch_cwd: Path) -> Path:
    if output_path is None:
        return input_path.resolve(strict=False)
    target = Path(output_path).expanduser()
    if not target.is_absolute():
        target = launch_cwd / target
    return target.resolve(strict=False)


def proof_redteam_finalize_not_run(
    error: str,
    *,
    input_path: Path,
    target_path: Path,
    force: bool,
) -> dict[str, object]:
    target_ref = artifact_target_ref(target_path)
    return {
        "written": False,
        "input_path": str(input_path),
        "target_path": str(target_path),
        "target_ref": target_ref,
        "replaced": False,
        "force": force,
        "valid": False,
        "errors": [error],
        "validation_commands": proof_redteam_finalize_validation_commands_for_ref(target_ref),
    }


def proof_redteam_finalized_markdown(payload: Mapping[str, object]) -> str | None:
    return markdown_payload_value(
        payload,
        keys=("markdown", "markdown_draft", "content", "artifact_markdown"),
        label="proof-redteam finalizer",
        required=False,
    )


def proof_redteam_output_target(output_path: str | None, *, launch_cwd: Path) -> Path:
    if output_path is None or not output_path.strip():
        raise GPDError("proof-redteam skeleton --write requires --output PATH")
    target = Path(output_path).expanduser()
    if not target.is_absolute():
        target = launch_cwd / target
    return target.resolve(strict=False)


def proof_redteam_write_not_run(error: str, *, target_path: Path, force: bool) -> dict[str, object]:
    target_ref = artifact_target_ref(target_path)
    return {
        "written": False,
        "target_path": str(target_path),
        "target_ref": target_ref,
        "replaced": False,
        "force": force,
        "error": error,
        "validation_commands": proof_redteam_validation_commands_for_ref(target_ref),
    }
