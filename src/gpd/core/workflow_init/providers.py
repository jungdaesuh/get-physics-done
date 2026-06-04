"""Provider factories for extracted workflow init builders."""

from __future__ import annotations

from pathlib import Path

from gpd.core.context_staged_providers import context_provider, reference_or_contract_provider
from gpd.core.workflow_init.dependencies import WorkflowInitDependencies


def staged_reference_provider(
    cwd: Path,
    reference_fields: frozenset[str],
    contract_fields: frozenset[str],
    deps: WorkflowInitDependencies,
):
    return reference_or_contract_provider(
        reference_fields=reference_fields,
        contract_fields=contract_fields,
        build_reference=lambda selected_fields: deps.build_staged_reference_runtime_context(cwd, selected_fields),
        build_contract=lambda: deps.build_new_project_contract_runtime_context(cwd),
    )


def staged_contract_provider(cwd: Path, trigger_fields: frozenset[str], deps: WorkflowInitDependencies):
    return context_provider(
        "contract_gate",
        trigger_fields,
        lambda: deps.build_new_project_contract_runtime_context(cwd),
    )


def staged_structured_state_provider(cwd: Path, trigger_fields: frozenset[str], deps: WorkflowInitDependencies):
    return context_provider(
        "structured_state",
        trigger_fields,
        lambda: deps.build_structured_state_runtime_context(cwd),
    )


__all__ = [
    "staged_contract_provider",
    "staged_reference_provider",
    "staged_structured_state_provider",
]
