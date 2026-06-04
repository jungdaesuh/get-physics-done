"""Prompt-budget assertions for `gpd-executor` bootstrap loading."""

from __future__ import annotations

from pathlib import Path

from gpd.adapters.install_utils import expand_at_includes
from tests.assertion_taxonomy_support import assert_prompt_contracts, semantic_anchor

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "src/gpd/agents"
SPECS_DIR = REPO_ROOT / "src/gpd/specs"
EXECUTION_DIR = SPECS_DIR / "references/execution"
ORCHESTRATION_DIR = SPECS_DIR / "references/orchestration"


def _read_executor_prompt() -> str:
    return (AGENTS_DIR / "gpd-executor.md").read_text(encoding="utf-8")


def _read_execution_reference(name: str) -> str:
    return (EXECUTION_DIR / name).read_text(encoding="utf-8")


def _read_orchestration_reference(name: str) -> str:
    return (ORCHESTRATION_DIR / name).read_text(encoding="utf-8")


def _between(text: str, start: str, end: str) -> str:
    _, start_marker, tail = text.partition(start)
    assert start_marker, f"Missing marker: {start}"
    body, end_marker, _ = tail.partition(end)
    assert end_marker, f"Missing marker: {end}"
    return body


def test_executor_bootstrap_does_not_eagerly_load_completion_only_templates() -> None:
    executor = _read_executor_prompt()
    role = _between(executor, "<role>", "</role>")

    assert "@{GPD_INSTALL_DIR}" not in executor
    assert "@{GPD_INSTALL_DIR}/templates/summary.md" not in role
    assert "@{GPD_INSTALL_DIR}/templates/calculation-log.md" not in role
    assert "@{GPD_INSTALL_DIR}/references/protocols/order-of-limits.md" not in role
    assert "Pattern A:" not in role
    assert "Pattern B:" not in role
    assert "Pattern C:" not in role
    assert "Pattern D:" not in role
    assert "first-result" not in role
    assert "pre-fanout" not in role
    assert "bounded execution segment envelope" not in role


def test_executor_prompt_does_not_self_bootstrap_execute_phase() -> None:
    executor = _read_executor_prompt()

    assert "execute-plan command" not in executor
    assert "init execute-phase" not in executor
    assert 'gpd --raw init execute-phase "${PHASE}"' not in executor
    assert_prompt_contracts(
        executor,
        semantic_anchor(
            "executor does not self-bootstrap execute-phase state",
            "Do not bootstrap phase state from inside the executor.",
        ),
    )


def test_expanded_executor_prompt_stays_under_budget_and_excludes_late_publication_artifacts() -> None:
    expanded = expand_at_includes(_read_executor_prompt(), SPECS_DIR, "/runtime/")

    bootstrap, _, _ = expanded.partition("<summary_creation>")

    assert len(expanded) < 60_000
    assert "Order-of-Limits Awareness" not in bootstrap
    assert "main.tex" not in expanded


def test_executor_base_stays_under_phase6_raw_line_budget_and_names_jit_modules() -> None:
    executor = _read_executor_prompt()

    assert len(executor) < 36_500
    assert len(executor.splitlines()) < 630
    assert "@{GPD_INSTALL_DIR}" not in executor
    for module_name in (
        "executor-derivation-checkpoints.md",
        "executor-numerical-protocol.md",
        "executor-tool-preflight.md",
        "executor-protocol-bundle-execution.md",
        "executor-completion.md",
    ):
        assert f"references/execution/{module_name}" in executor


def test_executor_module_load_manifest_is_body_free_late_load_metadata() -> None:
    executor = _read_executor_prompt()
    manifest = _between(executor, "<module_load_manifest>", "</module_load_manifest>")

    assert "module_load_manifest" in manifest
    assert "body-free" in manifest
    assert "load every executor reference" in manifest.lower()
    assert "@{GPD_INSTALL_DIR}" not in manifest
    for module_id, module_path in (
        ("executor.derivation_checkpoints", "references/execution/executor-derivation-checkpoints.md"),
        ("executor.numerical_protocol", "references/execution/executor-numerical-protocol.md"),
        ("executor.tool_preflight", "references/execution/executor-tool-preflight.md"),
        (
            "executor.protocol_bundle_execution",
            "references/execution/executor-protocol-bundle-execution.md",
        ),
        ("executor.completion", "references/execution/executor-completion.md"),
        ("executor.guard_index", "references/execution/guards/README.md"),
        ("executor.guard_core", "references/execution/guards/core-computation-guards.md"),
        ("executor.guard_domain", "references/execution/guards/domain-post-step-guards.md"),
        ("executor.guard_final", "references/execution/guards/final-verification-guards.md"),
    ):
        assert module_id in manifest
        assert module_path in manifest

    assert "% IDENTITY_CLAIM:" not in manifest
    assert "External Tool Failure Table" not in manifest
    assert "Final Self-Check" not in manifest
    assert "```yaml" not in manifest


def test_executor_jit_modules_hold_extracted_execution_detail() -> None:
    executor = _read_executor_prompt()
    derivation = _read_execution_reference("executor-derivation-checkpoints.md")
    numerical = _read_execution_reference("executor-numerical-protocol.md")
    tool_preflight = _read_execution_reference("executor-tool-preflight.md")
    bundle_execution = _read_execution_reference("executor-protocol-bundle-execution.md")
    completion = _read_execution_reference("executor-completion.md")

    assert "% IDENTITY_CLAIM:" not in executor
    assert "BOUNDARY_CONDITIONS:" not in executor
    assert "EXPANSION_ORDER:" not in executor
    assert "External Tool Failure Table" not in executor
    assert "Final Self-Check" not in executor

    assert "% IDENTITY_CLAIM:" in derivation
    assert "BOUNDARY_CONDITIONS:" in derivation
    assert "EXPANSION_ORDER:" in derivation
    assert "cancellation ratio" in derivation

    assert "references/protocols/numerical-computation.md" in numerical
    assert "references/verification/core/verification-numerical.md" in numerical
    assert "references/protocols/symbolic-to-numerical.md" in numerical
    assert "references/protocols/reproducibility.md" in numerical
    assert "[UNVERIFIED - training data]" in numerical

    assert "gpd validate plan-preflight <PLAN.md path>" in tool_preflight
    assert_prompt_contracts(
        tool_preflight,
        semantic_anchor(
            "executor tool preflight blocks on required specialized tools",
            "`required: true` specialized tool is blocking",
        ),
    )
    assert "use `wolfram`" in tool_preflight
    assert "External Tool Failure Table" in tool_preflight

    assert_prompt_contracts(
        bundle_execution,
        semantic_anchor(
            "executor protocol bundle loads only selected assets",
            (
                "Load only selected asset paths",
                "additive specialized guidance only",
                "Keep unselected bundle catalogs absent",
            ),
        ),
    )

    assert "Final Self-Check" in completion
    assert_prompt_contracts(
        completion,
        semantic_anchor(
            "executor completion contract result is invariant across profiles",
            "profiles and autonomy modes do NOT relax contract-result emission",
        ),
    )


def test_executor_guard_catalogs_are_on_demand_assets_not_base_prompt() -> None:
    executor = _read_executor_prompt()
    protocol_loading = _between(executor, "<protocol_loading>", "</protocol_loading>")
    guard_dir = SPECS_DIR / "references/execution/guards"
    guard_index = (guard_dir / "README.md").read_text(encoding="utf-8")
    core_guards = (guard_dir / "core-computation-guards.md").read_text(encoding="utf-8")
    domain_guards = (guard_dir / "domain-post-step-guards.md").read_text(encoding="utf-8")
    final_guards = (guard_dir / "final-verification-guards.md").read_text(encoding="utf-8")

    assert "Computation-Type Mini-Checklist" not in executor
    assert "Angular momentum / CG coefficients" not in executor
    assert "Lattice Boltzmann method" not in executor
    assert "# Domain Post-Step Guards" not in executor
    assert "Eddington luminosity" not in executor

    assert "references/execution/guards/README.md" in executor
    assert "references/execution/guards/core-computation-guards.md" in executor
    assert "references/execution/guards/domain-post-step-guards.md" in executor
    assert "references/execution/guards/final-verification-guards.md" in executor
    assert_prompt_contracts(
        executor,
        semantic_anchor(
            "executor prefers selected execution guide handles",
            "Prefer selected bundle `execution_guides`",
        ),
    )
    assert_prompt_contracts(
        protocol_loading,
        semantic_anchor(
            "executor opens selected handles before domain judgments",
            (
                "protocol_bundle_load_manifest",
                "Before",
                "domain",
                "method",
                "judgment",
                "execution_guides",
                "verification_domains",
                "asset paths",
                "a handle label alone is not evidence",
            ),
            match="casefold_normalized",
        ),
        semantic_anchor(
            "executor context-first protocol wording stays absent",
            "Read `<protocol_bundle_context>`",
            mode="absent",
            match="casefold_normalized",
        ),
    )
    assert protocol_loading.index("protocol_bundle_load_manifest") < protocol_loading.index("Before")
    assert_prompt_contracts(
        guard_index,
        semantic_anchor(
            "guard catalog prefers selected protocol bundle guides",
            "Prefer `execution_guides` listed in the selected protocol bundle context",
        ),
    )

    assert "Angular momentum / CG coefficients" in core_guards
    assert "Lattice Boltzmann method" in core_guards
    assert "# Domain Post-Step Guards" in domain_guards
    assert "Eddington luminosity" in final_guards


def test_curated_bundles_reference_compact_execution_guard_assets() -> None:
    bundle_dir = SPECS_DIR / "bundles"
    guard_dir = SPECS_DIR / "references/execution/guards"
    expected = {
        "cosmological-perturbation-cmb": "cosmological-perturbation-cmb.md",
        "density-functional-electronic-structure": "density-functional-electronic-structure.md",
        "fluid-mhd-dynamics": "fluid-mhd-dynamics.md",
        "lattice-gauge-monte-carlo": "lattice-gauge-monte-carlo.md",
        "numerical-relativity": "numerical-relativity.md",
        "stat-mech-simulation": "stat-mech-simulation.md",
        "tensor-network-dynamics": "tensor-network-dynamics.md",
    }

    for bundle_id, guard_name in expected.items():
        bundle_text = (bundle_dir / f"{bundle_id}.md").read_text(encoding="utf-8")
        guard_path = guard_dir / guard_name

        assert guard_path.exists()
        assert "references/execution/executor-subfield-guide.md" not in bundle_text
        assert f"references/execution/guards/{guard_name}" in bundle_text


def test_executor_context_pressure_thresholds_match_canonical_forced_checkpoint_wording() -> None:
    executor = _read_executor_prompt()
    canonical = (SPECS_DIR / "references/orchestration/context-pressure-thresholds.md").read_text(encoding="utf-8")

    assert "| gpd-executor | < 40% | 40-55% | 55-70% | > 70% |" in canonical
    assert "forced checkpoint at 50%" in canonical
    assert "context-pressure-thresholds.md" in executor
    assert "forced checkpoint starts at 50%" in executor
    assert "ORANGE still starts at 55%" in executor
    assert_prompt_contracts(
        executor,
        semantic_anchor(
            "executor stale context pressure threshold wording absent",
            "If running total exceeds 50%, you are in ORANGE",
            mode="absent",
        ),
    )
    assert ">50% context consumed" not in executor


def test_executor_base_defers_checkpoint_return_and_completion_event_protocols() -> None:
    executor = _read_executor_prompt()

    assert 'type="checkpoint:*"' in executor
    assert "gpd_return.status: checkpoint" in executor
    assert "execute-plan-checkpoints.md" in executor
    assert "continuation-boundary.md" in executor
    assert "executor-completion.md" in executor

    assert "bounded execution segment envelope" not in executor
    assert "Pattern A: Checkpoint-free" not in executor
    assert_prompt_contracts(
        executor,
        semantic_anchor(
            "executor inline checkpoint envelope fields absent",
            "type, plan, progress, completed tasks plus hashes",
            mode="absent",
        ),
    )
    assert 'gpd commit "execute(${phase_number})' not in executor


def test_executor_event_references_own_deferred_protocols() -> None:
    continuation = _read_orchestration_reference("continuation-boundary.md")
    checkpoints = _read_execution_reference("execute-plan-checkpoints.md")
    completion = _read_execution_reference("executor-completion.md")

    assert "one-shot" in continuation
    assert_prompt_contracts(
        continuation,
        semantic_anchor(
            "executor checkpoint continuation stops instead of waiting",
            "must not wait for the user",
        ),
    )
    assert "Checkpoint Return (For Orchestrator)" in checkpoints
    assert "execution_segment" in checkpoints
    assert "gpd validate summary-contract" in completion
    assert "Final Self-Check" in completion
