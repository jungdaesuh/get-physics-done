"""Tests for gpd.core.context — context assembly for AI agent commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gpd.contracts import ResearchContract
from gpd.core import context as context_module
from gpd.core.constants import ProjectLayout
from gpd.core.context import (
    _WRITE_PAPER_INIT_FIELDS,
    _generate_slug,
    _is_phase_complete,
    _load_project_contract,
    _merge_active_references,
    _merge_reference_intake,
    _normalize_phase_name,
    _render_active_reference_context,
    _state_exists,
    init_arxiv_submission,
    init_execute_phase,
    init_literature_review,
    init_map_research,
    init_milestone_op,
    init_new_milestone,
    init_new_project,
    init_peer_review,
    init_phase_op,
    init_plan_phase,
    init_progress,
    init_quick,
    init_research_phase,
    init_respond_to_referees,
    init_resume,
    init_sync_state,
    init_todos,
    init_verify_work,
    init_write_paper,
    load_config,
)
from gpd.core.continuation import RESUMABLE_SEGMENT_STATUSES
from gpd.core.contract_validation import contract_fingerprint
from gpd.core.errors import ConfigError, ValidationError
from gpd.core.recent_projects import record_recent_project
from gpd.core.resume_surface import RESUME_BACKEND_ONLY_FIELDS
from gpd.core.state import default_state_dict
from gpd.core.utils import file_lock
from gpd.core.workflow_staging import load_workflow_stage_manifest
from tests import context_stage_test_support as stage_ctx
from tests.helpers.cli import write_write_paper_authoring_input as _write_write_paper_authoring_input
from tests.workflow_stage_test_support import (
    install_fake_plan_phase_manifest,
    install_fake_stage_manifest,
)

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "stage0"
_write_bundle_ready_contract_state = stage_ctx.write_bundle_ready_contract_state
_write_knowledge_doc = stage_ctx.write_knowledge_doc
_write_manuscript_proof_review_artifacts = stage_ctx.write_manuscript_proof_review_artifacts
_write_manuscript_proof_review_artifacts_with_proof_path = (
    stage_ctx.write_manuscript_proof_review_artifacts_with_proof_path
)
_write_numerical_relativity_contract_state = stage_ctx.write_numerical_relativity_contract_state
_write_numerical_relativity_project = stage_ctx.write_numerical_relativity_project


def test_file_lock_leaves_durable_sidecar_after_release(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    target.write_text("{}", encoding="utf-8")
    lock_path = target.with_suffix(".json.lock")

    with file_lock(target):
        assert lock_path.exists()

    assert lock_path.exists()
    with file_lock(target):
        target.write_text('{"reacquired": true}', encoding="utf-8")

    assert json.loads(target.read_text(encoding="utf-8")) == {"reacquired": True}


def _setup_project(tmp_path: Path) -> Path:
    """Create a minimal GPD project structure and return project root."""
    planning = tmp_path / "GPD"
    planning.mkdir(parents=True, exist_ok=True)
    (planning / "phases").mkdir()
    return tmp_path


def _create_phase_dir(tmp_path: Path, name: str) -> Path:
    """Create a phase directory and return its path."""
    phase_dir = tmp_path / "GPD" / "phases" / name
    phase_dir.mkdir(parents=True, exist_ok=True)
    return phase_dir


def _create_config(tmp_path: Path, config: dict) -> Path:
    """Write config.json and return its path."""
    config_path = tmp_path / "GPD" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return config_path


@pytest.mark.parametrize("case", ("execute", "plan", "arxiv", "resume", "verify", "verify_staged", "progress"))
def test_context_init_does_not_create_state_lock(tmp_path: Path, case: str) -> None:
    _setup_project(tmp_path)
    if case in {"execute", "verify", "verify_staged"}:
        _create_phase_dir(tmp_path, "01-setup")
    if case == "plan":
        _create_phase_dir(tmp_path, "02-analysis")
    if case in {"execute", "plan", "arxiv", "verify", "verify_staged"}:
        _write_project_contract_state(tmp_path)
    if case in {"resume", "progress"}:
        _write_structured_state_memory(tmp_path)
    if case == "arxiv":
        (tmp_path / "GPD" / "PROJECT.md").write_text("# Project\n\nSubmission target.\n", encoding="utf-8")
        stage_ctx.write_project_paper_manuscript(tmp_path)

    actions = {
        "execute": lambda: init_execute_phase(tmp_path, "1", stage="phase_bootstrap"),
        "plan": lambda: init_plan_phase(tmp_path, "2", stage="phase_bootstrap"),
        "arxiv": lambda: init_arxiv_submission(tmp_path, subject="paper/main.tex", stage="bootstrap"),
        "resume": lambda: init_resume(tmp_path),
        "verify": lambda: init_verify_work(tmp_path, "1"),
        "verify_staged": lambda: init_verify_work(tmp_path, "1", stage="session_router"),
        "progress": lambda: init_progress(tmp_path),
    }

    stage_ctx.assert_no_state_lock_after(tmp_path, actions[case])


@pytest.mark.parametrize(
    ("case", "stage", "match"),
    (
        ("execute", "bogus", "Unknown execute-phase stage 'bogus'"),
        ("plan", "bogus", "Unknown plan-phase stage 'bogus'"),
        ("new-project", "bogus", "Unknown new-project stage"),
        ("new-project", "post_scope", "Unknown new-project stage"),
        ("new-project", "does-not-exist", "Unknown new-project stage"),
        ("write-paper", "bogus", "Unknown write-paper stage 'bogus'"),
        ("verify-work", "bogus", "Unknown verify-work stage 'bogus'"),
    ),
)
def test_staged_init_rejects_unknown_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str, stage: str, match: str
) -> None:
    _setup_project(tmp_path)
    if case in {"execute", "verify-work"}:
        _create_phase_dir(tmp_path, "01-setup")
    if case == "plan":
        _create_phase_dir(tmp_path, "02-analysis")
        install_fake_plan_phase_manifest(monkeypatch)

    actions = {
        "execute": lambda: init_execute_phase(tmp_path, "1", stage=stage),
        "plan": lambda: init_plan_phase(tmp_path, "2", stage=stage),
        "new-project": lambda: init_new_project(tmp_path, stage=stage),
        "write-paper": lambda: init_write_paper(tmp_path, stage=stage),
        "verify-work": lambda: init_verify_work(tmp_path, "1", stage=stage),
    }
    with pytest.raises(ValueError, match=match):
        actions[case]()


def _write_state_intent_recovery_files(project_root: Path) -> ProjectLayout:
    from gpd.core.state import default_state_dict

    layout = ProjectLayout(project_root)
    layout.state_json.parent.mkdir(parents=True, exist_ok=True)
    layout.state_json.write_text(json.dumps(default_state_dict(), indent=2) + "\n", encoding="utf-8")

    recovered_state = default_state_dict()
    recovered_state["position"]["current_phase"] = "05"
    recovered_state["position"]["status"] = "Executing"
    json_tmp = layout.gpd / ".state-json-tmp"
    md_tmp = layout.gpd / ".state-md-tmp"
    json_tmp.write_text(json.dumps(recovered_state, indent=2) + "\n", encoding="utf-8")
    md_tmp.write_text("# Recovered State\n", encoding="utf-8")
    layout.state_intent.write_text(f"{json_tmp}\n{md_tmp}\n", encoding="utf-8")
    return layout


def _create_roadmap(tmp_path: Path, content: str) -> Path:
    """Write ROADMAP.md and return its path."""
    roadmap = tmp_path / "GPD" / "ROADMAP.md"
    roadmap.parent.mkdir(parents=True, exist_ok=True)
    roadmap.write_text(content, encoding="utf-8")
    return roadmap


def _write_project_contract_state(tmp_path: Path) -> None:
    """Persist the Stage 0 project contract fixture into state.json."""
    from gpd.core.state import default_state_dict

    state = default_state_dict()
    state["project_contract"] = json.loads((FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"))
    (tmp_path / "GPD" / "state.json").write_text(json.dumps(state), encoding="utf-8")


def _write_coercive_project_contract_state(tmp_path: Path) -> None:
    """Persist a contract payload that should require schema normalization."""
    from gpd.core.state import default_state_dict

    state = default_state_dict()
    contract = json.loads((FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"))
    contract["references"][0]["must_surface"] = "yes"
    state["project_contract"] = contract
    (tmp_path / "GPD" / "state.json").write_text(json.dumps(state), encoding="utf-8")


def _write_recoverable_project_contract_state(tmp_path: Path) -> None:
    """Persist a contract payload that only needs recoverable normalization."""
    from gpd.core.state import default_state_dict

    state = default_state_dict()
    contract = json.loads((FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"))
    contract["claims"][0]["notes"] = "harmless"
    state["project_contract"] = contract
    (tmp_path / "GPD" / "state.json").write_text(json.dumps(state), encoding="utf-8")


def _write_structured_state_payload(tmp_path: Path) -> None:
    """Persist a representative structured state payload into state.json."""
    from gpd.core.state import default_state_dict

    state_path = tmp_path / "GPD" / "state.json"
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
    else:
        state = default_state_dict()

    state.setdefault("convention_lock", {}).update(
        {
            "metric_signature": "(-,+,+,+)",
            "fourier_convention": "physics",
            "natural_units": "SI",
        }
    )
    state["intermediate_results"] = [
        {
            "id": "R-01",
            "equation": "E = mc^2",
            "description": "Rest energy",
            "phase": "01",
            "depends_on": [],
            "verified": True,
            "verification_records": [{"verifier": "auditor", "method": "manual", "confidence": "high"}],
        },
        "stale markdown bullet",
    ]
    state["approximations"] = [
        {
            "name": "weak coupling",
            "validity_range": "g << 1",
            "controlling_param": "g",
            "current_value": "0.1",
            "status": "valid",
        }
    ]
    state["propagated_uncertainties"] = [
        {
            "quantity": "m_eff",
            "value": "1.2",
            "uncertainty": "0.1",
            "phase": "03",
            "method": "bootstrap",
        }
    ]
    state_path.write_text(json.dumps(state), encoding="utf-8")


def _assert_structured_state_context(ctx: dict[str, object], tmp_path: Path) -> None:
    """Assert the shared structured-state init payload contract."""
    assert ctx["state_load_source"] == "state.json"
    assert ctx["state_integrity_issues"] == []
    assert ctx["convention_lock"]["metric_signature"] == "(-,+,+,+)"
    assert ctx["convention_lock"]["fourier_convention"] == "physics"
    assert ctx["convention_lock"]["natural_units"] == "SI"
    assert ctx["intermediate_result_count"] == 1
    assert ctx["intermediate_results"][0]["id"] == "R-01"
    assert ctx["intermediate_results"][0]["verified"] is True
    assert ctx["approximation_count"] == 1
    assert ctx["approximations"][0]["name"] == "weak coupling"
    assert ctx["propagated_uncertainty_count"] == 1
    assert ctx["propagated_uncertainties"][0]["quantity"] == "m_eff"


def _write_stat_mech_project(tmp_path: Path) -> None:
    project = tmp_path / "GPD" / "PROJECT.md"
    project.write_text(
        """# Test Project

## What This Is

Monte Carlo study of a statistical mechanics lattice model near criticality.

## Research Context

### Theoretical Framework

Statistical mechanics

### Known Results

Binder cumulants, thermalization windows, and finite-size scaling should be benchmarked.
""",
        encoding="utf-8",
    )


def _assert_no_resume_compat_aliases(payload: dict[str, object]) -> None:
    for key in RESUME_BACKEND_ONLY_FIELDS:
        assert key not in payload


def _write_structured_state_memory(tmp_path: Path) -> None:
    """Persist conventions, canonical results, and approximations into state.json."""
    from gpd.core.state import default_state_dict

    state = default_state_dict()
    state["convention_lock"].update(
        {
            "metric_signature": "mostly-plus",
            "coordinate_system": "Cartesian",
        }
    )
    state["intermediate_results"] = [
        {
            "id": "R-01",
            "equation": "E = mc^2",
            "description": "Mass-energy relation",
            "phase": "1",
            "depends_on": [],
            "verified": True,
            "verification_records": [],
        }
    ]
    state["approximations"] = [
        {
            "name": "weak coupling",
            "validity_range": "g << 1",
            "controlling_param": "g",
            "current_value": "0.1",
            "status": "valid",
        }
    ]
    (tmp_path / "GPD" / "state.json").write_text(json.dumps(state), encoding="utf-8")


def _write_placeholder_heavy_structured_state_memory(tmp_path: Path) -> None:
    """Persist a convention lock with placeholder-heavy values into state.json."""
    from gpd.core.state import default_state_dict

    state = default_state_dict()
    state["convention_lock"].update(
        {
            "metric_signature": "mostly-plus",
            "fourier_convention": "not set",
            "natural_units": "[not set]",
            "gauge_choice": "\u2014",
            "coordinate_system": "Cartesian",
        }
    )
    (tmp_path / "GPD" / "state.json").write_text(json.dumps(state), encoding="utf-8")


def _write_current_execution(tmp_path: Path, payload: dict[str, object]) -> None:
    observability = tmp_path / "GPD" / "observability"
    observability.mkdir(parents=True, exist_ok=True)
    resume_file = payload.get("resume_file")
    if isinstance(resume_file, str) and resume_file:
        resume_path = Path(resume_file)
        if not resume_path.is_absolute():
            resume_path = tmp_path / resume_path
        resume_path.parent.mkdir(parents=True, exist_ok=True)
        resume_path.write_text("resume\n", encoding="utf-8")
    (observability / "current-execution.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_literature_review_anchor_file(tmp_path: Path) -> None:
    literature_dir = tmp_path / "GPD" / "literature"
    literature_dir.mkdir(parents=True, exist_ok=True)
    (literature_dir / "benchmark-REVIEW.md").write_text(
        """# Literature Review: Benchmark Survey

## Active Anchor Registry

| Anchor | Type | Why It Matters | Required Action | Downstream Use |
| ------ | ---- | -------------- | --------------- | -------------- |
| Benchmark Ref 2024 | benchmark | Published benchmark curve for the primary quantity | read/compare/cite | planning/execution |

## Open Questions

- Need exact normalization convention from the literature

```yaml
---
review_summary:
  topic: "Benchmark Survey"
  benchmark_values:
    - quantity: "critical slope"
      value: "1.23 +/- 0.04"
      source: "Benchmark Ref 2024"
  active_anchors:
    - anchor: "Benchmark Ref 2024"
      type: "benchmark"
      why_it_matters: "Published benchmark curve for the primary quantity"
      required_action: "read/compare/cite"
      downstream_use: "planning/execution"
---
```
""",
        encoding="utf-8",
    )


def _write_literature_citation_source_file(tmp_path: Path) -> None:
    literature_dir = tmp_path / "GPD" / "literature"
    literature_dir.mkdir(parents=True, exist_ok=True)
    (literature_dir / "benchmark-CITATION-SOURCES.json").write_text(
        json.dumps(
            [
                {
                    "reference_id": "ref-benchmark",
                    "source_type": "paper",
                    "title": "Benchmark Ref 2024",
                    "authors": ["A. Author", "B. Benchmarker"],
                    "year": "2024",
                    "bibtex_key": "benchmark2024",
                    "doi": "10.1000/benchmark.2024",
                    "arxiv_id": "2401.01234",
                    "url": "https://example.org/benchmark",
                    "journal": "J. Benchmarks",
                }
            ]
        ),
        encoding="utf-8",
    )


def _write_manuscript_bibliography_audit(tmp_path: Path) -> None:
    paper_dir = tmp_path / "paper"
    paper_dir.mkdir(exist_ok=True)
    (paper_dir / "BIBLIOGRAPHY-AUDIT.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-03-30T00:00:00+00:00",
                "total_sources": 1,
                "resolved_sources": 1,
                "partial_sources": 0,
                "unverified_sources": 0,
                "failed_sources": 0,
                "entries": [
                    {
                        "key": "benchmark2024",
                        "source_type": "paper",
                        "reference_id": "ref-benchmark",
                        "title": "Benchmark Paper",
                        "resolution_status": "provided",
                        "verification_status": "verified",
                        "verification_sources": ["manual"],
                        "canonical_identifiers": ["doi:10.1000/example"],
                        "missing_core_fields": [],
                        "enriched_fields": [],
                        "warnings": [],
                        "errors": [],
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_research_map_anchor_files(tmp_path: Path) -> None:
    map_dir = tmp_path / "GPD" / "research-map"
    map_dir.mkdir(parents=True, exist_ok=True)
    (map_dir / "REFERENCES.md").write_text(
        """# Reference and Anchor Map

## Active Anchor Registry

| Anchor | Type | Source / Locator | What It Constrains | Required Action | Carry Forward To |
| ------ | ---- | ---------------- | ------------------ | --------------- | ---------------- |
| prior-baseline | prior artifact | `GPD/phases/01-test-phase/01-SUMMARY.md` | Baseline summary for calibration and later comparisons | use | planning/execution |
| benchmark-paper | benchmark | Author et al., Journal, 2024 | Published comparison target for the decisive observable | read/compare/cite | verification/writing |

## Benchmarks and Comparison Targets

- Universal crossing window
  - Source: Author et al., Journal, 2024
  - Compared in: `GPD/phases/01-test-phase/01-SUMMARY.md`
  - Status: pending

## Prior Artifacts and Baselines

- `GPD/phases/01-test-phase/01-SUMMARY.md`: Prior baseline summary that later phases must keep visible

## Open Reference Questions

- Need collaboration note with the definitive normalization
""",
        encoding="utf-8",
    )

    (map_dir / "VALIDATION.md").write_text(
        """# Validation and Cross-Checks

## Comparison with Literature

- Result from Author et al., Journal, 2024: agreement still needs confirmation
  - Comparison in: `GPD/phases/01-test-phase/01-SUMMARY.md`
""",
        encoding="utf-8",
    )


def _setup_lifecycle_staged_payload_project(tmp_path: Path) -> Path:
    _setup_project(tmp_path)
    planning = tmp_path / "GPD"
    planning.joinpath("PROJECT.md").write_text("# Test Project\n", encoding="utf-8")
    planning.joinpath("ROADMAP.md").write_text(
        "# Roadmap\n\n## Phase 2: Analysis\n\n**Goal:** Compare the benchmark observable.\n",
        encoding="utf-8",
    )
    planning.joinpath("REQUIREMENTS.md").write_text("# Requirements\n- Preserve benchmark anchors.\n", encoding="utf-8")
    planning.joinpath("STATE.md").write_text("# State\nCurrent phase: 02\n", encoding="utf-8")

    phase_dir = _create_phase_dir(tmp_path, "02-analysis")
    (phase_dir / "02-PLAN.md").write_text("objective: compare benchmark observable\n", encoding="utf-8")
    (phase_dir / "02-SUMMARY.md").write_text("# Summary\nExisting result.\n", encoding="utf-8")
    (phase_dir / "02-CONTEXT.md").write_text("# Context\nLocked scope.\n", encoding="utf-8")
    (phase_dir / "02-RESEARCH.md").write_text("# Research\nMethod comparison.\n", encoding="utf-8")
    (phase_dir / "02-EXPERIMENT-DESIGN.md").write_text("# Experiment Design\nGrid scan.\n", encoding="utf-8")
    (phase_dir / "02-VERIFICATION.md").write_text("# Verification\nGap notes.\n", encoding="utf-8")
    (phase_dir / "02-VALIDATION.md").write_text("# Validation\nChecks.\n", encoding="utf-8")

    _write_project_contract_state(tmp_path)
    _write_structured_state_payload(tmp_path)
    _write_literature_review_anchor_file(tmp_path)
    _write_research_map_anchor_files(tmp_path)
    _write_current_execution(
        tmp_path,
        {
            "session_id": "sess-stage-parity",
            "phase": "02",
            "plan": "01",
            "segment_status": "waiting_review",
            "resume_file": "GPD/phases/02-analysis/.continue-here.md",
            "pre_fanout_review_pending": True,
        },
    )
    return phase_dir


class TestHelpers:
    def test_generate_slug(self) -> None:
        assert _generate_slug("Hello World!") == "hello-world"
        assert _generate_slug("") is None
        assert _generate_slug(None) is None
        assert _generate_slug("already-slug") == "already-slug"

    def test_normalize_phase_name(self) -> None:
        assert _normalize_phase_name("3") == "03"
        assert _normalize_phase_name("12") == "12"
        assert _normalize_phase_name("3.1") == "03.1"
        assert _normalize_phase_name("3.1.2") == "03.1.2"
        assert _normalize_phase_name("abc") == "abc"

    def test_is_phase_complete(self) -> None:
        assert _is_phase_complete(2, 2) is True
        assert _is_phase_complete(2, 3) is True
        assert _is_phase_complete(2, 1) is False
        assert _is_phase_complete(0, 0) is False


class TestLoadConfig:
    def test_defaults_when_no_config(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        config = load_config(tmp_path)
        assert config["autonomy"] == "supervised"
        assert config["review_cadence"] == "dense"
        assert config["research_mode"] == "balanced"
        assert config["commit_docs"] is True
        assert config["parallelization"] is True
        assert config["verifier"] is True
        assert config["checkpoint_after_first_load_bearing_result"] is True
        assert config["project_usd_budget"] is None
        assert config["session_usd_budget"] is None

    def test_custom_config(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_config(tmp_path, {"autonomy": "yolo", "review_cadence": "dense", "research_mode": "exploit"})
        config = load_config(tmp_path)
        assert config["autonomy"] == "yolo"
        assert config["review_cadence"] == "dense"
        assert config["research_mode"] == "exploit"

    def test_nested_config(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_config(
            tmp_path,
            {
                "workflow": {"research": False, "plan_checker": False},
                "execution": {"project_usd_budget": 12.5, "session_usd_budget": 2.5},
            },
        )
        config = load_config(tmp_path)
        assert config["research"] is False
        assert config["plan_checker"] is False
        assert config["project_usd_budget"] == 12.5
        assert config["session_usd_budget"] == 2.5

    def test_parallelization_bool(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_config(tmp_path, {"parallelization": False})
        config = load_config(tmp_path)
        assert config["parallelization"] is False

    def test_malformed_config_raises(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        config_path = tmp_path / "GPD" / "config.json"
        config_path.write_text("not valid json {{{", encoding="utf-8")
        with pytest.raises(ConfigError, match="Malformed config.json"):
            load_config(tmp_path)


class TestInitExecutePhase:
    def test_basic(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        phase_dir = _create_phase_dir(tmp_path, "01-setup")
        (phase_dir / "a-PLAN.md").write_text("plan", encoding="utf-8")
        (phase_dir / "a-SUMMARY.md").write_text("summary", encoding="utf-8")

        ctx = init_execute_phase(tmp_path, "1")
        assert ctx["phase_found"] is True
        assert ctx["phase_number"] == "01"
        assert ctx["plan_count"] == 1
        assert ctx["incomplete_count"] == 0
        assert ctx["state_exists"] is False
        assert ctx["review_cadence"] == "dense"
        assert ctx["checkpoint_after_first_load_bearing_result"] is True

    def test_resolves_ancestor_project_root_from_nested_workspace(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        phase_dir = _create_phase_dir(tmp_path, "01-setup")
        (phase_dir / "a-PLAN.md").write_text("plan", encoding="utf-8")
        nested = tmp_path / "workspace" / "notes"
        nested.mkdir(parents=True)

        ctx = init_execute_phase(nested, "1")

        assert ctx["phase_found"] is True
        assert ctx["phase_number"] == "01"
        assert ctx["plan_count"] == 1

    def test_missing_phase_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValidationError, match="phase is required"):
            init_execute_phase(tmp_path, "")

    def test_includes_state(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "01-setup")
        (tmp_path / "GPD" / "STATE.md").write_text("# State\nstuff", encoding="utf-8")

        ctx = init_execute_phase(tmp_path, "1", includes={"state"})
        assert ctx["state_content"] == "# State\nstuff"

    def test_includes_structured_state_context(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "01-setup")
        _write_structured_state_payload(tmp_path)

        ctx = init_execute_phase(tmp_path, "1", includes={"state"})

        _assert_structured_state_context(ctx, tmp_path)

    def test_json_only_state_counts_as_existing(self, tmp_path: Path) -> None:
        from gpd.core.state import default_state_dict

        _setup_project(tmp_path)
        phase_dir = _create_phase_dir(tmp_path, "01-setup")
        (phase_dir / "a-PLAN.md").write_text("plan", encoding="utf-8")
        (tmp_path / "GPD" / "state.json").write_text(json.dumps(default_state_dict()), encoding="utf-8")

        ctx = init_execute_phase(tmp_path, "1")

        assert ctx["state_exists"] is True

    def test_surfaces_derived_state_memory(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        phase_dir = _create_phase_dir(tmp_path, "01-setup")
        (phase_dir / "a-PLAN.md").write_text("plan", encoding="utf-8")
        _write_structured_state_memory(tmp_path)

        ctx = init_execute_phase(tmp_path, "1")

        assert ctx["derived_convention_lock"]["metric_signature"] == "mostly-plus"
        assert ctx["derived_convention_lock"]["coordinate_system"] == "Cartesian"
        assert ctx["derived_convention_lock_count"] == 2
        assert ctx["derived_intermediate_result_count"] == 1
        assert ctx["derived_intermediate_results"][0]["id"] == "R-01"
        assert ctx["derived_intermediate_results"][0]["equation"] == "E = mc^2"
        assert ctx["derived_approximation_count"] == 1
        assert ctx["derived_approximations"][0]["name"] == "weak coupling"

    def test_surfaces_material_convention_counts_with_placeholders(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        phase_dir = _create_phase_dir(tmp_path, "01-setup")
        (phase_dir / "a-PLAN.md").write_text("plan", encoding="utf-8")
        _write_placeholder_heavy_structured_state_memory(tmp_path)

        ctx = init_verify_work(tmp_path, "1")

        assert ctx["convention_lock"]["fourier_convention"] == "not set"
        assert ctx["convention_lock"]["natural_units"] == "[not set]"
        assert ctx["convention_lock"]["gauge_choice"] == "\u2014"
        assert ctx["convention_lock_count"] == 2
        assert ctx["derived_convention_lock_count"] == 2
        assert ctx["derived_convention_lock"] == {
            "metric_signature": "mostly-plus",
            "coordinate_system": "Cartesian",
        }

    def test_does_not_bootstrap_manuscript_proof_review_manifest(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        phase_dir = _create_phase_dir(tmp_path, "01-setup")
        (phase_dir / "a-PLAN.md").write_text("plan", encoding="utf-8")
        _write_manuscript_proof_review_artifacts(tmp_path)

        ctx = init_execute_phase(tmp_path, "1")

        status = ctx["derived_manuscript_proof_review_status"]
        assert status["state"] == "fresh"
        assert status["manifest_bootstrapped"] is False
        assert not (tmp_path / "paper" / "PROOF-REVIEW-MANIFEST.json").exists()

    def test_state_exists_ignores_backup_only_state_without_persisting_repair(
        self,
        tmp_path: Path,
    ) -> None:
        from gpd.core.state import default_state_dict

        _setup_project(tmp_path)
        (tmp_path / "GPD" / "state.json.bak").write_text(
            json.dumps(default_state_dict()),
            encoding="utf-8",
        )

        assert _state_exists(tmp_path) is False
        assert not (tmp_path / "GPD" / "state.json").exists()

    def test_surfaces_active_reference_context(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        phase_dir = _create_phase_dir(tmp_path, "01-setup")
        (phase_dir / "a-PLAN.md").write_text("plan", encoding="utf-8")
        _write_project_contract_state(tmp_path)

        ctx = init_execute_phase(tmp_path, "1")

        assert ctx["project_contract"]["references"][0]["id"] == "ref-benchmark"
        assert "Published comparison target" in ctx["active_reference_context"]

    def test_active_reference_context_collapses_non_durable_contract_warnings(self) -> None:
        rendered = _render_active_reference_context(
            active_references=[],
            effective_intake=stage_ctx.EMPTY_REFERENCE_INTAKE,
            literature_review_files=[],
            research_map_reference_files=[],
            stable_knowledge_doc_files=[],
            knowledge_doc_status_counts={},
            contract_validation={
                "valid": False,
                "errors": ["scope.question is required"],
                "warnings": [
                    "context_intake.user_asserted_anchors entry is not concrete enough to preserve as durable guidance: placeholder anchor",
                    "context_intake.context_gaps entry is only a placeholder and does not preserve actionable guidance: TBD",
                    "references.0.must_surface must be a boolean",
                ],
            },
            contract_load_info={
                "status": "loaded_with_schema_normalization",
                "errors": ["context_intake is required"],
                "warnings": [
                    "context_intake.must_include_prior_outputs entry does not resolve to a project-local artifact: missing/path.md",
                ],
            },
        )

        assert rendered.count("non-durable contract-intake warning") == 2
        assert (
            "context_intake.user_asserted_anchors entry is not concrete enough to preserve as durable guidance"
            not in rendered
        )
        assert (
            "context_intake.context_gaps entry is only a placeholder and does not preserve actionable guidance"
            not in rendered
        )
        assert (
            "context_intake.must_include_prior_outputs entry does not resolve to a project-local artifact"
            not in rendered
        )
        assert "references.0.must_surface must be a boolean" in rendered
        assert "context_intake is required" in rendered
        assert "scope.question is required" in rendered

    def test_ingests_reference_artifacts_without_project_contract(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        phase_dir = _create_phase_dir(tmp_path, "01-setup")
        (phase_dir / "a-PLAN.md").write_text("plan", encoding="utf-8")
        _write_literature_review_anchor_file(tmp_path)
        _write_research_map_anchor_files(tmp_path)

        ctx = init_execute_phase(tmp_path, "1")

        assert ctx["project_contract"] is None
        assert ctx["derived_active_reference_count"] >= 2
        assert ctx["active_reference_count"] >= 2
        assert "Benchmark Ref 2024" in ctx["active_reference_context"]
        assert "GPD/phases/01-test-phase/01-SUMMARY.md" in ctx["active_reference_context"]
        assert "GPD/research-map/REFERENCES.md" in ctx["active_reference_context"]
        assert "critical slope" in "\n".join(ctx["effective_reference_intake"]["known_good_baselines"])
        assert (
            "GPD/phases/01-test-phase/01-SUMMARY.md" in ctx["effective_reference_intake"]["must_include_prior_outputs"]
        )

    def test_surfaces_live_execution_context(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        phase_dir = _create_phase_dir(tmp_path, "01-setup")
        (phase_dir / "a-PLAN.md").write_text("plan", encoding="utf-8")
        _write_current_execution(
            tmp_path,
            {
                "session_id": "sess-1",
                "phase": "01",
                "plan": "01",
                "segment_status": "waiting_review",
                "first_result_gate_pending": True,
                "review_cadence": "adaptive",
            },
        )

        ctx = init_execute_phase(tmp_path, "1")

        assert ctx["has_live_execution"] is True
        assert ctx["execution_review_pending"] is True
        assert ctx["current_execution"]["segment_status"] == "waiting_review"

    def test_surfaces_pre_fanout_and_skeptical_execution_flags(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        phase_dir = _create_phase_dir(tmp_path, "01-setup")
        (phase_dir / "a-PLAN.md").write_text("plan", encoding="utf-8")
        _write_current_execution(
            tmp_path,
            {
                "session_id": "sess-1",
                "phase": "01",
                "plan": "01",
                "segment_status": "waiting_review",
                "checkpoint_reason": "pre_fanout",
                "pre_fanout_review_pending": True,
                "skeptical_requestioning_required": True,
                "downstream_locked": True,
            },
        )

        ctx = init_execute_phase(tmp_path, "1")

        assert ctx["execution_review_pending"] is True
        assert ctx["execution_pre_fanout_review_pending"] is True
        assert ctx["execution_skeptical_requestioning_required"] is True
        assert ctx["execution_downstream_locked"] is True

    def test_surfaces_selected_protocol_bundles(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        phase_dir = _create_phase_dir(tmp_path, "01-setup")
        (phase_dir / "a-PLAN.md").write_text("plan", encoding="utf-8")
        _write_stat_mech_project(tmp_path)
        _write_bundle_ready_contract_state(tmp_path)

        ctx = init_execute_phase(tmp_path, "1")

        assert "stat-mech-simulation" in ctx["selected_protocol_bundle_ids"]
        assert "monte-carlo.md" in ctx["protocol_bundle_context"]
        assert "selected_protocol_bundles" not in ctx
        assert "protocol_bundle_asset_paths" not in ctx
        manifest = ctx["protocol_bundle_load_manifest"]
        assert manifest["selected_bundle_ids"] == ctx["selected_protocol_bundle_ids"]
        assert manifest["bundle_count"] == ctx["protocol_bundle_count"]
        assert manifest["bundles"][0]["assets"]["planning_guides"][0]["path"] == (
            "references/planning/statistical-mechanics.md"
        )
        assert "asset_paths" not in manifest["bundles"][0]
        assert any(
            extension["bundle_id"] == "stat-mech-simulation" for extension in ctx["protocol_bundle_verifier_extensions"]
        )

    def test_surfaces_numerical_relativity_protocol_bundle(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        phase_dir = _create_phase_dir(tmp_path, "01-setup")
        (phase_dir / "a-PLAN.md").write_text("plan", encoding="utf-8")
        _write_numerical_relativity_project(tmp_path)
        _write_numerical_relativity_contract_state(tmp_path)

        ctx = init_execute_phase(tmp_path, "1")

        assert "numerical-relativity" in ctx["selected_protocol_bundle_ids"]
        assert "numerical-relativity.md" in ctx["protocol_bundle_context"]
        assert any(
            extension["bundle_id"] == "numerical-relativity" for extension in ctx["protocol_bundle_verifier_extensions"]
        )

    def test_protocol_bundle_verifier_extensions_match_mcp_bundle_checklist(self, tmp_path: Path) -> None:
        from gpd.mcp.servers.verification_server import get_bundle_checklist

        _setup_project(tmp_path)
        phase_dir = _create_phase_dir(tmp_path, "01-setup")
        (phase_dir / "a-PLAN.md").write_text("plan", encoding="utf-8")
        _write_stat_mech_project(tmp_path)
        _write_bundle_ready_contract_state(tmp_path)

        ctx = init_execute_phase(tmp_path, "1")
        checklist = get_bundle_checklist(ctx["selected_protocol_bundle_ids"])

        assert checklist["found"] is True
        assert checklist["bundle_checks"] == ctx["protocol_bundle_verifier_extensions"]


class TestInitExecutePhaseStagedWiring:
    def test_real_manifest_staged_payloads_match_required_fields(self, tmp_path: Path) -> None:
        _setup_lifecycle_staged_payload_project(tmp_path)
        manifest = load_workflow_stage_manifest("execute-phase")

        for stage_id in manifest.stage_ids():
            ctx = init_execute_phase(tmp_path, "2", stage=stage_id)
            stage = manifest.stage_by_id(stage_id)

            stage_ctx.assert_context_stage(ctx, manifest, "execute-phase", stage_id)
            if "reference_artifacts_content" in stage.required_init_fields:
                assert "Reference and Anchor Map" in ctx["reference_artifacts_content"]
            else:
                assert "reference_artifacts_content" not in ctx
            if "current_execution" in stage.required_init_fields:
                assert ctx["current_execution"]["session_id"] == "sess-stage-parity"
            else:
                assert "current_execution" not in ctx

    def test_stage_phase_bootstrap_returns_only_bootstrap_payload(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "01-setup")
        _write_project_contract_state(tmp_path)

        ctx = init_execute_phase(tmp_path, "1", stage="phase_bootstrap")

        assert ctx["phase_found"] is True
        assert ctx["staged_loading"]["stage_id"] == "phase_bootstrap"
        assert "reference_artifacts_content" not in ctx
        assert "protocol_bundle_context" not in ctx
        assert "current_execution" not in ctx

    def test_stage_phase_classification_skips_reference_artifact_payload(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "01-setup")
        _write_project_contract_state(tmp_path)
        calls: list[bool] = []

        def _record_artifact_payload(
            *_args: object, include_content: bool = True, **_kwargs: object
        ) -> dict[str, object]:
            calls.append(include_content)
            raise AssertionError("phase_classification should not scan reference artifacts")

        monkeypatch.setattr(context_module, "_reference_artifact_payload", _record_artifact_payload)

        ctx = init_execute_phase(tmp_path, "1", stage="phase_classification")

        assert ctx["staged_loading"]["stage_id"] == "phase_classification"
        assert "reference_artifacts_content" not in ctx
        assert calls == []


class TestInitPlanPhase:
    def test_real_manifest_staged_payloads_match_required_fields(self, tmp_path: Path) -> None:
        _setup_lifecycle_staged_payload_project(tmp_path)
        manifest = load_workflow_stage_manifest("plan-phase")

        for stage_id in manifest.stage_ids():
            ctx = init_plan_phase(tmp_path, "2", stage=stage_id)
            stage = manifest.stage_by_id(stage_id)

            stage_ctx.assert_context_stage(ctx, manifest, "plan-phase", stage_id)
            if "reference_artifacts_content" in stage.required_init_fields:
                assert "Reference and Anchor Map" in ctx["reference_artifacts_content"]
            else:
                assert "reference_artifacts_content" not in ctx
            if "experiment_design_content" in stage.required_init_fields:
                assert "Grid scan." in ctx["experiment_design_content"]
            else:
                assert "experiment_design_content" not in ctx
            if stage_id == "planner_authoring":
                assert "Current phase: 02" in ctx["state_content"]
                assert "Compare the benchmark observable" in ctx["roadmap_content"]
                assert "Preserve benchmark anchors" in ctx["requirements_content"]
                assert "Locked scope." in ctx["context_content"]
                assert "Method comparison." in ctx["research_content"]
                assert "verification_content" not in ctx
                assert "validation_content" not in ctx

    def test_basic(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        phase_dir = _create_phase_dir(tmp_path, "02-analysis")
        (phase_dir / "RESEARCH.md").write_text("research", encoding="utf-8")

        ctx = init_plan_phase(tmp_path, "2")
        assert ctx["phase_found"] is True
        assert ctx["phase_number"] == "02"
        assert ctx["has_research"] is True
        assert ctx["has_plans"] is False
        assert ctx["padded_phase"] == "02"
        assert "staged_loading" not in ctx

    def test_infers_next_unplanned_roadmap_phase_when_phase_is_omitted(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_roadmap(
            tmp_path,
            """\
            ## Milestone v1.0: Test

            ### Phase 1: Setup
            **Goal:** setup

            ### Phase 2: Analyze
            **Goal:** analyze
            """,
        )

        ctx = init_plan_phase(tmp_path, None)

        assert ctx["phase_found"] is False
        assert ctx["phase_number"] == "1"
        assert ctx["phase_name"] == "Setup"
        assert ctx["phase_slug"] == "setup"
        assert ctx["padded_phase"] == "01"

    def test_stage_phase_bootstrap_accepts_omitted_phase_when_roadmap_can_infer_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_project(tmp_path)
        _create_roadmap(
            tmp_path,
            """\
            ## Milestone v1.0: Test

            ### Phase 1: Setup
            **Goal:** setup
            """,
        )
        _write_project_contract_state(tmp_path)
        install_fake_plan_phase_manifest(monkeypatch)

        ctx = init_plan_phase(tmp_path, "", stage="phase_bootstrap")

        assert ctx["phase_found"] is False
        assert ctx["phase_number"] == "1"
        assert ctx["phase_name"] == "Setup"
        assert ctx["staged_loading"]["stage_id"] == "phase_bootstrap"

    def test_resolves_ancestor_project_root_from_nested_workspace(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        phase_dir = _create_phase_dir(tmp_path, "02-analysis")
        (tmp_path / "GPD" / "STATE.md").write_text("# State\nRoot state.\n", encoding="utf-8")
        (tmp_path / "GPD" / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
        (phase_dir / "RESEARCH.md").write_text("nested research", encoding="utf-8")
        nested = tmp_path / "workspace" / "notes"
        nested.mkdir(parents=True)

        ctx = init_plan_phase(nested, "2", includes={"state", "roadmap", "research"})

        assert ctx["phase_found"] is True
        assert ctx["phase_number"] == "02"
        assert ctx["planning_exists"] is True
        assert ctx["roadmap_exists"] is True
        assert ctx["state_content"] == "# State\nRoot state.\n"
        assert ctx["roadmap_content"] == "# Roadmap\n"
        assert ctx["research_content"] == "nested research"
        assert not (nested / "GPD").exists()

    def test_stage_phase_bootstrap_returns_only_bootstrap_payload(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "02-analysis")
        _write_project_contract_state(tmp_path)
        install_fake_plan_phase_manifest(monkeypatch)

        ctx = init_plan_phase(tmp_path, "2", stage="phase_bootstrap")

        assert ctx["phase_found"] is True
        assert ctx["project_contract_gate"]["visible"] is True
        assert ctx["staged_loading"]["stage_id"] == "phase_bootstrap"
        assert "contract_intake" not in ctx
        assert "active_reference_context" not in ctx
        assert "reference_artifacts_content" not in ctx
        assert "state_content" not in ctx

    @pytest.mark.parametrize("stage_id", ("planner_authoring", "checker_revision"))
    def test_reference_authoring_stages_surface_file_context(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage_id: str
    ) -> None:
        _setup_project(tmp_path)
        phase_dir = _create_phase_dir(tmp_path, "02-analysis")
        _write_project_contract_state(tmp_path)
        _write_literature_review_anchor_file(tmp_path)
        _write_research_map_anchor_files(tmp_path)
        (phase_dir / "02-CONTEXT.md").write_text("# Context\nLocked scope.\n", encoding="utf-8")
        (phase_dir / "02-RESEARCH.md").write_text("# Research\nMethod comparison.\n", encoding="utf-8")
        (phase_dir / "02-VERIFICATION.md").write_text("# Verification\nGap notes.\n", encoding="utf-8")
        (phase_dir / "02-VALIDATION.md").write_text("# Validation\nChecks.\n", encoding="utf-8")
        manifest = install_fake_plan_phase_manifest(monkeypatch)

        ctx = init_plan_phase(tmp_path, "2", stage=stage_id)
        stage = manifest.stage_by_id(stage_id)

        assert ctx["staged_loading"]["stage_id"] == stage_id
        assert set(ctx) == set(stage.required_init_fields) | {"staged_loading"}
        assert "[ref-benchmark]" in ctx["active_reference_context"]
        assert "Reference and Anchor Map" in ctx["reference_artifacts_content"]
        assert "Universal crossing window" in ctx["reference_artifacts_content"]
        assert "Locked scope." in ctx["context_content"]
        assert "Method comparison." in ctx["research_content"]
        assert "Gap notes." in ctx["verification_content"]
        assert "Checks." in ctx["validation_content"]
        if stage_id == "planner_authoring":
            assert ctx["contract_intake"]["must_read_refs"] == ["ref-benchmark"]
        else:
            assert ctx["project_contract_gate"]["visible"] is True
            assert "Method comparison." not in ctx.get("state_content", "")
            assert "experiment_design_content" not in ctx
            assert "planner_model" not in ctx

    def test_plan_phase_stage_rejects_include_mix(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "02-analysis")
        install_fake_plan_phase_manifest(monkeypatch)

        with pytest.raises(ValueError, match="does not allow --include together with --stage"):
            init_plan_phase(tmp_path, "2", includes={"state"}, stage="phase_bootstrap")

    def test_includes_research(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        phase_dir = _create_phase_dir(tmp_path, "02-analysis")
        (phase_dir / "RESEARCH.md").write_text("findings here", encoding="utf-8")

        ctx = init_plan_phase(tmp_path, "2", includes={"research"})
        assert ctx["research_content"] == "findings here"

    def test_includes_structured_state_context_when_state_is_requested(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "02-analysis")
        _write_structured_state_payload(tmp_path)

        ctx = init_plan_phase(tmp_path, "2", includes={"state"})

        _assert_structured_state_context(ctx, tmp_path)

    def test_surfaces_active_reference_context_and_reference_artifacts(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "02-analysis")
        _write_project_contract_state(tmp_path)
        literature_dir = tmp_path / "GPD" / "literature"
        literature_dir.mkdir()
        (literature_dir / "benchmark-REVIEW.md").write_text("# Literature Review\nbenchmark details", encoding="utf-8")
        map_dir = tmp_path / "GPD" / "research-map"
        map_dir.mkdir()
        (map_dir / "REFERENCES.md").write_text("# References Map\nanchor registry", encoding="utf-8")
        (map_dir / "VALIDATION.md").write_text("# Validation Map\nbenchmark checks", encoding="utf-8")

        ctx = init_plan_phase(tmp_path, "2")

        assert ctx["project_contract"]["references"][0]["id"] == "ref-benchmark"
        assert ctx["contract_intake"]["must_read_refs"] == ["ref-benchmark"]
        assert ctx["active_reference_count"] == 1
        assert "[ref-benchmark]" in ctx["active_reference_context"]
        assert "GPD/literature/benchmark-REVIEW.md" in ctx["literature_review_files"]
        assert "GPD/research-map/REFERENCES.md" in ctx["research_map_reference_files"]
        assert "GPD/research-map/VALIDATION.md" in ctx["reference_artifact_files"]
        assert "benchmark details" in ctx["reference_artifacts_content"]
        assert "anchor registry" in ctx["reference_artifacts_content"]

    def test_surfaces_stable_knowledge_docs_in_runtime_reference_payload(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "02-analysis")
        _write_project_contract_state(tmp_path)
        _write_knowledge_doc(tmp_path, status="stable")
        _write_knowledge_doc(
            tmp_path,
            knowledge_id="K-work-in-progress",
            status="in_review",
            body="Draft knowledge body.\n",
        )

        ctx = init_plan_phase(tmp_path, "2")

        assert "GPD/knowledge/K-renormalization-group-fixed-points.md" in ctx["knowledge_doc_files"]
        assert ctx["knowledge_doc_count"] == 2
        assert ctx["stable_knowledge_doc_files"] == ["GPD/knowledge/K-renormalization-group-fixed-points.md"]
        assert ctx["stable_knowledge_doc_count"] == 1
        assert ctx["knowledge_doc_status_counts"]["stable"] == 1
        assert ctx["knowledge_doc_status_counts"]["in_review"] == 1
        assert ctx["derived_knowledge_doc_count"] == 1
        assert ctx["derived_knowledge_docs"][0]["knowledge_id"] == "K-renormalization-group-fixed-points"
        assert ctx["knowledge_doc_warnings"] == []
        assert "GPD/knowledge/K-renormalization-group-fixed-points.md" in ctx["reference_artifact_files"]
        assert "Trusted knowledge body." in ctx["reference_artifacts_content"]
        assert "Draft knowledge body." not in ctx["reference_artifacts_content"]
        assert "K-work-in-progress" not in ctx["active_reference_context"]
        assert "non-stable knowledge doc(s) remain inventory-visible only" in ctx["active_reference_context"]

    def test_prefers_literature_review_files_over_stale_research_when_both_exist(
        self,
        tmp_path: Path,
    ) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "02-analysis")
        _write_project_contract_state(tmp_path)

        literature_dir = tmp_path / "GPD" / "literature"
        literature_dir.mkdir()
        (literature_dir / "canonical-REVIEW.md").write_text(
            "# Literature Review\n\nCanonical details.\n",
            encoding="utf-8",
        )
        (literature_dir / "canonical-CITATION-SOURCES.json").write_text(
            json.dumps(
                [
                    {
                        "reference_id": "ref-canonical",
                        "source_type": "paper",
                        "title": "Canonical Reference",
                        "authors": ["A. Author"],
                        "year": "2026",
                    }
                ]
            ),
            encoding="utf-8",
        )

        research_dir = tmp_path / "GPD" / "research"
        research_dir.mkdir()
        (research_dir / "stale-REVIEW.md").write_text(
            "# Stale Review\n\nStale details.\n",
            encoding="utf-8",
        )
        (research_dir / "stale-CITATION-SOURCES.json").write_text(
            json.dumps(
                [
                    {
                        "reference_id": "ref-stale",
                        "source_type": "paper",
                        "title": "Stale Reference",
                        "authors": ["A. Author"],
                        "year": "2024",
                    }
                ]
            ),
            encoding="utf-8",
        )

        ctx = init_plan_phase(tmp_path, "2")

        assert ctx["literature_review_files"] == ["GPD/literature/canonical-REVIEW.md"]
        assert ctx["citation_source_files"] == ["GPD/literature/canonical-CITATION-SOURCES.json"]
        assert "Canonical details." in ctx["reference_artifacts_content"]
        assert "Stale details." not in ctx["reference_artifacts_content"]
        assert "GPD/research/stale-REVIEW.md" not in ctx["reference_artifact_files"]

    def test_does_not_bootstrap_manuscript_proof_review_manifest(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "02-analysis")
        _write_manuscript_proof_review_artifacts(tmp_path)

        ctx = init_plan_phase(tmp_path, "2")

        status = ctx["derived_manuscript_proof_review_status"]
        assert status["state"] == "fresh"
        assert status["manifest_bootstrapped"] is False
        assert not (tmp_path / "paper" / "PROOF-REVIEW-MANIFEST.json").exists()

    def test_surfaces_derived_citation_sources_without_changing_reference_artifact_fields(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "02-analysis")
        _write_project_contract_state(tmp_path)
        _write_literature_review_anchor_file(tmp_path)
        _write_literature_citation_source_file(tmp_path)
        _write_research_map_anchor_files(tmp_path)

        ctx = init_plan_phase(tmp_path, "2")

        assert "GPD/literature/benchmark-CITATION-SOURCES.json" in ctx["citation_source_files"]
        assert ctx["citation_source_count"] == 1
        assert ctx["citation_source_warnings"] == []
        assert ctx["derived_citation_source_count"] == 1
        assert ctx["derived_citation_sources"][0]["reference_id"] == "ref-benchmark"
        assert ctx["derived_citation_sources"][0]["title"] == "Benchmark Ref 2024"
        assert ctx["derived_citation_sources"][0]["bibtex_key"] == "benchmark2024"
        assert ctx["derived_citation_sources"][0]["doi"] == "10.1000/benchmark.2024"
        assert ctx["derived_citation_sources"][0]["arxiv_id"] == "2401.01234"
        assert "GPD/literature/benchmark-CITATION-SOURCES.json" not in ctx["reference_artifact_files"]
        assert "Benchmark Survey" in ctx["reference_artifacts_content"]
        assert "Active Anchor Registry" in ctx["reference_artifacts_content"]

    def test_surfaces_derived_manuscript_reference_status_from_bibliography_audit(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "02-analysis")
        _write_manuscript_bibliography_audit(tmp_path)

        ctx = init_plan_phase(tmp_path, "2")

        assert ctx["derived_manuscript_reference_status_count"] == 1
        assert ctx["derived_manuscript_reference_status"]["ref-benchmark"]["bibtex_key"] == "benchmark2024"
        assert ctx["derived_manuscript_reference_status"]["ref-benchmark"]["title"] == "Benchmark Paper"
        assert ctx["derived_manuscript_reference_status"]["ref-benchmark"]["resolution_status"] == "provided"
        assert ctx["derived_manuscript_reference_status"]["ref-benchmark"]["verification_status"] == "verified"
        assert ctx["derived_manuscript_reference_status"]["ref-benchmark"]["manuscript_root"] == "paper"
        assert (
            ctx["derived_manuscript_reference_status"]["ref-benchmark"]["bibliography_audit_path"]
            == "paper/BIBLIOGRAPHY-AUDIT.json"
        )
        assert ctx["derived_manuscript_reference_status"]["ref-benchmark"]["source_artifacts"] == [
            "paper/BIBLIOGRAPHY-AUDIT.json"
        ]

    def test_surfaces_derived_state_memory_without_including_state_markdown(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "02-analysis")
        _write_structured_state_memory(tmp_path)

        ctx = init_plan_phase(tmp_path, "2")

        assert "state_content" not in ctx
        assert ctx["derived_convention_lock"]["metric_signature"] == "mostly-plus"
        assert ctx["derived_intermediate_result_count"] == 1
        assert ctx["derived_intermediate_results"][0]["description"] == "Mass-energy relation"
        assert ctx["derived_approximation_count"] == 1
        assert ctx["derived_approximations"][0]["controlling_param"] == "g"

    def test_merges_contract_and_artifact_reference_intake(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "02-analysis")
        _write_project_contract_state(tmp_path)
        _write_literature_review_anchor_file(tmp_path)
        _write_research_map_anchor_files(tmp_path)

        ctx = init_plan_phase(tmp_path, "2")

        assert ctx["contract_intake"]["must_read_refs"] == ["ref-benchmark"]
        assert ctx["project_contract"]["context_intake"]["must_read_refs"] == ["ref-benchmark"]
        assert "ref-benchmark" in ctx["effective_reference_intake"]["must_read_refs"]
        assert "lit-anchor-benchmark-ref-2024" in ctx["effective_reference_intake"]["must_read_refs"]
        assert "benchmark-paper" not in ctx["effective_reference_intake"]["must_read_refs"]
        assert (
            "GPD/phases/01-test-phase/01-SUMMARY.md" in ctx["effective_reference_intake"]["must_include_prior_outputs"]
        )
        assert ctx["active_reference_count"] >= ctx["derived_active_reference_count"]
        assert "GPD/research-map/REFERENCES.md" in ctx["active_reference_context"]
        assert "unresolved reference token" not in ctx["active_reference_context"]

    def test_contract_intake_comes_from_canonicalized_project_contract(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "02-analysis")
        _write_project_contract_state(tmp_path)
        _write_literature_review_anchor_file(tmp_path)
        _write_research_map_anchor_files(tmp_path)

        state_path = tmp_path / "GPD" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["project_contract"]["context_intake"]["must_read_refs"] = ["benchmark-paper"]
        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

        ctx = init_progress(tmp_path)

        assert ctx["project_contract"]["context_intake"]["must_read_refs"] == ["benchmark-paper"]
        assert ctx["contract_intake"]["must_read_refs"] == ["ref-benchmark"]
        assert ctx["project_contract_load_info"]["status"] == "loaded_with_approval_blockers"
        assert ctx["project_contract_validation"]["valid"] is False
        assert ctx["project_contract_gate"]["visible"] is True
        assert ctx["project_contract_gate"]["authoritative"] is False
        assert ctx["project_contract_gate"]["blocked"] is True
        assert ctx["project_contract_gate"]["repair_required"] is True

    def test_non_authoritative_project_contract_does_not_select_protocol_bundles(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup_project(tmp_path)

        from gpd.contracts import ResearchContract

        contract_payload = json.loads((FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"))
        contract_payload["scope"]["question"] = "numerical relativity benchmark study"
        contract_payload["scope"]["in_scope"] = ["numerical relativity", "benchmark alignment"]
        contract = ResearchContract.model_validate(contract_payload)

        # Mock at the state-module loader (the actual underlying call site).
        # The earlier wrapper-level mock on gpd.core.context._load_project_contract
        # was unreliable across platforms — Linux CI resolved the bare-name call
        # in _build_reference_runtime_context to the original wrapper body
        # despite a successful monkeypatch.setattr. Patching the underlying
        # loader is robust because every entry point bottoms out there.
        load_info = {
            "status": "loaded",
            "source_path": "GPD/state.json",
            "provenance": "fallback",
            "raw_project_contract_classified": False,
            "errors": [],
            "warnings": [],
        }
        monkeypatch.setattr(
            "gpd.core.state._load_project_contract_for_runtime_context",
            lambda cwd: (contract, dict(load_info)),
        )

        ctx = init_progress(tmp_path)

        project_contract = ctx.get("project_contract")
        if isinstance(project_contract, dict):
            assert project_contract["scope"]["question"] == contract.scope.question
        assert ctx["project_contract_gate"]["authoritative"] is False
        assert ctx["project_contract_gate"]["repair_required"] is True
        assert ctx["project_contract_gate"]["visible"] is True
        assert ctx["contract_intake"]["must_read_refs"] == ["ref-benchmark"]
        assert ctx["selected_protocol_bundle_ids"] == []
        assert ctx["protocol_bundle_load_manifest"]["selected_bundle_ids"] == []
        assert ctx["protocol_bundle_load_manifest"]["bundle_count"] == 0
        assert ctx["active_reference_count"] == 0
        assert ctx["effective_reference_intake"] == stage_ctx.EMPTY_REFERENCE_INTAKE
        assert "ref-benchmark" not in ctx["active_reference_context"]
        assert "Author et al., Journal, 2024" not in ctx["active_reference_context"]

    def test_ambiguous_reference_tokens_remain_unresolved(self) -> None:
        active_references = [
            {
                "id": "ref-a",
                "locator": "doc-a",
                "aliases": ["shared-token"],
            },
            {
                "id": "ref-b",
                "locator": "shared-token",
                "aliases": [],
            },
        ]

        intake = _merge_reference_intake(
            None,
            {"must_read_refs": ["shared-token", "doc-a"]},
            active_references,
        )

        assert intake["must_read_refs"] == ["shared-token", "ref-a"]

    def test_merge_active_references_keeps_must_surface_strictly_boolean(self) -> None:
        contract_references = [
            {
                "id": "ref-benchmark",
                "locator": "Benchmark Ref 2024",
                "role": "benchmark",
                "why_it_matters": "Published comparison target",
                "required_actions": ["read", "compare", "cite"],
                "applies_to": ["claim-benchmark"],
                "carry_forward_to": [],
                "source_artifacts": [],
                "aliases": [],
                "must_surface": "optional",
            }
        ]
        derived_references = [
            {
                "id": "ref-benchmark",
                "locator": "Benchmark Ref 2024",
                "role": "benchmark",
                "why_it_matters": "Derived metadata",
                "required_actions": ["read"],
                "applies_to": ["claim-benchmark"],
                "carry_forward_to": ["writing"],
                "source_artifacts": ["GPD/research-map/REFERENCES.md"],
                "aliases": ["benchmark-paper"],
                "must_surface": "no",
            }
        ]

        merged = _merge_active_references(contract_references, derived_references)
        ref = next(item for item in merged if item["id"] == "ref-benchmark")

        assert ref["must_surface"] is False
        assert isinstance(ref["must_surface"], bool)
        assert ref["required_actions"] == ["read", "compare", "cite"]
        assert ref["carry_forward_to"] == ["writing"]
        assert ref["aliases"] == ["benchmark-paper"]

    def test_merge_active_references_does_not_collapse_shared_aliases(self) -> None:
        contract_references = [
            {
                "id": "ref-a",
                "locator": "Doc A",
                "role": "benchmark",
                "why_it_matters": "First anchor",
                "required_actions": ["read"],
                "applies_to": ["claim-a"],
                "carry_forward_to": [],
                "source_artifacts": [],
                "aliases": ["shared-token"],
                "must_surface": True,
            }
        ]
        derived_references = [
            {
                "id": "ref-b",
                "locator": "Doc B",
                "role": "benchmark",
                "why_it_matters": "Second anchor",
                "required_actions": ["compare"],
                "applies_to": ["claim-b"],
                "carry_forward_to": [],
                "source_artifacts": ["GPD/research-map/REFERENCES.md"],
                "aliases": ["shared-token"],
                "must_surface": True,
            }
        ]

        merged = _merge_active_references(contract_references, derived_references)

        assert [ref["id"] for ref in merged] == ["ref-a", "ref-b"]
        assert merged[0]["aliases"] == ["shared-token"]
        assert merged[1]["aliases"] == ["shared-token"]

    def test_merge_active_references_upgrades_generic_kind_from_derived_reference(self) -> None:
        contract_references = [
            {
                "id": "ref-benchmark",
                "locator": "Benchmark Ref 2024",
                "kind": "other",
                "role": "other",
                "why_it_matters": "Published comparison target",
                "required_actions": [],
                "applies_to": [],
                "carry_forward_to": [],
                "source_artifacts": [],
                "aliases": [],
                "must_surface": False,
            }
        ]
        derived_references = [
            {
                "id": "ref-benchmark",
                "locator": "Benchmark Ref 2024",
                "kind": "paper",
                "role": "benchmark",
                "why_it_matters": "Derived metadata",
                "required_actions": ["read"],
                "applies_to": ["claim-benchmark"],
                "carry_forward_to": ["writing"],
                "source_artifacts": ["GPD/research-map/REFERENCES.md"],
                "aliases": ["benchmark-paper"],
                "must_surface": True,
            }
        ]

        merged = _merge_active_references(contract_references, derived_references)
        ref = next(item for item in merged if item["id"] == "ref-benchmark")

        assert ref["kind"] == "paper"
        assert ref["role"] == "benchmark"
        assert contract_references[0]["kind"] == "other"
        assert derived_references[0]["kind"] == "paper"

    def test_keeps_project_contract_references_raw_and_surfaces_derived_reference_fields(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "02-analysis")
        _write_project_contract_state(tmp_path)
        _write_literature_review_anchor_file(tmp_path)
        _write_research_map_anchor_files(tmp_path)

        ctx = init_plan_phase(tmp_path, "2")
        project_references = {ref["id"]: ref for ref in ctx["project_contract"]["references"]}
        active_references = {ref["id"]: ref for ref in ctx["active_references"]}

        assert project_references["ref-benchmark"].get("aliases", []) == []
        assert project_references["ref-benchmark"].get("applies_to", []) == ["claim-benchmark"]
        assert project_references["ref-benchmark"].get("carry_forward_to", []) == []
        assert project_references["ref-benchmark"]["required_actions"] == ["read", "compare", "cite"]
        assert project_references["ref-benchmark"]["must_surface"] is True
        assert "prior-baseline" not in project_references
        assert ctx["project_contract_validation"]["valid"] is True
        assert ctx["project_contract_gate"]["authoritative"] is True
        assert ctx["project_contract_load_info"]["warnings"] == []

        assert active_references["ref-benchmark"]["aliases"] == ["benchmark-paper"]
        assert active_references["ref-benchmark"]["applies_to"] == ["claim-benchmark"]
        assert active_references["ref-benchmark"]["carry_forward_to"] == ["verification", "writing"]
        assert active_references["ref-benchmark"]["required_actions"] == ["read", "compare", "cite"]
        assert active_references["prior-baseline"]["kind"] == "prior_artifact"
        assert active_references["prior-baseline"]["required_actions"] == ["use"]
        assert active_references["prior-baseline"]["carry_forward_to"] == ["planning", "execution"]

    def test_does_not_persist_canonical_reference_merges(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "02-analysis")
        _write_project_contract_state(tmp_path)
        _write_literature_review_anchor_file(tmp_path)
        _write_research_map_anchor_files(tmp_path)

        state_path = tmp_path / "GPD" / "state.json"
        before = state_path.read_text(encoding="utf-8")

        ctx = init_plan_phase(tmp_path, "2")

        after = state_path.read_text(encoding="utf-8")
        stored = json.loads(after)

        assert ctx["contract_intake"]["must_read_refs"] == ["ref-benchmark"]
        assert ctx["project_contract"]["context_intake"]["must_read_refs"] == ["ref-benchmark"]
        assert "ref-benchmark" in ctx["effective_reference_intake"]["must_read_refs"]
        assert "lit-anchor-benchmark-ref-2024" in ctx["effective_reference_intake"]["must_read_refs"]
        assert stored["project_contract"]["context_intake"]["must_read_refs"] == ["ref-benchmark"]
        assert before == after
        assert not (tmp_path / "GPD" / "STATE.md").exists()

    def test_reports_missing_active_references_explicitly(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "02-analysis")

        ctx = init_plan_phase(tmp_path, "2")

        assert ctx["project_contract"] is None
        assert ctx["active_reference_count"] == 0
        assert "None confirmed in `state.json.project_contract.references` yet." in ctx["active_reference_context"]

    def test_surfaces_protocol_bundle_context(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "02-analysis")
        _write_stat_mech_project(tmp_path)
        _write_bundle_ready_contract_state(tmp_path)

        ctx = init_plan_phase(tmp_path, "2")

        assert "stat-mech-simulation" in ctx["selected_protocol_bundle_ids"]
        assert ctx["protocol_bundle_count"] >= 1
        assert "Decisive artifacts:" in ctx["protocol_bundle_context"]


class TestInitNewProject:
    def test_empty_project(self, tmp_path: Path) -> None:
        ctx = init_new_project(tmp_path)
        assert ctx["has_research_files"] is False
        assert ctx["research_file_samples"] == []
        assert ctx["has_project_manifest"] is False
        assert "has_existing_project" not in ctx
        assert ctx["planning_exists"] is False
        assert "staged_loading" not in ctx

    def test_detects_manifest(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]", encoding="utf-8")
        ctx = init_new_project(tmp_path)
        assert ctx["has_project_manifest"] is True

    def test_detects_topic_stem_manuscript_entrypoint_without_main_tex(self, tmp_path: Path) -> None:
        stage_ctx.write_project_paper_manuscript(tmp_path, stem="curvature_flow_bounds", body="Hi")

        ctx = init_new_project(tmp_path)

        assert ctx["has_project_manifest"] is True
        assert "has_existing_project" not in ctx

    def test_surfaces_project_contract_state_and_validation(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _write_project_contract_state(tmp_path)

        ctx = init_new_project(tmp_path)

        assert ctx["project_contract"] is not None
        assert ctx["project_contract"]["scope"]["question"] == "What benchmark must the project recover?"
        assert ctx["project_contract_load_info"]["status"] == "loaded"
        assert ctx["project_contract_load_info"]["source_path"].endswith("state.json")
        assert ctx["project_contract_validation"] is not None
        assert ctx["project_contract_validation"]["valid"] is True
        assert ctx["project_contract_gate"]["authoritative"] is True

    def test_new_project_surfaces_partial_recoverable_state_without_project_md(self, tmp_path: Path) -> None:
        from gpd.core.state import default_state_dict

        planning = tmp_path / "GPD"
        planning.mkdir()
        (planning / "state.json").write_text(json.dumps(default_state_dict()), encoding="utf-8")
        (planning / "ROADMAP.md").write_text("# Roadmap\n\n## Phase 1: Setup\n", encoding="utf-8")

        ctx = init_new_project(tmp_path, stage="scope_intake")

        assert ctx["project_exists"] is False
        assert ctx["state_exists"] is True
        assert ctx["roadmap_exists"] is True
        assert ctx["recoverable_project_exists"] is True
        assert ctx["partial_project_exists"] is True
        assert ctx["project_recovery_status"] == "partial"

    def test_new_project_stage_scope_intake_filters_payload(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _write_project_contract_state(tmp_path)

        manifest = load_workflow_stage_manifest("new-project")

        ctx = init_new_project(tmp_path, stage="scope_intake")

        stage_ctx.assert_context_stage(ctx, manifest, "new-project", "scope_intake")
        assert ctx["research_file_samples"] == []
        assert "researcher_model" not in ctx
        assert "synthesizer_model" not in ctx
        assert "roadmapper_model" not in ctx
        assert "references/research/questioning.md" in ctx["staged_loading"]["must_not_eager_load"]
        assert "templates/project-contract-schema.md" in ctx["staged_loading"]["must_not_eager_load"]
        assert ctx["staged_loading"]["checkpoints"] == [
            "detect existing workspace state",
            "surface the first scoping question",
            "preserve contract gate visibility without assuming approval-stage authority",
        ]

    def test_new_project_stage_scope_approval_filters_payload(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _write_project_contract_state(tmp_path)

        manifest = load_workflow_stage_manifest("new-project")

        ctx = init_new_project(tmp_path, stage="scope_approval")

        stage_ctx.assert_context_stage(ctx, manifest, "new-project", "scope_approval")
        assert "templates/project.md" in ctx["staged_loading"]["must_not_eager_load"]
        assert "templates/requirements.md" in ctx["staged_loading"]["must_not_eager_load"]
        assert ctx["staged_loading"]["checkpoints"] == [
            "approval gate has passed",
            "project contract is ready for persistence",
        ]

    @pytest.mark.parametrize(
        "stage_id",
        (
            "minimal_artifacts",
            "workflow_preferences",
            "project_artifacts",
            "literature_survey",
            "requirements_authoring",
            "roadmap_authoring",
            "conventions_handoff",
            "completion",
        ),
    )
    def test_new_project_post_approval_stages_filter_payload(self, tmp_path: Path, stage_id: str) -> None:
        _setup_project(tmp_path)
        _write_project_contract_state(tmp_path)

        manifest = load_workflow_stage_manifest("new-project")

        ctx = init_new_project(tmp_path, stage=stage_id)

        stage_ctx.assert_context_stage(ctx, manifest, "new-project", stage_id)
        assert "workflows/new-project.md" in ctx["staged_loading"]["must_not_eager_load"]
        assert "reference_artifacts_content" not in ctx
        assert "active_reference_context" not in ctx
        assert "effective_reference_intake" not in ctx
        assert "reference_artifact_files" not in ctx
        assert "post_scope" not in ctx["staged_loading"]["next_stages"]
        if stage_id != "literature_survey":
            assert "GPD/literature/SUMMARY.md" not in ctx["staged_loading"]["writes_allowed"]
        if stage_id not in {"roadmap_authoring", "conventions_handoff", "completion"}:
            assert "workflows/new-project/conventions-handoff.md" in ctx["staged_loading"]["must_not_eager_load"]

    def test_new_project_bootstrap_omits_reference_ledger_payload(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _write_project_contract_state(tmp_path)
        _write_literature_review_anchor_file(tmp_path)
        _write_research_map_anchor_files(tmp_path)

        ctx = init_new_project(tmp_path)

        for key in (
            "contract_intake",
            "effective_reference_intake",
            "active_references",
            "active_reference_context",
            "reference_artifact_files",
            "reference_artifacts_content",
            "selected_protocol_bundle_ids",
            "protocol_bundle_load_manifest",
            "protocol_bundle_context",
        ):
            assert key not in ctx

    def test_new_project_bootstrap_skips_reference_artifact_ingestion(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup_project(tmp_path)
        _write_project_contract_state(tmp_path)
        _write_literature_review_anchor_file(tmp_path)
        _write_research_map_anchor_files(tmp_path)

        def _boom(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("reference artifact ingestion should not run during new-project bootstrap")

        monkeypatch.setattr(context_module, "ingest_reference_artifacts", _boom)

        ctx = init_new_project(tmp_path)

        assert ctx["project_contract_gate"]["visible"] is True
        assert ctx["project_contract_validation"]["valid"] is True

    def test_stage_scope_intake_returns_only_manifest_required_fields(self, tmp_path: Path) -> None:
        (tmp_path / "calc.py").write_text("import numpy\n", encoding="utf-8")
        manifest = load_workflow_stage_manifest("new-project")

        ctx = init_new_project(tmp_path, stage="scope_intake")

        stage_ctx.assert_context_stage(ctx, manifest, "new-project", "scope_intake")
        assert ctx["research_file_samples"] == ["calc.py"]
        assert "researcher_model" not in ctx
        assert "synthesizer_model" not in ctx
        assert "roadmapper_model" not in ctx
        assert "references/research/questioning.md" in ctx["staged_loading"]["must_not_eager_load"]
        assert ctx["staged_loading"]["checkpoints"] == [
            "detect existing workspace state",
            "surface the first scoping question",
            "preserve contract gate visibility without assuming approval-stage authority",
        ]
        assert ctx["staged_loading"]["writes_allowed"] == []

    def test_stage_scope_intake_existing_research_is_read_only_before_mapping_gate(self, tmp_path: Path) -> None:
        (tmp_path / "analysis.py").write_text("print('existing result')\n", encoding="utf-8")

        ctx = init_new_project(tmp_path, stage="scope_intake")

        assert ctx["has_git"] is False
        assert ctx["has_research_files"] is True
        assert ctx["needs_research_map"] is True
        assert ctx["staged_loading"]["writes_allowed"] == []
        assert not (tmp_path / ".git").exists()
        assert not (tmp_path / "GPD").exists()

    def test_stage_scope_approval_returns_only_contract_fields(self, tmp_path: Path) -> None:
        ctx = init_new_project(tmp_path, stage="scope_approval")

        assert set(ctx) == {
            "project_contract",
            "project_contract_gate",
            "project_contract_load_info",
            "project_contract_validation",
            "staged_loading",
        }
        assert ctx["staged_loading"]["stage_id"] == "scope_approval"
        assert ctx["staged_loading"]["order"] == 2
        assert ctx["staged_loading"]["loaded_authorities"] == [
            "workflows/new-project/scope-approval.md",
        ]
        assert ctx["staged_loading"]["conditional_authorities"] == [
            {
                "when": "contract_schema_validation_or_linkage_repair",
                "authorities": [
                    "templates/project-contract-schema.md",
                    "templates/project-contract-grounding-linkage.md",
                    "references/shared/canonical-schema-discipline.md",
                ],
            }
        ]
        assert "templates/project-contract-schema.md" in ctx["staged_loading"]["must_not_eager_load"]
        assert "templates/project-contract-grounding-linkage.md" in ctx["staged_loading"]["must_not_eager_load"]
        assert "references/shared/canonical-schema-discipline.md" in ctx["staged_loading"]["must_not_eager_load"]
        assert ctx["staged_loading"]["writes_allowed"] == [
            "GPD/state.json",
            "GPD/STATE.md",
            "GPD/state.json.bak",
            "GPD/state.json.lock",
        ]

    def test_resume_work_stage_resume_bootstrap_filters_payload(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _write_project_contract_state(tmp_path)
        _write_literature_review_anchor_file(tmp_path)

        manifest = load_workflow_stage_manifest("resume-work")

        ctx = init_resume(tmp_path, stage="resume_bootstrap")

        stage_ctx.assert_context_stage(ctx, manifest, "resume-work", "resume_bootstrap")
        assert "templates/state-json-schema.md" in ctx["staged_loading"]["must_not_eager_load"]
        assert "reference_artifacts_content" not in ctx
        assert "active_reference_context" not in ctx
        assert "project_contract_gate" not in ctx

    def test_resume_work_stage_state_restore_filters_payload(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _write_project_contract_state(tmp_path)

        manifest = load_workflow_stage_manifest("resume-work")

        ctx = init_resume(tmp_path, stage="state_restore")

        stage_ctx.assert_context_stage(ctx, manifest, "resume-work", "state_restore")
        assert ctx["project_contract_gate"]["visible"] is True
        assert {
            "reference_artifacts_content",
            "active_reference_context",
            "state_content",
            "project_content",
        }.isdisjoint(ctx)
        assert all(ctx[field] is not None for field in ("contract_intake", "effective_reference_intake"))

    def test_resume_work_stage_state_restore_skips_reference_artifact_payload(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_project(tmp_path)
        _write_project_contract_state(tmp_path)
        calls: list[bool] = []

        def _record_artifact_payload(
            *_args: object, include_content: bool = True, **_kwargs: object
        ) -> dict[str, object]:
            calls.append(include_content)
            raise AssertionError("state_restore should not scan reference artifacts")

        monkeypatch.setattr(context_module, "_reference_artifact_payload", _record_artifact_payload)
        monkeypatch.setattr(
            context_module,
            "_render_active_reference_context",
            stage_ctx.fail_if_context_builder_runs("_render_active_reference_context"),
        )

        ctx = init_resume(tmp_path, stage="state_restore")

        assert ctx["staged_loading"]["stage_id"] == "state_restore"
        assert "active_reference_context" not in ctx
        assert calls == []

    def test_resume_work_stage_resume_routing_uses_handoff_handles_without_file_bodies(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        from gpd.core.state import default_state_dict

        state = default_state_dict()
        state["continuation"]["handoff"]["resume_file"] = "GPD/phases/03-analysis/.continue-here.md"
        state["continuation"]["handoff"]["stopped_at"] = "2026-03-10T12:00:00+00:00"
        resume_path = tmp_path / "GPD" / "phases" / "03-analysis" / ".continue-here.md"
        resume_path.parent.mkdir(parents=True, exist_ok=True)
        resume_path.write_text("# Continue Here\nResume this derivation.\n", encoding="utf-8")
        (tmp_path / "GPD" / "state.json").write_text(json.dumps(state), encoding="utf-8")

        manifest = load_workflow_stage_manifest("resume-work")

        ctx = init_resume(tmp_path, stage="resume_routing")

        stage_ctx.assert_context_stage(ctx, manifest, "resume-work", "resume_routing")
        assert ctx["active_resume_kind"] == "continuity_handoff"
        assert {
            ctx["active_resume_pointer"],
            ctx["continuity_handoff_file"],
        } == {"GPD/phases/03-analysis/.continue-here.md"}
        assert {"roadmap_content", "continuity_handoff_content"}.isdisjoint(ctx)

    def test_sync_state_stage_sync_bootstrap_filters_payload(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)

        manifest = load_workflow_stage_manifest("sync-state")

        ctx = init_sync_state(tmp_path, stage="sync_bootstrap")

        stage_ctx.assert_context_stage(ctx, manifest, "sync-state", "sync_bootstrap")
        assert "templates/state-json-schema.md" in ctx["staged_loading"]["must_not_eager_load"]
        assert "state_md_content" not in ctx
        assert "state_json_content" not in ctx

    def test_sync_state_surfaces_current_workspace_only_policy(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside"
        outside.mkdir()

        ctx = init_sync_state(outside)

        assert ctx["workspace_root"] == outside.resolve().as_posix()
        assert ctx["project_root"] == outside.resolve().as_posix()
        assert ctx["project_root_source"] == "current_workspace"
        assert ctx["project_root_auto_selected"] is False
        assert ctx["init_root_policy"] == "current_workspace_only"
        assert ctx["project_reentry_mode"] == "current-workspace"
        assert "will not inspect or repair a recent project from another folder" in ctx["project_reentry_guidance"]

    def test_sync_state_resolves_ancestor_project_root_from_nested_workspace(self, tmp_path: Path) -> None:
        from gpd.core.state import default_state_dict, generate_state_markdown

        _setup_project(tmp_path)
        layout = ProjectLayout(tmp_path)
        state = default_state_dict()
        state["position"]["current_phase"] = "07"
        layout.state_json.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        layout.state_md.write_text(generate_state_markdown(state), encoding="utf-8")
        nested = tmp_path / "workspace" / "notes"
        nested.mkdir(parents=True)

        ctx = init_sync_state(nested)

        assert ctx["state_md_exists"] is True
        assert ctx["state_json_exists"] is True
        assert ctx["state_json_backup_exists"] is False
        assert '"current_phase": "07"' in ctx["state_json_content"]
        assert "**Current Phase:** 07" in ctx["state_md_content"]
        assert not (nested / "GPD").exists()

    def test_sync_state_stage_conflict_analysis_filters_payload(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _write_project_contract_state(tmp_path)

        manifest = load_workflow_stage_manifest("sync-state")

        ctx = init_sync_state(tmp_path, stage="conflict_analysis")

        stage_ctx.assert_context_stage(ctx, manifest, "sync-state", "conflict_analysis")
        assert ctx["project_contract_gate"]["visible"] is True
        assert "state_json_content" in ctx
        assert "state_md_content" in ctx

    def test_write_paper_bootstrap_stays_small_without_stage(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        (tmp_path / "GPD" / "PROJECT.md").write_text("# Project\n\nPaper target.\n", encoding="utf-8")
        _write_project_contract_state(tmp_path)
        _write_manuscript_proof_review_artifacts(tmp_path)

        ctx = init_write_paper(tmp_path)

        assert ctx["project_exists"] is True
        assert "staged_loading" not in ctx
        assert "reference_artifacts_content" not in ctx
        assert "state_content" not in ctx
        assert "current_execution" not in ctx
        assert "derived_manuscript_reference_status" in ctx
        assert "derived_manuscript_proof_review_status" in ctx
        assert "protocol_bundle_context" in ctx
        stage_ctx.assert_project_manuscript_publication_roots(ctx)
        assert ctx["contract_intake"]["must_read_refs"] == ["ref-benchmark"]
        assert "ref-benchmark" in ctx["effective_reference_intake"]["must_read_refs"]

    def test_write_paper_resolves_project_root_from_nested_workspace(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        (tmp_path / "GPD" / "PROJECT.md").write_text("# Project\n\nNested paper target.\n", encoding="utf-8")
        _write_project_contract_state(tmp_path)
        stage_ctx.write_project_paper_manuscript(tmp_path, body="Nested draft.")
        nested = tmp_path / "workspace" / "notes"
        nested.mkdir(parents=True)

        full_ctx = init_write_paper(nested)
        staged_ctx = init_write_paper(nested, stage="paper_bootstrap")

        assert full_ctx["state_exists"] is True
        assert full_ctx["project_exists"] is True
        stage_ctx.assert_project_manuscript_publication_roots(full_ctx)
        assert staged_ctx["project_exists"] is True
        stage_ctx.assert_project_manuscript_publication_roots(staged_ctx)
        assert not (nested / "GPD").exists()

    def test_write_paper_stage_paper_bootstrap_filters_payload(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        (tmp_path / "GPD" / "PROJECT.md").write_text("# Project\n\nPaper target.\n", encoding="utf-8")
        _write_project_contract_state(tmp_path)

        manifest = load_workflow_stage_manifest("write-paper", known_init_fields=_WRITE_PAPER_INIT_FIELDS)

        ctx = init_write_paper(tmp_path, stage="paper_bootstrap")

        stage_ctx.assert_context_stage(ctx, manifest, "write-paper", "paper_bootstrap")
        assert "reference_artifacts_content" not in ctx
        assert "state_content" not in ctx
        assert "derived_convention_lock" not in ctx
        assert ctx["publication_subject_status"] == "missing"
        assert ctx["publication_bootstrap_mode"] == "fresh_project_bootstrap"
        assert ctx["publication_bootstrap_root"] == "paper"
        assert ctx["selected_publication_root"] is None
        assert ctx["publication_intake_root"] is None
        assert "contract_intake" not in ctx
        assert "ref-benchmark" in ctx["effective_reference_intake"]["must_read_refs"]

    def test_write_paper_stage_bootstrap_binds_external_intake_subject(self, tmp_path: Path) -> None:
        intake_path = _write_write_paper_authoring_input(tmp_path)

        ctx = init_write_paper(
            tmp_path,
            subject=f"--intake {intake_path.name}",
            stage="paper_bootstrap",
        )

        assert ctx["project_exists"] is False
        assert ctx["write_paper_argument_input"] == f"--intake {intake_path.name}"
        assert "write_paper_launch_subject" not in ctx
        managed_root = stage_ctx.assert_managed_publication_roots(
            ctx,
            slug="external-authoring-test",
            status="bootstrap",
            owner="external_authoring_intake",
            source="explicit_intake_manifest",
            bootstrap_mode="fresh_project_bootstrap",
            bootstrap_root="GPD/publication/external-authoring-test/manuscript",
            artifact_base="GPD/publication/external-authoring-test/manuscript",
            manuscript_root="GPD/publication/external-authoring-test/manuscript",
            manuscript_entrypoint=None,
            selected_review_root="GPD/publication/external-authoring-test/review",
        )
        assert ctx["publication_subject"]["managed_intake_root"] == f"{managed_root}/intake"

    def test_write_paper_stage_bootstrap_rejects_inside_project_intake(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        (tmp_path / "GPD" / "PROJECT.md").write_text("# Project\n\nPaper target.\n", encoding="utf-8")
        _write_project_contract_state(tmp_path)
        intake_path = _write_write_paper_authoring_input(tmp_path)

        with pytest.raises(ValueError, match="only allowed from a workspace without an initialized GPD project"):
            init_write_paper(
                tmp_path,
                subject=f"--intake {intake_path.name}",
                stage="paper_bootstrap",
            )

    def test_write_paper_stage_bootstrap_rejects_external_intake_with_recoverable_state_only_project(
        self, tmp_path: Path
    ) -> None:
        gpd_dir = tmp_path / "GPD"
        gpd_dir.mkdir()
        (gpd_dir / "state.json").write_text(json.dumps(default_state_dict(), indent=2) + "\n", encoding="utf-8")
        intake_path = _write_write_paper_authoring_input(tmp_path)

        with pytest.raises(ValueError, match="only allowed from a workspace without an initialized GPD project"):
            init_write_paper(
                tmp_path,
                subject=f"--intake {intake_path.name}",
                stage="paper_bootstrap",
            )

    def test_write_paper_stage_outline_and_scaffold_loads_deferred_context(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        planning = tmp_path / "GPD"
        (planning / "PROJECT.md").write_text("# Project\n\nPaper target.\n", encoding="utf-8")
        (planning / "STATE.md").write_text("# State\n\nReady.\n", encoding="utf-8")
        (planning / "ROADMAP.md").write_text("# Roadmap\n\n## Milestone v1.0\n", encoding="utf-8")
        (planning / "REQUIREMENTS.md").write_text("# Requirements\n\n- Verified evidence\n", encoding="utf-8")
        _write_project_contract_state(tmp_path)
        _write_literature_review_anchor_file(tmp_path)
        _write_research_map_anchor_files(tmp_path)
        _write_structured_state_memory(tmp_path)

        manifest = load_workflow_stage_manifest("write-paper", known_init_fields=_WRITE_PAPER_INIT_FIELDS)

        ctx = init_write_paper(tmp_path, stage="outline_and_scaffold")

        stage_ctx.assert_context_stage(ctx, manifest, "write-paper", "outline_and_scaffold")
        assert "reference_artifacts_content" not in ctx
        assert "roadmap_content" not in ctx
        assert "requirements_content" not in ctx
        assert "GPD/research-map/REFERENCES.md" in ctx["reference_artifact_files"]
        assert ctx["literature_review_files"] == ["GPD/literature/benchmark-REVIEW.md"]
        assert ctx["derived_convention_lock_count"] == 2
        assert ctx["derived_intermediate_result_count"] == 1
        assert ctx["publication_bootstrap_mode"] == "fresh_project_bootstrap"
        assert ctx["selected_publication_root"] is None
        assert ctx["publication_intake_root"] is None
        assert "contract_intake" not in ctx
        assert ctx["effective_reference_intake"] == stage_ctx.EMPTY_REFERENCE_INTAKE

    def test_write_paper_stage_paper_bootstrap_surfaces_resolved_publication_subject(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        (tmp_path / "GPD" / "PROJECT.md").write_text("# Project\n\nPaper target.\n", encoding="utf-8")
        _write_project_contract_state(tmp_path)
        stage_ctx.write_project_paper_manuscript(tmp_path)

        ctx = init_write_paper(tmp_path, stage="paper_bootstrap")

        stage_ctx.assert_project_manuscript_publication_roots(
            ctx,
            artifact_base="paper",
            manuscript_root="paper",
            manuscript_entrypoint="paper/main.tex",
            artifact_manifest_path="paper/ARTIFACT-MANIFEST.json",
        )
        assert "contract_intake" not in ctx
        assert "ref-benchmark" in ctx["effective_reference_intake"]["must_read_refs"]

    def test_write_paper_bootstrap_surfaces_managed_publication_lane_without_stage(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        (tmp_path / "GPD" / "PROJECT.md").write_text("# Project\n\nPaper target.\n", encoding="utf-8")
        _write_project_contract_state(tmp_path)
        stage_ctx.write_managed_context_manuscript(tmp_path, subject_slug="curvature-flow-bounds")

        ctx = init_write_paper(tmp_path)

        stage_ctx.assert_managed_publication_roots(
            ctx,
            slug="curvature-flow-bounds",
            bootstrap_mode="resume_existing_manuscript",
            bootstrap_root="GPD/publication/curvature-flow-bounds/manuscript",
            artifact_base="GPD/publication/curvature-flow-bounds/manuscript",
            manuscript_root="GPD/publication/curvature-flow-bounds/manuscript",
            manuscript_entrypoint="GPD/publication/curvature-flow-bounds/manuscript/main.tex",
        )
        assert ctx["contract_intake"]["must_read_refs"] == ["ref-benchmark"]
        assert "ref-benchmark" in ctx["effective_reference_intake"]["must_read_refs"]

    def test_write_paper_stage_bootstrap_surfaces_managed_lane_roots_without_project_backing(
        self, tmp_path: Path
    ) -> None:
        _setup_project(tmp_path)
        manuscript = stage_ctx.write_managed_context_manuscript(
            tmp_path,
            subject_slug="external-lane",
            body="External lane draft.",
        )
        intake_dir = manuscript.parent.parent / "intake"
        intake_dir.mkdir(parents=True)
        (intake_dir / "write-paper-authoring-input.json").write_text('{"schema_version": 1}\n', encoding="utf-8")

        ctx = init_write_paper(tmp_path, stage="paper_bootstrap")

        assert ctx["project_exists"] is False
        stage_ctx.assert_managed_publication_roots(ctx, slug="external-lane")
        stage_ctx.assert_empty_reference_intake(ctx)

    def test_peer_review_stage_bootstrap_surfaces_selected_project_review_roots(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        (tmp_path / "GPD" / "PROJECT.md").write_text("# Project\n\nPeer review target.\n", encoding="utf-8")
        _write_project_contract_state(tmp_path)
        stage_ctx.write_project_paper_manuscript(tmp_path)

        manifest = load_workflow_stage_manifest("peer-review")
        ctx = init_peer_review(tmp_path, stage="bootstrap")

        stage_ctx.assert_context_stage(ctx, manifest, "peer-review", "bootstrap")
        stage_ctx.assert_publication_subject_roots(
            ctx,
            expected={
                "publication_lane_kind": "canonical_project_manuscript",
                "publication_lane_owner": "project_managed",
            },
        )
        assert ctx["selected_publication_root"] == "GPD"
        assert ctx["selected_review_root"] == "GPD/review"

    def test_peer_review_stage_bootstrap_skips_artifact_content_hydration(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup_project(tmp_path)
        (tmp_path / "GPD" / "PROJECT.md").write_text("# Project\n\nPeer review target.\n", encoding="utf-8")
        _write_project_contract_state(tmp_path)
        stage_ctx.write_project_paper_manuscript(tmp_path)
        calls: list[bool] = []
        monkeypatch.setattr(
            context_module, "_reference_artifact_payload", stage_ctx.record_reference_artifact_payload_calls(calls)
        )

        ctx = init_peer_review(tmp_path, stage="bootstrap")

        assert ctx["staged_loading"]["stage_id"] == "bootstrap"
        assert "reference_artifacts_content" not in ctx
        assert calls == [False]

    def test_respond_to_referees_stage_bootstrap_routes_explicit_manuscript_intake(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _write_project_contract_state(tmp_path)
        manuscript = stage_ctx.write_project_paper_manuscript(tmp_path)
        manuscript_dir = manuscript.parent
        reports = tmp_path / "reviews"
        reports.mkdir()
        (reports / "referee-1.md").write_text("# Referee 1\n", encoding="utf-8")
        intake = "--manuscript paper/main.tex --report reviews/referee-1.md"

        ctx = init_respond_to_referees(tmp_path, subject=intake, stage="bootstrap")

        assert ctx["response_intake_input"] == intake
        assert ctx["review_target_input"] == "paper/main.tex"
        assert ctx["resolved_review_target"] == str(manuscript)
        assert ctx["resolved_review_root"] == str(manuscript_dir)

    def test_respond_to_referees_response_authoring_hydrates_artifact_content(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup_project(tmp_path)
        _write_project_contract_state(tmp_path)
        stage_ctx.write_project_paper_manuscript(tmp_path)
        reports = tmp_path / "reviews"
        reports.mkdir()
        (reports / "referee-1.md").write_text("# Referee 1\n", encoding="utf-8")
        calls: list[bool] = []
        monkeypatch.setattr(
            context_module, "_reference_artifact_payload", stage_ctx.record_reference_artifact_payload_calls(calls)
        )

        ctx = init_respond_to_referees(
            tmp_path,
            subject="reviews/referee-1.md",
            stage="response_authoring",
        )

        assert ctx["staged_loading"]["stage_id"] == "response_authoring"
        assert ctx["reference_artifact_files"] == ["GPD/research-map/REFERENCES.md"]
        assert ctx["reference_artifacts_content"] == "hydrated reference artifacts"
        assert calls == [True]

    def test_respond_to_referees_stage_bootstrap_treats_bare_path_as_report_source(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _write_project_contract_state(tmp_path)
        manuscript = stage_ctx.write_project_paper_manuscript(tmp_path)
        manuscript_dir = manuscript.parent
        reports = tmp_path / "reviews"
        reports.mkdir()
        report = reports / "referee-1.md"
        report.write_text("# Referee 1\n", encoding="utf-8")

        ctx = init_respond_to_referees(tmp_path, subject="reviews/referee-1.md", stage="bootstrap")

        assert ctx["response_intake_input"] == "reviews/referee-1.md"
        assert ctx["review_target_input"] != "reviews/referee-1.md"
        assert ctx["resolved_review_target"] == str(manuscript)
        assert ctx["resolved_review_root"] == str(manuscript_dir)

    def test_peer_review_stage_bootstrap_resolves_project_context_from_nested_cwd_and_launch_relative_target(
        self, tmp_path: Path
    ) -> None:
        _setup_project(tmp_path)
        (tmp_path / "GPD" / "PROJECT.md").write_text("# Project\n\nNested peer review target.\n", encoding="utf-8")
        _write_project_contract_state(tmp_path)
        nested = tmp_path / "workspace" / "notes"
        nested.mkdir(parents=True)
        review_target = nested / "review-target.txt"
        review_target.write_text("Standalone artifact from nested launch cwd.\n", encoding="utf-8")

        full_ctx = init_peer_review(nested, subject=review_target.name)
        staged_ctx = init_peer_review(nested, subject=review_target.name, stage="bootstrap")

        for ctx in (full_ctx, staged_ctx):
            assert ctx["project_exists"] is True
            assert ctx["state_exists"] is True
            assert ctx["review_target_input"] == review_target.name
            assert ctx["review_target_mode"] == "standalone explicit-artifact review"
            assert ctx["resolved_review_target"] == str(review_target)
            assert ctx["resolved_review_root"] == str(nested)
            assert ctx["project_contract_validation"] is None
            assert ctx["project_contract_gate"]["status"] == "standalone_explicit_artifact"
            assert ctx["project_contract_gate"]["source_path"] is None
            assert ctx["project_contract_gate"]["authoritative"] is False
            assert ctx["project_contract_gate"]["visible"] is False
            assert ctx["project_contract_load_info"]["status"] == "standalone_explicit_artifact"
            assert ctx["project_contract_load_info"]["source_path"] is None
            assert ctx["contract_intake"] is None
            assert ctx["effective_reference_intake"] == stage_ctx.EMPTY_REFERENCE_INTAKE
            assert ctx.get("publication_bootstrap") is None
            assert ctx.get("publication_bootstrap_mode") is None
            assert ctx.get("publication_bootstrap_root") is None
            assert ctx.get("publication_bootstrap_detail") is None
            if "publication_intake_root" in ctx:
                assert ctx["publication_intake_root"] == f"{ctx['managed_publication_root']}/intake"
            stage_ctx.assert_external_artifact_publication_roots(ctx)
        assert full_ctx["project_contract"] is None
        assert full_ctx["active_reference_context"] == ""
        assert full_ctx["selected_protocol_bundle_ids"] == []
        assert full_ctx["protocol_bundle_load_manifest"]["selected_bundle_ids"] == []
        assert full_ctx["protocol_bundle_context"] is None
        assert {
            "project_contract",
            "active_reference_context",
            "selected_protocol_bundle_ids",
            "protocol_bundle_load_manifest",
            "protocol_bundle_context",
        }.isdisjoint(staged_ctx)

    def test_peer_review_stage_projectless_manuscript_artifact_uses_subject_owned_review_roots(
        self,
        tmp_path: Path,
    ) -> None:
        workspace = tmp_path / "standalone-review"
        manuscript_dir = workspace / "manuscript"
        manuscript_dir.mkdir(parents=True)
        manuscript = manuscript_dir / "standalone.tex"
        manuscript.write_text(
            "\\documentclass{article}\\begin{document}Standalone draft.\\end{document}\n",
            encoding="utf-8",
        )

        contexts = [
            init_peer_review(workspace, subject="manuscript/standalone.tex"),
            init_peer_review(workspace, subject="manuscript/standalone.tex", stage="bootstrap"),
            init_peer_review(workspace, subject="manuscript/standalone.tex", stage="preflight"),
        ]

        for ctx in contexts:
            assert ctx["project_exists"] is False
            assert ctx["review_target_mode"] == "standalone explicit-artifact review"
            assert ctx["resolved_review_target"] == str(manuscript)
            assert ctx["resolved_review_root"] == str(manuscript_dir)
            stage_ctx.assert_external_artifact_publication_roots(ctx, managed_manuscript_root=None)

    def test_arxiv_submission_stage_bootstrap_surfaces_subject_owned_publication_roots(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        (tmp_path / "GPD" / "PROJECT.md").write_text("# Project\n\nSubmission target.\n", encoding="utf-8")
        _write_project_contract_state(tmp_path)
        stage_ctx.write_managed_context_manuscript(tmp_path, subject_slug="curvature-flow-bounds")

        manifest = load_workflow_stage_manifest("arxiv-submission")
        ctx = init_arxiv_submission(tmp_path, stage="bootstrap")

        stage_ctx.assert_context_stage(ctx, manifest, "arxiv-submission", "bootstrap")
        stage_ctx.assert_managed_publication_roots(ctx, slug="curvature-flow-bounds", staged_payload=True)
        assert ctx["selected_review_root"] == "GPD/publication/curvature-flow-bounds/review"

    def test_arxiv_submission_stage_bootstrap_surfaces_newest_response_freshness(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        (tmp_path / "GPD" / "PROJECT.md").write_text("# Project\n\nSubmission target.\n", encoding="utf-8")
        _write_project_contract_state(tmp_path)
        publication_root = tmp_path / "GPD" / "publication" / "curvature-flow-bounds"
        stage_ctx.write_managed_context_manuscript(tmp_path, subject_slug="curvature-flow-bounds")
        review_dir = publication_root / "review"
        review_dir.mkdir(parents=True)
        response_frontmatter = (
            "---\n"
            "response_to: REFEREE-REPORT-R2.md\n"
            "round: 2\n"
            "manuscript_path: GPD/publication/curvature-flow-bounds/manuscript/main.tex\n"
            "---\n\n"
        )
        (publication_root / "AUTHOR-RESPONSE-R2.md").write_text(
            response_frontmatter + "# Author Response\n",
            encoding="utf-8",
        )
        (review_dir / "REFEREE_RESPONSE-R2.md").write_text(
            response_frontmatter + "# Referee Response\n",
            encoding="utf-8",
        )

        ctx = init_arxiv_submission(tmp_path, stage="bootstrap")

        assert ctx["latest_response_round"] == 2
        assert "latest_author_response" not in ctx
        assert "latest_referee_response" not in ctx
        assert ctx["latest_response_requires_fresh_review"] is True
        assert ctx["latest_response_required_review_round"] == 3
        assert ctx["latest_response_freshness_policy"] == "conservative_all_response_artifacts"

    def test_arxiv_submission_resolves_project_root_from_nested_workspace(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        (tmp_path / "GPD" / "PROJECT.md").write_text("# Project\n\nNested submission target.\n", encoding="utf-8")
        _write_project_contract_state(tmp_path)
        stage_ctx.write_managed_context_manuscript(
            tmp_path,
            subject_slug="curvature-flow-bounds",
            body="Nested submission draft.",
        )
        nested = tmp_path / "workspace" / "notes"
        nested.mkdir(parents=True)

        full_ctx = init_arxiv_submission(nested)
        staged_ctx = init_arxiv_submission(nested, stage="bootstrap")

        assert full_ctx["state_exists"] is True
        assert full_ctx["project_exists"] is True
        stage_ctx.assert_managed_publication_roots(full_ctx, slug="curvature-flow-bounds")
        assert staged_ctx["project_exists"] is True
        stage_ctx.assert_managed_publication_roots(staged_ctx, slug="curvature-flow-bounds", staged_payload=True)
        assert not (nested / "GPD").exists()


class TestInitNewMilestone:
    def test_basic(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_roadmap(tmp_path, "## Milestone v1.0: Setup Phase\n")

        ctx = init_new_milestone(tmp_path)
        assert ctx["current_milestone"] == "v1.0"
        assert ctx["current_milestone_name"] == "Setup Phase"
        assert "planning_exists" not in ctx

    def test_surfaces_project_contract_and_effective_reference_context(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_roadmap(tmp_path, "## Milestone v1.0: Setup Phase\n")
        _write_project_contract_state(tmp_path)
        _write_literature_review_anchor_file(tmp_path)
        _write_research_map_anchor_files(tmp_path)

        ctx = init_new_milestone(tmp_path)

        assert ctx["project_contract"]["scope"]["question"] == "What benchmark must the project recover?"
        assert "roadmapper_model" in ctx
        assert ctx["contract_intake"]["must_read_refs"] == ["ref-benchmark"]
        assert ctx["project_contract"]["context_intake"]["must_read_refs"] == ["ref-benchmark"]
        assert ctx["project_contract_gate"]["visible"] is True
        assert ctx["project_contract_gate"]["authoritative"] is True
        assert "ref-benchmark" in ctx["effective_reference_intake"]["must_read_refs"]
        assert "lit-anchor-benchmark-ref-2024" in ctx["effective_reference_intake"]["must_read_refs"]
        assert (
            "GPD/phases/01-test-phase/01-SUMMARY.md" in ctx["effective_reference_intake"]["must_include_prior_outputs"]
        )
        assert "Benchmark Ref 2024" in ctx["active_reference_context"]
        assert "GPD/research-map/REFERENCES.md" in ctx["reference_artifact_files"]

    def test_new_milestone_stage_bootstrap_filters_payload(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_roadmap(tmp_path, "## Milestone v1.0: Setup Phase\n")
        _write_project_contract_state(tmp_path)

        manifest = load_workflow_stage_manifest("new-milestone")

        ctx = init_new_milestone(tmp_path, stage="milestone_bootstrap")

        stage_ctx.assert_context_stage(ctx, manifest, "new-milestone", "milestone_bootstrap")
        assert "planning_exists" not in ctx
        assert "roadmapper_model" not in ctx

    def test_new_milestone_stage_resolves_ancestor_project_root_from_nested_workspace(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_roadmap(tmp_path, "## Milestone v1.0: Setup Phase\n")
        (tmp_path / "GPD" / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
        _write_project_contract_state(tmp_path)
        nested = tmp_path / "workspace" / "notes"
        nested.mkdir(parents=True)

        ctx = init_new_milestone(nested, stage="milestone_bootstrap")

        assert ctx["project_exists"] is True
        assert ctx["roadmap_exists"] is True
        assert ctx["state_exists"] is True
        assert ctx["current_milestone"] == "v1.0"
        assert not (nested / "GPD").exists()

    def test_does_not_bootstrap_manuscript_proof_review_manifest(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_roadmap(tmp_path, "## Milestone v1.0: Setup Phase\n")
        _write_manuscript_proof_review_artifacts(tmp_path)

        ctx = init_new_milestone(tmp_path)

        status = ctx["derived_manuscript_proof_review_status"]
        assert status["state"] == "fresh"
        assert status["manifest_bootstrapped"] is False
        assert not (tmp_path / "paper" / "PROOF-REVIEW-MANIFEST.json").exists()

    def test_surfaces_project_contract_load_and_validation_gates_when_contract_is_not_authoritative(
        self, tmp_path: Path
    ) -> None:
        _setup_project(tmp_path)
        _create_roadmap(tmp_path, "## Milestone v1.0: Setup Phase\n")

        from gpd.core.state import default_state_dict

        state = default_state_dict()
        contract = json.loads((FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"))
        contract["context_intake"] = dict(stage_ctx.EMPTY_REFERENCE_INTAKE)
        contract["references"][0]["role"] = "background"
        contract["references"][0]["must_surface"] = False
        state["project_contract"] = contract
        (tmp_path / "GPD" / "state.json").write_text(json.dumps(state), encoding="utf-8")

        ctx = init_new_milestone(tmp_path)

        assert ctx["project_contract"] is not None
        assert ctx["project_contract"]["references"][0]["role"] == "background"
        assert ctx["project_contract_load_info"]["status"] == "blocked_integrity"
        assert ctx["project_contract_validation"]["valid"] is False
        assert ctx["project_contract_gate"]["visible"] is True
        assert ctx["project_contract_gate"]["authoritative"] is False
        assert "project_contract_load_info" in ctx
        assert "project_contract_validation" in ctx

    def test_new_milestone_stage_survey_objectives_filters_payload(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_roadmap(tmp_path, "## Milestone v1.0: Setup Phase\n")
        _write_project_contract_state(tmp_path)
        _write_literature_review_anchor_file(tmp_path)
        _write_research_map_anchor_files(tmp_path)

        manifest = load_workflow_stage_manifest("new-milestone")

        ctx = init_new_milestone(tmp_path, stage="survey_objectives")

        stage_ctx.assert_context_stage(ctx, manifest, "new-milestone", "survey_objectives")
        assert ctx["staged_loading"]["checkpoints"] == [
            "prior milestone context reviewed",
            "survey choice and objective scope captured",
        ]
        assert "contract_intake" in ctx
        assert "effective_reference_intake" in ctx
        assert "reference_artifact_files" in ctx
        assert "reference_artifacts_content" not in ctx
        assert "roadmapper_model" not in ctx

    def test_new_milestone_stage_roadmap_authoring_filters_payload(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_roadmap(tmp_path, "## Milestone v1.0: Setup Phase\n")
        (tmp_path / "GPD" / "PROJECT.md").write_text("# Project\n\nMilestone context.\n", encoding="utf-8")
        (tmp_path / "GPD" / "STATE.md").write_text("# State\n\nReady.\n", encoding="utf-8")
        (tmp_path / "GPD" / "REQUIREMENTS.md").write_text("# Requirements\n\n- Confirm objective.\n", encoding="utf-8")
        (tmp_path / "GPD" / "ROADMAP.md").write_text("# Roadmap\n\n## Milestone v1.0\n", encoding="utf-8")
        _write_project_contract_state(tmp_path)
        _write_literature_review_anchor_file(tmp_path)
        _write_research_map_anchor_files(tmp_path)

        manifest = load_workflow_stage_manifest("new-milestone")

        ctx = init_new_milestone(tmp_path, stage="roadmap_authoring")

        stage_ctx.assert_context_stage(ctx, manifest, "new-milestone", "roadmap_authoring")
        assert ctx["staged_loading"]["checkpoints"] == [
            "objectives finalized",
            "roadmap authored",
        ]
        assert "project_content" not in ctx
        assert "state_content" not in ctx
        assert "requirements_content" not in ctx
        assert "roadmap_content" not in ctx
        assert "reference_artifact_files" in ctx
        assert "reference_artifacts_content" not in ctx


class TestInitQuick:
    def test_first_quick_task(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        (tmp_path / "GPD" / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
        ctx = init_quick(tmp_path, "Fix tensor product calculation")
        assert ctx["next_num"] == 1
        assert ctx["slug"] is not None
        assert "fix" in ctx["slug"]
        assert ctx["task_dir"] is not None
        assert ctx["project_exists"] is True

    def test_increments_number(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        quick_dir = tmp_path / "GPD" / "quick"
        quick_dir.mkdir()
        (quick_dir / "1-first-task").mkdir()
        (quick_dir / "2-second-task").mkdir()

        ctx = init_quick(tmp_path, "next task")
        assert ctx["next_num"] == 3

    def test_permission_error_on_quick_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _setup_project(tmp_path)
        quick_dir = tmp_path / "GPD" / "quick"
        quick_dir.mkdir()

        original_iterdir = Path.iterdir

        def _raise_permission(self: Path) -> None:
            if self == quick_dir:
                raise PermissionError("Permission denied")
            return original_iterdir(self)

        monkeypatch.setattr(Path, "iterdir", _raise_permission)

        ctx = init_quick(tmp_path, "some task")
        # Falls back to default numbering when directory is unreadable
        assert ctx["next_num"] == 1

    def test_stage_task_authoring_uses_quick_manifest_contract(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup_project(tmp_path)
        (tmp_path / "GPD" / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
        _write_project_contract_state(tmp_path)
        monkeypatch.setattr(
            context_module,
            "_resolve_model",
            lambda cwd, agent_type, config=None, runtime=None: f"{agent_type}-model",
        )
        monkeypatch.setattr(
            context_module,
            "_build_reference_runtime_context",
            stage_ctx.fail_if_context_builder_runs("_build_reference_runtime_context"),
        )
        manifest = load_workflow_stage_manifest("quick")

        ctx = init_quick(tmp_path, "Quick dimensional check", stage="task_authoring")

        stage_ctx.assert_context_stage(ctx, manifest, "quick", "task_authoring")
        assert "project_contract_gate" in ctx
        for reference_heavy_field in (
            "active_reference_context",
            "contract_intake",
            "derived_manuscript_proof_review_status",
            "effective_reference_intake",
            "protocol_bundle_context",
            "protocol_bundle_load_manifest",
            "reference_artifact_files",
            "reference_artifacts_content",
        ):
            assert reference_heavy_field not in ctx

    def test_stage_reference_context_loads_reference_handles_when_selected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup_project(tmp_path)
        (tmp_path / "GPD" / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
        _write_project_contract_state(tmp_path)
        monkeypatch.setattr(
            "gpd.core.context._resolve_model",
            lambda cwd, agent_type, config=None, runtime=None: f"{agent_type}-model",
        )
        calls: list[Path] = []

        def reference_runtime_context(
            cwd: Path,
            *,
            include_artifact_content: bool = True,
            include_active_reference_context: bool = True,
            include_protocol_context: bool = True,
            **_kwargs: object,
        ) -> dict[str, object]:
            calls.append(cwd)
            assert include_artifact_content is False
            assert include_active_reference_context is False
            assert include_protocol_context is False
            return {
                "project_contract": {"version": 1},
                "project_contract_gate": {"authoritative": True},
                "project_contract_load_info": {"status": "loaded"},
                "project_contract_validation": {"valid": True},
                "contract_intake": {"must_read_refs": ["ref-benchmark"]},
                "effective_reference_intake": {"must_read_refs": ["ref-benchmark"]},
                "selected_protocol_bundle_ids": ["core"],
                "protocol_bundle_count": 1,
                "protocol_bundle_load_manifest": {"selected_bundle_ids": ["core"], "bundle_count": 1},
                "protocol_bundle_verifier_extensions": ["verifier extensions"],
                "reference_artifact_files": ["GPD/research-map/REFERENCES.md"],
                "literature_review_files": ["GPD/literature/SUMMARY.md"],
                "literature_review_count": 1,
                "research_map_reference_files": ["GPD/research-map/REFERENCES.md"],
                "research_map_reference_count": 1,
                "derived_manuscript_proof_review_status": {"status": "not applicable"},
            }

        monkeypatch.setattr(context_module, "_build_reference_runtime_context", reference_runtime_context)
        manifest = load_workflow_stage_manifest("quick")

        ctx = init_quick(tmp_path, "Look up benchmark source", stage="reference_context")

        assert calls == [tmp_path]
        stage_ctx.assert_context_stage(ctx, manifest, "quick", "reference_context")
        assert ctx["contract_intake"] == {"must_read_refs": ["ref-benchmark"]}
        assert ctx["effective_reference_intake"] == {"must_read_refs": ["ref-benchmark"]}
        assert ctx["selected_protocol_bundle_ids"] == ["core"]
        assert ctx["protocol_bundle_count"] == 1
        assert ctx["protocol_bundle_load_manifest"] == {"selected_bundle_ids": ["core"], "bundle_count": 1}
        assert ctx["protocol_bundle_verifier_extensions"] == ["verifier extensions"]
        assert ctx["reference_artifact_files"] == ["GPD/research-map/REFERENCES.md"]
        assert "protocol_bundle_context" not in ctx
        assert "active_reference_context" not in ctx
        assert "reference_artifacts_content" not in ctx

    @pytest.mark.parametrize(
        ("stage_id", "required_fields", "loads_reference_handles"),
        (
            ("handle_only_reference", ("description", "project_exists", "reference_artifact_files"), True),
            (
                "summary_handles",
                ("description", "project_exists", "selected_protocol_bundle_ids", "protocol_bundle_load_manifest"),
                False,
            ),
            (
                "artifact_handles",
                (
                    "description",
                    "project_exists",
                    "reference_artifact_files",
                    "selected_protocol_bundle_ids",
                    "protocol_bundle_load_manifest",
                ),
                True,
            ),
        ),
    )
    def test_stage_reference_handle_payloads_skip_heavy_context(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        stage_id: str,
        required_fields: tuple[str, ...],
        loads_reference_handles: bool,
    ) -> None:
        _setup_project(tmp_path)
        (tmp_path / "GPD" / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
        _write_project_contract_state(tmp_path)
        install_fake_stage_manifest(monkeypatch, workflow_id="quick", stages={stage_id: required_fields})
        calls: list[bool] = []
        monkeypatch.setattr(
            context_module,
            "_reference_artifact_payload",
            stage_ctx.record_reference_artifact_payload_calls(calls)
            if loads_reference_handles
            else stage_ctx.fail_if_context_builder_runs("_reference_artifact_payload"),
        )
        monkeypatch.setattr(
            context_module,
            "_render_active_reference_context",
            stage_ctx.fail_if_context_builder_runs("_render_active_reference_context"),
        )
        monkeypatch.setattr(
            context_module,
            "render_protocol_bundle_context",
            stage_ctx.fail_if_context_builder_runs("render_protocol_bundle_context"),
        )

        ctx = init_quick(tmp_path, "Check artifact handles", stage=stage_id)

        assert ctx["staged_loading"]["stage_id"] == stage_id
        if "reference_artifact_files" in required_fields:
            assert ctx["reference_artifact_files"] == ["GPD/research-map/REFERENCES.md"]
        if "protocol_bundle_load_manifest" in required_fields:
            assert ctx["selected_protocol_bundle_ids"] == []
            assert ctx["protocol_bundle_load_manifest"]["selected_bundle_ids"] == []
        stage_ctx.assert_stage_omits_heavy_reference_context(ctx)
        assert calls == ([False] if loads_reference_handles else [])

    def test_stage_reference_context_defers_artifact_content_until_body_selection(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup_project(tmp_path)
        (tmp_path / "GPD" / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
        _write_project_contract_state(tmp_path)
        calls: list[bool] = []
        monkeypatch.setattr(
            context_module, "_reference_artifact_payload", stage_ctx.record_reference_artifact_payload_calls(calls)
        )

        ctx = init_quick(tmp_path, "Look up benchmark source", stage="reference_context")

        assert ctx["staged_loading"]["stage_id"] == "reference_context"
        assert ctx["reference_artifact_files"] == ["GPD/research-map/REFERENCES.md"]
        assert "reference_artifacts_content" not in ctx
        assert calls == [False]

    def test_stage_validation_failure_names_workflow_stage_and_spec(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import sys
        import types

        _setup_project(tmp_path)
        (tmp_path / "GPD" / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
        calls: list[tuple[str, str, str, dict[str, object]]] = []

        class Stage:
            id = "task_authoring"
            required_init_fields = ("description",)
            init_spec_id = "quick.task_authoring.v1"

        class Manifest:
            def stage_by_id(self, stage_id: str) -> Stage:
                assert stage_id == "task_authoring"
                return Stage()

            def stage_ids(self) -> tuple[str, ...]:
                return ("task_authoring",)

            def staged_loading_payload(self, stage_id: str) -> dict[str, object]:
                assert stage_id == "task_authoring"
                return {"workflow_id": "quick", "stage_id": stage_id, "init_spec_id": Stage.init_spec_id}

        def fake_load_workflow_stage_manifest(
            workflow_id: str,
            allowed_tools: set[str] | None = None,
            known_init_fields: set[str] | None = None,
        ) -> Manifest:
            assert workflow_id == "quick"
            return Manifest()

        def validate_staged_init_payload(
            workflow_id: str,
            stage_id: str,
            init_spec_id: str,
            payload: dict[str, object],
        ) -> None:
            calls.append((workflow_id, stage_id, init_spec_id, payload))
            assert set(payload) == {"description"}
            assert "staged_loading" not in payload
            raise ValueError("description has wrong type")

        validator_module = types.ModuleType("gpd.core.workflow_init_specs")
        validator_module.validate_staged_init_payload = validate_staged_init_payload
        monkeypatch.setitem(sys.modules, "gpd.core.workflow_init_specs", validator_module)
        monkeypatch.setattr("gpd.core.workflow_staging.load_workflow_stage_manifest", fake_load_workflow_stage_manifest)

        with pytest.raises(ValueError) as exc_info:
            init_quick(tmp_path, "Bad staged payload", stage="task_authoring")

        message = str(exc_info.value)
        assert "workflow=quick" in message
        assert "stage=task_authoring" in message
        assert "init_spec_id=quick.task_authoring.v1" in message
        assert "description has wrong type" in message
        assert calls == [("quick", "task_authoring", "quick.task_authoring.v1", {"description": "Bad staged payload"})]

    def test_staged_quick_init_blocks_without_initialized_project(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)

        with pytest.raises(ValueError, match="quick staged init requires an initialized GPD project"):
            init_quick(tmp_path, "Quick reference check", stage="task_bootstrap")

    def test_no_description(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        ctx = init_quick(tmp_path)
        assert ctx["slug"] is None
        assert ctx["task_dir"] is None


class TestInitResume:
    def test_no_interrupted_agent(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        ctx = init_resume(tmp_path)
        assert ctx["has_interrupted_agent"] is False
        assert ctx["interrupted_agent_id"] is None

    def test_with_interrupted_agent(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        (tmp_path / "GPD" / "current-agent-id.txt").write_text("agent-123\n", encoding="utf-8")

        ctx = init_resume(tmp_path)
        assert ctx["has_interrupted_agent"] is True
        assert ctx["interrupted_agent_id"] == "agent-123"
        assert ctx["active_resume_kind"] == "interrupted_agent"
        assert ctx["active_resume_origin"] == "interrupted_agent_marker"
        assert ctx["active_resume_pointer"] == "agent-123"
        assert ctx["resume_candidates"] == [
            {
                "status": "interrupted",
                "agent_id": "agent-123",
                "kind": "interrupted_agent",
                "origin": "interrupted_agent_marker",
                "resume_pointer": "agent-123",
            }
        ]
        assert "source" not in ctx["resume_candidates"][0]
        assert "resume_surface" not in ctx

    def test_resume_prefers_explicit_gpd_workspace_over_recent_project(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        recent_project = tmp_path / "recent-project"
        data_root = tmp_path / "data"

        workspace.mkdir()
        recent_project.mkdir()
        _setup_project(workspace)
        (workspace / "GPD" / "current-agent-id.txt").write_text("agent-local\n", encoding="utf-8")

        _setup_project(recent_project)
        from gpd.core.state import default_state_dict

        (recent_project / "GPD" / "state.json").write_text(
            json.dumps(default_state_dict()),
            encoding="utf-8",
        )
        (recent_project / "GPD" / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
        (recent_project / "GPD" / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
        resume_path = recent_project / "GPD" / "phases" / "01-analysis" / ".continue-here.md"
        resume_path.parent.mkdir(parents=True, exist_ok=True)
        resume_path.write_text("resume\n", encoding="utf-8")
        record_recent_project(
            recent_project,
            session_data={
                "last_date": "2026-03-29T12:00:00+00:00",
                "resume_file": "GPD/phases/01-analysis/.continue-here.md",
            },
            store_root=data_root,
        )

        ctx = init_resume(workspace, data_root=data_root)

        assert ctx["project_root"] == workspace.resolve().as_posix()
        assert ctx["project_root_source"] == "current_workspace"
        assert ctx["project_root_auto_selected"] is False
        assert ctx["init_root_policy"] == "project_reentry_allowed"
        assert ctx["project_reentry_mode"] == "current-workspace"
        assert ctx["project_reentry_selected_candidate"] is not None
        assert ctx["project_reentry_selected_candidate"]["source"] == "current_workspace"
        assert ctx["has_interrupted_agent"] is True
        assert ctx["interrupted_agent_id"] == "agent-local"
        assert ctx["active_resume_kind"] == "interrupted_agent"

    def test_json_only_state_counts_as_existing(self, tmp_path: Path) -> None:
        from gpd.core.state import default_state_dict

        _setup_project(tmp_path)
        (tmp_path / "GPD" / "state.json").write_text(json.dumps(default_state_dict()), encoding="utf-8")

        ctx = init_resume(tmp_path)

        assert ctx["state_exists"] is True

    def test_exposes_bounded_segment_resume_candidate(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _write_current_execution(
            tmp_path,
            {
                "session_id": "sess-1",
                "phase": "03",
                "plan": "02",
                "segment_id": "seg-4",
                "segment_status": "paused",
                "resume_file": "GPD/phases/03-analysis/.continue-here.md",
                "updated_at": "2026-03-10T12:00:00+00:00",
            },
        )

        ctx = init_resume(tmp_path)

        assert ctx["resume_surface_schema_version"] == 1
        assert "resume_mode" not in ctx
        assert ctx["active_resume_kind"] == "bounded_segment"
        assert ctx["active_resume_origin"] == "continuation.bounded_segment"
        assert ctx["active_resume_pointer"] == "GPD/phases/03-analysis/.continue-here.md"
        assert ctx["active_bounded_segment"]["segment_id"] == "seg-4"
        assert ctx["derived_execution_head"]["segment_id"] == "seg-4"
        _assert_no_resume_compat_aliases(ctx)
        assert "resume_surface" not in ctx
        assert "segment_candidates" not in ctx
        assert ctx["resume_candidates"][0]["kind"] == "bounded_segment"
        assert ctx["resume_candidates"][0]["origin"] == "continuation.bounded_segment"
        assert ctx["resume_candidates"][0]["resume_pointer"] == "GPD/phases/03-analysis/.continue-here.md"
        assert "source" not in ctx["resume_candidates"][0]

    def test_canonical_bounded_segment_carries_last_result_id_and_hydrates_result(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        from gpd.core.state import default_state_dict

        state = default_state_dict()
        state["continuation"]["bounded_segment"] = {
            "resume_file": "GPD/phases/03-analysis/.continue-here.md",
            "phase": "03",
            "plan": "02",
            "segment_id": "seg-canonical",
            "segment_status": "paused",
            "last_result_id": "result-canonical",
        }
        state["intermediate_results"] = [
            {
                "id": "result-canonical",
                "equation": "R = A + B",
                "description": "Canonical bridge result",
                "phase": "03",
                "depends_on": [],
                "verified": True,
                "verification_records": [],
            }
        ]
        (tmp_path / "GPD" / "state.json").write_text(json.dumps(state), encoding="utf-8")
        resume_path = tmp_path / "GPD" / "phases" / "03-analysis" / ".continue-here.md"
        resume_path.parent.mkdir(parents=True, exist_ok=True)
        resume_path.write_text("resume\n", encoding="utf-8")

        ctx = init_resume(tmp_path)

        assert ctx["active_resume_kind"] == "bounded_segment"
        assert ctx["active_resume_origin"] == "continuation.bounded_segment"
        assert ctx["active_bounded_segment"]["last_result_id"] == "result-canonical"
        assert ctx["resume_candidates"][0]["last_result_id"] == "result-canonical"
        assert ctx["resume_candidates"][0]["last_result"]["id"] == "result-canonical"
        assert ctx["active_resume_result"]["id"] == "result-canonical"
        assert "resume_surface" not in ctx

    def test_normalizes_live_execution_phase_plan_and_checkpoint_reason(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _write_current_execution(
            tmp_path,
            {
                "session_id": "sess-raw",
                "phase": "3",
                "plan": "2",
                "segment_id": "seg-9",
                "segment_status": "waiting_review",
                "resume_file": "GPD/phases/03-analysis/.continue-here.md",
                "checkpoint_reason": "pre-fanout",
                "pre_fanout_review_pending": True,
                "updated_at": "2026-03-10T12:00:00+00:00",
            },
        )

        ctx = init_resume(tmp_path)

        assert ctx["active_bounded_segment"]["phase"] == "03"
        assert ctx["active_bounded_segment"]["plan"] == "02"
        assert ctx["active_bounded_segment"]["checkpoint_reason"] == "pre_fanout"
        candidate = ctx["resume_candidates"][0]
        assert candidate["phase"] == "03"
        assert candidate["plan"] == "02"
        assert candidate["checkpoint_reason"] == "pre_fanout"
        assert candidate["origin"] == "continuation.bounded_segment"
        assert "source" not in candidate

    def test_resume_candidate_carries_pre_fanout_and_skeptical_review_fields(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _write_current_execution(
            tmp_path,
            {
                "session_id": "sess-1",
                "phase": "03",
                "plan": "02",
                "segment_id": "seg-7",
                "segment_status": "waiting_review",
                "resume_file": "GPD/phases/03-analysis/.continue-here.md",
                "checkpoint_reason": "pre_fanout",
                "pre_fanout_review_pending": True,
                "skeptical_requestioning_required": True,
                "skeptical_requestioning_summary": "Proxy passed but benchmark anchor remains unchecked.",
                "weakest_unchecked_anchor": "Ref-01 benchmark figure",
                "disconfirming_observation": "Direct observable misses the literature band.",
                "downstream_locked": True,
                "last_result_label": "Proxy benchmark fit",
                "updated_at": "2026-03-10T12:00:00+00:00",
            },
        )

        ctx = init_resume(tmp_path)

        assert "resume_mode" not in ctx
        assert ctx["execution_pre_fanout_review_pending"] is True
        assert ctx["execution_skeptical_requestioning_required"] is True
        candidate = ctx["resume_candidates"][0]
        assert candidate["checkpoint_reason"] == "pre_fanout"
        assert candidate["pre_fanout_review_pending"] is True
        assert candidate["skeptical_requestioning_required"] is True
        assert candidate["weakest_unchecked_anchor"] == "Ref-01 benchmark figure"
        assert candidate["disconfirming_observation"] == "Direct observable misses the literature band."
        assert candidate["downstream_locked"] is True
        assert candidate["origin"] == "continuation.bounded_segment"
        assert "source" not in candidate

    def test_resume_candidate_keeps_clear_without_unlock_as_bounded_segment_state(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _write_current_execution(
            tmp_path,
            {
                "session_id": "sess-1",
                "phase": "03",
                "plan": "02",
                "segment_id": "seg-8",
                "segment_status": "waiting_review",
                "resume_file": "GPD/phases/03-analysis/.continue-here.md",
                "checkpoint_reason": "pre_fanout",
                "pre_fanout_review_pending": True,
                "pre_fanout_review_cleared": True,
                "downstream_locked": True,
                "updated_at": "2026-03-10T12:00:00+00:00",
            },
        )

        ctx = init_resume(tmp_path)

        assert "resume_mode" not in ctx
        assert ctx["execution_pre_fanout_review_pending"] is True
        assert ctx["execution_downstream_locked"] is True
        assert ctx["active_bounded_segment"]["pre_fanout_review_cleared"] is True
        assert ctx["resume_candidates"][0]["checkpoint_reason"] == "pre_fanout"
        assert ctx["resume_candidates"][0]["pre_fanout_review_cleared"] is True
        assert ctx["resume_candidates"][0]["origin"] == "continuation.bounded_segment"
        assert "source" not in ctx["resume_candidates"][0]

    def test_non_resumable_live_execution_does_not_create_resume_candidate(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _write_current_execution(
            tmp_path,
            {
                "session_id": "sess-1",
                "phase": "03",
                "plan": "02",
                "segment_id": "seg-4",
                "segment_status": "active",
                "current_task": "Running bounded segment",
                "updated_at": "2026-03-10T12:00:00+00:00",
            },
        )

        ctx = init_resume(tmp_path)

        assert "resume_mode" not in ctx
        assert ctx["active_bounded_segment"] is None
        assert ctx["derived_execution_head"]["segment_id"] == "seg-4"
        assert ctx["active_resume_kind"] is None
        _assert_no_resume_compat_aliases(ctx)
        assert "segment_candidates" not in ctx
        assert ctx["resume_candidates"] == []
        assert "active_execution_segment" not in ctx
        assert "resume_surface" not in ctx

    def test_live_execution_workspace_prevents_recent_project_hijack(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        recent_project = tmp_path / "recent-project"
        data_root = tmp_path / "data"
        _setup_project(workspace)
        _write_current_execution(
            workspace,
            {
                "session_id": "sess-local",
                "phase": "03",
                "plan": "02",
                "segment_id": "seg-local",
                "segment_status": "active",
                "updated_at": "2026-03-10T12:00:00+00:00",
            },
        )

        _setup_project(recent_project)
        (recent_project / "GPD" / "PROJECT.md").write_text("# Recent project\n", encoding="utf-8")
        (recent_project / "GPD" / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
        resume_path = recent_project / "GPD" / "phases" / "01-analysis" / ".continue-here.md"
        resume_path.parent.mkdir(parents=True, exist_ok=True)
        resume_path.write_text("resume\n", encoding="utf-8")
        record_recent_project(
            recent_project,
            session_data={
                "last_date": "2026-03-29T12:00:00+00:00",
                "resume_file": "GPD/phases/01-analysis/.continue-here.md",
            },
            store_root=data_root,
        )

        ctx = init_resume(workspace, data_root=data_root)

        assert ctx["project_root"] == workspace.resolve().as_posix()
        assert ctx["project_reentry_mode"] == "current-workspace"
        assert ctx["project_reentry_selected_candidate"]["reason"] == "workspace carries live execution state"
        assert ctx["derived_execution_head"]["segment_id"] == "seg-local"
        assert ctx["active_resume_kind"] is None
        assert ctx["resume_candidates"] == []

    def test_recent_bounded_segment_promotion_revalidates_stale_resume_file(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        continuation_state = {
            "active_bounded_segment": None,
            "active_resume_kind": None,
            "active_resume_origin": None,
            "active_resume_pointer": None,
            "resume_candidates": [],
        }
        reentry_metadata = {
            "project_root": tmp_path.resolve(strict=False).as_posix(),
            "project_root_auto_selected": True,
            "project_reentry_selected_candidate": {
                "source": "recent_project",
                "project_root": tmp_path.resolve(strict=False).as_posix(),
                "resume_target_kind": "bounded_segment",
                "resume_file": "GPD/phases/01-analysis/.continue-here.md",
                "resumable": True,
                "source_segment_id": "seg-stale",
                "recovery_phase": "01",
                "recovery_plan": "01",
            },
        }

        promoted, was_promoted = context_module._promote_auto_selected_recent_bounded_segment(
            continuation_state,
            reentry_metadata=reentry_metadata,
            result_lookup_by_id={},
        )

        assert was_promoted is False
        assert promoted == continuation_state

    def test_handoff_resume_file_no_longer_hydrates_resume_authority(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        from gpd.core.state import default_state_dict

        state = default_state_dict()
        state["session"] = {
            "resume_file": "GPD/phases/03-analysis/.continue-here.md",
            "stopped_at": "2026-03-10T12:00:00+00:00",
            "hostname": "stale-host",
            "platform": "stale-platform",
        }
        resume_path = tmp_path / "GPD" / "phases" / "03-analysis" / ".continue-here.md"
        resume_path.parent.mkdir(parents=True, exist_ok=True)
        resume_path.write_text("resume\n", encoding="utf-8")
        (tmp_path / "GPD" / "state.json").write_text(json.dumps(state), encoding="utf-8")

        ctx = init_resume(tmp_path)

        assert ctx["active_resume_kind"] is None
        assert ctx["active_resume_origin"] is None
        assert ctx["active_resume_pointer"] is None
        assert ctx["machine_change_detected"] is False
        assert ctx["machine_change_notice"] is None
        assert ctx["continuity_handoff_file"] is None
        assert ctx["recorded_continuity_handoff_file"] is None
        assert ctx["session_hostname"] is None
        assert ctx["session_platform"] is None
        assert ctx["session_last_date"] is None
        assert ctx["session_stopped_at"] is None
        assert ctx["resume_candidates"] == []
        assert "resume_surface" not in ctx

    def test_init_resume_does_not_recover_intent_during_read_only_discovery(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        layout = _write_state_intent_recovery_files(tmp_path)

        before_state_json = layout.state_json.read_text(encoding="utf-8")
        before_state_intent = layout.state_intent.read_text(encoding="utf-8")
        before_json_tmp = (layout.gpd / ".state-json-tmp").read_text(encoding="utf-8")
        before_md_tmp = (layout.gpd / ".state-md-tmp").read_text(encoding="utf-8")

        ctx = init_resume(tmp_path)

        assert ctx["state_exists"] is True
        assert layout.state_json.read_text(encoding="utf-8") == before_state_json
        assert layout.state_intent.read_text(encoding="utf-8") == before_state_intent
        assert (layout.gpd / ".state-json-tmp").read_text(encoding="utf-8") == before_json_tmp
        assert (layout.gpd / ".state-md-tmp").read_text(encoding="utf-8") == before_md_tmp

    def test_state_md_fallback_projects_session_continuity_into_resume_authority(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        from gpd.core.state import default_state_dict, generate_state_markdown

        state = default_state_dict()
        state["continuation"]["handoff"]["resume_file"] = "GPD/phases/03-analysis/.continue-here.md"
        state["continuation"]["handoff"]["stopped_at"] = "2026-03-10T12:00:00+00:00"
        state["continuation"]["machine"]["hostname"] = "stale-host"
        state["continuation"]["machine"]["platform"] = "stale-platform"
        resume_path = tmp_path / "GPD" / "phases" / "03-analysis" / ".continue-here.md"
        resume_path.parent.mkdir(parents=True, exist_ok=True)
        resume_path.write_text("resume\n", encoding="utf-8")
        (tmp_path / "GPD" / "STATE.md").write_text(generate_state_markdown(state), encoding="utf-8")

        ctx = init_resume(tmp_path)

        assert ctx["continuity_handoff_file"] == "GPD/phases/03-analysis/.continue-here.md"
        assert ctx["recorded_continuity_handoff_file"] == "GPD/phases/03-analysis/.continue-here.md"
        assert ctx["active_resume_pointer"] == "GPD/phases/03-analysis/.continue-here.md"
        assert ctx["active_resume_kind"] == "continuity_handoff"
        assert ctx["active_resume_origin"] == "continuation.handoff"

    def test_init_resume_propagates_unexpected_continuation_errors(self, tmp_path: Path, monkeypatch) -> None:
        _setup_project(tmp_path)

        def _boom(*_args, **_kwargs):
            raise RuntimeError("canonical resolution exploded")

        monkeypatch.setattr(context_module, "resolve_continuation", _boom)

        with pytest.raises(RuntimeError, match="canonical resolution exploded"):
            init_resume(tmp_path)


class TestInitVerifyWork:
    def test_basic(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        phase_dir = _create_phase_dir(tmp_path, "01-setup")
        (phase_dir / "01-VERIFICATION.md").write_text("verified", encoding="utf-8")

        ctx = init_verify_work(tmp_path, "1")
        assert ctx["phase_found"] is True
        assert ctx["has_verification"] is True
        assert ctx["project_root"] == tmp_path.resolve(strict=False).as_posix()
        assert ctx["phase_dir_abs"].endswith("/GPD/phases/01-setup")

    def test_resolves_ancestor_project_root_from_nested_workspace(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        phase_dir = _create_phase_dir(tmp_path, "01-setup")
        (phase_dir / "01-VERIFICATION.md").write_text("verified", encoding="utf-8")
        nested = tmp_path / "workspace" / "notes"
        nested.mkdir(parents=True)

        ctx = init_verify_work(nested, "1")

        assert ctx["phase_found"] is True
        assert ctx["phase_number"] == "01"
        assert ctx["has_verification"] is True
        assert ctx["project_root"] == tmp_path.resolve(strict=False).as_posix()
        assert ctx["phase_dir_abs"].endswith("/GPD/phases/01-setup")

    def test_stage_session_router_returns_bootstrap_only_payload(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "01-setup")
        _write_project_contract_state(tmp_path)

        ctx = init_verify_work(tmp_path, "1", stage="session_router")

        assert ctx["phase_found"] is True
        assert ctx["project_root"] == tmp_path.resolve(strict=False).as_posix()
        assert ctx["phase_dir_abs"].endswith("/GPD/phases/01-setup")
        assert ctx["project_contract_gate"]["visible"] is True
        assert ctx["phase_proof_review_status"]["scope"] == "phase"
        assert ctx["phase_proof_review_status"]["state"] == "not_reviewed"
        assert ctx["active_verification_sessions"] == []
        assert "verification_report_status" not in ctx
        assert ctx["verification_report_status_payload"]["routing_status"] == "missing"
        assert ctx["staged_loading"]["stage_id"] == "session_router"
        assert ctx["staged_loading"]["checkpoints"] == [
            "active session check completed",
            "review preflight completed",
            "contract gate remains visible",
        ]
        assert "project_contract" not in ctx
        assert "active_reference_context" not in ctx
        assert "reference_artifacts_content" not in ctx
        assert "convention_lock" not in ctx

    def test_stage_session_router_allows_missing_phase_for_active_session_routing(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _write_project_contract_state(tmp_path)

        ctx = init_verify_work(tmp_path, "", stage="session_router")

        assert ctx["phase_found"] is False
        assert "phase_dir" not in ctx
        assert ctx["phase_dir_abs"] is None
        assert "phase_number" not in ctx
        assert ctx["project_root"] == tmp_path.resolve(strict=False).as_posix()
        assert ctx["project_contract_gate"]["visible"] is True
        assert ctx["active_verification_sessions"] == []
        assert ctx["staged_loading"]["stage_id"] == "session_router"

    def test_stage_session_router_surfaces_active_verification_sessions(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        phase_dir = _create_phase_dir(tmp_path, "01-setup")
        _write_project_contract_state(tmp_path)
        (phase_dir / "01-VERIFICATION.md").write_text(
            "---\n"
            "status: gaps_found\n"
            "session_status: validating\n"
            'score: "2/6 checks verified"\n'
            "---\n\n"
            "# Verification\n",
            encoding="utf-8",
        )

        ctx = init_verify_work(tmp_path, "", stage="session_router")

        assert ctx["active_verification_sessions"] == [
            {
                "path": (phase_dir / "01-VERIFICATION.md").as_posix(),
                "phase": "01",
                "status": "gaps_found",
                "routing_status": "gaps_found",
                "session_status": "validating",
                "score": "2/6 checks verified",
                "errors": [],
            }
        ]

    def test_staged_verify_work_init_does_not_bootstrap_phase_proof_review_manifest(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        phase_dir = _create_phase_dir(tmp_path, "01-setup")
        (phase_dir / "01-SUMMARY.md").write_text("# Summary\n", encoding="utf-8")
        (phase_dir / "01-VERIFICATION.md").write_text("# Verification\n", encoding="utf-8")

        ctx = init_verify_work(tmp_path, "1", stage="session_router")

        assert ctx["phase_proof_review_status"]["state"] == "fresh"
        assert ctx["phase_proof_review_status"]["manifest_bootstrapped"] is False
        assert not (phase_dir / "01-PROOF-REVIEW-MANIFEST.json").exists()

    def test_stage_phase_bootstrap_surfaces_proof_redteam_finalizer_bridge(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        phase_dir = _create_phase_dir(tmp_path, "01-setup")
        _write_project_contract_state(tmp_path)

        ctx = init_verify_work(tmp_path, "1", stage="phase_bootstrap")

        bridge = ctx["proof_redteam_finalizer_bridge"]
        assert ctx["staged_loading"]["stage_id"] == "phase_bootstrap"
        assert "proof_redteam_finalizer_bridge" in ctx["staged_loading"]["required_init_fields"]
        assert bridge["command_name"] == "gpd proof-redteam finalize"
        assert bridge["supported_statuses"] == ["passed"]
        assert bridge["expected_proof_redteam_path"] == (phase_dir / "01-PROOF-REDTEAM.md").as_posix()
        assert "gpd proof-redteam finalize" in bridge["writer_command_template"]

    def test_missing_phase_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValidationError, match="phase is required"):
            init_verify_work(tmp_path, "")

    def test_stage_inventory_build_surfaces_reference_and_convention_context(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "01-setup")
        _write_stat_mech_project(tmp_path)
        _write_bundle_ready_contract_state(tmp_path)
        _write_structured_state_payload(tmp_path)

        ctx = init_verify_work(tmp_path, "1", stage="inventory_build")

        assert ctx["staged_loading"]["stage_id"] == "inventory_build"
        assert "project_contract" not in ctx
        assert ctx["project_contract_gate"]["visible"] is True
        assert ctx["project_contract_load_info"]["status"] == "blocked_integrity"
        assert "active_verification_sessions" not in ctx
        assert "verification_report_status_payload" not in ctx
        assert "verification_report_path" not in ctx
        assert ctx["phase_dir_abs"].endswith("GPD/phases/01-setup")
        assert "active_reference_context" not in ctx
        assert "active_reference_count" not in ctx
        assert ctx["active_references"][0]["id"] == "ref-benchmark"
        assert ctx["effective_reference_intake"]["must_read_refs"] == ["ref-benchmark"]
        assert "stat-mech-simulation" in ctx["selected_protocol_bundle_ids"]
        assert ctx["protocol_bundle_count"] == 1
        assert ctx["convention_lock"]["metric_signature"] == "(-,+,+,+)"
        assert ctx["derived_convention_lock"]["metric_signature"] == "(-,+,+,+)"
        assert "reference_artifacts_content" not in ctx

    def test_stage_inventory_build_surfaces_schema_bridge_without_loading_schema_authorities(
        self, tmp_path: Path
    ) -> None:
        _setup_project(tmp_path)
        phase_dir = _create_phase_dir(tmp_path, "01-setup")
        (phase_dir / "01-PLAN.md").write_text("# Plan\n", encoding="utf-8")
        _write_stat_mech_project(tmp_path)
        _write_bundle_ready_contract_state(tmp_path)
        _write_structured_state_payload(tmp_path)

        ctx = init_verify_work(tmp_path, "1", stage="inventory_build")
        bridge = ctx["verification_report_skeleton_bridge"]
        finalizer_bridge = ctx["verification_report_finalizer_bridge"]

        assert ctx["staged_loading"]["stage_id"] == "inventory_build"
        assert "verification_report_skeleton_bridge" in ctx["staged_loading"]["required_init_fields"]
        assert "verification_report_finalizer_bridge" in ctx["staged_loading"]["required_init_fields"]
        assert bridge["command_name"] == "gpd verification-report skeleton"
        assert bridge["skeleton_command"] == (
            f"gpd verification-report skeleton {(phase_dir / '01-PLAN.md').as_posix()} --format markdown"
        )
        assert bridge["writer_command"] == (
            f"gpd verification-report skeleton {(phase_dir / '01-PLAN.md').as_posix()} "
            f"--write --output {(phase_dir / '01-VERIFICATION.md').as_posix()} --force "
            "--body-file BODY.md --validate contract"
        )
        assert bridge["supported_statuses"] == ["gaps_found"]
        assert bridge["gap_report_skeleton_command"] == bridge["skeleton_command"]
        assert bridge["gap_report_writer_command"] == bridge["writer_command"]
        assert "gap-report-only" in bridge["status_policy"]
        body_contract = bridge["body_contract"]
        assert "`BODY.md` is body-only Markdown" in body_contract
        assert "one fenced executed `python`/`bash` block" in body_contract
        assert "adjacent `**Output:**` plus fenced `output` block" in body_contract
        assert "following `PASS`/`FAIL`/`INCONCLUSIVE` verdict line" in body_contract
        assert "prose bullets alone are invalid" in body_contract
        schema_sources = bridge["schema_sources"]
        assert [source["name"] for source in schema_sources] == [
            "verifier_agent",
            "verification_report_template",
            "contract_results_schema",
        ]
        assert [source["runtime_ref"] for source in schema_sources] == [
            "{GPD_AGENTS_DIR}/gpd-verifier.md",
            "{GPD_INSTALL_DIR}/templates/verification-report.md",
            "{GPD_INSTALL_DIR}/templates/contract-results-schema.md",
        ]
        assert all(Path(source["source_path"]).is_file() for source in schema_sources)
        assert bridge["expected_target_plan_path"] == (phase_dir / "01-PLAN.md").as_posix()
        assert bridge["expected_verification_path"] == (phase_dir / "01-VERIFICATION.md").as_posix()
        assert finalizer_bridge["command_name"] == "gpd verification-report finalize"
        assert finalizer_bridge["writer_command_template"] == (
            f"gpd verification-report finalize {(phase_dir / '01-PLAN.md').as_posix()} --patch PATCH.json "
            f"--body-file BODY.md --output {(phase_dir / '01-VERIFICATION.md').as_posix()} "
            "--validate contract --force"
        )
        assert "passed" in finalizer_bridge["supported_statuses"]
        assert bridge["validation_command"] == (
            f"gpd validate verification-contract {(phase_dir / '01-VERIFICATION.md').as_posix()}"
        )
        assert "run writer_command" in bridge["fallback_rule"]
        assert "body-only evidence" in bridge["fallback_rule"]
        assert "satisfies body_contract" in bridge["fallback_rule"]
        assert "Use skeleton_command as preview context only" in bridge["fallback_rule"]
        assert "do not hand-author or reflow VERIFICATION.md frontmatter" in bridge["fallback_rule"]
        assert "use the generated frontmatter as the starting YAML" not in bridge["fallback_rule"]

        manifest = load_workflow_stage_manifest("verify-work")
        inventory_build = manifest.stage("inventory_build")
        assert inventory_build.loaded_authorities == ("workflows/verify-work/inventory-build.md",)
        assert {
            conditional.when: conditional.authorities for conditional in inventory_build.conditional_authorities
        } == {"full_independence_policy_check": ("references/verification/meta/verification-independence.md",)}
        assert "references/verification/meta/verification-independence.md" in inventory_build.must_not_eager_load
        assert "templates/verification-report.md" not in inventory_build.loaded_authorities
        assert "templates/contract-results-schema.md" not in inventory_build.loaded_authorities
        assert "templates/verification-report.md" in inventory_build.must_not_eager_load
        assert "templates/contract-results-schema.md" in inventory_build.must_not_eager_load
        assert "verification_report_skeleton_bridge" not in init_verify_work(tmp_path, "1")

    def test_stage_inventory_build_fails_when_schema_bridge_phase_is_unresolved(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _write_stat_mech_project(tmp_path)
        _write_bundle_ready_contract_state(tmp_path)
        _write_structured_state_payload(tmp_path)

        with pytest.raises(ValueError, match="requires a resolved phase"):
            init_verify_work(tmp_path, "99", stage="inventory_build")

    def test_stage_inventory_build_uses_reference_metadata_without_artifact_content(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "01-setup")
        _write_stat_mech_project(tmp_path)
        _write_bundle_ready_contract_state(tmp_path)
        _write_structured_state_payload(tmp_path)
        calls: list[bool] = []

        def _record_artifact_payload(
            _cwd: Path,
            *,
            include_content: bool = True,
        ) -> dict[str, object]:
            calls.append(include_content)
            return {
                "literature_review_files": [],
                "literature_review_count": 0,
                "research_map_reference_files": ["GPD/research-map/REFERENCES.md"],
                "research_map_reference_count": 1,
                "knowledge_doc_files": [],
                "knowledge_doc_count": 0,
                "stable_knowledge_doc_files": [],
                "stable_knowledge_doc_count": 0,
                "knowledge_doc_status_counts": {},
                "reference_artifact_files": ["GPD/research-map/REFERENCES.md"],
                "reference_artifacts_content": "should not surface" if include_content else None,
            }

        monkeypatch.setattr(context_module, "_reference_artifact_payload", _record_artifact_payload)

        ctx = init_verify_work(tmp_path, "1", stage="inventory_build")

        assert ctx["staged_loading"]["stage_id"] == "inventory_build"
        assert "research_map_reference_files" not in ctx
        assert "reference_artifacts_content" not in ctx
        assert calls == [False]

    def test_stage_interactive_validation_defers_reference_artifact_content(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "01-setup")
        _write_project_contract_state(tmp_path)

        literature_dir = tmp_path / "GPD" / "literature"
        literature_dir.mkdir(parents=True)
        (literature_dir / "benchmark-notes.md").write_text("# Benchmark\nReference details.\n", encoding="utf-8")

        ctx = init_verify_work(tmp_path, "1", stage="interactive_validation")

        assert ctx["staged_loading"]["stage_id"] == "interactive_validation"
        assert ctx["reference_artifact_files"]
        assert "reference_artifacts_content" not in ctx

    def test_stage_gap_repair_surfaces_reference_artifact_handles(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "01-setup")
        _write_project_contract_state(tmp_path)

        literature_dir = tmp_path / "GPD" / "literature"
        literature_dir.mkdir(parents=True)
        (literature_dir / "benchmark-notes.md").write_text("# Benchmark\nReference details.\n", encoding="utf-8")

        ctx = init_verify_work(tmp_path, "1", stage="gap_repair")

        assert ctx["staged_loading"]["stage_id"] == "gap_repair"
        assert ctx["reference_artifact_files"]
        assert "GPD/literature/benchmark-notes.md" in ctx["reference_artifact_files"]
        assert "reference_artifacts_content" not in ctx

    def test_verify_work_surfaces_derived_stable_knowledge_docs(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "01-setup")
        _write_knowledge_doc(tmp_path, status="stable")
        _write_knowledge_doc(
            tmp_path,
            knowledge_id="K-work-in-progress",
            status="draft",
            body="Draft knowledge body.\n",
        )

        ctx = init_verify_work(tmp_path, "1")

        assert ctx["knowledge_doc_count"] == 2
        assert ctx["derived_knowledge_doc_count"] == 1
        assert ctx["derived_knowledge_docs"][0]["status"] == "stable"
        assert ctx["knowledge_doc_warnings"] == []
        assert "GPD/knowledge/K-renormalization-group-fixed-points.md" in ctx["reference_artifact_files"]
        assert "GPD/knowledge/K-work-in-progress.md" not in ctx["reference_artifact_files"]
        assert "Draft knowledge body." not in ctx["reference_artifacts_content"]
        assert "non-stable knowledge doc(s) remain inventory-visible only" in ctx["active_reference_context"]

    def test_exposes_active_reference_context(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "01-setup")
        _write_project_contract_state(tmp_path)

        ctx = init_verify_work(tmp_path, "1")

        assert ctx["project_contract"]["references"][0]["role"] == "benchmark"
        assert "## Active Reference Registry" in ctx["active_reference_context"]

    def test_exposes_selected_protocol_bundle_ids(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "01-setup")
        _write_stat_mech_project(tmp_path)
        _write_bundle_ready_contract_state(tmp_path)

        ctx = init_verify_work(tmp_path, "1")

        assert "stat-mech-simulation" in ctx["selected_protocol_bundle_ids"]
        assert "Verifier extensions:" in ctx["protocol_bundle_context"]

    def test_surfaces_convention_lock_fields(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "01-setup")
        _write_structured_state_payload(tmp_path)

        ctx = init_verify_work(tmp_path, "1")

        assert ctx["state_load_source"] == "state.json"
        assert ctx["convention_lock"]["metric_signature"] == "(-,+,+,+)"
        assert ctx["convention_lock"]["fourier_convention"] == "physics"
        assert ctx["convention_lock_count"] >= ctx["derived_convention_lock_count"] >= 1
        assert ctx["derived_convention_lock"]["metric_signature"] == "(-,+,+,+)"

    def test_bootstraps_phase_proof_review_manifest(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        phase_dir = _create_phase_dir(tmp_path, "01-setup")
        (phase_dir / "01-SUMMARY.md").write_text("# Summary\n", encoding="utf-8")
        (phase_dir / "01-VERIFICATION.md").write_text("# Verification\n", encoding="utf-8")

        ctx = init_verify_work(tmp_path, "1")

        assert ctx["phase_proof_review_status"]["state"] == "fresh"
        assert ctx["phase_proof_review_status"]["manifest_bootstrapped"] is True
        assert (tmp_path / "GPD" / "phases" / "01-setup" / "01-PROOF-REVIEW-MANIFEST.json").exists()

    def test_reports_stale_phase_proof_review_after_phase_edit(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        phase_dir = _create_phase_dir(tmp_path, "01-setup")
        summary_path = phase_dir / "01-SUMMARY.md"
        summary_path.write_text("# Summary\n", encoding="utf-8")
        (phase_dir / "01-VERIFICATION.md").write_text("# Verification\n", encoding="utf-8")

        initial = init_verify_work(tmp_path, "1")
        assert initial["phase_proof_review_status"]["state"] == "fresh"

        summary_path.write_text("# Summary\n\nUpdated derivation.\n", encoding="utf-8")

        ctx = init_verify_work(tmp_path, "1")

        assert ctx["phase_proof_review_status"]["state"] == "stale"
        assert ctx["phase_proof_review_status"]["can_rely_on_prior_review"] is False

    def test_exposes_manuscript_proof_review_status(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "01-setup")
        _write_manuscript_proof_review_artifacts(tmp_path)

        ctx = init_verify_work(tmp_path, "1")

        status = ctx["derived_manuscript_proof_review_status"]
        assert status["state"] == "fresh"
        assert status["can_rely_on_prior_review"] is True
        assert status["manifest_bootstrapped"] is True
        assert status["manifest_path"] == "paper/PROOF-REVIEW-MANIFEST.json"
        assert status["anchor_artifact"] == "GPD/review/PROOF-REDTEAM.md"
        assert status["watched_file_count"] >= 3
        assert status["changed_file_count"] == 0

    def test_reports_stale_manuscript_proof_review_after_bibliography_edit(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "01-setup")
        bibliography_path = _write_manuscript_proof_review_artifacts(tmp_path)

        initial = init_verify_work(tmp_path, "1")
        assert initial["derived_manuscript_proof_review_status"]["state"] == "fresh"

        bibliography_path.write_text("@article{demo,title={Updated Demo}}\n", encoding="utf-8")

        ctx = init_verify_work(tmp_path, "1")

        status = ctx["derived_manuscript_proof_review_status"]
        assert status["state"] == "stale"
        assert status["can_rely_on_prior_review"] is False
        assert status["changed_file_count"] >= 1
        assert "paper/references.bib" in status["changed_files"]

    def test_reports_stale_manuscript_proof_review_after_external_proof_edit(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "01-setup")
        _write_manuscript_proof_review_artifacts_with_proof_path(
            tmp_path,
            proof_artifact_path="proofs/external-proof.tex",
        )
        external_proof_path = tmp_path / "proofs" / "external-proof.tex"

        initial = init_verify_work(tmp_path, "1")
        assert initial["derived_manuscript_proof_review_status"]["state"] == "fresh"
        assert (
            external_proof_path.as_posix().removeprefix(f"{tmp_path.as_posix()}/")
            in initial["derived_manuscript_proof_review_status"]["watched_files"]
        )

        external_proof_path.write_text(
            "\\documentclass{article}\n\\begin{document}\nRevised external proof.\n\\end{document}\n",
            encoding="utf-8",
        )

        ctx = init_verify_work(tmp_path, "1")

        status = ctx["derived_manuscript_proof_review_status"]
        assert status["state"] == "stale"
        assert status["can_rely_on_prior_review"] is False
        assert external_proof_path.as_posix().removeprefix(f"{tmp_path.as_posix()}/") in status["changed_files"]


class TestInitTodos:
    def test_empty_todos(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        ctx = init_todos(tmp_path)
        assert ctx["todo_count"] == 0
        assert ctx["todos"] == []
        assert ctx["project_exists"] is False
        assert ctx["workspace_root"] == tmp_path.as_posix()
        assert ctx["project_root"] == tmp_path.as_posix()

    def test_resolves_ancestor_project_root_from_nested_workspace(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        (tmp_path / "GPD" / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
        (tmp_path / "GPD" / "STATE.md").write_text("# State\n", encoding="utf-8")
        pending = tmp_path / "GPD" / "todos" / "pending"
        pending.mkdir(parents=True)
        (pending / "root-todo.md").write_text("title: Root todo\narea: theory\n", encoding="utf-8")
        nested = tmp_path / "workspace" / "notes"
        nested.mkdir(parents=True)

        ctx = init_todos(nested)

        assert ctx["project_exists"] is True
        assert ctx["workspace_root"] == nested.as_posix()
        assert ctx["project_root"] == tmp_path.as_posix()
        assert ctx["todo_count"] == 1
        assert ctx["todos"][0]["path"] == "GPD/todos/pending/root-todo.md"
        assert not (nested / "GPD").exists()

    def test_finds_todos(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        pending = tmp_path / "GPD" / "todos" / "pending"
        pending.mkdir(parents=True)
        (pending / "check-convergence.md").write_text(
            'title: "Check convergence"\narea: numerical\ncreated: 2026-03-01\n\n'
            "The body may mention area: theory and created: 2024-01-01, but those lines must be ignored.",
            encoding="utf-8",
        )

        ctx = init_todos(tmp_path)
        assert ctx["todo_count"] == 1
        assert ctx["todos"][0]["title"] == "Check convergence"
        assert ctx["todos"][0]["area"] == "numerical"
        assert ctx["todos"][0]["created"] == "2026-03-01"

    def test_body_metadata_like_lines_do_not_override_missing_header_fields(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        pending = tmp_path / "GPD" / "todos" / "pending"
        pending.mkdir(parents=True)
        (pending / "check-convergence.md").write_text(
            'title: "Check convergence"\n\n'
            "The body may mention area: numerical and created: 2026-03-01.\n"
            "Those lines must not be treated as todo metadata.",
            encoding="utf-8",
        )

        ctx = init_todos(tmp_path)
        assert ctx["todo_count"] == 1
        assert ctx["todos"][0]["title"] == "Check convergence"
        assert ctx["todos"][0]["area"] == "general"
        assert ctx["todos"][0]["created"] == "unknown"

    def test_skips_todo_with_malformed_yaml_frontmatter(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        pending = tmp_path / "GPD" / "todos" / "pending"
        pending.mkdir(parents=True)
        (pending / "good.md").write_text(
            "---\ntitle: Good todo\narea: numerical\ncreated: 2026-03-01\n---\nBody\n",
            encoding="utf-8",
        )
        (pending / "bad.md").write_text(
            "---\ntitle: Broken todo\narea: [unterminated\nBody without a closing delimiter\n",
            encoding="utf-8",
        )

        ctx = init_todos(tmp_path)

        assert ctx["todo_count"] == 1
        assert [todo["file"] for todo in ctx["todos"]] == ["good.md"]

    def test_preserves_yaml_created_date_scalar(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        pending = tmp_path / "GPD" / "todos" / "pending"
        pending.mkdir(parents=True)
        (pending / "check-convergence.md").write_text(
            "---\ntitle: Check convergence\narea: numerical\ncreated: 2026-03-01\n---\nBody\n",
            encoding="utf-8",
        )

        ctx = init_todos(tmp_path)

        assert ctx["todo_count"] == 1
        assert ctx["todos"][0]["created"] == "2026-03-01"

    def test_todo_body_starting_with_horizontal_rule_is_not_skipped(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        pending = tmp_path / "GPD" / "todos" / "pending"
        pending.mkdir(parents=True)
        (pending / "note.md").write_text(
            "---\nBody starts with a rule, not metadata.\n",
            encoding="utf-8",
        )

        ctx = init_todos(tmp_path)

        assert ctx["todo_count"] == 1
        assert ctx["todos"][0]["file"] == "note.md"
        assert ctx["todos"][0]["title"] == "Untitled"
        assert ctx["todos"][0]["area"] == "general"
        assert ctx["todos"][0]["created"] == "unknown"

    def test_area_filter(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        pending = tmp_path / "GPD" / "todos" / "pending"
        pending.mkdir(parents=True)
        (pending / "a.md").write_text("title: A\narea: theory", encoding="utf-8")
        (pending / "b.md").write_text("title: B\narea: numerical", encoding="utf-8")

        ctx = init_todos(tmp_path, area="theory")
        assert ctx["todo_count"] == 1
        assert ctx["todos"][0]["title"] == "A"


class TestInitMilestoneOp:
    def test_empty_project(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        ctx = init_milestone_op(tmp_path)
        assert ctx["phase_count"] == 0
        assert ctx["completed_phases"] == 0
        assert ctx["all_phases_complete"] is False

    def test_counts_roadmap_phases_and_disk_completion(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_roadmap(
            tmp_path,
            """\
            ## Milestone v1.0: Test

            ### Phase 1: Setup
            **Goal:** setup

            ### Phase 2: Build
            **Goal:** build
            """,
        )
        p1 = _create_phase_dir(tmp_path, "01-setup")
        (p1 / "a-PLAN.md").write_text("plan", encoding="utf-8")
        (p1 / "a-SUMMARY.md").write_text("summary", encoding="utf-8")

        ctx = init_milestone_op(tmp_path)

        assert ctx["phase_count"] == 2
        assert ctx["completed_phases"] == 1
        assert ctx["all_phases_complete"] is False

    def test_resolves_ancestor_project_root_from_nested_workspace(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_roadmap(
            tmp_path,
            """\
            ## Milestone v1.0: Test

            ### Phase 1: Setup
            **Goal:** setup
            """,
        )
        (tmp_path / "GPD" / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
        p1 = _create_phase_dir(tmp_path, "01-setup")
        (p1 / "a-PLAN.md").write_text("plan", encoding="utf-8")
        (p1 / "a-SUMMARY.md").write_text("summary", encoding="utf-8")
        nested = tmp_path / "workspace" / "notes"
        nested.mkdir(parents=True)

        ctx = init_milestone_op(nested)

        assert ctx["init_root_policy"] == "project_scoped"
        assert ctx["project_exists"] is True
        assert ctx["roadmap_exists"] is True
        assert ctx["phase_count"] == 1
        assert ctx["completed_phases"] == 1
        assert ctx["all_phases_complete"] is True
        assert not (nested / "GPD").exists()

    def test_counts_phases(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        # Complete phase
        p1 = _create_phase_dir(tmp_path, "01-setup")
        (p1 / "a-PLAN.md").write_text("plan", encoding="utf-8")
        (p1 / "a-SUMMARY.md").write_text("summary", encoding="utf-8")
        # Incomplete phase
        p2 = _create_phase_dir(tmp_path, "02-analysis")
        (p2 / "b-PLAN.md").write_text("plan", encoding="utf-8")

        ctx = init_milestone_op(tmp_path)
        assert ctx["phase_count"] == 2
        assert ctx["completed_phases"] == 1
        assert ctx["all_phases_complete"] is False

    def test_archive_inventory_counts_top_level_files(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        archive_dir = tmp_path / "GPD" / "milestones"
        archive_dir.mkdir(parents=True, exist_ok=True)
        for name in ("v1.0-ROADMAP.md", "v1.0-REQUIREMENTS.md", "v1.0-MILESTONE-AUDIT.md"):
            (archive_dir / name).write_text("archive", encoding="utf-8")

        ctx = init_milestone_op(tmp_path)

        assert ctx["archive_count"] == 3
        assert ctx["archived_milestones"] == [
            "v1.0-MILESTONE-AUDIT.md",
            "v1.0-REQUIREMENTS.md",
            "v1.0-ROADMAP.md",
        ]

    def test_surfaces_project_contract_gate_and_active_reference_context(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _write_project_contract_state(tmp_path)

        ctx = init_milestone_op(tmp_path)

        assert ctx["project_contract"] is not None
        assert ctx["project_contract"]["scope"]["question"] == "What benchmark must the project recover?"
        assert ctx["project_contract_load_info"]["status"] == "loaded"
        assert ctx["project_contract_validation"] is not None
        assert ctx["project_contract_gate"]["visible"] is True
        assert ctx["project_contract_gate"]["status"] == ctx["project_contract_load_info"]["status"]
        assert ctx["project_contract_gate"]["authoritative"] is True
        assert ctx["project_contract_validation"]["valid"] is True
        assert "[ref-benchmark]" in ctx["active_reference_context"]


class TestInitMapResearch:
    def test_no_maps(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        ctx = init_map_research(tmp_path)
        assert ctx["has_maps"] is False
        assert ctx["existing_maps"] == []
        assert ctx["map_focus"] == ""
        assert ctx["map_focus_provided"] is False

    def test_resolves_ancestor_project_root_from_nested_workspace(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        nested = tmp_path / "workspace" / "notes"
        nested.mkdir(parents=True)
        map_dir = tmp_path / "GPD" / "research-map"
        map_dir.mkdir()
        (map_dir / "theory.md").write_text("# Theory Map", encoding="utf-8")

        ctx = init_map_research(nested)

        assert ctx["init_root_policy"] == "project_scoped"
        assert ctx["planning_exists"] is True
        assert ctx["research_map_dir_exists"] is True
        assert ctx["has_maps"] is True
        assert "theory.md" in ctx["existing_maps"]

    def test_existing_maps(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        map_dir = tmp_path / "GPD" / "research-map"
        map_dir.mkdir()
        (map_dir / "theory.md").write_text("# Theory Map", encoding="utf-8")

        ctx = init_map_research(tmp_path)
        assert ctx["has_maps"] is True
        assert "theory.md" in ctx["existing_maps"]

    def test_surfaces_project_contract_for_reference_mapping(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _write_project_contract_state(tmp_path)

        ctx = init_map_research(tmp_path)

        assert ctx["project_contract"]["scope"]["question"] == "What benchmark must the project recover?"
        assert "ref-benchmark" in ctx["active_reference_context"]

    def test_surfaces_artifact_derived_reference_context_without_contract(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _write_literature_review_anchor_file(tmp_path)
        _write_research_map_anchor_files(tmp_path)

        ctx = init_map_research(tmp_path)

        assert ctx["project_contract"] is None
        assert ctx["derived_active_reference_count"] >= 2
        assert "Benchmark Ref 2024" in ctx["active_reference_context"]
        assert (
            "GPD/phases/01-test-phase/01-SUMMARY.md" in ctx["effective_reference_intake"]["must_include_prior_outputs"]
        )

    def test_stage_bootstrap_returns_only_manifest_required_fields(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_project(tmp_path)
        _write_project_contract_state(tmp_path)
        install_fake_stage_manifest(
            monkeypatch,
            workflow_id="map-research",
            stages={
                "bootstrap": [
                    "mapper_model",
                    "commit_docs",
                    "research_mode",
                    "has_maps",
                    "project_contract",
                    "project_contract_gate",
                    "project_contract_load_info",
                    "project_contract_validation",
                    "active_reference_context",
                    "reference_artifacts_content",
                ]
            },
        )

        ctx = init_map_research(tmp_path, stage="bootstrap")

        assert ctx["staged_loading"]["workflow_id"] == "map-research"
        assert ctx["staged_loading"]["stage_id"] == "bootstrap"
        assert set(ctx) == {
            "mapper_model",
            "commit_docs",
            "research_mode",
            "has_maps",
            "project_contract",
            "project_contract_gate",
            "project_contract_load_info",
            "project_contract_validation",
            "active_reference_context",
            "reference_artifacts_content",
            "staged_loading",
        }

    def test_stage_bootstrap_surfaces_focus_argument(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)

        ctx = init_map_research(tmp_path, focus="Hamiltonian sector", stage="map_bootstrap")

        assert ctx["map_focus"] == "Hamiltonian sector"
        assert ctx["map_focus_provided"] is True
        assert ctx["staged_loading"]["stage_id"] == "map_bootstrap"

    def test_stage_map_bootstrap_defers_full_reference_context(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_project(tmp_path)
        _write_project_contract_state(tmp_path)
        _write_literature_review_anchor_file(tmp_path)
        monkeypatch.setattr(
            context_module,
            "_build_reference_runtime_context",
            stage_ctx.fail_if_context_builder_runs("_build_reference_runtime_context"),
        )

        ctx = init_map_research(tmp_path, stage="map_bootstrap")

        assert ctx["staged_loading"]["stage_id"] == "map_bootstrap"
        assert "active_reference_context" not in ctx
        assert "reference_artifacts_content" not in ctx
        assert ctx["project_contract_gate"]["visible"] is True


class TestInitLiteratureReview:
    def test_resolves_ancestor_project_root_from_nested_workspace(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _write_project_contract_state(tmp_path)
        _write_literature_review_anchor_file(tmp_path)
        (tmp_path / "GPD" / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
        (tmp_path / "GPD" / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
        nested = tmp_path / "workspace" / "notes"
        nested.mkdir(parents=True)

        ctx = init_literature_review(nested, topic="Curvature flow bounds")

        assert ctx["topic"] == "Curvature flow bounds"
        assert ctx["slug"] == "curvature-flow-bounds"
        assert ctx["project_exists"] is True
        assert ctx["roadmap_exists"] is True
        assert ctx["state_exists"] is True
        assert ctx["literature_review_files"] == ["GPD/literature/benchmark-REVIEW.md"]
        assert "Benchmark Ref 2024" in ctx["active_reference_context"]

    def test_stage_loads_review_bootstrap_payload(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _setup_project(tmp_path)
        _write_project_contract_state(tmp_path)
        _write_literature_review_anchor_file(tmp_path)
        install_fake_stage_manifest(
            monkeypatch,
            workflow_id="literature-review",
            stages={
                "bootstrap": [
                    "topic",
                    "slug",
                    "commit_docs",
                    "state_exists",
                    "project_exists",
                    "project_contract",
                    "project_contract_gate",
                    "project_contract_load_info",
                    "project_contract_validation",
                    "active_reference_context",
                    "reference_artifacts_content",
                ]
            },
        )

        ctx = init_literature_review(tmp_path, topic="Curvature flow bounds", stage="bootstrap")

        assert ctx["topic"] == "Curvature flow bounds"
        assert ctx["slug"] == "curvature-flow-bounds"
        assert ctx["staged_loading"]["workflow_id"] == "literature-review"
        assert ctx["staged_loading"]["stage_id"] == "bootstrap"
        assert set(ctx) == {
            "topic",
            "slug",
            "commit_docs",
            "state_exists",
            "project_exists",
            "project_contract",
            "project_contract_gate",
            "project_contract_load_info",
            "project_contract_validation",
            "active_reference_context",
            "reference_artifacts_content",
            "staged_loading",
        }

    def test_stage_review_bootstrap_defers_full_reference_context(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_project(tmp_path)
        _write_project_contract_state(tmp_path)
        _write_literature_review_anchor_file(tmp_path)
        monkeypatch.setattr(
            context_module,
            "_build_reference_runtime_context",
            stage_ctx.fail_if_context_builder_runs("_build_reference_runtime_context"),
        )

        ctx = init_literature_review(tmp_path, topic="Curvature flow bounds", stage="review_bootstrap")

        assert ctx["staged_loading"]["stage_id"] == "review_bootstrap"
        assert "active_reference_context" not in ctx
        assert ctx["active_reference_count"] >= 1
        assert "ref-benchmark" in {ref["id"] for ref in ctx["active_references"]}
        assert "reference_artifacts_content" not in ctx
        assert ctx["project_contract_gate"]["visible"] is True


class TestInitProgress:
    def test_empty_project(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        ctx = init_progress(tmp_path)
        assert ctx["phase_count"] == 0
        assert ctx["current_phase"] is None
        assert ctx["next_phase"] is None
        assert ctx["paused_at"] is None

    def test_progress_prefers_local_phase_surface_over_recent_project(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        recent_project = tmp_path / "recent-project"
        data_root = tmp_path / "data"

        _setup_project(workspace)
        _setup_project(recent_project)
        (recent_project / "GPD" / "PROJECT.md").write_text("# Recent project\n", encoding="utf-8")
        (recent_project / "GPD" / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
        phase_dir = _create_phase_dir(recent_project, "01-recent")
        (phase_dir / "01-PLAN.md").write_text("plan\n", encoding="utf-8")
        resume_file = phase_dir / ".continue-here.md"
        resume_file.write_text("resume\n", encoding="utf-8")
        record_recent_project(
            recent_project,
            session_data={
                "last_date": "2026-03-29T12:00:00+00:00",
                "resume_file": "GPD/phases/01-recent/.continue-here.md",
            },
            store_root=data_root,
        )

        ctx = init_progress(workspace, data_root=data_root)

        assert ctx["project_root"] == workspace.resolve().as_posix()
        assert ctx["project_root_source"] == "current_workspace"
        assert ctx["project_reentry_mode"] == "current-workspace"
        assert ctx["project_reentry_selected_candidate"]["reason"] == "workspace carries local GPD phase directory"
        assert ctx["phase_count"] == 0

    def test_phase_statuses(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        # Complete phase
        p1 = _create_phase_dir(tmp_path, "01-setup")
        (p1 / "a-PLAN.md").write_text("plan", encoding="utf-8")
        (p1 / "a-SUMMARY.md").write_text("summary", encoding="utf-8")
        # In-progress phase
        p2 = _create_phase_dir(tmp_path, "02-analysis")
        (p2 / "b-PLAN.md").write_text("plan", encoding="utf-8")
        # Pending phase
        _create_phase_dir(tmp_path, "03-synthesis")

        ctx = init_progress(tmp_path)
        assert ctx["phase_count"] == 3
        assert ctx["completed_count"] == 1
        assert ctx["in_progress_count"] == 1
        assert ctx["current_phase"]["number"] == "02"
        assert ctx["next_phase"]["number"] == "03"

    def test_progress_uses_roadmap_inventory_for_phases_without_directories(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        (tmp_path / "GPD" / "ROADMAP.md").write_text(
            "# Roadmap\n\n"
            "## Phase 1: Setup\n\n"
            "**Goal:** Establish baseline.\n\n"
            "## Phase 2: Analysis\n\n"
            "**Goal:** Analyze the main target.\n\n"
            "## Phase 3: Synthesis\n\n"
            "**Goal:** Package the result.\n",
            encoding="utf-8",
        )
        p1 = _create_phase_dir(tmp_path, "01-setup")
        (p1 / "a-PLAN.md").write_text("plan", encoding="utf-8")
        (p1 / "a-SUMMARY.md").write_text("summary", encoding="utf-8")
        p2 = _create_phase_dir(tmp_path, "02-analysis")
        (p2 / "b-PLAN.md").write_text("plan", encoding="utf-8")

        ctx = init_progress(tmp_path)

        assert [phase["number"] for phase in ctx["phases"]] == ["1", "2", "3"]
        assert ctx["phase_count"] == 3
        assert ctx["completed_count"] == 1
        assert ctx["current_phase"]["number"] == "2"
        assert ctx["current_phase"]["disk_status"] == "planned"
        assert ctx["next_phase"]["number"] == "3"
        assert ctx["next_phase"]["directory"] is None

    def test_progress_prefers_phase_inventory_over_stale_state_position(self, tmp_path: Path) -> None:
        from gpd.core.state import default_state_dict

        _setup_project(tmp_path)
        phase_dir = _create_phase_dir(tmp_path, "02-analysis")
        (phase_dir / "b-PLAN.md").write_text("plan", encoding="utf-8")

        state = default_state_dict()
        state["position"]["current_phase"] = "03"
        (tmp_path / "GPD" / "state.json").write_text(json.dumps(state), encoding="utf-8")

        ctx = init_progress(tmp_path)

        assert ctx["state_exists"] is True
        assert ctx["current_phase"]["number"] == "02"

    def test_detects_paused_state(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        (tmp_path / "GPD" / "STATE.md").write_text(
            "# State\n**Status:** Paused\n**Stopped at:** 2026-03-01T12:00:00Z", encoding="utf-8"
        )

        ctx = init_progress(tmp_path)
        assert ctx["paused_at"] == "2026-03-01T12:00:00Z"

    def test_progress_can_skip_recent_project_reentry_for_projectless_config_bootstrap(
        self,
        tmp_path: Path,
    ) -> None:
        workspace = tmp_path / "workspace"
        candidate = tmp_path / "recoverable-project"
        data_root = tmp_path / "data"

        (workspace / "GPD" / "phases").mkdir(parents=True)
        _create_config(
            workspace,
            {
                "autonomy": "balanced",
                "review_cadence": "adaptive",
                "research_mode": "balanced",
            },
        )

        gpd_dir = candidate / "GPD"
        gpd_dir.mkdir(parents=True)
        (gpd_dir / "STATE.md").write_text("# Research State\n", encoding="utf-8")
        (gpd_dir / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
        (gpd_dir / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
        resume_file = gpd_dir / "phases" / "01" / ".continue-here.md"
        resume_file.parent.mkdir(parents=True, exist_ok=True)
        resume_file.write_text("resume\n", encoding="utf-8")
        record_recent_project(
            candidate,
            session_data={
                "last_date": "2026-03-29T12:00:00+00:00",
                "stopped_at": "Phase 01",
                "resume_file": "GPD/phases/01/.continue-here.md",
            },
            store_root=data_root,
        )

        ctx = init_progress(workspace, includes={"config"}, data_root=data_root, include_project_reentry=False)

        assert ctx["workspace_root"] == workspace.resolve().as_posix()
        assert ctx["project_root"] == workspace.resolve().as_posix()
        assert ctx["project_root_source"] == "workspace"
        assert ctx["project_root_auto_selected"] is False
        assert ctx["init_root_policy"] == "project_scoped"
        assert ctx["config_content"] is not None
        assert "project_reentry_mode" not in ctx
        assert "project_reentry_candidates" not in ctx
        assert "project_reentry_selected_candidate" not in ctx

    def test_progress_without_recent_project_reentry_still_resolves_ancestor_project(
        self,
        tmp_path: Path,
    ) -> None:
        project = tmp_path / "project"
        nested = project / "src" / "notes"

        project.mkdir()
        _setup_project(project)
        (project / "GPD" / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
        nested.mkdir(parents=True)

        ctx = init_progress(nested, include_project_reentry=False)

        assert ctx["workspace_root"] == nested.resolve().as_posix()
        assert ctx["project_root"] == project.resolve().as_posix()
        assert ctx["project_root_source"] == "workspace"
        assert ctx["project_root_auto_selected"] is False
        assert ctx["init_root_policy"] == "project_scoped"
        assert ctx["project_exists"] is True
        assert "project_reentry_mode" not in ctx

    def test_progress_rejects_stale_autonomy_values(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_config(tmp_path, {"autonomy": "guided"})

        with pytest.raises(ConfigError, match="Invalid config.json values"):
            init_progress(tmp_path)

    def test_progress_prefers_explicit_gpd_workspace_config_over_recent_project(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        recent_project = tmp_path / "recent-project"
        data_root = tmp_path / "data"

        workspace.mkdir()
        recent_project.mkdir()
        _setup_project(workspace)
        _create_config(workspace, {"autonomy": "guided"})

        _setup_project(recent_project)
        from gpd.core.state import default_state_dict

        (recent_project / "GPD" / "state.json").write_text(
            json.dumps(default_state_dict()),
            encoding="utf-8",
        )
        (recent_project / "GPD" / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
        (recent_project / "GPD" / "PROJECT.md").write_text("# Project\n", encoding="utf-8")
        resume_path = recent_project / "GPD" / "phases" / "01-analysis" / ".continue-here.md"
        resume_path.parent.mkdir(parents=True, exist_ok=True)
        resume_path.write_text("resume\n", encoding="utf-8")
        record_recent_project(
            recent_project,
            session_data={
                "last_date": "2026-03-29T12:00:00+00:00",
                "resume_file": "GPD/phases/01-analysis/.continue-here.md",
            },
            store_root=data_root,
        )

        with pytest.raises(ConfigError, match="Invalid config.json values"):
            init_progress(workspace, data_root=data_root)

    def test_progress_prefers_live_execution_pause_state(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _write_current_execution(
            tmp_path,
            {
                "session_id": "sess-2",
                "phase": "02",
                "segment_status": "paused",
                "resume_file": "GPD/phases/02-analysis/.continue-here.md",
                "updated_at": "2026-03-11T08:00:00+00:00",
            },
        )

        ctx = init_progress(tmp_path)

        assert ctx["paused_at"] == "2026-03-11T08:00:00+00:00"
        assert ctx["execution_resumable"] is True
        assert ctx["has_work_in_progress"] is True

    @pytest.mark.parametrize("segment_status", sorted(RESUMABLE_SEGMENT_STATUSES))
    def test_progress_uses_canonical_resumable_statuses_for_pause_timestamp(
        self,
        tmp_path: Path,
        segment_status: str,
    ) -> None:
        _setup_project(tmp_path)
        _write_current_execution(
            tmp_path,
            {
                "session_id": f"sess-{segment_status}",
                "phase": "02",
                "segment_status": segment_status,
                "resume_file": "GPD/phases/02-analysis/.continue-here.md",
                "updated_at": "2026-03-11T08:00:00+00:00",
            },
        )

        ctx = init_progress(tmp_path)

        assert ctx["execution_resumable"] is True
        assert ctx["execution_paused_at"] == "2026-03-11T08:00:00+00:00"
        assert ctx["paused_at"] == "2026-03-11T08:00:00+00:00"

    def test_progress_marks_handoff_only_resume_target_as_work_in_progress(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        from gpd.core.state import default_state_dict

        resume_file = "GPD/phases/02-analysis/.continue-here.md"
        resume_path = tmp_path / resume_file
        resume_path.parent.mkdir(parents=True, exist_ok=True)
        resume_path.write_text("resume\n", encoding="utf-8")
        state = default_state_dict()
        state["continuation"]["handoff"]["resume_file"] = resume_file
        state["continuation"]["handoff"]["stopped_at"] = "2026-03-11T08:00:00+00:00"
        (tmp_path / "GPD" / "state.json").write_text(json.dumps(state), encoding="utf-8")

        ctx = init_progress(tmp_path)

        assert ctx["current_phase"] is None
        assert ctx["current_execution"] is None
        assert ctx["execution_resume_file_source"] == "handoff_resume_file"
        assert ctx["execution_resume_file"] == resume_file
        assert ctx["has_work_in_progress"] is True

    def test_progress_labels_canonical_bounded_segment_resume_source(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        from gpd.core.state import default_state_dict

        resume_file = "GPD/phases/02-analysis/.continue-here.md"
        resume_path = tmp_path / resume_file
        resume_path.parent.mkdir(parents=True, exist_ok=True)
        resume_path.write_text("resume\n", encoding="utf-8")
        state = default_state_dict()
        state["continuation"]["bounded_segment"] = {
            "resume_file": resume_file,
            "phase": "02",
            "plan": "01",
            "segment_id": "seg-canonical",
            "segment_status": "paused",
        }
        (tmp_path / "GPD" / "state.json").write_text(json.dumps(state), encoding="utf-8")

        ctx = init_progress(tmp_path)

        assert ctx["current_execution"] is None
        assert ctx["execution_resume_file_source"] == "continuation.bounded_segment"
        assert ctx["execution_resume_file"] == resume_file
        assert ctx["execution_resumable"] is True
        assert ctx["has_work_in_progress"] is True

    def test_progress_derives_execution_flags_from_canonical_bounded_segment_without_live_snapshot(
        self, tmp_path: Path
    ) -> None:
        _setup_project(tmp_path)
        from gpd.core.state import default_state_dict

        resume_file = "GPD/phases/02-analysis/.continue-here.md"
        resume_path = tmp_path / resume_file
        resume_path.parent.mkdir(parents=True, exist_ok=True)
        resume_path.write_text("resume\n", encoding="utf-8")
        state = default_state_dict()
        state["continuation"]["bounded_segment"] = {
            "resume_file": resume_file,
            "phase": "02",
            "plan": "01",
            "segment_id": "seg-canonical-flags",
            "segment_status": "waiting_review",
            "blocked_reason": "human review required",
            "waiting_for_review": True,
            "pre_fanout_review_pending": True,
            "skeptical_requestioning_required": True,
            "downstream_locked": True,
            "updated_at": "2026-03-11T08:00:00+00:00",
        }
        (tmp_path / "GPD" / "state.json").write_text(json.dumps(state), encoding="utf-8")

        ctx = init_progress(tmp_path)

        assert ctx["current_execution"] is None
        assert ctx["has_live_execution"] is False
        assert ctx["execution_review_pending"] is True
        assert ctx["execution_pre_fanout_review_pending"] is True
        assert ctx["execution_skeptical_requestioning_required"] is True
        assert ctx["execution_downstream_locked"] is True
        assert ctx["execution_blocked"] is True
        assert ctx["execution_paused_at"] == "2026-03-11T08:00:00+00:00"
        assert ctx["paused_at"] == "2026-03-11T08:00:00+00:00"

    def test_progress_does_not_surface_execution_flags_from_non_resumable_bounded_segment(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        from gpd.core.state import default_state_dict

        state = default_state_dict()
        state["continuation"]["bounded_segment"] = {
            "resume_file": "GPD/phases/02-analysis/missing.md",
            "phase": "02",
            "plan": "01",
            "segment_id": "seg-missing-resume",
            "segment_status": "waiting_review",
            "blocked_reason": "human review required",
            "waiting_for_review": True,
            "pre_fanout_review_pending": True,
            "skeptical_requestioning_required": True,
            "downstream_locked": True,
            "updated_at": "2026-03-11T08:00:00+00:00",
        }
        (tmp_path / "GPD" / "state.json").write_text(json.dumps(state), encoding="utf-8")

        ctx = init_progress(tmp_path)

        assert ctx["execution_resume_file"] is None
        assert ctx["execution_resumable"] is False
        assert ctx["execution_review_pending"] is False
        assert ctx["execution_pre_fanout_review_pending"] is False
        assert ctx["execution_skeptical_requestioning_required"] is False
        assert ctx["execution_downstream_locked"] is False
        assert ctx["execution_blocked"] is False
        assert ctx["execution_paused_at"] is None

    def test_progress_ors_live_snapshot_flags_with_canonical_bounded_segment(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        from gpd.core.state import default_state_dict

        resume_file = "GPD/phases/02-analysis/.continue-here.md"
        resume_path = tmp_path / resume_file
        resume_path.parent.mkdir(parents=True, exist_ok=True)
        resume_path.write_text("resume\n", encoding="utf-8")
        state = default_state_dict()
        state["continuation"]["bounded_segment"] = {
            "resume_file": resume_file,
            "phase": "02",
            "plan": "01",
            "segment_id": "seg-canonical-or",
            "segment_status": "paused",
            "blocked_reason": "manual checkpoint",
            "pre_fanout_review_pending": True,
            "downstream_locked": True,
            "updated_at": "2026-03-11T08:00:00+00:00",
        }
        (tmp_path / "GPD" / "state.json").write_text(json.dumps(state), encoding="utf-8")
        _write_current_execution(
            tmp_path,
            {
                "session_id": "sess-live",
                "phase": "02",
                "plan": "01",
                "segment_id": "seg-live",
                "segment_status": "active",
                "resume_file": resume_file,
                "updated_at": "2026-03-11T09:00:00+00:00",
            },
        )

        ctx = init_progress(tmp_path)

        assert ctx["has_live_execution"] is True
        assert ctx["current_execution"]["segment_status"] == "active"
        assert ctx["execution_review_pending"] is True
        assert ctx["execution_pre_fanout_review_pending"] is True
        assert ctx["execution_downstream_locked"] is True
        assert ctx["execution_blocked"] is True
        assert ctx["execution_paused_at"] == "2026-03-11T08:00:00+00:00"

    def test_progress_normalizes_absolute_live_execution_resume_file(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        resume_path = tmp_path / "GPD" / "phases" / "02-analysis" / ".continue-here.md"
        resume_path.parent.mkdir(parents=True, exist_ok=True)
        resume_path.write_text("resume\n", encoding="utf-8")
        _write_current_execution(
            tmp_path,
            {
                "session_id": "sess-2",
                "phase": "02",
                "segment_status": "paused",
                "resume_file": str(resume_path),
                "updated_at": "2026-03-11T08:00:00+00:00",
            },
        )

        ctx = init_progress(tmp_path)

        assert ctx["current_execution"]["resume_file"] == "GPD/phases/02-analysis/.continue-here.md"
        assert ctx["current_execution_resume_file"] == "GPD/phases/02-analysis/.continue-here.md"
        assert ctx["execution_resume_file"] == "GPD/phases/02-analysis/.continue-here.md"

    def test_progress_normalizes_live_execution_phase_when_no_phase_inventory_exists(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _write_current_execution(
            tmp_path,
            {
                "session_id": "sess-2",
                "phase": "2",
                "plan": "1",
                "segment_status": "paused",
                "checkpoint_reason": "pre-fanout",
                "resume_file": "GPD/phases/02-analysis/.continue-here.md",
                "updated_at": "2026-03-11T08:00:00+00:00",
            },
        )

        ctx = init_progress(tmp_path)

        assert ctx["current_phase"]["number"] == "02"
        assert ctx["current_execution"]["phase"] == "02"
        assert ctx["current_execution"]["plan"] == "01"
        assert ctx["current_execution"]["checkpoint_reason"] == "pre_fanout"

    def test_includes_project(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        (tmp_path / "GPD" / "PROJECT.md").write_text("# My Project", encoding="utf-8")

        ctx = init_progress(tmp_path, includes={"project"})
        assert ctx["project_content"] == "# My Project"

    def test_progress_includes_structured_state_context_when_state_is_requested(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _write_structured_state_payload(tmp_path)

        ctx = init_progress(tmp_path, includes={"state"})

        _assert_structured_state_context(ctx, tmp_path)

    def test_progress_exposes_reference_registry(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _write_project_contract_state(tmp_path)

        ctx = init_progress(tmp_path)

        assert ctx["project_contract"]["references"][0]["must_surface"] is True
        assert "10.1234/benchmark-figure-2" in ctx["active_reference_context"]

    def test_progress_default_omits_reference_artifact_content_until_requested(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _write_project_contract_state(tmp_path)
        _write_research_map_anchor_files(tmp_path)

        ctx = init_progress(tmp_path)

        assert "GPD/research-map/REFERENCES.md" in ctx["reference_artifact_files"]
        assert ctx["reference_artifacts_content"] is None

        ctx_with_references = init_progress(tmp_path, includes={"references"})

        assert "Reference and Anchor Map" in ctx_with_references["reference_artifacts_content"]
        assert "Universal crossing window" in ctx_with_references["reference_artifacts_content"]

    def test_progress_default_omits_protocol_bundle_context_until_requested(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _write_stat_mech_project(tmp_path)
        _write_bundle_ready_contract_state(tmp_path)

        ctx = init_progress(tmp_path)

        assert "stat-mech-simulation" in ctx["selected_protocol_bundle_ids"]
        assert ctx["protocol_bundle_count"] >= 1
        assert ctx["protocol_bundle_load_manifest"]["selected_bundle_ids"] == ctx["selected_protocol_bundle_ids"]
        assert "Every physics calculation involves approximations" not in json.dumps(
            ctx["protocol_bundle_load_manifest"]
        )
        assert ctx["protocol_bundle_context"] is None

        ctx_with_protocols = init_progress(tmp_path, includes={"protocols"})

        assert "Decisive artifacts:" in ctx_with_protocols["protocol_bundle_context"]

    def test_progress_surfaces_knowledge_inventory_and_runtime_counts(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _write_knowledge_doc(tmp_path, status="stable")
        _write_knowledge_doc(
            tmp_path,
            knowledge_id="K-work-in-progress",
            status="in_review",
            body="Draft knowledge body.\n",
        )

        ctx = init_progress(tmp_path)

        assert ctx["knowledge_doc_count"] == 2
        assert ctx["stable_knowledge_doc_count"] == 1
        assert ctx["knowledge_doc_status_counts"]["stable"] == 1
        assert ctx["knowledge_doc_status_counts"]["in_review"] == 1
        assert ctx["derived_knowledge_doc_count"] == 1
        assert ctx["knowledge_doc_warnings"] == []
        assert "GPD/knowledge/K-renormalization-group-fixed-points.md" in ctx["knowledge_doc_files"]
        assert ctx["stable_knowledge_doc_files"] == ["GPD/knowledge/K-renormalization-group-fixed-points.md"]

    def test_progress_surfaces_derived_state_memory(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _write_structured_state_memory(tmp_path)

        ctx = init_progress(tmp_path)

        assert ctx["state_exists"] is True
        assert ctx["derived_convention_lock"]["metric_signature"] == "mostly-plus"
        assert ctx["derived_convention_lock_count"] == 2
        assert ctx["derived_intermediate_result_count"] == 1
        assert ctx["derived_intermediate_results"][0]["verified"] is True
        assert ctx["derived_approximation_count"] == 1
        assert ctx["derived_approximations"][0]["status"] == "valid"

    def test_progress_hides_project_contract_when_raw_state_requires_contract_scalar_normalization(
        self, tmp_path: Path
    ) -> None:
        _setup_project(tmp_path)
        _write_coercive_project_contract_state(tmp_path)

        from gpd.core.state import state_load

        loaded = state_load(tmp_path)
        ctx = init_progress(tmp_path)

        assert loaded.state["project_contract"] is None
        assert ctx["project_contract"] is None
        assert "None confirmed in `state.json.project_contract.references` yet." in ctx["active_reference_context"]

    def test_progress_keeps_project_contract_when_raw_state_only_needs_recoverable_normalization(
        self, tmp_path: Path
    ) -> None:
        _setup_project(tmp_path)
        _write_recoverable_project_contract_state(tmp_path)

        ctx = init_progress(tmp_path)

        assert ctx["project_contract"] is not None
        assert ctx["project_contract"]["claims"][0]["id"] == "claim-benchmark"
        assert ctx["project_contract_load_info"]["status"] == "loaded_with_schema_normalization"
        assert ctx["project_contract_gate"]["authoritative"] is False
        assert ctx["project_contract_gate"]["repair_required"] is True
        assert ctx["project_contract_gate"]["visible"] is True
        assert ctx["contract_intake"]["must_read_refs"] == ["ref-benchmark"]
        assert "Recover known limiting behavior" not in ctx["active_reference_context"]
        assert "ref-benchmark" not in ctx["effective_reference_intake"]["must_read_refs"]
        assert "None confirmed in `state.json.project_contract.references` yet." in ctx["active_reference_context"]

    def test_progress_matches_state_loader_for_recoverably_normalized_project_contract(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _write_recoverable_project_contract_state(tmp_path)

        from gpd.core.state import state_load

        loaded = state_load(tmp_path)
        ctx = init_progress(tmp_path)

        assert ctx["project_contract"] is not None
        assert ctx["project_contract"]["claims"][0]["id"] == "claim-benchmark"
        assert loaded.state["project_contract"]["claims"][0]["id"] == "claim-benchmark"
        assert "notes" not in loaded.state["project_contract"]["claims"][0]
        assert ctx["project_contract_gate"]["visible"] is True
        assert ctx["project_contract_gate"]["authoritative"] is False

    def test_load_project_contract_keeps_primary_contract_when_unrelated_root_section_is_schema_corrupt(
        self, tmp_path: Path
    ) -> None:
        _setup_project(tmp_path)
        _write_project_contract_state(tmp_path)
        from gpd.core.state import default_state_dict

        planning = tmp_path / "GPD"
        primary_state = json.loads((planning / "state.json").read_text(encoding="utf-8"))
        primary_state["blockers"] = "bad-root-shape"
        (planning / "state.json").write_text(json.dumps(primary_state, indent=2) + "\n", encoding="utf-8")

        backup_question = "Recovered from schema-corrupt backup state"
        backup_state = default_state_dict()
        backup_contract = json.loads((FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"))
        backup_contract["scope"]["question"] = backup_question
        backup_state["project_contract"] = backup_contract
        (planning / "state.json.bak").write_text(json.dumps(backup_state, indent=2) + "\n", encoding="utf-8")

        loaded, load_info = _load_project_contract(tmp_path)
        ctx = init_progress(tmp_path)
        primary_question = json.loads((FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"))["scope"][
            "question"
        ]

        assert loaded is not None
        assert load_info["source_path"].endswith("state.json")
        assert loaded.scope.question == primary_question
        assert loaded.scope.question != backup_question
        assert ctx["project_contract"] is not None
        assert ctx["project_contract"]["scope"]["question"] == primary_question
        assert ctx["project_contract_load_info"]["source_path"].endswith("state.json")

    def test_load_project_contract_surfaces_blocked_status_for_invalid_state_backed_contract(
        self, tmp_path: Path
    ) -> None:
        _setup_project(tmp_path)

        from gpd.core.state import default_state_dict

        state = default_state_dict()
        contract = json.loads((FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"))
        contract["references"] = ["bad"]
        state["project_contract"] = contract
        (tmp_path / "GPD" / "state.json").write_text(json.dumps(state), encoding="utf-8")

        loaded, load_info = _load_project_contract(tmp_path)
        ctx = init_progress(tmp_path)

        assert loaded is None
        assert load_info["status"] == "blocked_schema"
        assert ctx["project_contract"] is None
        assert ctx["project_contract_load_info"]["status"] == "blocked_schema"
        assert {
            key: value
            for key, value in ctx["project_contract_gate"].items()
            if key
            not in {
                "provenance",
                "raw_project_contract_classified",
                "confirmed_at",
                "confirmed_contract_hash",
                "confirmed_context_hash",
            }
        } == {
            "status": "blocked_schema",
            "visible": False,
            "blocked": True,
            "load_blocked": True,
            "approval_blocked": False,
            "authoritative": False,
            "repair_required": True,
            "source_path": ctx["project_contract_load_info"]["source_path"],
        }
        assert ctx["project_contract_load_info"]["source_path"].endswith("state.json")
        assert load_info["provenance"] == "raw"
        assert load_info["raw_project_contract_classified"] is True
        assert ctx["project_contract_gate"]["provenance"] == "raw"
        assert ctx["project_contract_gate"]["raw_project_contract_classified"] is True

    def test_load_project_contract_accepts_list_shape_drift_from_raw_state_as_loaded(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)

        from gpd.core.state import default_state_dict

        state = default_state_dict()
        contract = json.loads((FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"))
        contract["references"][0]["aliases"] = "not-a-list"
        state["project_contract"] = contract
        (tmp_path / "GPD" / "state.json").write_text(json.dumps(state), encoding="utf-8")

        loaded, load_info = _load_project_contract(tmp_path)

        assert loaded is not None
        assert load_info["status"] == "loaded_with_schema_normalization"
        assert load_info["errors"] == []

    def test_load_project_contract_fallback_salvages_nested_metadata_must_surface(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup_project(tmp_path)

        contract = json.loads((FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"))
        contract["references"][0]["metadata"] = {"must_surface": "yes"}

        from gpd.core.state import ensure_state_schema

        normalized_state = ensure_state_schema({"project_contract": contract})
        monkeypatch.setattr(
            "gpd.core.state.peek_state_json", lambda cwd, **kwargs: (normalized_state, [], "state.json")
        )
        monkeypatch.setattr("gpd.core.state._load_raw_project_contract_payload", lambda cwd: None)

        loaded, load_info = _load_project_contract(tmp_path)

        assert loaded is not None
        assert load_info["status"] == "loaded"
        assert loaded.references[0].id == "ref-benchmark"
        assert loaded.references[0].must_surface is True

    def test_load_project_contract_surfaces_duplicate_contract_ids_as_visible_blocked_integrity(
        self, tmp_path: Path
    ) -> None:
        _setup_project(tmp_path)

        from gpd.core.state import default_state_dict

        state = default_state_dict()
        contract = json.loads((FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"))
        contract["claims"].append(dict(contract["claims"][0]))
        state["project_contract"] = contract
        (tmp_path / "GPD" / "state.json").write_text(json.dumps(state), encoding="utf-8")

        loaded, load_info = _load_project_contract(tmp_path)
        ctx = init_progress(tmp_path)

        assert loaded is not None
        assert load_info["status"] == "blocked_integrity"
        assert any("duplicate" in error for error in load_info["errors"])
        assert ctx["project_contract"] is not None
        assert ctx["project_contract"]["claims"][0]["id"] == "claim-benchmark"
        assert ctx["project_contract_load_info"]["status"] == "blocked_integrity"
        assert ctx["project_contract_gate"]["visible"] is True
        assert ctx["project_contract_gate"]["blocked"] is True
        assert ctx["project_contract_gate"]["authoritative"] is False
        assert ctx["project_contract_gate"]["status"] == "blocked_integrity"
        assert any("duplicate" in error for error in load_info["errors"])

    def test_load_project_contract_rejects_whole_singleton_defaulting_from_raw_state(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)

        from gpd.core.state import default_state_dict

        state = default_state_dict()
        contract = json.loads((FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"))
        contract["context_intake"] = "not-a-dict"
        state["project_contract"] = contract
        (tmp_path / "GPD" / "state.json").write_text(json.dumps(state), encoding="utf-8")

        loaded, load_info = _load_project_contract(tmp_path)

        assert loaded is None
        assert load_info["status"] == "blocked_schema"


class TestInitPhaseOp:
    """Tests for init_phase_op context assembly."""

    def test_no_phase_returns_phase_found_false(self, tmp_path):
        """init_phase_op with no phase should set phase_found=False."""
        from gpd.core.context import init_phase_op

        gpd_dir = tmp_path / "GPD"
        gpd_dir.mkdir()
        (gpd_dir / "config.json").write_text("{}", encoding="utf-8")

        result = init_phase_op(tmp_path)
        assert isinstance(result, dict)
        assert result.get("phase_found") is False

    def test_with_phase_directory(self, tmp_path):
        """init_phase_op with existing phase should set phase_found=True."""
        from gpd.core.context import init_phase_op

        gpd_dir = tmp_path / "GPD"
        phases_dir = gpd_dir / "phases" / "01-test"
        phases_dir.mkdir(parents=True)
        (gpd_dir / "config.json").write_text("{}", encoding="utf-8")

        result = init_phase_op(tmp_path, phase="1")
        assert isinstance(result, dict)
        # Phase should be found since we created the directory
        if result.get("phase_found"):
            assert "01" in str(result.get("phase_number", ""))

    def test_resolves_ancestor_project_root_from_nested_workspace(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "01-test")
        nested = tmp_path / "workspace" / "notes"
        nested.mkdir(parents=True)

        result = init_phase_op(nested, phase="1")

        assert isinstance(result, dict)
        assert result["init_root_policy"] == "project_scoped"
        assert result["planning_exists"] is True
        assert result["phase_found"] is True
        assert result["phase_number"] == "01"
        assert str(result["phase_dir"]).startswith("GPD/phases/01-")

    def test_includes_structured_state_context_when_state_is_requested(self, tmp_path):
        """init_phase_op should surface canonical state slices when state is included."""
        from gpd.core.context import init_phase_op

        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "01-test")
        _write_structured_state_payload(tmp_path)

        result = init_phase_op(tmp_path, phase="1", includes={"state"})

        _assert_structured_state_context(result, tmp_path)

    def test_stage_bootstrap_returns_only_manifest_required_fields(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "01-test")
        _write_structured_state_payload(tmp_path)
        _write_project_contract_state(tmp_path)
        manifest = install_fake_stage_manifest(
            monkeypatch,
            workflow_id="research-phase",
            stages={
                "bootstrap": [
                    "executor_model",
                    "verifier_model",
                    "commit_docs",
                    "research_mode",
                    "phase_found",
                    "phase_dir",
                    "phase_number",
                    "phase_name",
                    "project_contract",
                    "project_contract_gate",
                    "project_contract_load_info",
                    "project_contract_validation",
                    "active_reference_context",
                    "reference_artifacts_content",
                ]
            },
        )

        result = init_phase_op(tmp_path, phase="1", stage="bootstrap")

        stage_ctx.assert_context_stage(result, manifest, "research-phase", "bootstrap")

    def test_stage_phase_bootstrap_defers_heavy_context_builders(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "01-test")
        _write_project_contract_state(tmp_path)
        monkeypatch.setattr(
            "gpd.core.context._build_reference_runtime_context",
            stage_ctx.fail_if_context_builder_runs("_build_reference_runtime_context"),
        )
        monkeypatch.setattr(
            "gpd.core.context._build_state_memory_runtime_context",
            stage_ctx.fail_if_context_builder_runs("_build_state_memory_runtime_context"),
        )
        monkeypatch.setattr(
            "gpd.core.context._build_execution_runtime_context",
            stage_ctx.fail_if_context_builder_runs("_build_execution_runtime_context"),
        )

        result = init_phase_op(tmp_path, phase="1", stage="phase_bootstrap")

        assert result["staged_loading"]["stage_id"] == "phase_bootstrap"
        assert "active_reference_context" not in result
        assert "derived_convention_lock" not in result
        assert "current_execution" not in result
        assert result["project_contract_gate"]["visible"] is True

    def test_stage_builds_heavy_contexts_when_manifest_requires_them(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Defensive isolation: other tests in the same xdist worker can call
        # importlib.reload(gpd.core.context) (e.g. test_context_platform.py)
        # and warm @cache on the workflow-staging manifest loader. Clear both
        # before this test so monkeypatched builders + fake manifest get the
        # fresh module wiring.
        import importlib

        from gpd.core.workflow_staging import invalidate_workflow_stage_manifest_cache

        invalidate_workflow_stage_manifest_cache()
        importlib.reload(context_module)
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "01-test")
        install_fake_stage_manifest(
            monkeypatch,
            workflow_id="research-phase",
            stages={
                "research_handoff": [
                    "active_reference_context",
                    "reference_artifacts_content",
                    "state_load_source",
                    "derived_convention_lock",
                    "current_execution",
                ]
            },
        )
        calls: list[str] = []

        def reference_context(
            cwd: Path,
            *,
            include_artifact_content: bool = True,
            include_active_reference_context: bool = True,
            include_protocol_context: bool = True,
            **_kwargs: object,
        ) -> dict[str, object]:
            calls.append("reference")
            assert include_artifact_content is True
            assert include_active_reference_context is True
            assert include_protocol_context is False
            return {
                **{
                    field: f"reference::{field}"
                    for field in (
                        context_module._EXECUTE_PHASE_CONTRACT_GATE_FIELDS
                        | context_module._EXECUTE_PHASE_REFERENCE_RUNTIME_FIELDS
                    )
                },
                "active_reference_context": "reference context",
                "reference_artifacts_content": "reference artifacts",
            }

        def structured_state_context(cwd: Path) -> dict[str, object]:
            calls.append("structured_state")
            return {
                field: f"structured_state::{field}" for field in context_module._EXECUTE_PHASE_STRUCTURED_STATE_FIELDS
            }

        def state_memory_context(cwd: Path) -> dict[str, object]:
            calls.append("state_memory")
            return {
                **{field: f"state_memory::{field}" for field in context_module._EXECUTE_PHASE_STATE_MEMORY_FIELDS},
                "derived_convention_lock": {"metric_signature": "mostly-plus"},
            }

        def execution_context(cwd: Path) -> dict[str, object]:
            calls.append("execution")
            return {
                **{field: f"execution::{field}" for field in context_module._EXECUTE_PHASE_EXECUTION_RUNTIME_FIELDS},
                "current_execution": {"phase": "01", "segment_status": "running"},
            }

        monkeypatch.setattr(context_module, "_build_reference_runtime_context", reference_context)
        monkeypatch.setattr(context_module, "_build_structured_state_runtime_context", structured_state_context)
        monkeypatch.setattr(context_module, "_build_state_memory_runtime_context", state_memory_context)
        monkeypatch.setattr(context_module, "_build_execution_runtime_context", execution_context)

        # Call via the (potentially reloaded) module attribute so the function
        # body resolves the monkeypatched builders against the current module
        # globals rather than a stale top-of-file `init_phase_op` binding.
        result = context_module.init_phase_op(tmp_path, phase="1", stage="research_handoff")

        assert calls == ["reference", "structured_state", "state_memory", "execution"]
        assert result["active_reference_context"] == "reference context"
        assert result["reference_artifacts_content"] == "reference artifacts"
        assert "protocol_bundle_context" not in result
        assert "active_references" not in result
        assert "protocol_bundle_load_manifest" not in result
        assert result["state_load_source"] == "structured_state::state_load_source"
        assert result["derived_convention_lock"] == {"metric_signature": "mostly-plus"}
        assert result["current_execution"] == {"phase": "01", "segment_status": "running"}

    def test_init_research_phase_alias_uses_the_same_stage_manifest_contract(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "01-test")
        manifest = install_fake_stage_manifest(
            monkeypatch,
            workflow_id="research-phase",
            stages={
                "bootstrap": [
                    "phase_found",
                    "phase_dir",
                    "phase_number",
                    "phase_name",
                    "commit_docs",
                    "research_mode",
                ]
            },
        )

        result = init_research_phase(tmp_path, phase="1", stage="bootstrap")

        stage_ctx.assert_context_stage(result, manifest, "research-phase", "bootstrap")

    def test_stage_research_handoff_returns_only_manifest_required_fields(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_project(tmp_path)
        _create_phase_dir(tmp_path, "01-test")
        manifest = install_fake_stage_manifest(
            monkeypatch,
            workflow_id="research-phase",
            stages={
                "bootstrap": [
                    "phase_found",
                    "phase_dir",
                    "phase_number",
                    "phase_name",
                    "commit_docs",
                    "research_mode",
                ],
                "research_handoff": [
                    "commit_docs",
                    "autonomy",
                    "review_cadence",
                    "research_mode",
                    "phase_found",
                    "phase_dir",
                    "phase_number",
                    "phase_name",
                    "phase_slug",
                    "padded_phase",
                    "contract_intake",
                    "effective_reference_intake",
                    "active_reference_context",
                    "reference_artifact_files",
                    "reference_artifacts_content",
                    "selected_protocol_bundle_ids",
                    "protocol_bundle_load_manifest",
                    "protocol_bundle_context",
                    "protocol_bundle_verifier_extensions",
                    "current_execution",
                    "config_content",
                    "state_content",
                    "roadmap_content",
                ],
            },
        )

        result = init_research_phase(tmp_path, phase="1", stage="research_handoff")

        stage_ctx.assert_context_stage(result, manifest, "research-phase", "research_handoff")


def test_context_reference_builder_surfaces_alignment_on_gate_dict(tmp_path: Path) -> None:
    """init_progress surfaces recorded alignment hashes on project_contract_gate."""
    from gpd.core.state import state_record_contract_alignment

    _setup_project(tmp_path)
    _write_project_contract_state(tmp_path)
    contract = ResearchContract.model_validate(
        json.loads((FIXTURES_DIR / "project_contract.json").read_text(encoding="utf-8"))
    )
    contract_hash = contract_fingerprint(contract)
    state_record_contract_alignment(
        tmp_path,
        contract_hash=contract_hash,
        context_hash="sha256:context-hash",
        now="2026-04-23T12:00:00+00:00",
    )

    ctx = init_progress(tmp_path)
    gate = ctx["project_contract_gate"]
    assert gate["confirmed_at"] == "2026-04-23T12:00:00+00:00"
    assert gate["confirmed_contract_hash"] == contract_hash
    assert gate["confirmed_context_hash"] == "sha256:context-hash"


def test_context_new_project_builder_omits_alignment_keys(tmp_path: Path) -> None:
    """init_new_project without recorded alignment omits the three alignment keys.

    The new-project builder passes ``state_obj=None`` when assembling the
    project_contract_gate payload (Wave A contract). Because no state object
    sources the fields, the three alignment keys are absent from the gate by
    design — not present-with-None. This test pins that behaviour so regressions
    that start leaking None placeholders into the gate dict get caught early.
    """
    ctx = init_new_project(tmp_path)
    assert "project_contract_gate" in ctx
    gate = ctx["project_contract_gate"]
    assert isinstance(gate, dict)
    assert "confirmed_at" not in gate
    assert "confirmed_contract_hash" not in gate
    assert "confirmed_context_hash" not in gate
