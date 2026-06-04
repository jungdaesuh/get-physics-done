from __future__ import annotations

import re
from pathlib import Path

from gpd.adapters.install_utils import expand_at_includes
from gpd.core.strict_yaml import load_strict_yaml
from tests.lifecycle_contract_test_support import (
    assert_forbidden_contract as _assert_forbidden,
)
from tests.lifecycle_contract_test_support import (
    assert_machine_contract as _assert_machine,
)
from tests.lifecycle_contract_test_support import (
    assert_semantic_contract as _assert_semantic,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "src/gpd/agents"
TEMPLATES_DIR = REPO_ROOT / "src/gpd/specs/templates"


def _read_template(name: str) -> str:
    return (TEMPLATES_DIR / name).read_text(encoding="utf-8")


def _expanded_template(name: str) -> str:
    return expand_at_includes(_read_template(name), REPO_ROOT / "src/gpd/specs", "/runtime/")


def _section(text: str, heading: str) -> str:
    match = re.search(rf"^(?P<level>#+)\s+{re.escape(heading)}\s*$", text, flags=re.MULTILINE)
    assert match is not None, f"missing markdown heading: {heading}"

    heading_level = len(match.group("level"))
    next_heading = re.search(rf"^#{{1,{heading_level}}}\s+", text[match.end() :], flags=re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(text)
    return text[match.end() : end]


def _tagged_section(text: str, tag: str) -> str:
    start = f"<{tag}>"
    end = f"</{tag}>"
    assert start in text, f"missing start tag: {start}"
    assert end in text, f"missing end tag: {end}"
    return text.split(start, 1)[1].split(end, 1)[0]


def _contains_all(text: str, tokens: tuple[str, ...]) -> None:
    missing = [token for token in tokens if token not in text]
    assert not missing, f"missing expected tokens: {missing}"


def _fenced_blocks(text: str, language: str) -> list[str]:
    fence_pattern = re.compile(r"```(?P<language>[^\n]*)\n(?P<body>.*?)\n```", flags=re.DOTALL)
    return [
        match.group("body")
        for match in fence_pattern.finditer(text)
        if match.group("language").strip().split()[:1] == [language]
    ]


def _single_yaml_fence(text: str) -> object:
    blocks = _fenced_blocks(text, "yaml")
    assert len(blocks) == 1
    return load_strict_yaml(blocks[0])


def _as_mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return value


def _as_list(value: object) -> list[object]:
    assert isinstance(value, list)
    return value


def _first_mapping(value: object) -> dict[str, object]:
    items = _as_list(value)
    assert len(items) == 1
    return _as_mapping(items[0])


def test_plan_contract_schema_surfaces_defaultable_semantic_fields_and_hard_constraints() -> None:
    plan_schema = _expanded_template("plan-contract-schema.md")

    schema_version_example = _as_mapping(_single_yaml_fence(_section(plan_schema, "`schema_version`")))
    scope_example = _as_mapping(_as_mapping(_single_yaml_fence(_section(plan_schema, "`scope`")))["scope"])
    context_intake_example = _as_mapping(
        _as_mapping(_single_yaml_fence(_section(plan_schema, "`context_intake`")))["context_intake"]
    )
    approach_policy_example = _as_mapping(
        _as_mapping(_single_yaml_fence(_section(plan_schema, "`approach_policy`")))["approach_policy"]
    )
    observables_example = _first_mapping(_single_yaml_fence(_section(plan_schema, "`observables[]`")))
    references_example = _first_mapping(_single_yaml_fence(_section(plan_schema, "`references[]`")))
    links_example = _first_mapping(_single_yaml_fence(_section(plan_schema, "`links[]`")))
    required_shape = _section(plan_schema, "Required Shape")
    context_intake_rules = _section(plan_schema, "`context_intake`")
    approach_policy_rules = _section(plan_schema, "`approach_policy`")
    references_rules = _section(plan_schema, "`references[]`")
    links_rules = _section(plan_schema, "`links[]`")
    alignment_rules = _section(plan_schema, "Contract Alignment Rules")

    _assert_machine(
        plan_schema,
        "plan contract defaultable semantic fields",
        "observables[].kind",
        "deliverables[].kind",
        "acceptance_tests[].kind",
        "references[].kind",
        "references[].role",
        "links[].relation",
    )
    _assert_semantic(plan_schema, "plan contract default other rule", "their default is `other`")

    assert schema_version_example == {"schema_version": 1}
    assert scope_example["in_scope"] == ["Recover the benchmark curve within tolerance"]
    assert isinstance(scope_example["in_scope"], list)
    assert context_intake_example["must_read_refs"] == ["ref-main"]
    assert context_intake_example["must_include_prior_outputs"] == ["GPD/phases/00-baseline/00-01-SUMMARY.md"]
    assert isinstance(context_intake_example["must_include_prior_outputs"], list)
    assert isinstance(approach_policy_example["formulations"], list)
    assert observables_example["kind"] == "scalar"
    assert references_example["kind"] == "paper"
    assert references_example["role"] == "benchmark"
    assert references_example["must_surface"] is True
    assert references_example["required_actions"] == ["read", "compare", "cite", "avoid"]
    assert links_example["relation"] == "supports"

    _contains_all(
        required_shape,
        (
            "`schema_version`",
            "integer `1`",
            "`scope`",
            "`context_intake`",
            "`approach_policy`",
            "`uncertainty_markers`",
            "YAML object",
            "not strings or lists",
            "hard grounding/anchor requirement",
        ),
    )
    _contains_all(
        context_intake_rules,
        (
            "`contract.context_intake`",
            "required",
            "non-empty object",
            "not a string or list",
            "Use concrete anchors",
            "`must_read_refs[]`",
            "`must_include_prior_outputs[]`",
            "`user_asserted_anchors[]`",
            "`known_good_baselines[]`",
        ),
    )
    _contains_all(
        approach_policy_rules,
        (
            "`approach_policy`",
            "YAML object",
            "not a string or list",
            "does not count as grounding",
            "`context_intake`",
            "preserved scoping inputs",
            "`references[]`",
        ),
    )
    _contains_all(
        references_rules,
        (
            "`kind`",
            "`role`",
            "`must_surface`",
            "boolean scalar",
            "`true`",
            "`false`",
            "synonyms",
            "`required_actions`",
            "`applies_to[]`",
            "concrete enough to re-find later",
        ),
    )
    _assert_semantic(
        plan_schema,
        "plan contract proof-bearing claim kind rule",
        "Proof-bearing claims must use an explicit non-`other` `claim_kind`",
    )
    _contains_all(
        links_rules,
        (
            "`source`",
            "`target`",
            "declared observable",
            "claim",
            "deliverable",
            "acceptance-test",
            "reference",
            "forbidden-proxy",
            "link IDs",
        ),
    )
    _contains_all(
        alignment_rules,
        (
            "`references[]`",
            "`context_intake`",
            "preserved scoping inputs",
            "`must_surface: true`",
            "concrete grounding",
            "warning",
            "not a blocker",
        ),
    )
    _assert_semantic(
        plan_schema,
        "plan contract required non-scoping lists",
        "For non-scoping plans, `claims[]`, `deliverables[]`, `acceptance_tests[]`, and `forbidden_proxies[]` are all required.",
    )


def test_planner_prompt_surfaces_default_salvage_and_specific_semantics() -> None:
    planner_prompt = _read_template("planner-subagent-prompt.md")

    assert planner_prompt.count("## Standard Planning Template") == 1
    assert planner_prompt.count("## Revision Template") == 1
    assert planner_prompt.count("@{GPD_INSTALL_DIR}/templates/plan-contract-schema.md") == 1
    _assert_machine(
        planner_prompt,
        "planner prompt contract gate placeholders",
        "**Project Contract Gate:** {project_contract_gate}",
        "**Project Contract Load Info:** {project_contract_load_info}",
        "**Project Contract Validation:** {project_contract_validation}",
    )
    for token in (
        "project_contract_gate.authoritative",
        "project_contract_load_info.status",
        "project_contract_validation.valid",
        "project_contract",
        "effective_reference_intake",
        "active_reference_context",
        "approach_policy",
        "scope.in_scope",
        "contract.context_intake",
        "claim_kind",
    ):
        _assert_machine(planner_prompt, f"planner prompt contract token {token}", token)
    _assert_semantic(
        planner_prompt,
        "planner prompt no silent branch and proof audit rules",
        "Do not silently branch or widen scope.",
        "`tool_requirements` pass `gpd validate plan-preflight <PLAN.md>`",
        "Proof-bearing plans keep proof artifacts and sibling `*-PROOF-REDTEAM.md` audits explicit",
    )
    _assert_forbidden(
        planner_prompt,
        "planner prompt stale contract visibility prose",
        "The contract still exposes defaultable semantic fields",
        "Stale proof review gate",
    )


def test_planner_and_checker_examples_surface_concrete_contract_anchors() -> None:
    planner_prompt = (REPO_ROOT / "src/gpd/agents/gpd-planner.md").read_text(encoding="utf-8")
    checker_prompt = (REPO_ROOT / "src/gpd/agents/gpd-plan-checker.md").read_text(encoding="utf-8")
    checker_contract_gate = _section(checker_prompt, "Dimension 0: Contract Gate")

    _assert_machine(
        planner_prompt,
        "planner prompt concrete contract anchors",
        'in_scope: ["Recover the benchmark curve within tolerance"]',
        "claim_kind: theorem",
        'parameters -> symbol "q"',
        "hypotheses -> hyp-gauge",
        "conclusion_clauses -> concl-transverse",
        "GPD/phases/01-vacuum-polarization/01-01-SUMMARY.md",
        "GPD/phases/00-baseline/00-01-SUMMARY.md#gauge-and-tensor-convention",
    )
    _assert_machine(
        checker_prompt,
        "checker prompt concrete contract anchors",
        "schema_version: 1",
        'in_scope: ["Recover the benchmark value within tolerance"]',
        "claim_kind: theorem",
        "parameters:",
        "- symbol: k",
        'domain_or_type: "dimensionless"',
        "aliases: [kappa]",
        "required_in_proof: true",
        "hypotheses:",
        "- id: hyp-normalization",
        'text: "Reference normalization and tolerance convention match Ref-01"',
        "symbols: [k]",
        "category: assumption",
        "conclusion_clauses:",
        "- id: concl-benchmark",
        'text: "Benchmark agreement stays within tolerance at every approved sample"',
        "proof_deliverables: [deliv-proof-main]",
    )
    _assert_forbidden(
        checker_prompt,
        "checker prompt no collapsed proof lists",
        "parameters: [k]",
        'hypotheses: ["Reference normalization and tolerance convention match Ref-01"]',
        'conclusion_clauses: ["Benchmark agreement stays within tolerance at every approved sample"]',
    )
    _contains_all(
        checker_contract_gate,
        (
            "stable knowledge docs",
            "shared reference context",
            "reviewed background syntheses",
            "do not override",
            "`convention_lock`",
            "`project_contract`",
            "PLAN `contract`",
            "`contract_results`",
            "`comparison_verdicts`",
            "proof-review artifacts",
            "direct benchmark/result evidence",
        ),
    )
    _assert_machine(
        checker_prompt,
        "checker prompt baseline summary anchors",
        "GPD/phases/00-baseline/00-01-SUMMARY.md",
        "GPD/phases/00-baseline/00-01-SUMMARY.md#gauge-unit-and-notation-conventions",
    )


def test_plan_checker_prompt_surfaces_direct_schema_visibility_and_read_only_authority() -> None:
    checker_prompt = (AGENTS_DIR / "gpd-plan-checker.md").read_text(encoding="utf-8")

    assert checker_prompt.count("@{GPD_INSTALL_DIR}/templates/plan-contract-schema.md") >= 2
    _assert_machine(
        checker_prompt,
        "plan checker read-only schema visibility",
        "{GPD_INSTALL_DIR}/references/shared/shared-protocols.md",
        "Apply `{GPD_INSTALL_DIR}/references/orchestration/continuation-boundary.md` for one-shot handoff semantics.",
        "artifact_write_authority: read_only",
        "approved_plans:",
        '    - "04-01"',
        "blocked_plans: []",
        "GPD/phases/00-baseline/00-01-SUMMARY.md",
        "GPD/phases/00-baseline/00-01-SUMMARY.md#gauge-unit-and-notation-conventions",
        "GPD/phases/00-baseline/00-01-SUMMARY.md#gauge-and-tensor-convention",
        "GPD/phases/01-vacuum-polarization/01-01-SUMMARY.md",
    )
    _assert_semantic(
        checker_prompt,
        "plan checker typed checkpoint stop",
        "If user input is needed, return the typed checkpoint and stop.",
    )
    _assert_forbidden(
        checker_prompt,
        "plan checker no eager shared protocol include or write authority",
        "@{GPD_INSTALL_DIR}/references/shared/shared-protocols.md",
        "file_write",
    )


def test_phase_prompt_surfaces_default_salvage_and_hard_plan_requirements() -> None:
    phase_prompt = _read_template("phase-prompt.md")

    assert phase_prompt.count("Quick contract rules:") == 1
    assert phase_prompt.count("@{GPD_INSTALL_DIR}/templates/plan-contract-schema.md") == 1
    for token in (
        "tool_requirements",
        "researcher_setup",
        "type: execute",
        "gap_closure: true",
        "scope.in_scope",
        "claim_kind",
        "observables[].kind",
        "deliverables[].kind",
        "acceptance_tests[].kind",
        "references[].kind",
        "references[].role",
        "links[].relation",
        "must_surface",
        "required_actions[]",
        "applies_to[]",
        "carry_forward_to[]",
        "uncertainty_markers",
    ):
        _assert_machine(phase_prompt, f"phase prompt contract token {token}", token)


def test_contract_schema_docs_make_lowercase_closed_vocab_rule_model_visible() -> None:
    plan_schema = _expanded_template("plan-contract-schema.md")
    project_schema = _expanded_template("project-contract-schema.md")
    state_schema = _expanded_template("state-json-schema.md")

    expected = "Case drift such as `Theorem`, `Benchmark`, or `Read` fails strict validation."

    _assert_semantic(plan_schema, "plan schema lowercase vocabulary rule", expected)
    _assert_semantic(project_schema, "project schema lowercase vocabulary rule", expected)
    _assert_semantic(state_schema, "state schema lowercase vocabulary rule", expected)


def test_planner_prompt_stays_compact_while_preserving_canonical_contract_wiring() -> None:
    planner_prompt = (REPO_ROOT / "src/gpd/agents/gpd-planner.md").read_text(encoding="utf-8")
    planner_role = planner_prompt.partition("</role>")[0]

    _assert_machine(
        planner_prompt,
        "planner prompt compact proof field examples",
        'parameters -> symbol "q"',
        "hypotheses -> hyp-gauge",
        "conclusion_clauses -> concl-transverse",
    )
    _assert_forbidden(
        planner_prompt,
        "planner prompt stale expanded proof and context prose",
        'parameters: ["q"]',
        'hypotheses: ["Gauge-fixing and regularization conventions match the approved anchor"]',
        'conclusion_clauses: ["q_mu Pi^{mu nu} = 0"]',
        "15-20%",
        "Context %",
        "No plan-checker",
        "The system starts broad and narrows automatically.",
        "approach_validated: true",
    )
    assert planner_prompt.count("| **YOLO** |") == 1
    assert "<worked_examples>" not in planner_prompt
    assert "<goal_backward>" not in planner_prompt
    assert "Worked Examples: Complete PLAN.md Files" not in planner_prompt
    assert "Goal-Backward Methodology for Physics" not in planner_prompt
    _assert_machine(
        planner_prompt,
        "planner prompt compact contract wiring",
        "tool_requirements[].id",
        "must be unique within the list",
        'in_scope: ["Recover the benchmark curve within tolerance"]',
        "claim_kind: theorem",
        'proof_deliverables: ["deliv-proof-vac-pol"]',
        "GPD/phases/00-baseline/00-01-SUMMARY.md#gauge-and-tensor-convention",
        "GPD/phases/01-vacuum-polarization/01-01-SUMMARY.md",
    )
    _assert_forbidden(
        planner_role,
        "planner role no eager workflow/template references",
        "@{GPD_INSTALL_DIR}/workflows/execute-plan.md",
        "@{GPD_INSTALL_DIR}/templates/summary.md",
        "@{GPD_INSTALL_DIR}/references/protocols/order-of-limits.md",
    )


def test_proof_obligation_planning_surfaces_require_claim_audit_and_stale_review_gate() -> None:
    plan_schema = _read_template("plan-contract-schema.md")
    planner_prompt = _read_template("planner-subagent-prompt.md")
    phase_prompt = _read_template("phase-prompt.md")
    observables_rules = _section(plan_schema, "`observables[]`")
    planner_contract_rules = _tagged_section(planner_prompt, "contract_visibility_requirements")
    phase_quick_rules = phase_prompt.split("Quick contract rules:", 1)[1].split("---", 1)[0]

    _assert_machine(
        plan_schema,
        "plan schema observable kind vocabulary",
        "kind: scalar|curve|map|classification|proof_obligation|other",
    )
    _contains_all(
        observables_rules,
        (
            "`kind`",
            "proof_obligation",
            "`definition`",
            "theorem/result",
            "hypotheses",
            "parameter regime",
            "body prose",
        ),
    )

    _contains_all(
        planner_contract_rules,
        (
            "proof-bearing work",
            "explicit non-`other` `claim_kind`",
            "auditable hypotheses",
            "quantified variables",
            "named parameters",
        ),
    )
    _assert_forbidden(
        planner_prompt,
        "planner prompt stale proof audit headings",
        "**Proof claim audit:**",
        "**Stale proof review gate:**",
    )

    _contains_all(
        phase_quick_rules,
        (
            "proof-bearing work",
            "explicit non-`other` `claim_kind`",
            "hypotheses",
            "parameters",
            "conclusions auditable",
            "`observables[].kind: proof_obligation`",
            "theorem or claim",
            "parameter regime",
            "proof audit",
            "stale",
            "`status: passed`",
        ),
    )


def test_planner_gap_closure_example_keeps_execute_type_and_required_contract_block() -> None:
    planner_prompt = (REPO_ROOT / "src/gpd/agents/gpd-planner.md").read_text(encoding="utf-8")
    gap_closure_mode = _tagged_section(planner_prompt, "gap_closure_mode")
    gap_closure_example = _as_mapping(_single_yaml_fence(gap_closure_mode))
    contract = _as_mapping(gap_closure_example["contract"])
    scope = _as_mapping(contract["scope"])
    context_intake = _as_mapping(contract["context_intake"])
    claims = _as_list(contract["claims"])
    deliverables = _as_list(contract["deliverables"])
    acceptance_tests = _as_list(contract["acceptance_tests"])
    forbidden_proxies = _as_list(contract["forbidden_proxies"])
    uncertainty_markers = _as_mapping(contract["uncertainty_markers"])

    _contains_all(
        gap_closure_mode,
        (
            "`type: execute`",
            "`gap_closure: true`",
            "verification",
            "repair marker",
            "PLAN.md",
            "failed verification",
            "new passing check",
        ),
    )
    _assert_forbidden(gap_closure_mode, "planner gap closure no stale type", "type: gap_closure")
    assert gap_closure_example["gap_closure"] is True
    assert set(contract) == {
        "schema_version",
        "scope",
        "context_intake",
        "claims",
        "deliverables",
        "acceptance_tests",
        "forbidden_proxies",
        "uncertainty_markers",
    }
    assert contract["schema_version"] == 1
    assert isinstance(scope["question"], str)
    assert scope["in_scope"] == ["Repair the failed verification for the published benchmark comparison"]
    assert context_intake["must_include_prior_outputs"] == ["GPD/phases/XX-name/XX-NN-SUMMARY.md"]
    assert isinstance(context_intake["must_include_prior_outputs"], list)
    assert isinstance(context_intake["crucial_inputs"], list)

    assert len(claims) == 1
    claim = _as_mapping(claims[0])
    assert claim["claim_kind"] == "other"
    assert claim["deliverables"] == ["deliv-gap-fix"]
    assert claim["acceptance_tests"] == ["test-gap-fix"]

    assert len(deliverables) == 1
    deliverable = _as_mapping(deliverables[0])
    assert deliverable["kind"] == "report"
    assert deliverable["path"] == "GPD/phases/XX-name/XX-NN-SUMMARY.md"

    assert len(acceptance_tests) == 1
    acceptance_test = _as_mapping(acceptance_tests[0])
    assert acceptance_test["subject"] == "claim-gap-fix"
    assert acceptance_test["kind"] == "other"
    assert acceptance_test["evidence_required"] == ["deliv-gap-fix"]

    assert len(forbidden_proxies) == 1
    forbidden_proxy = _as_mapping(forbidden_proxies[0])
    assert forbidden_proxy["subject"] == "claim-gap-fix"
    assert isinstance(uncertainty_markers["weakest_anchors"], list)
    assert isinstance(uncertainty_markers["disconfirming_observations"], list)
