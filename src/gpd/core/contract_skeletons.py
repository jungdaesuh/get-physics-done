"""Reusable builders for contract-backed result skeletons."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from gpd.contracts import (
    ContractForbiddenProxyResult,
    ContractReference,
    ContractReferenceUsage,
    ContractResultEntry,
    ContractResults,
    ResearchContract,
)

__all__ = ["build_contract_results_skeleton"]

ContractResultsSkeletonTarget = Literal["summary", "verification"]


def build_contract_results_skeleton(
    contract: ResearchContract,
    *,
    target: ContractResultsSkeletonTarget,
) -> dict[str, object]:
    """Return a conservative ``contract_results`` skeleton for all contract IDs.

    The skeleton is intentionally non-passing: it enumerates the contract surface
    without inventing evidence, completed reference actions, or rejected
    forbidden-proxy checks.
    """

    if target not in {"summary", "verification"}:
        raise ValueError("contract_results skeleton target must be one of: summary, verification")

    prefix = _summary_prefix_for_target(target)
    contract_results = ContractResults(
        claims={
            claim.id: ContractResultEntry(
                status="blocked",
                summary=f"{prefix}: this claim needs independent evidence before it can pass.",
                linked_ids=_dedupe((*claim.deliverables, *claim.acceptance_tests, *claim.references)),
            )
            for claim in contract.claims
        },
        deliverables={
            deliverable.id: ContractResultEntry(
                status="not_attempted",
                summary=f"{prefix}: this deliverable has not been judged by the builder.",
                path=deliverable.path,
            )
            for deliverable in contract.deliverables
        },
        acceptance_tests={
            test.id: ContractResultEntry(
                status="blocked",
                summary=f"{prefix}: this acceptance test needs decisive verification evidence.",
                linked_ids=_dedupe((test.subject, *test.evidence_required)),
            )
            for test in contract.acceptance_tests
        },
        references={
            reference.id: _reference_usage_for_skeleton(reference, prefix=prefix) for reference in contract.references
        },
        forbidden_proxies={
            proxy.id: ContractForbiddenProxyResult(
                status="unresolved",
                notes=f"{prefix}: this forbidden proxy has not yet been independently rejected.",
            )
            for proxy in contract.forbidden_proxies
        },
        uncertainty_markers=contract.uncertainty_markers,
    )

    return contract_results.model_dump(mode="json", exclude_none=True)


def _summary_prefix_for_target(target: ContractResultsSkeletonTarget) -> str:
    if target == "verification":
        return "Verification gap skeleton"
    return "Summary skeleton"


def _reference_usage_for_skeleton(reference: ContractReference, *, prefix: str) -> ContractReferenceUsage:
    if _is_decisive_reference(reference) or reference.must_surface:
        return ContractReferenceUsage(
            status="missing",
            completed_actions=[],
            missing_actions=_missing_reference_actions(reference),
            summary=(f"{prefix}: required reference actions remain unresolved for {reference.locator}."),
        )
    return ContractReferenceUsage(
        status="not_applicable",
        completed_actions=[],
        missing_actions=[],
        summary=f"{prefix}: no required verification action is recorded for this reference.",
    )


def _missing_reference_actions(reference: ContractReference) -> list[str]:
    return list(reference.required_actions) or ["read"]


def _is_decisive_reference(reference: ContractReference) -> bool:
    return reference.role == "benchmark" or "compare" in reference.required_actions


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
