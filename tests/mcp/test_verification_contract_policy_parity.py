from __future__ import annotations

import json
from pathlib import Path

import anyio

from tests.assertion_taxonomy_support import assert_prompt_contracts, semantic_concept


def _assert_semantic_surface(text: str, label: str, *, required: tuple[str, ...]) -> None:
    assert_prompt_contracts(text, *semantic_concept(label, required=required))


def test_verification_contract_policy_text_stays_aligned_across_public_surfaces() -> None:
    from gpd.mcp.builtin_servers import build_public_descriptors
    from gpd.mcp.servers.verification_server import (
        _CONTRACT_PAYLOAD_INPUT_SCHEMA,
        _CONTRACT_SCOPE_INPUT_SCHEMA,
        mcp,
    )
    from gpd.mcp.verification_contract_policy import (
        VERIFICATION_BINDING_FIELD_NAMES,
        VERIFICATION_BINDING_TARGETS,
        VERIFICATION_CONTRACT_POLICY_TEXT,
        verification_contract_surface_summary_text,
        verification_server_description,
    )

    descriptors = build_public_descriptors()
    verification_descriptor = descriptors["gpd-verification"]
    tools = {tool.name: tool for tool in anyio.run(mcp.list_tools)}
    infra_descriptor = json.loads((Path(__file__).resolve().parents[2] / "infra" / "gpd-verification.json").read_text())
    repo_root = Path(__file__).resolve().parents[2]
    plan_schema = (repo_root / "src/gpd/specs/templates/plan-contract-schema.md").read_text(encoding="utf-8")
    state_schema = (repo_root / "src/gpd/specs/templates/state-json-schema.md").read_text(encoding="utf-8")
    project_contract_schema = (repo_root / "src/gpd/specs/templates/project-contract-schema.md").read_text(
        encoding="utf-8"
    )
    grounding_linkage = (repo_root / "src/gpd/specs/templates/project-contract-grounding-linkage.md").read_text(
        encoding="utf-8"
    )

    assert _CONTRACT_PAYLOAD_INPUT_SCHEMA["description"] == VERIFICATION_CONTRACT_POLICY_TEXT
    assert VERIFICATION_BINDING_TARGETS == (
        "observable",
        "claim",
        "deliverable",
        "acceptance_test",
        "reference",
        "forbidden_proxy",
    )
    assert VERIFICATION_BINDING_FIELD_NAMES == (
        "binding.observable_ids",
        "binding.claim_ids",
        "binding.deliverable_ids",
        "binding.acceptance_test_ids",
        "binding.reference_ids",
        "binding.forbidden_proxy_ids",
    )
    assert verification_descriptor["description"] == verification_server_description()
    assert infra_descriptor["description"] == verification_server_description()
    assert verification_descriptor["description"].startswith("GPD physics verification support tools.")
    _assert_semantic_surface(
        verification_descriptor["description"],
        "verification descriptor scientific status boundary",
        required=("static triage", "MCP results", "final scientific verification status"),
    )
    assert tools["run_contract_check"].description is not None
    assert tools["suggest_contract_checks"].description is not None
    assert verification_contract_surface_summary_text() in verification_descriptor["description"]
    assert verification_descriptor["description"].count(VERIFICATION_CONTRACT_POLICY_TEXT) == 0
    assert tools["run_contract_check"].description.count(VERIFICATION_CONTRACT_POLICY_TEXT) == 0
    assert tools["suggest_contract_checks"].description.count(VERIFICATION_CONTRACT_POLICY_TEXT) == 0
    assert verification_contract_surface_summary_text() in tools["run_contract_check"].description
    assert verification_contract_surface_summary_text() in tools["suggest_contract_checks"].description
    _assert_semantic_surface(
        tools["run_contract_check"].description,
        "run_contract_check description request shape",
        required=("request", "object", "input schema", "request.contract", "optional", "project_dir"),
    )
    _assert_semantic_surface(
        tools["suggest_contract_checks"].description,
        "suggest_contract_checks description request shape",
        required=("request_template", "active_checks", "contract", "object", "schema_required_request_fields"),
    )
    _assert_semantic_surface(
        VERIFICATION_CONTRACT_POLICY_TEXT,
        "contract payload strictness policy",
        required=(
            "Nested object schemas",
            "closed",
            "unknown top-level",
            "nested keys",
            "hard errors",
            "contract-payload closed-enum case drift",
            "observed enum-like source values",
            "match exactly",
        ),
    )
    _assert_semantic_surface(
        verification_contract_surface_summary_text(),
        "contract payload summary strictness",
        required=(
            "contract-payload enum case drift",
            "recoverable",
            "observed enums",
            "source evidence",
            "exactly",
        ),
    )
    _assert_semantic_surface(
        VERIFICATION_CONTRACT_POLICY_TEXT,
        "must_surface grounding severity",
        required=("references[]", "must_surface=true", "blocker", "non-blocking warning"),
    )
    for field_name in VERIFICATION_BINDING_FIELD_NAMES:
        assert f"`{field_name}`" in VERIFICATION_CONTRACT_POLICY_TEXT
    _assert_semantic_surface(
        plan_schema,
        "plan schema must_surface grounding policy",
        required=("references[]", "concrete grounding", "must_surface: true", "warning", "not a blocker"),
    )
    assert "@{GPD_INSTALL_DIR}/templates/project-contract-schema.md" in state_schema
    _assert_semantic_surface(
        grounding_linkage,
        "project contract must_surface grounding policy",
        required=("references[]", "prior-output", "user-anchor", "baseline grounding", "must_surface: true", "warning"),
    )
    _assert_semantic_surface(
        _CONTRACT_SCOPE_INPUT_SCHEMA["description"],
        "contract scope input requires in-scope boundary",
        required=("Project-scoping contracts", "scope.in_scope", "objective", "boundary"),
    )
    _assert_semantic_surface(
        plan_schema,
        "plan schema scope boundary requirement",
        required=("scope.in_scope", "required", "project boundary", "objective"),
    )
    _assert_semantic_surface(
        project_contract_schema,
        "project contract schema scope boundary requirement",
        required=("scope.in_scope", "project boundary", "objective"),
    )
