"""Public proof-redteam validation wrappers and conservative skeleton/finalizer builders."""

from __future__ import annotations

import hashlib
import tempfile
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from gpd.contracts import PROOF_AUDIT_REVIEWER
from gpd.core.frontmatter import FrontmatterParseError, extract_frontmatter
from gpd.core.proof_redteam_contract import (
    PROOF_REDTEAM_OPEN_STATUS_VALUES,
    PROOF_REDTEAM_REQUIRED_COVERAGE_SUBSECTIONS,
    PROOF_REDTEAM_REQUIRED_SECTIONS,
    read_proof_redteam_status,
)
from gpd.core.reproducibility import compute_sha256
from gpd.core.utils import atomic_write

__all__ = [
    "PROOF_REDTEAM_BODY_CONTRACT",
    "ProofRedteamFinalizationResult",
    "ProofRedteamSkeleton",
    "ProofRedteamSkeletonStatus",
    "ProofRedteamValidationResult",
    "build_proof_redteam_skeleton",
    "finalize_proof_redteam_artifact",
    "render_proof_redteam_frontmatter_yaml",
    "render_proof_redteam_markdown",
    "validate_proof_redteam_artifact",
]

ProofRedteamSkeletonStatus = Literal["gaps_found", "human_needed"]

PROOF_REDTEAM_BODY_CONTRACT = (
    "Proof-redteam skeletons are non-certifying drafts: replace every TODO row with exact proof locations, "
    "structured gaps, and an adversarial probe before treating the claim as established."
)

_SUPPORTED_SKELETON_STATUSES = frozenset(PROOF_REDTEAM_OPEN_STATUS_VALUES)
_PLACEHOLDER_PROOF_ARTIFACT_PATH = "TODO-proof-artifact-path"


class ProofRedteamValidationResult(BaseModel):
    """Structured result for proof-redteam artifact validation."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    path: str
    valid: bool
    status: str | None = None
    errors: list[str] = Field(default_factory=list)


class ProofRedteamSkeleton(BaseModel):
    """Typed payload for copy-safe proof-redteam skeletons."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    frontmatter: dict[str, object]
    frontmatter_yaml: str
    markdown_draft: str
    body_stub: str
    body_contract: str
    authoring_rules: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    claim_id: str
    claim_text: str | None = None
    target_status: ProofRedteamSkeletonStatus = "gaps_found"


class ProofRedteamFinalizationResult(BaseModel):
    """Structured result for helper-owned passed proof-redteam finalization."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    path: str
    valid: bool
    status: str | None = None
    errors: list[str] = Field(default_factory=list)
    reviewed_at: str | None = None
    artifact_sha256: str | None = None
    audit_artifact_sha256: str | None = None
    proof_artifact_sha256: str | None = None
    claim_statement_sha256: str | None = None
    proof_audit: dict[str, object] | None = None


def validate_proof_redteam_artifact(
    path: str | Path,
    *,
    project_root: str | Path,
    expected_manuscript_path: str | None = None,
    expected_manuscript_sha256: str | None = None,
    expected_round: int | None = None,
    expected_claim_ids: Iterable[str] = (),
    expected_proof_artifact_paths: Iterable[str] = (),
) -> ProofRedteamValidationResult:
    """Validate a proof-redteam artifact through the existing strict proof-review parser."""

    artifact_path = Path(path)
    status, error = read_proof_redteam_status(
        artifact_path,
        project_root=Path(project_root),
        expected_manuscript_path=expected_manuscript_path,
        expected_manuscript_sha256=expected_manuscript_sha256,
        expected_round=expected_round,
        expected_claim_ids=tuple(expected_claim_ids),
        expected_proof_artifact_paths=tuple(expected_proof_artifact_paths),
    )
    if error is not None:
        return ProofRedteamValidationResult(
            path=artifact_path.as_posix(),
            valid=False,
            errors=[error],
        )
    return ProofRedteamValidationResult(
        path=artifact_path.as_posix(),
        valid=True,
        status=status,
    )


def finalize_proof_redteam_artifact(
    path: str | Path,
    *,
    project_root: str | Path,
    claim_id: str,
    claim_text: str,
    proof_artifact_path: str | Path,
    reviewed_at: str | None = None,
    expected_manuscript_path: str | None = None,
    expected_manuscript_sha256: str | None = None,
    expected_round: int | None = None,
    output_path: str | Path | None = None,
) -> ProofRedteamFinalizationResult:
    """Finalize an existing proof-redteam body/draft as a validated passed artifact.

    The finalizer owns mechanical passed frontmatter and hashes, then delegates
    the scientific shape checks to ``validate_proof_redteam_artifact``. It does
    not place the final artifact hash inside the artifact frontmatter, avoiding
    a self-hash dependency.
    """

    project_root_path = Path(project_root).expanduser().resolve(strict=False)
    source_path = _resolve_io_path(path, project_root_path)
    target_path = _resolve_io_path(output_path, project_root_path) if output_path is not None else source_path
    result_path = target_path.as_posix()

    normalized_claim_id = claim_id.strip()
    if not normalized_claim_id:
        return _invalid_finalization_result(result_path, "claim_id must not be blank")
    normalized_claim_text = claim_text.strip()
    if not normalized_claim_text:
        return _invalid_finalization_result(result_path, "claim_text must not be blank")

    normalized_reviewed_at = _normalize_reviewed_at(reviewed_at)
    if normalized_reviewed_at is None:
        return _invalid_finalization_result(result_path, "reviewed_at must not be blank when provided")

    manuscript_fields, manuscript_error = _normalize_finalizer_manuscript_fields(
        expected_manuscript_path=expected_manuscript_path,
        expected_manuscript_sha256=expected_manuscript_sha256,
        expected_round=expected_round,
    )
    if manuscript_error is not None:
        return _invalid_finalization_result(result_path, manuscript_error, reviewed_at=normalized_reviewed_at)
    validation_manuscript_path = manuscript_fields.get("manuscript_path")
    validation_manuscript_sha256 = manuscript_fields.get("manuscript_sha256")
    validation_round = manuscript_fields.get("round")

    try:
        source_content = source_path.read_text(encoding="utf-8")
        _meta, body = extract_frontmatter(source_content)
    except (OSError, UnicodeDecodeError) as exc:
        return _invalid_finalization_result(result_path, str(exc), reviewed_at=normalized_reviewed_at)
    except FrontmatterParseError as exc:
        return _invalid_finalization_result(result_path, str(exc), reviewed_at=normalized_reviewed_at)

    proof_resolution = _resolve_finalizer_proof_artifact_path(
        proof_artifact_path,
        project_root=project_root_path,
        artifact_dir=target_path.parent.resolve(strict=False),
    )
    if proof_resolution.error is not None:
        return _invalid_finalization_result(result_path, proof_resolution.error, reviewed_at=normalized_reviewed_at)

    assert proof_resolution.resolved_path is not None
    assert proof_resolution.redteam_path is not None
    assert proof_resolution.audit_path is not None
    proof_artifact_sha256 = compute_sha256(proof_resolution.resolved_path)
    claim_statement_sha256 = hashlib.sha256(normalized_claim_text.encode("utf-8")).hexdigest()

    frontmatter = _build_passed_proof_redteam_frontmatter(
        claim_id=normalized_claim_id,
        proof_artifact_path=proof_resolution.redteam_path,
        reviewed_at=normalized_reviewed_at,
        proof_artifact_sha256=proof_artifact_sha256,
        claim_statement_sha256=claim_statement_sha256,
        manuscript_fields=manuscript_fields,
    )
    candidate = _render_finalized_markdown(frontmatter, body)

    candidate_validation = _validate_candidate_markdown(
        candidate,
        target_path=target_path,
        project_root=project_root_path,
        expected_claim_ids=(normalized_claim_id,),
        expected_proof_artifact_paths=(proof_resolution.redteam_path,),
        expected_manuscript_path=validation_manuscript_path if isinstance(validation_manuscript_path, str) else None,
        expected_manuscript_sha256=validation_manuscript_sha256
        if isinstance(validation_manuscript_sha256, str)
        else None,
        expected_round=validation_round if isinstance(validation_round, int) else None,
    )
    if not candidate_validation.valid:
        return ProofRedteamFinalizationResult(
            path=result_path,
            valid=False,
            errors=list(candidate_validation.errors),
            reviewed_at=normalized_reviewed_at,
            proof_artifact_sha256=proof_artifact_sha256,
            claim_statement_sha256=claim_statement_sha256,
        )
    if candidate_validation.status != "passed":
        return ProofRedteamFinalizationResult(
            path=result_path,
            valid=False,
            status=candidate_validation.status,
            errors=["finalized proof-redteam artifact did not validate with status=passed"],
            reviewed_at=normalized_reviewed_at,
            proof_artifact_sha256=proof_artifact_sha256,
            claim_statement_sha256=claim_statement_sha256,
        )

    atomic_write(target_path, candidate)
    final_validation = validate_proof_redteam_artifact(
        target_path,
        project_root=project_root_path,
        expected_claim_ids=(normalized_claim_id,),
        expected_proof_artifact_paths=(proof_resolution.redteam_path,),
        expected_manuscript_path=validation_manuscript_path if isinstance(validation_manuscript_path, str) else None,
        expected_manuscript_sha256=validation_manuscript_sha256
        if isinstance(validation_manuscript_sha256, str)
        else None,
        expected_round=validation_round if isinstance(validation_round, int) else None,
    )
    if not final_validation.valid:
        return ProofRedteamFinalizationResult(
            path=result_path,
            valid=False,
            errors=list(final_validation.errors),
            reviewed_at=normalized_reviewed_at,
            proof_artifact_sha256=proof_artifact_sha256,
            claim_statement_sha256=claim_statement_sha256,
        )
    if final_validation.status != "passed":
        return ProofRedteamFinalizationResult(
            path=result_path,
            valid=False,
            status=final_validation.status,
            errors=["written proof-redteam artifact did not validate with status=passed"],
            reviewed_at=normalized_reviewed_at,
            proof_artifact_sha256=proof_artifact_sha256,
            claim_statement_sha256=claim_statement_sha256,
        )

    audit_artifact_sha256 = compute_sha256(target_path)
    proof_audit = _build_downstream_proof_audit(
        proof_artifact_path=proof_resolution.audit_path,
        proof_artifact_sha256=proof_artifact_sha256,
        audit_artifact_path=_audit_artifact_path_label(target_path),
        audit_artifact_sha256=audit_artifact_sha256,
        claim_statement_sha256=claim_statement_sha256,
        reviewed_at=normalized_reviewed_at,
    )
    return ProofRedteamFinalizationResult(
        path=result_path,
        valid=True,
        status=final_validation.status,
        errors=[],
        reviewed_at=normalized_reviewed_at,
        artifact_sha256=audit_artifact_sha256,
        audit_artifact_sha256=audit_artifact_sha256,
        proof_artifact_sha256=proof_artifact_sha256,
        claim_statement_sha256=claim_statement_sha256,
        proof_audit=proof_audit,
    )


def build_proof_redteam_skeleton(
    *,
    claim_id: str,
    claim_text: str | None = None,
    status: ProofRedteamSkeletonStatus = "gaps_found",
    proof_artifact_paths: Iterable[str] = (),
    manuscript_path: str | None = None,
    manuscript_sha256: str | None = None,
    round_number: int | None = None,
) -> ProofRedteamSkeleton:
    """Return a non-certifying proof-redteam artifact skeleton.

    The builder owns schema-shaped frontmatter and required section headings,
    but it never judges proof validity. It emits only open skeleton states.
    """

    if status not in _SUPPORTED_SKELETON_STATUSES:
        raise ValueError("proof-redteam skeleton supports only status='gaps_found' or status='human_needed'")
    normalized_claim_id = claim_id.strip()
    if not normalized_claim_id:
        raise ValueError("proof-redteam skeleton requires a non-empty claim_id")
    normalized_claim_text = _normalize_optional_text(claim_text)
    normalized_proof_paths = _normalize_proof_artifact_paths(proof_artifact_paths)
    manuscript_fields = _normalize_manuscript_fields(
        manuscript_path=manuscript_path,
        manuscript_sha256=manuscript_sha256,
        round_number=round_number,
    )
    frontmatter = _build_proof_redteam_frontmatter(
        claim_id=normalized_claim_id,
        status=status,
        proof_artifact_paths=normalized_proof_paths,
        manuscript_fields=manuscript_fields,
    )
    body_stub = _body_stub(
        claim_id=normalized_claim_id,
        claim_text=normalized_claim_text,
        proof_artifact_path=normalized_proof_paths[0],
        status=status,
    )
    frontmatter_yaml = render_proof_redteam_frontmatter_yaml(frontmatter)
    authoring_rules = _authoring_rules()
    warnings = _warnings()
    return ProofRedteamSkeleton(
        frontmatter=frontmatter,
        frontmatter_yaml=frontmatter_yaml,
        markdown_draft=render_proof_redteam_markdown(
            frontmatter_yaml,
            body_stub,
            authoring_rules=authoring_rules,
            warnings=warnings,
        ),
        body_stub=body_stub,
        body_contract=PROOF_REDTEAM_BODY_CONTRACT,
        authoring_rules=authoring_rules,
        warnings=warnings,
        claim_id=normalized_claim_id,
        claim_text=normalized_claim_text,
        target_status=status,
    )


def render_proof_redteam_frontmatter_yaml(frontmatter: dict[str, object]) -> str:
    """Return proof-redteam YAML frontmatter with delimiters."""

    yaml_str = yaml.dump(
        frontmatter,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=999999,
    ).rstrip()
    return f"---\n{yaml_str}\n---\n"


def render_proof_redteam_markdown(
    frontmatter_yaml: str,
    body_stub: str,
    *,
    authoring_rules: Iterable[str] = (),
    warnings: Iterable[str] = (),
) -> str:
    """Return a copy-safe Markdown proof-redteam draft."""

    sections = [body_stub.rstrip()]
    warning_section = _markdown_list_section("Generated Warnings", warnings)
    if warning_section:
        sections.append(warning_section)
    rules_section = _markdown_list_section("Generated Frontmatter Rules", authoring_rules)
    if rules_section:
        sections.append(rules_section)
    rendered_body = "\n\n".join(section for section in sections if section)
    return f"{frontmatter_yaml.rstrip()}\n\n{rendered_body}\n"


def _build_passed_proof_redteam_frontmatter(
    *,
    claim_id: str,
    proof_artifact_path: str,
    reviewed_at: str,
    proof_artifact_sha256: str,
    claim_statement_sha256: str,
    manuscript_fields: dict[str, object],
) -> dict[str, object]:
    return {
        "status": "passed",
        "reviewer": PROOF_AUDIT_REVIEWER,
        "claim_ids": [claim_id],
        "proof_artifact_paths": [proof_artifact_path],
        **manuscript_fields,
        "missing_parameter_symbols": [],
        "missing_hypothesis_ids": [],
        "coverage_gaps": [],
        "scope_status": "matched",
        "quantifier_status": "matched",
        "counterexample_status": "none_found",
        "proof_artifact_sha256": proof_artifact_sha256,
        "claim_statement_sha256": claim_statement_sha256,
        "reviewed_at": reviewed_at,
    }


def _build_proof_redteam_frontmatter(
    *,
    claim_id: str,
    status: ProofRedteamSkeletonStatus,
    proof_artifact_paths: tuple[str, ...],
    manuscript_fields: dict[str, object],
) -> dict[str, object]:
    structured_defaults = _structured_defaults(status)
    return {
        "status": status,
        "reviewer": PROOF_AUDIT_REVIEWER,
        "claim_ids": [claim_id],
        "proof_artifact_paths": list(proof_artifact_paths),
        **manuscript_fields,
        **structured_defaults,
    }


def _structured_defaults(status: ProofRedteamSkeletonStatus) -> dict[str, object]:
    if status == "human_needed":
        coverage_gap = "Human judgment is required before this proof audit can close."
    else:
        coverage_gap = "Builder skeleton: proof obligations have not been audited."
    return {
        "missing_parameter_symbols": ["TODO-check-named-parameters"],
        "missing_hypothesis_ids": ["TODO-check-hypotheses"],
        "coverage_gaps": [coverage_gap],
        "scope_status": "unclear",
        "quantifier_status": "unclear",
        "counterexample_status": "not_attempted",
    }


def _body_stub(
    *,
    claim_id: str,
    claim_text: str | None,
    proof_artifact_path: str,
    status: ProofRedteamSkeletonStatus,
) -> str:
    (
        root_heading,
        inventory_heading,
        ledger_heading,
        adversarial_heading,
        verdict_heading,
        follow_up_heading,
    ) = PROOF_REDTEAM_REQUIRED_SECTIONS
    (
        named_parameter_heading,
        hypothesis_heading,
        quantifier_heading,
        conclusion_heading,
    ) = PROOF_REDTEAM_REQUIRED_COVERAGE_SUBSECTIONS
    proof_location = f"{proof_artifact_path}:TODO"
    claim_line = claim_text or f"TODO exact statement for {claim_id}"
    return (
        f"{root_heading}\n\n"
        f"{inventory_heading}\n\n"
        f"- Exact claim / theorem text: {claim_line}\n"
        "- Claim / theorem target: TODO identify the theorem target under audit.\n"
        "- Named parameters:\n"
        "  - TODO list each named parameter or state that none appear.\n"
        "- Hypotheses:\n"
        "  - TODO list each hypothesis or state that none appear.\n"
        "- Quantifier / domain obligations:\n"
        "  - TODO list every quantifier and domain obligation.\n"
        "- Conclusion clauses:\n"
        "  - TODO list each conclusion clause that the proof must establish.\n\n"
        f"{ledger_heading}\n\n"
        f"{named_parameter_heading}\n\n"
        "| Parameter | Role / Domain | Proof Location | Status | Notes |\n"
        "| --- | --- | --- | --- | --- |\n"
        f"| TODO | TODO | {proof_location} | open | Builder skeleton; audit needed. |\n\n"
        f"{hypothesis_heading}\n\n"
        "| Hypothesis | Proof Location | Status | Notes |\n"
        "| --- | --- | --- | --- |\n"
        f"| TODO | {proof_location} | open | Builder skeleton; audit needed. |\n\n"
        f"{quantifier_heading}\n\n"
        "| Obligation | Proof Location | Status | Notes |\n"
        "| --- | --- | --- | --- |\n"
        f"| TODO | {proof_location} | open | Builder skeleton; audit needed. |\n\n"
        f"{conclusion_heading}\n\n"
        "| Clause | Proof Location | Status | Notes |\n"
        "| --- | --- | --- | --- |\n"
        f"| TODO | {proof_location} | open | Builder skeleton; audit needed. |\n\n"
        f"{adversarial_heading}\n\n"
        "- Probe type: TODO counterexample attempt, boundary case, dropped-parameter test, or narrower-case challenge.\n"
        "- Result: TODO record the adversarial result before closure.\n\n"
        f"{verdict_heading}\n\n"
        "- Scope status: `unclear`\n"
        "- Quantifier status: `unclear`\n"
        "- Counterexample status: `not_attempted`\n"
        "- Blocking gaps:\n"
        f"  - Current skeleton status is `{status}`; replace TODO coverage before closure.\n\n"
        f"{follow_up_heading}\n\n"
        "- Replace every TODO with exact proof locations, structured gaps, and required repair work.\n"
    )


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_proof_artifact_paths(values: Iterable[str]) -> tuple[str, ...]:
    normalized = _dedupe(value.strip() for value in values if value.strip())
    return tuple(normalized) if normalized else (_PLACEHOLDER_PROOF_ARTIFACT_PATH,)


def _normalize_reviewed_at(value: str | None) -> str | None:
    if value is None:
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    normalized = value.strip()
    return normalized or None


def _normalize_finalizer_manuscript_fields(
    *,
    expected_manuscript_path: str | None,
    expected_manuscript_sha256: str | None,
    expected_round: int | None,
) -> tuple[dict[str, object], str | None]:
    return _normalize_scoped_manuscript_fields(
        manuscript_path=expected_manuscript_path,
        manuscript_sha256=expected_manuscript_sha256,
        round_number=expected_round,
        incomplete_error=(
            "manuscript-scoped proof-redteam finalization requires expected_manuscript_path, "
            "expected_manuscript_sha256, and expected_round"
        ),
        path_field_name="expected_manuscript_path",
        sha_field_name="expected_manuscript_sha256",
        round_field_name="expected_round",
    )


def _normalize_manuscript_fields(
    *,
    manuscript_path: str | None,
    manuscript_sha256: str | None,
    round_number: int | None,
) -> dict[str, object]:
    fields, error = _normalize_scoped_manuscript_fields(
        manuscript_path=manuscript_path,
        manuscript_sha256=manuscript_sha256,
        round_number=round_number,
        incomplete_error=(
            "manuscript-scoped proof-redteam skeletons require manuscript_path, manuscript_sha256, and round_number"
        ),
        path_field_name="manuscript_path",
        sha_field_name="manuscript_sha256",
        round_field_name="round_number",
    )
    if error is not None:
        raise ValueError(error)
    return fields


def _normalize_scoped_manuscript_fields(
    *,
    manuscript_path: str | None,
    manuscript_sha256: str | None,
    round_number: int | None,
    incomplete_error: str,
    path_field_name: str,
    sha_field_name: str,
    round_field_name: str,
) -> tuple[dict[str, object], str | None]:
    provided = (
        manuscript_path is not None,
        manuscript_sha256 is not None,
        round_number is not None,
    )
    if any(provided) and not all(provided):
        return {}, incomplete_error
    if not any(provided):
        return {}, None
    normalized_manuscript_path = manuscript_path.strip() if manuscript_path is not None else ""
    normalized_manuscript_sha256 = manuscript_sha256.strip().lower() if manuscript_sha256 is not None else ""
    if not normalized_manuscript_path:
        return {}, f"{path_field_name} must not be blank"
    if len(normalized_manuscript_sha256) != 64 or any(
        char not in "0123456789abcdef" for char in normalized_manuscript_sha256
    ):
        return {}, f"{sha_field_name} must be a lowercase 64-hex digest"
    if round_number is None or round_number < 1:
        return {}, f"{round_field_name} must be a positive integer"
    return {
        "manuscript_path": normalized_manuscript_path,
        "manuscript_sha256": normalized_manuscript_sha256,
        "round": round_number,
    }, None


class _FinalizerProofArtifactPathResolution(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid", arbitrary_types_allowed=True)

    resolved_path: Path | None = None
    redteam_path: str | None = None
    audit_path: str | None = None
    error: str | None = None


def _resolve_finalizer_proof_artifact_path(
    value: str | Path,
    *,
    project_root: Path,
    artifact_dir: Path,
) -> _FinalizerProofArtifactPathResolution:
    raw_text = str(value).strip()
    if not raw_text:
        return _FinalizerProofArtifactPathResolution(error="proof_artifact_path must not be blank")

    raw_path = Path(raw_text).expanduser()
    if raw_path.is_absolute():
        candidates = [raw_path.resolve(strict=False)]
    else:
        candidates = [
            (project_root / raw_path).resolve(strict=False),
            (artifact_dir / raw_path).resolve(strict=False),
        ]

    resolved_path = next((candidate for candidate in candidates if candidate.exists() and candidate.is_file()), None)
    if resolved_path is None:
        return _FinalizerProofArtifactPathResolution(
            error=f"proof_artifact_path does not resolve to a readable file: {raw_text}"
        )

    project_relative = _relative_path_label(resolved_path, project_root)
    if project_relative is None:
        return _FinalizerProofArtifactPathResolution(error="proof_artifact_path must resolve inside the project root")

    audit_relative = _relative_path_label(resolved_path, artifact_dir) or project_relative
    return _FinalizerProofArtifactPathResolution(
        resolved_path=resolved_path,
        redteam_path=project_relative,
        audit_path=audit_relative,
    )


def _resolve_io_path(value: str | Path, project_root: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = project_root / path
    return path.resolve(strict=False)


def _relative_path_label(path: Path, base: Path) -> str | None:
    try:
        return path.resolve(strict=False).relative_to(base.resolve(strict=False)).as_posix()
    except ValueError:
        return None


def _render_finalized_markdown(frontmatter: dict[str, object], body: str) -> str:
    rendered_body = body.lstrip().rstrip()
    return f"{render_proof_redteam_frontmatter_yaml(frontmatter).rstrip()}\n\n{rendered_body}\n"


def _validate_candidate_markdown(
    content: str,
    *,
    target_path: Path,
    project_root: Path,
    expected_claim_ids: tuple[str, ...],
    expected_proof_artifact_paths: tuple[str, ...],
    expected_manuscript_path: str | None,
    expected_manuscript_sha256: str | None,
    expected_round: int | None,
) -> ProofRedteamValidationResult:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=target_path.parent,
            prefix=f".{target_path.name}.candidate.",
            suffix=".md",
            delete=False,
        ) as handle:
            tmp_path = Path(handle.name)
            handle.write(content)
        return validate_proof_redteam_artifact(
            tmp_path,
            project_root=project_root,
            expected_claim_ids=expected_claim_ids,
            expected_proof_artifact_paths=expected_proof_artifact_paths,
            expected_manuscript_path=expected_manuscript_path,
            expected_manuscript_sha256=expected_manuscript_sha256,
            expected_round=expected_round,
        )
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _audit_artifact_path_label(target_path: Path) -> str:
    return target_path.name


def _build_downstream_proof_audit(
    *,
    proof_artifact_path: str,
    proof_artifact_sha256: str,
    audit_artifact_path: str,
    audit_artifact_sha256: str,
    claim_statement_sha256: str,
    reviewed_at: str,
) -> dict[str, object]:
    return {
        "completeness": "complete",
        "reviewed_at": reviewed_at,
        "reviewer": PROOF_AUDIT_REVIEWER,
        "proof_artifact_path": proof_artifact_path,
        "proof_artifact_sha256": proof_artifact_sha256,
        "audit_artifact_path": audit_artifact_path,
        "audit_artifact_sha256": audit_artifact_sha256,
        "claim_statement_sha256": claim_statement_sha256,
        "covered_hypothesis_ids": [],
        "missing_hypothesis_ids": [],
        "covered_parameter_symbols": [],
        "missing_parameter_symbols": [],
        "uncovered_quantifiers": [],
        "uncovered_conclusion_clause_ids": [],
        "quantifier_status": "matched",
        "scope_status": "matched",
        "counterexample_status": "none_found",
        "stale": False,
    }


def _invalid_finalization_result(
    path: str,
    error: str,
    *,
    reviewed_at: str | None = None,
) -> ProofRedteamFinalizationResult:
    return ProofRedteamFinalizationResult(
        path=path,
        valid=False,
        errors=[error],
        reviewed_at=reviewed_at,
    )


def _authoring_rules() -> list[str]:
    return [
        "Keep the generated status as gaps_found or human_needed until a separate proof critic supplies a complete audit.",
        "Keep reviewer as gpd-check-proof for proof-redteam artifacts.",
        "Replace TODO rows with exact proof locations and structured coverage findings.",
        "Keep structured frontmatter fields synchronized with the verdict section.",
    ]


def _warnings() -> list[str]:
    return [
        "Generated frontmatter is schema-owned; regenerate it from typed inputs instead of hand-authoring YAML.",
        "This skeleton does not decide proof validity.",
        "Validate the completed artifact before any workflow relies on it.",
    ]


def _markdown_list_section(title: str, items: Iterable[str]) -> str:
    entries = [item.strip() for item in items if item.strip()]
    if not entries:
        return ""
    return f"## {title}\n\n" + "\n".join(f"- {entry}" for entry in entries)


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
