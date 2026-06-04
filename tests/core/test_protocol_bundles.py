"""Tests for metadata-driven protocol bundle selection."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from gpd.contracts import ResearchContract
from gpd.core.protocol_bundles import (
    BundleAsset,
    BundleAssets,
    BundleVerifierExtension,
    ResolvedProtocolBundle,
    build_protocol_bundle_load_manifest,
    get_protocol_bundle,
    invalidate_protocol_bundle_cache,
    list_protocol_bundles,
    render_protocol_bundle_context,
    select_protocol_bundles,
)

_FORBIDDEN_MANIFEST_ASSET_BODY_FIELDS = {"body", "content", "text", "markdown"}


def _stat_mech_contract() -> ResearchContract:
    return ResearchContract.model_validate(
        {
            "scope": {
                "question": "What critical exponents and finite-size scaling collapse does the simulation recover?",
            },
            "observables": [
                {
                    "id": "obs-binder",
                    "name": "Binder cumulant crossing",
                    "kind": "curve",
                    "definition": "Binder cumulant across temperature and system size",
                }
            ],
            "claims": [
                {
                    "id": "claim-critical",
                    "statement": "The model exhibits the expected universality class",
                    "deliverables": ["deliv-dataset", "deliv-figure"],
                    "acceptance_tests": ["test-benchmark"],
                    "references": ["ref-benchmark"],
                }
            ],
            "deliverables": [
                {
                    "id": "deliv-dataset",
                    "kind": "dataset",
                    "path": "results/raw-measurements.csv",
                    "description": "Raw Monte Carlo measurements with metadata",
                },
                {
                    "id": "deliv-figure",
                    "kind": "figure",
                    "path": "figures/finite-size-collapse.png",
                    "description": "Finite-size scaling collapse figure",
                },
            ],
            "acceptance_tests": [
                {
                    "id": "test-benchmark",
                    "subject": "claim-critical",
                    "kind": "benchmark",
                    "procedure": "Compare finite-size scaling and critical exponents against high-precision literature benchmarks",
                    "pass_condition": "Recovered exponents match benchmark within uncertainty",
                }
            ],
            "references": [
                {
                    "id": "ref-benchmark",
                    "kind": "paper",
                    "locator": "High-precision Monte Carlo benchmark paper",
                    "role": "benchmark",
                    "why_it_matters": "Decisive benchmark for universality and finite-size behavior",
                    "required_actions": ["read", "compare", "cite"],
                }
            ],
            "forbidden_proxies": [
                {
                    "id": "fp-trend",
                    "subject": "claim-critical",
                    "proxy": "Qualitative agreement without benchmarked scaling analysis",
                    "reason": "Would allow false progress through pretty plots alone",
                }
            ],
            "uncertainty_markers": {
                "weakest_anchors": ["Autocorrelation estimate near criticality"],
                "disconfirming_observations": ["Finite-size crossings drift outside the expected universality window"],
            },
        }
    )


def _benchmark_only_contract() -> ResearchContract:
    return ResearchContract.model_validate(
        {
            "scope": {
                "question": "Does the output match a benchmark?",
            },
            "acceptance_tests": [
                {
                    "id": "test-benchmark",
                    "subject": "claim-generic",
                    "kind": "benchmark",
                    "procedure": "Compare against a benchmark.",
                    "pass_condition": "Matches benchmark.",
                }
            ],
            "references": [
                {
                    "id": "ref-benchmark",
                    "kind": "paper",
                    "locator": "Benchmark paper",
                    "role": "benchmark",
                    "why_it_matters": "Reference comparison.",
                }
            ],
        }
    )


def _project_text(what_this_is: str, framework: str, known_results: str) -> str:
    return f"""
    # Test Project

    ## What This Is
    {what_this_is}

    ## Research Context

    ### Theoretical Framework
    {framework}

    ### Known Results
    {known_results}
    """


def _resolved_bundle_from_registry(bundle_id: str) -> ResolvedProtocolBundle:
    bundle = get_protocol_bundle(bundle_id)
    assert bundle is not None
    return ResolvedProtocolBundle(
        bundle_id=bundle.bundle_id,
        title=bundle.title,
        summary=bundle.summary,
        score=1,
        selection_tags=bundle.selection_tags,
        assets=bundle.assets,
        anchor_prompts=bundle.anchor_prompts,
        reference_prompts=bundle.reference_prompts,
        estimator_policies=bundle.estimator_policies,
        decisive_artifact_guidance=bundle.decisive_artifact_guidance,
        verifier_extensions=bundle.verifier_extensions,
    )


def _bundle_contract(
    *,
    question: str,
    observable_name: str,
    observable_kind: str,
    observable_definition: str,
    claim_statement: str,
    dataset_path: str,
    figure_path: str,
    procedure: str,
    pass_condition: str,
    reference_locator: str,
    reference_why: str,
    forbidden_proxy: str,
) -> ResearchContract:
    return ResearchContract.model_validate(
        {
            "scope": {
                "question": question,
            },
            "observables": [
                {
                    "id": "obs-primary",
                    "name": observable_name,
                    "kind": observable_kind,
                    "definition": observable_definition,
                }
            ],
            "claims": [
                {
                    "id": "claim-primary",
                    "statement": claim_statement,
                    "deliverables": ["deliv-data", "deliv-figure"],
                    "acceptance_tests": ["test-benchmark"],
                    "references": ["ref-benchmark"],
                }
            ],
            "deliverables": [
                {
                    "id": "deliv-data",
                    "kind": "dataset",
                    "path": dataset_path,
                    "description": "Primary dataset or checkpoint artifact",
                },
                {
                    "id": "deliv-figure",
                    "kind": "figure",
                    "path": figure_path,
                    "description": "Primary benchmark or comparison figure",
                },
            ],
            "acceptance_tests": [
                {
                    "id": "test-benchmark",
                    "subject": "claim-primary",
                    "kind": "benchmark",
                    "procedure": procedure,
                    "pass_condition": pass_condition,
                }
            ],
            "references": [
                {
                    "id": "ref-benchmark",
                    "kind": "paper",
                    "locator": reference_locator,
                    "role": "benchmark",
                    "why_it_matters": reference_why,
                    "required_actions": ["read", "compare", "cite"],
                    "must_surface": True,
                    "applies_to": ["claim-primary"],
                }
            ],
            "forbidden_proxies": [
                {
                    "id": "fp-proxy",
                    "subject": "claim-primary",
                    "proxy": forbidden_proxy,
                    "reason": "Would allow reporting success without the decisive benchmark-backed observable.",
                }
            ],
            "uncertainty_markers": {
                "weakest_anchors": ["Benchmark comparability under the stated conventions"],
                "disconfirming_observations": [
                    "Benchmark agreement fails once the decisive comparison is made explicit"
                ],
            },
        }
    )


def test_bundle_registry_lists_curated_bundles() -> None:
    bundle_ids = {bundle.bundle_id for bundle in list_protocol_bundles()}
    assert {
        "stat-mech-simulation",
        "numerical-relativity",
        "lattice-gauge-monte-carlo",
        "tensor-network-dynamics",
        "cosmological-perturbation-cmb",
        "fluid-mhd-dynamics",
        "density-functional-electronic-structure",
    } <= bundle_ids


def test_get_protocol_bundle_returns_verifier_extensions() -> None:
    bundle = get_protocol_bundle("stat-mech-simulation")

    assert bundle is not None
    assert bundle.trigger.min_term_matches == 2
    assert bundle.trigger.min_tag_matches == 1
    assert bundle.assets.subfield_guides[0].path == "references/subfields/stat-mech.md"
    assert bundle.assets.planning_guides[0].path == "references/planning/statistical-mechanics.md"
    assert bundle.verifier_extensions[0].check_ids == ["5.4", "5.14", "5.16"]


def test_list_protocol_bundles_skips_invalid_bundle_files(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    bundles_dir = tmp_path / "bundles"
    bundles_dir.mkdir()
    (bundles_dir / "valid-bundle.md").write_text(
        """---
bundle_id: valid-bundle
bundle_version: 1
title: Valid Bundle
summary: Valid bundles remain available.
trigger:
  any_terms:
    - benchmark
  min_term_matches: 1
---

# Valid Bundle
""",
        encoding="utf-8",
    )
    (bundles_dir / "broken-frontmatter.md").write_text(
        """---
bundle_id: broken-frontmatter
title: Broken Frontmatter
summary: [unterminated
---

# Broken Frontmatter
""",
        encoding="utf-8",
    )
    (bundles_dir / "invalid-schema.md").write_text(
        """---
bundle_id: invalid-schema
bundle_version: nope
title: Invalid Schema
summary: This bundle should be skipped.
---

# Invalid Schema
""",
        encoding="utf-8",
    )

    try:
        with caplog.at_level(logging.WARNING, logger="gpd.core.protocol_bundles"):
            bundles = list_protocol_bundles(bundles_dir=bundles_dir)
            bundle = get_protocol_bundle("valid-bundle", bundles_dir=bundles_dir)
    finally:
        invalidate_protocol_bundle_cache()

    assert [entry.bundle_id for entry in bundles] == ["valid-bundle"]
    assert bundle is not None

    warning_messages = [
        record.message for record in caplog.records if "Skipping invalid protocol bundle" in record.message
    ]
    assert len(warning_messages) == 2
    assert any("broken-frontmatter.md" in message for message in warning_messages)
    assert any("invalid-schema.md" in message for message in warning_messages)


def test_select_protocol_bundles_uses_project_metadata_and_contract() -> None:
    project_text = """
    # Test Project

    ## What This Is
    Monte Carlo study of a statistical mechanics lattice model near the critical point.

    ## Research Context

    ### Theoretical Framework
    Statistical mechanics

    ### Known Results
    Compare Binder cumulants, autocorrelation times, and finite-size scaling to benchmark data.
    """

    selected = select_protocol_bundles(project_text, _stat_mech_contract())

    assert [bundle.bundle_id for bundle in selected] == ["stat-mech-simulation"]
    assert "acceptance-kind:benchmark" in selected[0].matched_tags
    assert "finite-size scaling" in selected[0].matched_terms
    assert "references/protocols/monte-carlo.md" in selected[0].asset_paths
    assert "references/planning/statistical-mechanics.md" in selected[0].asset_paths


def test_bundle_assets_iterate_planning_guides_in_stable_role_order() -> None:
    assets = BundleAssets(
        protocols_optional=[BundleAsset(path="references/protocols/statistical-inference.md")],
        planning_guides=[BundleAsset(path="references/planning/planner-approximations.md")],
        execution_guides=[BundleAsset(path="references/execution/executor-subfield-guide.md")],
    )

    assert [role for role, _asset in assets.iter_assets()] == [
        "protocols_optional",
        "planning_guides",
        "execution_guides",
    ]


def test_planning_guides_use_bundle_asset_path_validation(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    bundles_dir = tmp_path / "bundles"
    bundles_dir.mkdir()
    (bundles_dir / "invalid-planning-guide.md").write_text(
        """---
bundle_id: invalid-planning-guide
bundle_version: 1
title: Invalid Planning Guide
summary: Planning guide paths must stay within specs.
trigger:
  any_terms:
    - benchmark
  min_term_matches: 1
assets:
  planning_guides:
    - path: ../outside.md
---

# Invalid Planning Guide
""",
        encoding="utf-8",
    )

    try:
        with caplog.at_level(logging.WARNING, logger="gpd.core.protocol_bundles"):
            bundles = list_protocol_bundles(bundles_dir=bundles_dir)
    finally:
        invalidate_protocol_bundle_cache()

    assert bundles == []
    assert any("invalid-planning-guide.md" in record.message for record in caplog.records)


def test_build_protocol_bundle_load_manifest_is_metadata_only_and_role_keyed() -> None:
    selected = select_protocol_bundles(
        "Statistical mechanics Monte Carlo with autocorrelation and finite-size scaling benchmarks.",
        _stat_mech_contract(),
    )

    manifest = build_protocol_bundle_load_manifest(selected)

    assert manifest["schema_version"] == 1
    assert manifest["selection_source"] == "project_metadata"
    assert manifest["selected_bundle_ids"] == ["stat-mech-simulation"]
    assert manifest["bundle_count"] == 1
    assert manifest["missing_bundle_ids"] == []

    bundle_payload = manifest["bundles"][0]
    assert bundle_payload["bundle_id"] == "stat-mech-simulation"
    assert bundle_payload["selection"]["matched_terms"]
    assert "asset_paths" not in bundle_payload
    assert "body" not in bundle_payload

    for assets in bundle_payload["assets"].values():
        for asset_payload in assets:
            assert asset_payload["body_loaded"] is False
            assert _FORBIDDEN_MANIFEST_ASSET_BODY_FIELDS.isdisjoint(asset_payload)

    planning_guides = bundle_payload["assets"]["planning_guides"]
    assert planning_guides == [
        {
            "path": "references/planning/statistical-mechanics.md",
            "portable_path": "@{GPD_INSTALL_DIR}/references/planning/statistical-mechanics.md",
            "required": False,
            "note": (
                "Use the ensemble, scaling, thermalization, and benchmark-before-production skeleton "
                "when planning simulation phases."
            ),
            "body_loaded": False,
        }
    ]
    serialized = json.dumps(manifest)
    assert "Use for partition functions" not in serialized


def test_protocol_bundle_load_manifest_marks_every_registered_asset_handle_only() -> None:
    selected = [_resolved_bundle_from_registry(bundle.bundle_id) for bundle in list_protocol_bundles()]

    manifest = build_protocol_bundle_load_manifest(selected)

    asset_count = 0
    for bundle_payload in manifest["bundles"]:
        for assets in bundle_payload["assets"].values():
            for asset_payload in assets:
                asset_count += 1
                assert asset_payload["body_loaded"] is False
                assert _FORBIDDEN_MANIFEST_ASSET_BODY_FIELDS.isdisjoint(asset_payload)
                assert set(asset_payload) == {
                    "path",
                    "portable_path",
                    "required",
                    "note",
                    "body_loaded",
                }

    assert asset_count > 0


def test_render_protocol_bundle_context_is_explicit_when_none_selected() -> None:
    rendered = render_protocol_bundle_context([])

    assert "None selected from project metadata" in rendered
    assert "Fall back to shared protocols and on-demand routing." in rendered


def test_render_protocol_bundle_context_surfaces_guidance() -> None:
    selected = select_protocol_bundles(
        "Statistical mechanics Monte Carlo with autocorrelation and finite-size scaling benchmarks.",
        _stat_mech_contract(),
    )

    rendered = render_protocol_bundle_context(selected)

    assert json.dumps("Statistical Mechanics Simulation", ensure_ascii=False) in rendered
    assert json.dumps("stat-mech-simulation", ensure_ascii=False) in rendered
    assert "Usage contract: additive specialized guidance only." in rendered
    assert "Selection tags:" in rendered
    assert "Estimator policies:" in rendered
    assert "Verifier extensions:" in rendered
    assert "planning guides:" in rendered
    assert "{GPD_INSTALL_DIR}/references/protocols/monte-carlo.md" in rendered
    assert "{GPD_INSTALL_DIR}/references/planning/statistical-mechanics.md" in rendered


def test_render_protocol_bundle_context_includes_asset_notes() -> None:
    selected = [
        ResolvedProtocolBundle(
            bundle_id="note-test",
            title="Note Test",
            summary="Bundle used to verify asset note rendering.",
            score=1,
            assets=BundleAssets(
                protocols_core=[
                    BundleAsset(path="references/protocols/note-test.md", note="Use this as the canonical overview"),
                ]
            ),
        )
    ]

    rendered = render_protocol_bundle_context(selected)

    assert f"(note: {json.dumps('Use this as the canonical overview', ensure_ascii=False)})" in rendered
    assert "{GPD_INSTALL_DIR}/references/protocols/note-test.md" in rendered


def test_render_protocol_bundle_context_literalizes_markdown_sensitive_metadata() -> None:
    selected = [
        ResolvedProtocolBundle(
            bundle_id="bundle-id\n### injected",
            title="Bundle title\n## injected",
            summary="Bundle summary\n### injected",
            score=1,
            matched_tags=["tag-one", "tag-two\n### injected"],
            matched_terms=["term-one", "term-two\n## injected"],
            selection_tags=["selection-one", "selection-two\n### injected"],
            assets=BundleAssets(
                protocols_core=[
                    BundleAsset(
                        path="references/protocols/malicious.md",
                        note="note\n### injected",
                    )
                ]
            ),
            anchor_prompts=["anchor-one", "anchor-two\n### injected"],
            reference_prompts=["reference-one", "reference-two\n## injected"],
            estimator_policies=["policy-one", "policy-two\n### injected"],
            decisive_artifact_guidance=["artifact-one", "artifact-two\n## injected"],
            verifier_extensions=[
                BundleVerifierExtension(
                    name="extension label\n### injected",
                    rationale="Rationale text.",
                    check_ids=["5.1", "5.2\n### injected"],
                )
            ],
        )
    ]

    rendered = render_protocol_bundle_context(selected)

    assert rendered.count("\n### ") == 1
    assert "\n### injected" not in rendered
    assert "\n## injected" not in rendered
    assert json.dumps("Bundle title\n## injected", ensure_ascii=False) in rendered
    assert json.dumps("Bundle summary\n### injected", ensure_ascii=False) in rendered
    assert json.dumps(["tag-one", "tag-two\n### injected"], ensure_ascii=False) in rendered
    assert json.dumps("note\n### injected", ensure_ascii=False) in rendered
    assert json.dumps("extension label\n### injected", ensure_ascii=False) in rendered


def test_select_protocol_bundles_lattice_gauge_excludes_stat_mech_when_both_match() -> None:
    project_text = _project_text(
        "Hybrid Monte Carlo lattice QCD study with Wilson fermion ensembles and finite-size scaling diagnostics.",
        "Gauge theory",
        "Scale setting, continuum extrapolation, autocorrelation, topology freezing, and benchmark comparisons are all required.",
    )
    contract = _bundle_contract(
        question="Does the lattice-QCD analysis recover benchmark observables after continuum extrapolation?",
        observable_name="Continuum-extrapolated hadron mass",
        observable_kind="scalar",
        observable_definition="Hadronic observable extracted from lattice correlators and extrapolated to the continuum limit",
        claim_statement="The lattice calculation reproduces benchmark hadronic behavior with controlled topology and continuum systematics.",
        dataset_path="results/lattice-ensembles.csv",
        figure_path="figures/lattice-continuum-fit.png",
        procedure="Compare continuum-extrapolated observables and topology diagnostics against trusted lattice benchmarks.",
        pass_condition="Continuum-fit result and topology diagnostics agree with benchmark expectations within uncertainty.",
        reference_locator="Trusted lattice-QCD benchmark ensemble and scale-setting paper",
        reference_why="Benchmark ensembles and reference scales anchor the lattice comparison.",
        forbidden_proxy="Pretty correlator plateaus without topology, scale-setting, or continuum checks",
    )

    selected = select_protocol_bundles(project_text, contract)

    assert [bundle.bundle_id for bundle in selected] == ["lattice-gauge-monte-carlo"]
    assert "lattice qcd" in selected[0].matched_terms


def test_select_protocol_bundles_matches_heading_derived_tags(tmp_path) -> None:
    bundles_dir = tmp_path / "bundles"
    bundles_dir.mkdir()
    (bundles_dir / "heading-tag-bundle.md").write_text(
        """---
bundle_id: heading-tag-bundle
bundle_version: 1
title: Heading Tag Bundle
summary: Test bundle for heading-derived project tags.
trigger:
  any_tags:
    - theoretical-framework:statistical-mechanics
  min_tag_matches: 1
  min_score: 4
---

# Heading Tag Bundle
""",
        encoding="utf-8",
    )

    try:
        selected = select_protocol_bundles(
            _project_text(
                "Monte Carlo study of a statistical mechanics model.",
                "Statistical mechanics",
                "Finite-size scaling is benchmarked.",
            ),
            None,
            bundles_dir=bundles_dir,
        )
    finally:
        invalidate_protocol_bundle_cache()

    assert [bundle.bundle_id for bundle in selected] == ["heading-tag-bundle"]
    assert selected[0].matched_tags == ["theoretical-framework:statistical-mechanics"]


@pytest.mark.parametrize(
    ("bundle_id", "project_text", "contract", "expected_asset", "expected_term"),
    [
        (
            "numerical-relativity",
            _project_text(
                "BSSN numerical relativity study of a binary black hole system with moving-puncture evolution.",
                "General relativity",
                "Track apparent horizon properties, constraint propagation, and gravitational waveform benchmarks.",
            ),
            _bundle_contract(
                question="What waveform and remnant properties does the BSSN evolution recover?",
                observable_name="Waveform phase difference",
                observable_kind="curve",
                observable_definition="Phase-aligned gravitational waveform comparison against trusted reference data",
                claim_statement="The evolution reproduces benchmark waveform structure with controlled constraint growth.",
                dataset_path="results/nr-constraints.csv",
                figure_path="figures/nr-waveform-comparison.png",
                procedure="Compare waveform phase, remnant properties, and constraint convergence against a trusted numerical-relativity benchmark.",
                pass_condition="Waveform and remnant metrics agree within the stated numerical uncertainty.",
                reference_locator="SXS-style numerical-relativity benchmark waveform catalog",
                reference_why="Benchmark waveform and remnant data anchor the strong-field result.",
                forbidden_proxy="Smooth-looking waveforms without converged constraints or benchmark agreement",
            ),
            "references/protocols/numerical-relativity.md",
            "bssn",
        ),
        (
            "lattice-gauge-monte-carlo",
            _project_text(
                "Hybrid Monte Carlo lattice QCD study with Wilson fermion ensembles and gradient-flow diagnostics.",
                "Gauge theory",
                "Scale setting, continuum extrapolation, and topology freezing checks are benchmarked against trusted ensembles.",
            ),
            _bundle_contract(
                question="Does the lattice-QCD analysis recover benchmark hadronic observables after continuum extrapolation?",
                observable_name="Continuum-extrapolated hadron mass",
                observable_kind="scalar",
                observable_definition="Hadronic observable extracted from lattice correlators and extrapolated to the continuum limit",
                claim_statement="The lattice calculation reproduces benchmark hadronic behavior with controlled topology and continuum systematics.",
                dataset_path="results/lattice-ensembles.csv",
                figure_path="figures/lattice-continuum-fit.png",
                procedure="Compare continuum-extrapolated observables and topology diagnostics against trusted lattice benchmarks.",
                pass_condition="Continuum-fit result and topology diagnostics agree with benchmark expectations within uncertainty.",
                reference_locator="Trusted lattice-QCD benchmark ensemble and scale-setting paper",
                reference_why="Benchmark ensembles and reference scales anchor the lattice comparison.",
                forbidden_proxy="Pretty correlator plateaus without topology, scale-setting, or continuum checks",
            ),
            "references/protocols/lattice-gauge-theory.md",
            "lattice qcd",
        ),
        (
            "tensor-network-dynamics",
            _project_text(
                "Tensor network quench study using MPS and TEBD with explicit bond-dimension growth control.",
                "Condensed matter",
                "Benchmark the entanglement growth window and compare observables against trusted DMRG or exact-diagonalization baselines.",
            ),
            _bundle_contract(
                question="How long does the tensor-network evolution remain reliable before entanglement saturation dominates?",
                observable_name="Post-quench magnetization",
                observable_kind="curve",
                observable_definition="Time-dependent many-body observable extracted from a tensor-network simulation",
                claim_statement="The tensor-network calculation captures benchmark dynamics within the declared reliable bond-dimension window.",
                dataset_path="results/tensor-network-time-series.csv",
                figure_path="figures/tensor-network-convergence.png",
                procedure="Compare bond-dimension convergence and benchmark observables against trusted tensor-network or ED references.",
                pass_condition="Decisive observables remain benchmark-consistent inside the declared reliable time window.",
                reference_locator="Published DMRG or exact-diagonalization benchmark for the same quench setup",
                reference_why="Benchmark data anchors the reliable finite-chi time window.",
                forbidden_proxy="Late-time traces shown after entanglement saturation without benchmarked validity window",
            ),
            "references/protocols/tensor-networks.md",
            "tebd",
        ),
        (
            "cosmological-perturbation-cmb",
            _project_text(
                "Cosmological perturbation calculation of the CMB power spectrum using CLASS transfer functions and Bardeen potentials.",
                "Cosmology",
                "Cross-check acoustic-peak structure, transfer functions, and Planck-normalized observables against code baselines.",
            ),
            _bundle_contract(
                question="Do the perturbation equations recover benchmark CMB and transfer-function behavior?",
                observable_name="CMB TT power spectrum",
                observable_kind="curve",
                observable_definition="Angular power spectrum computed from cosmological perturbation evolution",
                claim_statement="The cosmological perturbation pipeline reproduces benchmark CMB structure with consistent gauge and normalization choices.",
                dataset_path="results/cmb-spectrum.csv",
                figure_path="figures/cmb-class-comparison.png",
                procedure="Compare transfer functions and CMB spectra against CLASS or CAMB benchmark outputs and analytic limits.",
                pass_condition="Benchmark CMB observables and analytic limits agree within the stated tolerance.",
                reference_locator="Planck and CLASS benchmark cosmology reference",
                reference_why="Benchmark spectra and conventions anchor the cosmological comparison.",
                forbidden_proxy="Background-only agreement without transfer-function or CMB benchmark parity",
            ),
            "references/protocols/cosmological-perturbation-theory.md",
            "class",
        ),
        (
            "fluid-mhd-dynamics",
            _project_text(
                "Magnetohydrodynamics simulation of Alfven-wave propagation and turbulence spectra with explicit div B control.",
                "Fluid dynamics",
                "Reynolds-number, Lundquist-number, and CFL-sensitive behavior is benchmarked against analytic and literature expectations.",
            ),
            _bundle_contract(
                question="Does the fluid or MHD simulation reproduce benchmark wave speeds and turbulence behavior in the intended regime?",
                observable_name="Alfven-wave phase speed",
                observable_kind="scalar",
                observable_definition="Measured phase speed or growth rate from the simulated fluid or MHD system",
                claim_statement="The simulation reproduces benchmark wave or instability behavior in the declared flow regime.",
                dataset_path="results/fluid-benchmarks.csv",
                figure_path="figures/fluid-spectrum-comparison.png",
                procedure="Compare wave speeds, conservation diagnostics, and turbulence spectra against analytic or literature benchmarks.",
                pass_condition="Decisive fluid or MHD observables agree with regime-appropriate benchmark expectations.",
                reference_locator="Trusted CFD or MHD benchmark reference for the chosen setup",
                reference_why="Benchmark flow behavior anchors regime-specific validation.",
                forbidden_proxy="Visually plausible flow fields without regime checks, conservation diagnostics, or benchmark comparisons",
            ),
            "references/protocols/fluid-dynamics-mhd.md",
            "alfven wave",
        ),
        (
            "density-functional-electronic-structure",
            _project_text(
                "Density functional theory calculation of electronic structure with Kohn-Sham states, pseudopotentials, and k-point mesh convergence.",
                "Condensed matter",
                "Benchmark band-gap and structural observables while tracking exchange-correlation and plane-wave cutoff choices.",
            ),
            _bundle_contract(
                question="Does the DFT workflow recover benchmark electronic-structure observables with converged numerical settings?",
                observable_name="Band gap",
                observable_kind="scalar",
                observable_definition="Electronic-structure observable extracted from a DFT or DFT+U calculation",
                claim_statement="The electronic-structure workflow reproduces benchmark observables with explicit functional and convergence discipline.",
                dataset_path="results/dft-convergence.csv",
                figure_path="figures/dft-benchmark-comparison.png",
                procedure="Compare converged observables against experiment or trusted higher-level references while reporting functional sensitivity.",
                pass_condition="Benchmark observables agree within the stated uncertainty after convergence and functional-family checks.",
                reference_locator="Electronic-structure benchmark paper or trusted experimental reference",
                reference_why="Benchmark observables anchor the DFT comparison and expose proxy-versus-direct gaps.",
                forbidden_proxy="Single-shot Kohn-Sham output treated as final without convergence or benchmark comparison",
            ),
            "references/protocols/density-functional-theory.md",
            "kohn sham",
        ),
    ],
)
def test_select_protocol_bundles_identifies_curated_bundle(
    bundle_id: str,
    project_text: str,
    contract: ResearchContract,
    expected_asset: str,
    expected_term: str,
) -> None:
    selected = select_protocol_bundles(project_text, contract)

    assert [bundle.bundle_id for bundle in selected] == [bundle_id]
    assert expected_asset in selected[0].asset_paths
    assert expected_term in selected[0].matched_terms


@pytest.mark.parametrize(
    ("bundle_id", "project_text", "contract", "expected_role_paths"),
    [
        (
            "fluid-mhd-dynamics",
            _project_text(
                "Magnetohydrodynamics simulation of Alfven-wave propagation, turbulence spectra, and div B control.",
                "Fluid dynamics",
                "Use Reynolds-number, Lundquist-number, CFL, conservation, and analytic wave-speed benchmarks.",
            ),
            _bundle_contract(
                question="Does the MHD simulation preserve div B and reproduce benchmark wave behavior?",
                observable_name="Alfven-wave phase speed",
                observable_kind="scalar",
                observable_definition="Measured phase speed from the simulated MHD system",
                claim_statement="The simulation reproduces benchmark MHD wave behavior with controlled divergence.",
                dataset_path="results/mhd-benchmarks.csv",
                figure_path="figures/mhd-wave-comparison.png",
                procedure="Compare wave speed, conservation, divergence, and spectrum diagnostics against benchmarks.",
                pass_condition="MHD observables agree with regime-appropriate benchmark expectations.",
                reference_locator="Trusted MHD benchmark reference for Alfven-wave propagation",
                reference_why="Benchmark wave behavior anchors the regime-specific validation.",
                forbidden_proxy="Visually plausible fields without div B, conservation, or benchmark checks",
            ),
            {
                "verification_domains": {"references/verification/domains/verification-domain-fluid-plasma.md"},
                "execution_guides": {"references/execution/guards/fluid-mhd-dynamics.md"},
            },
        ),
        (
            "lattice-gauge-monte-carlo",
            _project_text(
                "Hybrid Monte Carlo lattice QCD study with Wilson fermions, topology freezing, and continuum extrapolation.",
                "Gauge theory",
                "Use scale setting, finite-volume checks, topology diagnostics, and trusted lattice benchmarks.",
            ),
            _bundle_contract(
                question="Does the lattice-QCD analysis survive continuum, topology, and benchmark checks?",
                observable_name="Continuum-extrapolated hadron mass",
                observable_kind="scalar",
                observable_definition="Hadronic observable extracted from lattice correlators and extrapolated to the continuum",
                claim_statement="The lattice calculation reproduces benchmark hadronic behavior with controlled systematics.",
                dataset_path="results/lattice-ensembles.csv",
                figure_path="figures/lattice-continuum-fit.png",
                procedure="Compare continuum-extrapolated observables and topology diagnostics against benchmarks.",
                pass_condition="Continuum-fit result and topology diagnostics agree within uncertainty.",
                reference_locator="Trusted lattice-QCD benchmark ensemble and scale-setting paper",
                reference_why="Benchmark ensembles and reference scales anchor the lattice comparison.",
                forbidden_proxy="Single-spacing correlator agreement without topology, scale-setting, or continuum checks",
            ),
            {
                "verification_domains": {
                    "references/verification/domains/verification-domain-qft.md",
                    "references/verification/domains/verification-domain-nuclear-particle.md",
                },
                "execution_guides": {"references/execution/guards/lattice-gauge-monte-carlo.md"},
            },
        ),
        (
            "numerical-relativity",
            _project_text(
                "BSSN numerical relativity study of a binary black hole system with moving-puncture evolution.",
                "General relativity",
                "Track apparent horizons, constraint propagation, and gravitational waveform benchmarks.",
            ),
            _bundle_contract(
                question="Does the BSSN evolution recover benchmark waveform and remnant properties?",
                observable_name="Waveform phase difference",
                observable_kind="curve",
                observable_definition="Phase-aligned gravitational waveform comparison against trusted reference data",
                claim_statement="The evolution reproduces benchmark waveform structure with controlled constraint growth.",
                dataset_path="results/nr-constraints.csv",
                figure_path="figures/nr-waveform-comparison.png",
                procedure="Compare waveform phase, remnant properties, and constraint convergence against benchmarks.",
                pass_condition="Waveform and remnant metrics agree within the stated numerical uncertainty.",
                reference_locator="SXS-style numerical-relativity benchmark waveform catalog",
                reference_why="Benchmark waveform and remnant data anchor the strong-field result.",
                forbidden_proxy="Smooth-looking waveforms without converged constraints or benchmark agreement",
            ),
            {
                "verification_domains": {"references/verification/domains/verification-domain-gr-cosmology.md"},
                "execution_guides": {"references/execution/guards/numerical-relativity.md"},
            },
        ),
        (
            "tensor-network-dynamics",
            _project_text(
                "Tensor network quench study using MPS and TEBD with explicit bond-dimension growth control.",
                "Condensed matter",
                "Benchmark entanglement growth and observables against trusted DMRG or exact-diagonalization baselines.",
            ),
            _bundle_contract(
                question="How long does the tensor-network evolution remain reliable before entanglement saturation dominates?",
                observable_name="Post-quench magnetization",
                observable_kind="curve",
                observable_definition="Time-dependent many-body observable from a tensor-network simulation",
                claim_statement="The calculation captures benchmark dynamics inside the declared reliable bond-dimension window.",
                dataset_path="results/tensor-network-time-series.csv",
                figure_path="figures/tensor-network-convergence.png",
                procedure="Compare bond-dimension convergence and benchmark observables against trusted references.",
                pass_condition="Decisive observables remain benchmark-consistent inside the reliable time window.",
                reference_locator="Published DMRG or exact-diagonalization benchmark for the same quench setup",
                reference_why="Benchmark data anchors the reliable finite-chi time window.",
                forbidden_proxy="Late-time traces shown after entanglement saturation without benchmarked validity window",
            ),
            {
                "verification_domains": {"references/verification/domains/verification-domain-condmat.md"},
                "execution_guides": {"references/execution/guards/tensor-network-dynamics.md"},
            },
        ),
    ],
)
def test_selected_canary_bundles_expose_domain_and_execution_handles(
    bundle_id: str,
    project_text: str,
    contract: ResearchContract,
    expected_role_paths: dict[str, set[str]],
) -> None:
    selected = select_protocol_bundles(project_text, contract)
    manifest = build_protocol_bundle_load_manifest(selected)

    assert [bundle.bundle_id for bundle in selected] == [bundle_id]
    bundle_assets = manifest["bundles"][0]["assets"]
    for role, expected_paths in expected_role_paths.items():
        role_payloads = bundle_assets[role]
        role_paths = {asset_payload["path"] for asset_payload in role_payloads}
        assert expected_paths <= role_paths
        for asset_payload in role_payloads:
            assert asset_payload["body_loaded"] is False
            assert _FORBIDDEN_MANIFEST_ASSET_BODY_FIELDS.isdisjoint(asset_payload)


def test_select_protocol_bundles_rejects_weak_text_only_overlap() -> None:
    selected = select_protocol_bundles(
        "Monte Carlo autocorrelation study with some benchmark notes.",
        None,
    )

    assert selected == []


def test_select_protocol_bundles_rejects_benchmark_tags_without_enough_distinctive_terms() -> None:
    selected = select_protocol_bundles(
        "Monte Carlo benchmark comparison for a generic model.",
        _benchmark_only_contract(),
    )

    assert selected == []


def test_mismatched_project_metadata_keeps_bundle_context_in_generic_fallback_mode() -> None:
    selected = select_protocol_bundles(
        """
        # Test Project

        ## What This Is
        Quantum-gravity saddle bookkeeping with Page-curve comparisons and holographic entropy arguments.
        """,
        _benchmark_only_contract(),
    )

    assert selected == []
    rendered = render_protocol_bundle_context(selected)
    assert "Usage contract: additive specialized guidance only." in rendered
    assert "None selected from project metadata" in rendered
    assert "Fall back to shared protocols and on-demand routing." in rendered
