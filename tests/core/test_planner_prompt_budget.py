"""Prompt-budget assertions for `gpd-planner` bootstrap loading."""

from __future__ import annotations

from pathlib import Path

from tests.assertion_taxonomy_support import assert_prompt_contracts, forbidden_duplicate, semantic_anchor
from tests.prompt_metrics_support import expanded_include_markers, expanded_prompt_text, measure_prompt_surface

REPO_ROOT = Path(__file__).resolve().parents[2]
PLANNER_PATH = REPO_ROOT / "src" / "gpd" / "agents" / "gpd-planner.md"
SOURCE_ROOT = REPO_ROOT / "src" / "gpd"
PATH_PREFIX = "/runtime/"
PLANNING_REFERENCES_DIR = SOURCE_ROOT / "specs" / "references" / "planning"
PLANNER_JIT_MODULES = {
    "autonomy": PLANNING_REFERENCES_DIR / "planner-autonomy-policy.md",
    "research_mode": PLANNING_REFERENCES_DIR / "planner-research-mode-policy.md",
    "tangent": PLANNING_REFERENCES_DIR / "planner-tangent-decision-model.md",
    "proof": PLANNING_REFERENCES_DIR / "planner-proof-bearing-plan-checklist.md",
    "protocol_bundle": PLANNING_REFERENCES_DIR / "planner-protocol-bundle-planning.md",
    "task_dependency": PLANNING_REFERENCES_DIR / "planner-task-and-dependency-guide.md",
    "gap_revision": PLANNING_REFERENCES_DIR / "planner-gap-and-revision-policy.md",
    "execution": PLANNING_REFERENCES_DIR / "planner-execution-procedure.md",
}

OLD_DOMAIN_CATALOG_HEADINGS = (
    "QFT Perturbative Calculation",
    "Condensed Matter (Analytical)",
    "Condensed Matter (Numerical)",
    "General Relativity / Cosmology",
    "AMO / Quantum Optics",
    "Numerical PDE/ODE",
    "Effective Field Theory",
    "### Domain Selection",
    "### Cross-Domain Projects",
)

ON_DEMAND_PLANNING_GUIDES = {
    "qft-perturbative-calculation.md": "QFT Perturbative Calculation",
    "condensed-matter-analytical.md": "Condensed Matter (Analytical)",
    "condensed-matter-numerical.md": "Condensed Matter (Numerical)",
    "statistical-mechanics.md": "Statistical Mechanics Planning Guide",
    "gr-cosmology.md": "General Relativity / Cosmology",
    "amo-quantum-optics.md": "AMO / Quantum Optics",
    "numerical-pde-ode.md": "Numerical PDE/ODE",
    "effective-field-theory.md": "Effective Field Theory",
    "cross-domain-convention-bridge.md": "Cross-Domain Projects Planning Guide",
}


def _read_planner_prompt() -> str:
    return PLANNER_PATH.read_text(encoding="utf-8")


def _read_reference(name: str) -> str:
    return PLANNER_JIT_MODULES[name].read_text(encoding="utf-8")


def _between(text: str, start: str, end: str) -> str:
    _, start_marker, tail = text.partition(start)
    assert start_marker, f"Missing marker: {start}"
    body, end_marker, _ = tail.partition(end)
    assert end_marker, f"Missing marker: {end}"
    return body


def test_planner_bootstrap_uses_mandatory_plan_template_file_read_gate() -> None:
    planner = _read_planner_prompt()
    role = _between(planner, "<role>", "</role>")

    assert_prompt_contracts(
        role,
        forbidden_duplicate(
            "planner does not eagerly include phase template",
            "@{GPD_INSTALL_DIR}/templates/phase-prompt.md",
            max_count=0,
        ),
        forbidden_duplicate(
            "planner does not eagerly include plan contract schema",
            "@{GPD_INSTALL_DIR}/templates/plan-contract-schema.md",
            max_count=0,
        ),
        forbidden_duplicate(
            "planner does not eagerly include execution workflow",
            "@{GPD_INSTALL_DIR}/workflows/execute-plan.md",
            max_count=0,
        ),
        forbidden_duplicate(
            "planner does not eagerly include summary template",
            "@{GPD_INSTALL_DIR}/templates/summary.md",
            max_count=0,
        ),
        forbidden_duplicate(
            "planner does not eagerly include order-of-limits reference",
            "@{GPD_INSTALL_DIR}/references/protocols/order-of-limits.md",
            max_count=0,
        ),
        semantic_anchor(
            "planner keeps mandatory file-read gate semantics visible",
            (
                "Before emitting or revising any `PLAN.md`",
                "before plan frontmatter",
                "stop as blocked or checkpointed through the standard return skeleton",
                "do not reconstruct the schema from memory",
            ),
        ),
    )
    file_read_phrase = "use `file_read`"
    phase_template_path = "{GPD_INSTALL_DIR}/templates/phase-prompt.md"
    schema_template_path = "{GPD_INSTALL_DIR}/templates/plan-contract-schema.md"
    assert role.index(file_read_phrase) < role.index(phase_template_path)
    assert role.index(phase_template_path) < role.index(schema_template_path)


def test_raw_planner_prompt_stays_under_phase6_cap() -> None:
    planner = _read_planner_prompt()

    assert len(planner.splitlines()) < 800
    assert len(planner) < 27_700


def test_planner_return_surface_uses_profile_and_role_kits() -> None:
    planner = _read_planner_prompt()
    returns = _between(planner, "<structured_returns>", "</structured_returns>")
    gap_closure = _between(planner, "<gap_closure_mode>", "</gap_closure_mode>")

    assert "gpd return skeleton --role planner --status <status>" in returns
    assert "gpd --raw return profiles" in returns
    assert "frontmatter `role_kits`" in returns
    assert (
        "Completed returns name only fresh PLAN.md files that passed `gpd validate plan-preflight <PLAN.md>`" in returns
    )
    assert_prompt_contracts(
        returns,
        semantic_anchor("planner stale yaml-envelope wording absent", "a YAML envelope is required", mode="absent"),
    )
    assert "gpd_return:\n  status: completed" in returns
    assert "plans_created: 1" in returns

    assert "gap_closure: true" in gap_closure
    assert "```yaml" in gap_closure
    assert "proxy-no-status-only" in gap_closure
    assert "weakest_anchors" in gap_closure


def test_expanded_planner_prompt_stays_under_budget() -> None:
    metrics = measure_prompt_surface(
        PLANNER_PATH,
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )

    assert metrics.raw_include_count == 0
    assert metrics.expanded_char_count < 40_000
    assert metrics.expanded_line_count < 750


def test_removed_planner_includes_are_late_loaded_by_path_not_body() -> None:
    planner = _read_planner_prompt()
    expanded = expanded_prompt_text(PLANNER_PATH, src_root=SOURCE_ROOT, path_prefix=PATH_PREFIX)
    markers = expanded_include_markers(expanded)

    for filename in (
        "phase-prompt.md",
        "planner-conventions.md",
        "planner-approximations.md",
    ):
        assert all(filename not in marker for marker in markers)

    assert "{GPD_INSTALL_DIR}/templates/phase-prompt.md" in planner
    assert "{GPD_INSTALL_DIR}/references/planning/planner-conventions.md" in planner
    assert "{GPD_INSTALL_DIR}/references/planning/planner-approximations.md" in planner
    assert "Phase Plan Prompt Template" not in planner
    assert "Notation and Convention Tracking" not in planner
    assert "Approximation Schemes and Validity" not in planner

    conventions = _between(planner, "<physics_conventions>", "</physics_conventions>")
    approximations = _between(planner, "<approximation_tracking>", "</approximation_tracking>")

    assert "@{GPD_INSTALL_DIR}" not in conventions
    assert_prompt_contracts(
        conventions,
        semantic_anchor(
            "planner convention gate before task decomposition",
            "Every plan must establish or inherit conventions before task decomposition.",
        ),
    )
    assert (
        "Load `{GPD_INSTALL_DIR}/references/planning/planner-conventions.md` when conventions are missing"
        in conventions
    )
    assert "convention_lock" in conventions

    assert "@{GPD_INSTALL_DIR}" not in approximations
    assert_prompt_contracts(
        approximations,
        semantic_anchor(
            "planner approximation tracking stays concise and active",
            "identify active approximations, expansion parameters, neglected terms",
        ),
    )
    assert "Load `{GPD_INSTALL_DIR}/references/planning/planner-approximations.md` when selecting" in approximations
    assert "`name`, `parameter`, `validity`, `breaks_when`, and `check`" in approximations


def test_planner_prompt_no_longer_carries_the_removed_high_level_boilerplate() -> None:
    planner = _read_planner_prompt()

    for removed_marker in (
        "Quality Degradation Curve",
        "Research Fast",
        "Specificity Examples",
    ):
        assert removed_marker not in planner


def test_domain_blueprint_catalog_is_on_demand_not_in_base_prompt() -> None:
    planner = _read_planner_prompt()

    assert "references/planning/domain-strategy-index.md" in planner
    assert "planning_guides" in planner

    for removed_heading in OLD_DOMAIN_CATALOG_HEADINGS:
        assert removed_heading not in planner


def test_planner_protocol_bundle_guidance_is_manifest_and_handle_first() -> None:
    planner = _read_planner_prompt()
    physics_verification = _between(planner, "<physics_verification>", "</physics_verification>")

    assert_prompt_contracts(
        physics_verification,
        semantic_anchor(
            "planner opens selected protocol handles before domain judgments",
            (
                "protocol_bundle_load_manifest",
                "Before any domain or method judgment",
                "open only relevant",
                "planning_guides",
                "verification_domains",
                "execution_guides",
                "portable_path",
                "a handle label alone is not evidence",
            ),
            match="casefold_normalized",
        ),
        semantic_anchor(
            "planner context-first protocol wording stays absent",
            "consult selected protocol bundle context first",
            mode="absent",
            match="casefold_normalized",
        ),
    )
    assert physics_verification.index("protocol_bundle_load_manifest") < physics_verification.index(
        "Before any domain or method judgment"
    )
    assert physics_verification.index("Before any domain or method judgment") < physics_verification.index(
        "portable_path"
    )


def test_planner_policy_detail_lives_in_jit_modules_not_base_prompt() -> None:
    planner = _read_planner_prompt()

    expected_reference_paths = {
        "planner-autonomy-policy.md",
        "planner-research-mode-policy.md",
        "planner-tangent-decision-model.md",
        "planner-proof-bearing-plan-checklist.md",
        "planner-protocol-bundle-planning.md",
        "planner-task-and-dependency-guide.md",
        "planner-gap-and-revision-policy.md",
        "planner-execution-procedure.md",
    }
    for filename in expected_reference_paths:
        assert f"references/planning/{filename}" in planner
        assert (PLANNING_REFERENCES_DIR / filename).is_file()

    for detailed_marker in (
        "### Planning Decision Matrix",
        '### Explore Mode (`research_mode: "explore"`)',
        "Example outcome in explore mode when alternatives remain live",
        "Gap-specific fields to insert into the canonical `phase-prompt.md` template",
        "Triage decision matrix",
        "Always-visible fallback skeleton:",
    ):
        assert detailed_marker not in planner

    autonomy = _read_reference("autonomy")
    assert "Supervised mode" in autonomy
    assert "Balanced mode" in autonomy
    assert "YOLO mode" in autonomy
    assert "[Y/n/e]" in autonomy
    assert "Planning Decision Matrix" in autonomy

    research_mode = _read_reference("research_mode")
    assert_prompt_contracts(
        research_mode,
        semantic_anchor(
            "planner research mode does not relax correctness",
            "Research mode controls breadth, not correctness.",
        ),
    )
    assert "Explore Mode" in research_mode
    assert "Exploit Mode" in research_mode
    assert "Adaptive Mode" in research_mode

    tangent = _read_reference("tangent")
    assert "Branch as alternative hypothesis" in tangent
    assert "gpd:tangent" in tangent
    assert "gpd:quick" in tangent
    assert "gpd:add-todo" in tangent
    assert "## CHECKPOINT REACHED" in tangent

    proof = _read_reference("proof")
    assert "claim_kind: theorem" in proof
    assert "proof_deliverables" in proof
    assert "*-PROOF-REDTEAM.md" in proof

    protocol_bundle = _read_reference("protocol_bundle")
    assert "planning_guides" in protocol_bundle
    assert "Fallback Skeleton" in protocol_bundle
    assert "never changes `project_contract`" in protocol_bundle

    task_dependency = _read_reference("task_dependency")
    assert "Task Anatomy" in task_dependency
    assert "Dependency Graph Detail" in task_dependency

    gap_revision = _read_reference("gap_revision")
    assert "gap_closure: true" in gap_revision
    assert "Revision From Checker Feedback" in gap_revision

    execution = _read_reference("execution")
    assert "Optional Context Triage" in execution
    assert "gpd validate plan-preflight <PLAN.md>" in execution


def test_on_demand_domain_planning_guides_are_reachable() -> None:
    index = (PLANNING_REFERENCES_DIR / "domain-strategy-index.md").read_text(encoding="utf-8")

    for guide_name, expected_heading in ON_DEMAND_PLANNING_GUIDES.items():
        guide_path = PLANNING_REFERENCES_DIR / guide_name
        assert guide_path.is_file(), guide_name
        assert f"references/planning/{guide_name}" in index
        assert expected_heading in guide_path.read_text(encoding="utf-8")


def test_planner_prompt_delegates_raw_plan_template_to_canonical_template() -> None:
    planner = _read_planner_prompt()

    assert "## PLAN.md Source Of Truth" in planner
    assert_prompt_contracts(
        planner,
        semantic_anchor(
            "planner delegates raw plan template to canonical source",
            "Do not inline, paraphrase, or reconstruct a second raw PLAN template here.",
        ),
    )
    assert "## PLAN.md Structure" not in planner
    assert "```markdown\n---\nphase: XX-name" not in planner
    assert "claim-polarization" not in planner
    assert "deliv-vac-pol" not in planner
    assert "<execution_context>Use the already-loaded `phase-prompt.md`" not in planner
    assert "Researcher Setup Frontmatter" not in planner
    assert "Tool Requirements Frontmatter" not in planner


def test_planner_delegates_checkpoint_examples_to_canonical_reference() -> None:
    planner = _read_planner_prompt()
    checkpoint_section = _between(planner, "<checkpoints>", "</checkpoints>")

    assert "references/orchestration/checkpoints.md" in checkpoint_section
    assert "references/orchestration/checkpoint-ux-convention.md" in checkpoint_section
    assert_prompt_contracts(
        checkpoint_section,
        semantic_anchor(
            "planner delegates checkpoint examples to canonical reference",
            "Do not inline a second checkpoint template here.",
        ),
        semantic_anchor(
            "planner inline checkpoint examples stay absent",
            ("Bad -- Checkpointing every derivation step", "Good -- Single verification at logical boundary"),
            mode="absent",
        ),
    )
    assert '<task type="checkpoint:human-verify"' not in checkpoint_section
    assert '<task type="checkpoint:decision"' not in checkpoint_section


def test_planner_optional_heuristics_and_checker_examples_live_in_late_refs() -> None:
    planner = _read_planner_prompt()
    scope = (PLANNING_REFERENCES_DIR / "planner-scope-examples.md").read_text(encoding="utf-8")
    procedure = (PLANNING_REFERENCES_DIR / "planner-execution-procedure.md").read_text(encoding="utf-8")
    gap_revision = (PLANNING_REFERENCES_DIR / "planner-gap-and-revision-policy.md").read_text(encoding="utf-8")

    assert "references/planning/planner-scope-examples.md" in planner
    assert "references/planning/planner-execution-procedure.md" in planner
    assert "references/planning/planner-gap-and-revision-policy.md" in planner

    for moved_marker in (
        "Dynamic Difficulty Escalation",
        "Depth Escalation Suggested",
        "Example escalation message",
        "Gap-Specific Contract Fields",
        "Checker Feedback Examples",
    ):
        assert moved_marker not in planner

    assert "Execution Time Heuristics" in scope
    assert "Dynamic Difficulty Escalation" in scope
    assert "User Decision Fidelity" in procedure
    assert "Completion Checklists" in procedure
    assert "Checker Feedback Examples" in gap_revision
    assert_prompt_contracts(
        gap_revision,
        semantic_anchor(
            "planner gap revision keeps convention mismatch example",
            "Convention mismatch between imported reference and lock",
        ),
    )
