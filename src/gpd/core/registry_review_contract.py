"""Review-contract registry projection helpers."""

from __future__ import annotations

from gpd.core.registry_types import (
    ReviewCommandContract,
    ReviewContractConditionalRequirement,
    ReviewContractScopeVariant,
)
from gpd.core.review_contract_prompt import normalize_review_contract_frontmatter_payload, render_review_contract_prompt


def render_review_contract_section(review_contract: ReviewCommandContract | None) -> str:
    """Render a model-visible review-contract block for command prompt bodies."""

    if review_contract is None:
        return ""
    return render_review_contract_prompt(review_contract)


def _parse_review_contract(raw: object, command_name: str) -> ReviewCommandContract | None:
    """Parse review-contract frontmatter through the canonical shared normalizer."""

    try:
        payload = normalize_review_contract_frontmatter_payload(raw)
    except ValueError as exc:
        raise ValueError(f"review-contract for {command_name}: {exc}") from exc

    if not payload:
        return None

    scope_variants_payload = list(payload["scope_variants"])
    if str(payload["review_mode"]) == "publication" and not scope_variants_payload:
        required_evidence = [str(item) for item in payload["required_evidence"]]
        if any("external-artifact review" in item.casefold() for item in required_evidence):
            scope_variants_payload = [
                {
                    "scope": "explicit_artifact",
                    "activation": "explicit external artifact subject was supplied",
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
                }
            ]

    return ReviewCommandContract(
        review_mode=str(payload["review_mode"]),
        required_outputs=list(payload["required_outputs"]),
        required_evidence=list(payload["required_evidence"]),
        blocking_conditions=list(payload["blocking_conditions"]),
        preflight_checks=list(payload["preflight_checks"]),
        stage_artifacts=list(payload["stage_artifacts"]),
        conditional_requirements=[
            ReviewContractConditionalRequirement(
                when=str(requirement["when"]),
                required_outputs=list(requirement.get("required_outputs", [])),
                required_evidence=list(requirement.get("required_evidence", [])),
                blocking_conditions=list(requirement.get("blocking_conditions", [])),
                preflight_checks=list(requirement.get("preflight_checks", [])),
                blocking_preflight_checks=list(requirement.get("blocking_preflight_checks", [])),
                stage_artifacts=list(requirement.get("stage_artifacts", [])),
            )
            for requirement in payload["conditional_requirements"]
        ],
        scope_variants=[
            ReviewContractScopeVariant(
                scope=str(variant["scope"]),
                activation=str(variant["activation"]),
                relaxed_preflight_checks=list(variant.get("relaxed_preflight_checks", [])),
                optional_preflight_checks=list(variant.get("optional_preflight_checks", [])),
                required_outputs_override=list(variant.get("required_outputs_override", [])),
                required_evidence_override=list(variant.get("required_evidence_override", [])),
                blocking_conditions_override=list(variant.get("blocking_conditions_override", [])),
            )
            for variant in scope_variants_payload
        ],
        required_state=str(payload["required_state"]),
        schema_version=int(payload["schema_version"]),
    )


__all__ = ["_parse_review_contract", "render_review_contract_section"]
