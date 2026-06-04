"""Typed builders for verification report frontmatter skeletons."""

from __future__ import annotations

import shlex
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from gpd.contracts import (
    ComparisonVerdict,
    ContractEvidenceStatus,
    ContractForbiddenProxyResult,
    ContractForbiddenProxyStatus,
    ContractProofAudit,
    ContractReference,
    ContractReferenceAction,
    ContractReferenceActionStatus,
    ContractReferenceUsage,
    ContractResultEntry,
    ResearchContract,
    SuggestedContractCheck,
    VerificationEvidence,
)
from gpd.core.contract_skeletons import build_contract_results_skeleton

__all__ = [
    "VERIFICATION_REPORT_BODY_CONTRACT",
    "VerificationComparisonVerdictPatch",
    "VerificationForbiddenProxyOutcomePatch",
    "VerificationReportComposition",
    "VerificationReportOutcomePatch",
    "VerificationReportSkeleton",
    "VerificationReferenceActionPatch",
    "VerificationSuggestedCheckPatch",
    "VerificationTargetOutcomePatch",
    "VerificationReportValidationMode",
    "VerificationReportValidationResult",
    "build_verification_gap_report_frontmatter",
    "build_verification_report_skeleton",
    "compose_verification_report_markdown",
    "finalize_verification_report",
    "render_verification_report_frontmatter_yaml",
    "render_verification_report_markdown",
    "validate_rendered_verification_report",
]

_DEFAULT_VERIFIED_AT = "1970-01-01T00:00:00Z"
_DEFAULT_PLAN_CONTRACT_REF = "GPD/phases/UNKNOWN/UNKNOWN-PLAN.md#/contract"
_FALLBACK_TARGET_REPORT_PATH = "VERIFICATION.md"
VERIFICATION_REPORT_BODY_CONTRACT = (
    "`BODY.md` is body-only Markdown: include one fenced executed `python`/`bash` block, an adjacent "
    "`**Output:**` plus fenced `output` block, then a following `PASS`/`FAIL`/`INCONCLUSIVE` "
    "verdict line; prose bullets alone are invalid."
)

VerificationReportValidationMode = Literal["none", "frontmatter", "contract"]
VerificationReportStatus = Literal["passed", "gaps_found", "expert_needed", "human_needed"]
VerificationTargetKind = Literal["claim", "deliverable", "acceptance_test"]


class VerificationReportSkeleton(BaseModel):
    """Typed payload for copy-safe verification report skeletons."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    frontmatter: dict[str, object]
    frontmatter_yaml: str
    markdown_draft: str
    body_stub: str
    body_contract: str
    body_template: str
    validation_commands: list[str] = Field(default_factory=list)
    authoring_rules: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    plan_path: str | None = None
    plan_contract_ref: str
    target_status: Literal["gaps_found"] = "gaps_found"
    target_report_path: str | None = None
    target_report_ref: str | None = None


class VerificationTargetOutcomePatch(BaseModel):
    """Typed patch for one claim, deliverable, or acceptance-test result."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    target_kind: VerificationTargetKind
    target_id: str
    status: ContractEvidenceStatus
    summary: str | None = None
    evidence: list[VerificationEvidence] = Field(default_factory=list)
    notes: str | None = None
    linked_ids: list[str] = Field(default_factory=list)
    path: str | None = None
    proof_audit: ContractProofAudit | None = None

    def to_contract_result_entry(self) -> ContractResultEntry:
        """Return the strict contract-results entry represented by this patch."""

        return ContractResultEntry(
            status=self.status,
            summary=self.summary,
            evidence=self.evidence,
            notes=self.notes,
            linked_ids=self.linked_ids,
            path=self.path,
            proof_audit=self.proof_audit,
        )


class VerificationReferenceActionPatch(BaseModel):
    """Typed patch for one reference-action ledger entry."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    reference_id: str
    status: ContractReferenceActionStatus
    completed_actions: list[ContractReferenceAction] = Field(default_factory=list)
    missing_actions: list[ContractReferenceAction] = Field(default_factory=list)
    summary: str | None = None
    evidence: list[VerificationEvidence] = Field(default_factory=list)

    def to_contract_reference_usage(self) -> ContractReferenceUsage:
        """Return the strict contract reference-usage entry represented by this patch."""

        return ContractReferenceUsage(
            status=self.status,
            completed_actions=self.completed_actions,
            missing_actions=self.missing_actions,
            summary=self.summary,
            evidence=self.evidence,
        )


class VerificationForbiddenProxyOutcomePatch(BaseModel):
    """Typed patch for one forbidden-proxy verification outcome."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    forbidden_proxy_id: str
    status: ContractForbiddenProxyStatus
    notes: str | None = None
    evidence: list[VerificationEvidence] = Field(default_factory=list)

    def to_contract_forbidden_proxy_result(self) -> ContractForbiddenProxyResult:
        """Return the strict forbidden-proxy result represented by this patch."""

        return ContractForbiddenProxyResult(
            status=self.status,
            notes=self.notes,
            evidence=self.evidence,
        )


class VerificationComparisonVerdictPatch(ComparisonVerdict):
    """Named finalizer patch model that reuses the strict comparison verdict schema."""


class VerificationSuggestedCheckPatch(SuggestedContractCheck):
    """Named finalizer patch model that reuses the strict suggested-check schema."""


class VerificationReportOutcomePatch(BaseModel):
    """Typed patch applied by the verification-report finalizer."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    status: VerificationReportStatus = "gaps_found"
    verified: str | None = None
    phase: str | None = None
    score: str | None = None
    target_outcomes: list[VerificationTargetOutcomePatch] = Field(default_factory=list)
    reference_actions: list[VerificationReferenceActionPatch] = Field(default_factory=list)
    forbidden_proxy_outcomes: list[VerificationForbiddenProxyOutcomePatch] = Field(default_factory=list)
    comparison_verdicts: list[VerificationComparisonVerdictPatch] | None = None
    suggested_contract_checks: list[VerificationSuggestedCheckPatch] | None = None


class VerificationReportValidationResult(BaseModel):
    """Structured validation outcome for a rendered verification report."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    mode: VerificationReportValidationMode
    valid: bool
    missing: list[str] = Field(default_factory=list)
    present: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    schema_name: str | None = None
    oracle_evidence_count: int | None = None


class VerificationReportComposition(BaseModel):
    """Rendered verification report plus optional validation result."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    frontmatter_yaml: str
    markdown: str
    validation: VerificationReportValidationResult


def build_verification_gap_report_frontmatter(
    contract: ResearchContract,
    *,
    phase: str = "unknown",
    verified: str | None = None,
    plan_contract_ref: str = _DEFAULT_PLAN_CONTRACT_REF,
    score: str | None = None,
    verification_report_path: str | None = None,
) -> dict[str, object]:
    """Return a schema-valid verification gap report frontmatter skeleton.

    The builder is intentionally conservative: it records every contract ID, marks
    claim/test work as blocked until a verifier supplies real evidence, and
    represents unresolved benchmark/cross-method anchors as inconclusive gaps.
    It does not judge physics and does not include runtime return envelopes.
    """

    comparison_verdicts = _comparison_verdicts_for_gap_skeleton(contract)
    suggested_checks = _suggested_contract_checks_for_gap_skeleton(
        contract,
        evidence_path=verification_report_path,
    )

    return {
        "phase": phase,
        "verified": verified if verified is not None else _DEFAULT_VERIFIED_AT,
        "status": "gaps_found",
        "score": score if score is not None else _gap_score(contract),
        "plan_contract_ref": plan_contract_ref,
        "contract_results": build_contract_results_skeleton(contract, target="verification"),
        "comparison_verdicts": [verdict.model_dump(mode="json", exclude_none=True) for verdict in comparison_verdicts],
        "suggested_contract_checks": [check.model_dump(mode="json", exclude_none=True) for check in suggested_checks],
    }


def build_verification_report_skeleton(
    *,
    contract: ResearchContract,
    plan_path: str | Path | None = None,
    plan_contract_ref: str = _DEFAULT_PLAN_CONTRACT_REF,
    status: str = "gaps_found",
    verified: str | None = None,
    score: str | None = None,
) -> VerificationReportSkeleton:
    """Return an agent-facing verification report skeleton payload.

    The current typed builder intentionally supports only gap reports: a
    skeleton cannot certify a passed verification. Callers that want a
    successful report must supply real verifier evidence and pass validation.
    """

    if status != "gaps_found":
        raise ValueError(
            "verification-report skeleton cannot certify passed reports; only status='gaps_found' is supported"
        )

    plan = Path(plan_path) if plan_path is not None else None
    resolved_plan_contract_ref = plan_contract_ref
    if plan is not None and plan_contract_ref == _DEFAULT_PLAN_CONTRACT_REF:
        plan_ref = _project_relative_ref(plan.as_posix()) or plan.as_posix()
        resolved_plan_contract_ref = f"{plan_ref}#/contract"
    target_report_path = _verification_report_path_from_plan(plan)
    target_report_ref = _project_relative_ref(target_report_path)
    frontmatter = build_verification_gap_report_frontmatter(
        contract,
        phase=_phase_from_plan_path(plan),
        verified=verified,
        plan_contract_ref=resolved_plan_contract_ref,
        score=score,
        verification_report_path=target_report_ref or target_report_path,
    )
    validation_commands = _validation_commands(target_report_ref or target_report_path)
    body_contract = VERIFICATION_REPORT_BODY_CONTRACT
    body_template = _body_template()
    body_stub = _body_stub(
        validation_commands,
        body_contract=body_contract,
        body_template=body_template,
    )
    frontmatter_yaml = render_verification_report_frontmatter_yaml(
        frontmatter,
        target_report_ref=target_report_ref,
    )
    authoring_rules = _authoring_rules()
    warnings = _warnings()
    return VerificationReportSkeleton(
        frontmatter=frontmatter,
        frontmatter_yaml=frontmatter_yaml,
        markdown_draft=render_verification_report_markdown(
            frontmatter_yaml,
            body_stub,
            authoring_rules=authoring_rules,
            warnings=warnings,
        ),
        body_stub=body_stub,
        body_contract=body_contract,
        body_template=body_template,
        validation_commands=validation_commands,
        authoring_rules=authoring_rules,
        warnings=warnings,
        plan_path=None if plan is None else str(plan),
        plan_contract_ref=resolved_plan_contract_ref,
        target_status=status,
        target_report_path=target_report_path,
        target_report_ref=target_report_ref,
    )


def finalize_verification_report(
    *,
    contract: ResearchContract,
    outcome: VerificationReportOutcomePatch,
    body_markdown: str,
    plan_path: str | Path | None = None,
    plan_contract_ref: str = _DEFAULT_PLAN_CONTRACT_REF,
    target_report_ref: str | None = None,
    source_path: str | Path | None = None,
) -> VerificationReportComposition:
    """Finalize a verification report from typed patches and body-only evidence.

    The finalizer owns mechanical frontmatter construction only. It still
    delegates acceptance of ``passed`` and oracle evidence to the existing
    verification-contract validators.
    """

    if _body_markdown_starts_with_frontmatter(body_markdown):
        raise ValueError("verification report body_markdown must be body-only Markdown without YAML frontmatter")

    plan = Path(plan_path) if plan_path is not None else None
    resolved_plan_contract_ref = plan_contract_ref
    if plan is not None and plan_contract_ref == _DEFAULT_PLAN_CONTRACT_REF:
        plan_ref = _project_relative_ref(plan.as_posix()) or plan.as_posix()
        resolved_plan_contract_ref = f"{plan_ref}#/contract"

    report_source_path = Path(source_path) if source_path is not None else _source_path_from_plan(plan)
    resolved_target_report_ref = target_report_ref
    if resolved_target_report_ref is None:
        resolved_target_report_ref = _target_report_ref_from_plan_or_source(plan, report_source_path)

    frontmatter = build_verification_report_frontmatter_from_patch(
        contract,
        outcome,
        phase=outcome.phase or _phase_from_plan_path(plan),
        plan_contract_ref=resolved_plan_contract_ref,
        target_report_ref=resolved_target_report_ref,
    )
    return compose_verification_report_markdown(
        frontmatter,
        body_markdown,
        target_report_ref=resolved_target_report_ref,
        source_path=report_source_path,
        validation_mode="contract",
    )


def build_verification_report_frontmatter_from_patch(
    contract: ResearchContract,
    outcome: VerificationReportOutcomePatch,
    *,
    phase: str = "unknown",
    plan_contract_ref: str = _DEFAULT_PLAN_CONTRACT_REF,
    target_report_ref: str | None = None,
) -> dict[str, object]:
    """Return canonical verification frontmatter from a typed outcome patch."""

    contract_results = _contract_results_from_outcome_patch(contract, outcome)
    comparison_verdicts = _comparison_verdicts_from_outcome_patch(contract, outcome)
    suggested_checks = _suggested_checks_from_outcome_patch(
        contract,
        outcome,
        evidence_path=target_report_ref,
    )
    return {
        "phase": phase,
        "verified": outcome.verified or _DEFAULT_VERIFIED_AT,
        "status": outcome.status,
        "score": outcome.score or _score_from_outcome(contract, outcome),
        "plan_contract_ref": plan_contract_ref,
        "contract_results": contract_results,
        "comparison_verdicts": [verdict.model_dump(mode="json", exclude_none=True) for verdict in comparison_verdicts],
        "suggested_contract_checks": [check.model_dump(mode="json", exclude_none=True) for check in suggested_checks],
    }


def render_verification_report_frontmatter_yaml(
    frontmatter: dict[str, object],
    *,
    target_report_ref: str | None = None,
) -> str:
    """Return copy-safe YAML frontmatter with delimiters.

    The raw ``frontmatter`` remains schema-shaped. This renderer removes empty
    list fields that are easy to fill incorrectly by hand.
    """

    copy_safe = _copy_safe_frontmatter(frontmatter, target_report_ref=target_report_ref)
    yaml_str = yaml.dump(
        copy_safe,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=999999,
    ).rstrip()
    return f"---\n{yaml_str}\n---\n"


def render_verification_report_markdown(
    frontmatter_yaml: str,
    body_stub: str,
    *,
    authoring_rules: Iterable[str] = (),
    warnings: Iterable[str] = (),
) -> str:
    """Return a copy-safe Markdown verification draft."""

    sections = [body_stub.rstrip()]
    warning_section = _markdown_list_section("Generated Warnings", warnings)
    if warning_section:
        sections.append(warning_section)
    rules_section = _markdown_list_section("Generated Frontmatter Rules", authoring_rules)
    if rules_section:
        sections.append(rules_section)
    rendered_body = "\n\n".join(section for section in sections if section)
    return f"{frontmatter_yaml.rstrip()}\n\n{rendered_body}\n"


def compose_verification_report_markdown(
    frontmatter: dict[str, object],
    body_markdown: str,
    *,
    target_report_ref: str | None = None,
    source_path: str | Path | None = None,
    validation_mode: VerificationReportValidationMode = "none",
) -> VerificationReportComposition:
    """Render generated frontmatter with caller-supplied body Markdown.

    ``body_markdown`` is body-only content. It is never parsed as YAML and must
    carry runtime transcripts, hashes, oracle output, and ``gpd_return`` prose
    outside the schema-owned frontmatter.
    """

    frontmatter_yaml = render_verification_report_frontmatter_yaml(
        frontmatter,
        target_report_ref=target_report_ref,
    )
    markdown = render_verification_report_markdown(frontmatter_yaml, body_markdown)
    validation = validate_rendered_verification_report(
        markdown,
        source_path=source_path,
        mode=validation_mode,
    )
    return VerificationReportComposition(
        frontmatter_yaml=frontmatter_yaml,
        markdown=markdown,
        validation=validation,
    )


def validate_rendered_verification_report(
    markdown: str,
    *,
    source_path: str | Path | None = None,
    mode: VerificationReportValidationMode = "frontmatter",
) -> VerificationReportValidationResult:
    """Validate rendered report Markdown through existing validators."""

    if mode == "none":
        return VerificationReportValidationResult(mode=mode, valid=True)
    if mode not in {"frontmatter", "contract"}:
        raise ValueError("verification report validation mode must be one of: none, frontmatter, contract")

    path = Path(source_path) if source_path is not None else None
    try:
        from gpd.core.frontmatter import FrontmatterParseError, FrontmatterValidationError, validate_frontmatter

        schema_result = validate_frontmatter(markdown, "verification", source_path=path)
    except (FrontmatterParseError, FrontmatterValidationError) as exc:
        return VerificationReportValidationResult(
            mode=mode,
            valid=False,
            errors=[f"{type(exc).__name__}: {exc}"],
            schema_name="verification",
        )

    errors = list(schema_result.errors)
    oracle_evidence_count: int | None = None
    if mode == "contract":
        from gpd.core.correctness_validators import validate_verification_oracle_evidence

        oracle_result = validate_verification_oracle_evidence(markdown, source_path=path)
        errors.extend(oracle_result.errors)
        oracle_evidence_count = oracle_result.evidence_count

    return VerificationReportValidationResult(
        mode=mode,
        valid=len(schema_result.missing) == 0 and not errors,
        missing=list(schema_result.missing),
        present=list(schema_result.present),
        errors=errors,
        schema_name=schema_result.schema_name,
        oracle_evidence_count=oracle_evidence_count,
    )


def _phase_from_plan_path(plan_path: Path | None) -> str:
    if plan_path is None:
        return "unknown"
    parent = plan_path.parent
    if parent.name:
        return parent.name
    return "unknown"


def _verification_report_path_from_plan(plan_path: Path | None) -> str | None:
    if plan_path is None:
        return None
    name = plan_path.name
    if "PLAN.md" in name:
        return str(plan_path.with_name(name.replace("PLAN.md", "VERIFICATION.md")))
    return str(plan_path.with_name("VERIFICATION.md"))


def _source_path_from_plan(plan_path: Path | None) -> Path | None:
    target_path = _verification_report_path_from_plan(plan_path)
    return Path(target_path) if target_path is not None else None


def _target_report_ref_from_plan_or_source(plan_path: Path | None, source_path: Path | None) -> str | None:
    source_ref = _project_relative_ref(source_path.as_posix()) if source_path is not None else None
    if source_ref is not None:
        return source_ref
    target_path = _verification_report_path_from_plan(plan_path)
    return _project_relative_ref(target_path)


def _project_relative_ref(path_text: str | None) -> str | None:
    if path_text is None:
        return None
    path = Path(path_text)
    parts = path.parts
    if "GPD" in parts:
        return Path(*parts[parts.index("GPD") :]).as_posix()
    return path.as_posix()


def _body_markdown_starts_with_frontmatter(body_markdown: str) -> bool:
    stripped = body_markdown.lstrip("\ufeff \t\r\n")
    return stripped == "---" or stripped.startswith("---\n") or stripped.startswith("---\r\n")


def _contract_results_from_outcome_patch(
    contract: ResearchContract,
    outcome: VerificationReportOutcomePatch,
) -> dict[str, object]:
    contract_results = build_contract_results_skeleton(contract, target="verification")

    for patch in outcome.target_outcomes:
        section = _target_outcome_section(patch.target_kind)
        entries = contract_results.get(section)
        if not isinstance(entries, dict):
            entries = {}
            contract_results[section] = entries
        entries[patch.target_id] = patch.to_contract_result_entry().model_dump(mode="json", exclude_none=True)

    references = contract_results.get("references")
    if not isinstance(references, dict):
        references = {}
        contract_results["references"] = references
    for patch in outcome.reference_actions:
        references[patch.reference_id] = patch.to_contract_reference_usage().model_dump(mode="json", exclude_none=True)

    forbidden_proxies = contract_results.get("forbidden_proxies")
    if not isinstance(forbidden_proxies, dict):
        forbidden_proxies = {}
        contract_results["forbidden_proxies"] = forbidden_proxies
    for patch in outcome.forbidden_proxy_outcomes:
        forbidden_proxies[patch.forbidden_proxy_id] = patch.to_contract_forbidden_proxy_result().model_dump(
            mode="json",
            exclude_none=True,
        )

    return contract_results


def _comparison_verdicts_from_outcome_patch(
    contract: ResearchContract,
    outcome: VerificationReportOutcomePatch,
) -> list[ComparisonVerdict]:
    if outcome.comparison_verdicts is not None:
        return [
            ComparisonVerdict.model_validate(verdict.model_dump(mode="json")) for verdict in outcome.comparison_verdicts
        ]
    if outcome.status == "passed":
        return []
    return _comparison_verdicts_for_gap_skeleton(contract)


def _suggested_checks_from_outcome_patch(
    contract: ResearchContract,
    outcome: VerificationReportOutcomePatch,
    *,
    evidence_path: str | None,
) -> list[SuggestedContractCheck]:
    if outcome.suggested_contract_checks is not None:
        return [
            SuggestedContractCheck.model_validate(check.model_dump(mode="json"))
            for check in outcome.suggested_contract_checks
        ]
    if outcome.status == "passed":
        return []
    return _suggested_contract_checks_for_gap_skeleton(contract, evidence_path=evidence_path)


def _target_outcome_section(target_kind: VerificationTargetKind) -> str:
    return {
        "claim": "claims",
        "deliverable": "deliverables",
        "acceptance_test": "acceptance_tests",
    }[target_kind]


def _score_from_outcome(contract: ResearchContract, outcome: VerificationReportOutcomePatch) -> str:
    target_count = len(contract.claims) + len(contract.deliverables) + len(contract.acceptance_tests)
    if outcome.status == "passed":
        return f"{target_count}/{target_count} contract targets passed"
    return _gap_score(contract)


def _validation_commands(target_report_path: str | None) -> list[str]:
    target = target_report_path or _FALLBACK_TARGET_REPORT_PATH
    quoted_target = shlex.quote(target)
    return [
        f"gpd frontmatter validate {quoted_target} --schema verification",
        f"gpd validate verification-contract {quoted_target}",
    ]


def _authoring_rules() -> list[str]:
    return [
        "Use frontmatter_yaml as the starting YAML; do not hand-convert the raw JSON payload.",
        "Keep top-level status as gaps_found until independent verification evidence supports a different report.",
        "Do not put prose strings in contract_results evidence lists; structured evidence items must be objects.",
        "Keep runtime metadata, gpd_return, and oracle transcript details in the Markdown body, not frontmatter.",
        "Use only PLAN contract IDs in contract_results, comparison_verdicts, and suggested_contract_checks.",
    ]


def _warnings() -> list[str]:
    return [
        "Generated frontmatter is schema-owned; regenerate it with typed inputs instead of hand-authoring YAML.",
        "Put hashes, command transcripts, oracle output, and gpd_return data in the Markdown body or return envelope.",
        "Validate after any report write before claiming the report as current or completed.",
    ]


def _markdown_list_section(title: str, items: Iterable[str]) -> str:
    entries = [item.strip() for item in items if item.strip()]
    if not entries:
        return ""
    return f"## {title}\n\n" + "\n".join(f"- {entry}" for entry in entries)


def _body_template() -> str:
    return (
        "### Computational Oracle: replace with executed check name\n\n"
        "```python\n"
        "# Replace this block with the exact Python or bash check you executed.\n"
        "# Keep hashes, command transcripts, and oracle details in the body, not frontmatter.\n"
        'raise SystemExit("template only - replace before validation")\n'
        "```\n\n"
        "**Output:**\n\n"
        "```output\n"
        "not executed - replace with the exact stdout/stderr from the command\n"
        "```\n\n"
        "**Verdict:** PASS/FAIL/INCONCLUSIVE - replace with one verdict tied to the output."
    )


def _body_stub(
    validation_commands: list[str],
    *,
    body_contract: str,
    body_template: str,
) -> str:
    commands_block = "\n".join(f"- `{command}`" for command in validation_commands)
    return (
        "# Verification Draft\n\n"
        "## Verdict\n\n"
        "Draft gap report. Replace this paragraph with the verification conclusion after running the required checks.\n\n"
        "## Evidence\n\n"
        f"{body_contract}\n\n"
        f"{body_template}\n\n"
        "Replace the template before contract validation; do not invent output or reuse stale evidence.\n\n"
        "## Gaps\n\n"
        "Explain unresolved contract targets, missing references, and follow-up checks here.\n\n"
        "## Validation\n\n"
        f"{commands_block}\n"
    )


def _copy_safe_frontmatter(
    frontmatter: dict[str, object],
    *,
    target_report_ref: str | None,
) -> dict[str, object]:
    copy_safe = _prune_empty_authoring_bait(frontmatter)
    if target_report_ref is not None:
        checks = copy_safe.get("suggested_contract_checks")
        if isinstance(checks, list):
            for check in checks:
                if isinstance(check, dict) and check.get("evidence_path") is not None:
                    check["evidence_path"] = target_report_ref
    return copy_safe


def _prune_empty_authoring_bait(value: object) -> object:
    if isinstance(value, dict):
        pruned: dict[str, object] = {}
        for key, child in value.items():
            if key in {"evidence", "linked_ids"} and child == []:
                continue
            pruned[key] = _prune_empty_authoring_bait(child)
        return pruned
    if isinstance(value, list):
        return [_prune_empty_authoring_bait(item) for item in value]
    return value


def _gap_score(contract: ResearchContract) -> str:
    target_count = len(contract.claims) + len(contract.deliverables) + len(contract.acceptance_tests)
    if target_count == 0:
        return "verification gaps found; no contract targets passed by this skeleton"
    return f"0/{target_count} contract targets passed by this skeleton; verification gaps require follow-up"


def _is_decisive_reference(reference: ContractReference) -> bool:
    return reference.role == "benchmark" or "compare" in reference.required_actions


def _comparison_kind_for_reference(reference: ContractReference) -> str:
    if reference.role == "benchmark":
        return "benchmark"
    if "compare" in reference.required_actions:
        return "cross_method"
    return "other"


def _comparison_verdicts_for_gap_skeleton(contract: ResearchContract) -> list[ComparisonVerdict]:
    reference_by_id = {reference.id: reference for reference in contract.references}
    claim_by_id = {claim.id: claim for claim in contract.claims}
    verdicts: list[ComparisonVerdict] = []

    for reference in contract.references:
        if not _is_decisive_reference(reference):
            continue
        comparison_kind = _comparison_kind_for_reference(reference)
        verdicts.append(
            ComparisonVerdict(
                subject_id=reference.id,
                subject_kind="reference",
                subject_role="decisive",
                comparison_kind=comparison_kind,
                metric="reference_actions",
                threshold="required reference actions completed",
                verdict="inconclusive",
                recommended_action=_recommended_action_for_comparison_kind(comparison_kind),
                notes="Required reference work remains unresolved in this gap skeleton.",
            )
        )

    for test in contract.acceptance_tests:
        if test.kind not in {"benchmark", "cross_method"}:
            continue
        reference_id = _reference_id_for_acceptance_test(
            test_subject=test.subject,
            evidence_required=test.evidence_required,
            reference_by_id=reference_by_id,
            claim_references=claim_by_id.get(test.subject).references if test.subject in claim_by_id else [],
        )
        if test.kind == "benchmark" and reference_id is None:
            continue
        verdicts.append(
            ComparisonVerdict(
                subject_id=test.id,
                subject_kind="acceptance_test",
                subject_role="decisive",
                reference_id=reference_id,
                comparison_kind=test.kind,
                metric="acceptance_condition",
                threshold=test.pass_condition,
                verdict="inconclusive",
                recommended_action=_recommended_action_for_comparison_kind(test.kind),
                notes="Decisive acceptance-test work remains unresolved in this gap skeleton.",
            )
        )

    return verdicts


def _reference_id_for_acceptance_test(
    *,
    test_subject: str,
    evidence_required: Iterable[str],
    reference_by_id: dict[str, ContractReference],
    claim_references: Iterable[str],
) -> str | None:
    del test_subject
    for candidate in (*tuple(evidence_required), *tuple(claim_references)):
        reference = reference_by_id.get(candidate)
        if reference is not None and _is_decisive_reference(reference):
            return candidate
    for reference in reference_by_id.values():
        if _is_decisive_reference(reference):
            return reference.id
    return next(iter(reference_by_id), None)


def _suggested_contract_checks_for_gap_skeleton(
    contract: ResearchContract,
    *,
    evidence_path: str | None,
) -> list[SuggestedContractCheck]:
    checks: list[SuggestedContractCheck] = []
    seen: set[tuple[str, str, str]] = set()

    for test in contract.acceptance_tests:
        if test.kind not in {"benchmark", "cross_method"}:
            continue
        _append_suggested_check(
            checks,
            seen=seen,
            check=_check_name_for_comparison_kind(test.kind),
            reason=(
                f"Decisive {test.kind} acceptance work remains unresolved; complete the check before marking it passed."
            ),
            suggested_subject_kind="acceptance_test",
            suggested_subject_id=test.id,
            evidence_path=evidence_path,
        )

    for reference in contract.references:
        if not _is_decisive_reference(reference):
            continue
        comparison_kind = _comparison_kind_for_reference(reference)
        _append_suggested_check(
            checks,
            seen=seen,
            check=_check_name_for_comparison_kind(comparison_kind),
            reason=(f"Required {comparison_kind} reference work remains unresolved for {reference.locator}."),
            suggested_subject_kind="reference",
            suggested_subject_id=reference.id,
            evidence_path=evidence_path,
        )

    return checks


def _append_suggested_check(
    checks: list[SuggestedContractCheck],
    *,
    seen: set[tuple[str, str, str]],
    check: str,
    reason: str,
    suggested_subject_kind: str,
    suggested_subject_id: str,
    evidence_path: str | None,
) -> None:
    key = (check, suggested_subject_kind, suggested_subject_id)
    if key in seen:
        return
    seen.add(key)
    checks.append(
        SuggestedContractCheck(
            check=check,
            reason=reason,
            suggested_subject_kind=suggested_subject_kind,
            suggested_subject_id=suggested_subject_id,
            evidence_path=evidence_path,
        )
    )


def _check_name_for_comparison_kind(comparison_kind: str) -> str:
    if comparison_kind == "cross_method":
        return "contract.cross_method_comparison"
    if comparison_kind == "benchmark":
        return "contract.benchmark_reproduction"
    return "contract.decisive_reference_check"


def _recommended_action_for_comparison_kind(comparison_kind: str) -> str:
    if comparison_kind == "cross_method":
        return "Complete the unresolved cross-method comparison and rerun verification."
    if comparison_kind == "benchmark":
        return "Restore or surface the benchmark reference and rerun the benchmark comparison."
    return "Complete the unresolved decisive reference work and rerun verification."
