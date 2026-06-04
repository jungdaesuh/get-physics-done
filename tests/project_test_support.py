"""Project fixtures shared by command-level tests."""

from __future__ import annotations

import json
from pathlib import Path

from gpd.core.reproducibility import compute_sha256
from gpd.core.state import default_state_dict, generate_state_markdown
from tests.manuscript_test_support import CANONICAL_MANUSCRIPT_STEM
from tests.manuscript_test_support import manuscript_path as canonical_manuscript_path
from tests.manuscript_test_support import manuscript_pdf_path as canonical_manuscript_pdf_path


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_cli_smoke_project(project_root: Path) -> Path:
    """Create a minimal GPD project with all files command smoke tests touch."""
    planning = project_root / "GPD"
    planning.mkdir()

    state = default_state_dict()
    state["position"].update(
        {
            "current_phase": "01",
            "current_phase_name": "Test Phase",
            "total_phases": 2,
            "status": "Planning",
        }
    )
    state["convention_lock"].update(
        {
            "metric_signature": "(-,+,+,+)",
            "coordinate_system": "Cartesian",
            "custom_conventions": {"my_custom": "value"},
        }
    )
    _write_json(planning / "state.json", state)
    (planning / "STATE.md").write_text(generate_state_markdown(state), encoding="utf-8")
    (planning / "PROJECT.md").write_text(
        "# Test Project\n\n## Core Research Question\nWhat is physics?\n", encoding="utf-8"
    )
    (planning / "REQUIREMENTS.md").write_text("# Requirements\n\n- [ ] **REQ-01**: Do the thing\n", encoding="utf-8")
    (planning / "ROADMAP.md").write_text(
        "# Roadmap\n\n## Phase 1: Test Phase\nGoal: Test\nRequirements: REQ-01\n"
        "\n## Phase 2: Phase Two\nGoal: More tests\nRequirements: REQ-01\n",
        encoding="utf-8",
    )
    (planning / "CONVENTIONS.md").write_text(
        "# Conventions\n\n- Metric: (-,+,+,+)\n- Coordinates: Cartesian\n", encoding="utf-8"
    )
    _write_json(
        planning / "config.json",
        {
            "autonomy": "yolo",
            "research_mode": "balanced",
            "parallelization": True,
            "commit_docs": True,
            "model_profile": "review",
            "workflow": {"research": True, "plan_checker": True, "verifier": True},
        },
    )

    p1 = planning / "phases" / "01-test-phase"
    p1.mkdir(parents=True)
    (p1 / "README.md").write_text("# Phase 1: Test Phase\n", encoding="utf-8")
    (p1 / "01-SUMMARY.md").write_text(
        "---\n"
        "phase: 01-test-phase\n"
        "plan: 01\n"
        "depth: full\n"
        "provides: [executed plan summary]\n"
        "completed: 2026-03-10\n"
        "---\n\n"
        "# Summary\n\nExecuted plan summary.\n",
        encoding="utf-8",
    )
    (p1 / "01-VERIFICATION.md").write_text(
        "---\n"
        "phase: 01-test-phase\n"
        "verified: 2026-03-10T00:00:00Z\n"
        "status: passed\n"
        "score: 1/1 checks passed\n"
        "---\n\n"
        "# Verification\n\nVerified result.\n",
        encoding="utf-8",
    )
    p2 = planning / "phases" / "02-phase-two"
    p2.mkdir(parents=True)
    (p2 / "README.md").write_text("# Phase 2: Phase Two\n", encoding="utf-8")

    paper_dir = project_root / "paper"
    paper_dir.mkdir()
    manuscript = canonical_manuscript_path(project_root)
    manuscript.write_text(
        "\\documentclass{article}\n\\begin{document}\nTest manuscript.\n\\end{document}\n",
        encoding="utf-8",
    )
    compiled_manuscript = canonical_manuscript_pdf_path(project_root)
    compiled_manuscript.write_bytes(b"%PDF-1.4\n% fake arxiv submission pdf\n")
    _write_json(
        paper_dir / "PAPER-CONFIG.json",
        {
            "title": "Curvature Flow Bounds",
            "authors": [{"name": "A. Researcher"}],
            "abstract": "Abstract.",
            "sections": [{"heading": "Introduction", "content": "Test manuscript."}],
        },
    )
    _write_json(
        paper_dir / "ARTIFACT-MANIFEST.json",
        {
            "version": 1,
            "paper_title": "Test",
            "journal": "prl",
            "created_at": "2026-03-10T00:00:00+00:00",
            "manuscript_sha256": compute_sha256(manuscript),
            "manuscript_mtime_ns": manuscript.stat().st_mtime_ns,
            "artifacts": [
                {
                    "artifact_id": "manuscript",
                    "category": "tex",
                    "path": f"{CANONICAL_MANUSCRIPT_STEM}.tex",
                    "sha256": compute_sha256(manuscript),
                    "produced_by": "tests.test_cli_commands",
                    "sources": [],
                    "metadata": {"role": "manuscript"},
                },
                {
                    "artifact_id": "compiled-manuscript",
                    "category": "pdf",
                    "path": f"{CANONICAL_MANUSCRIPT_STEM}.pdf",
                    "sha256": compute_sha256(compiled_manuscript),
                    "produced_by": "tests.test_cli_commands",
                    "sources": [{"path": f"{CANONICAL_MANUSCRIPT_STEM}.tex", "role": "compiled_from"}],
                    "metadata": {"role": "compiled_manuscript"},
                },
            ],
        },
    )
    _write_json(
        paper_dir / "BIBLIOGRAPHY-AUDIT.json",
        {
            "generated_at": "2026-03-10T00:00:00+00:00",
            "total_sources": 0,
            "resolved_sources": 0,
            "partial_sources": 0,
            "unverified_sources": 0,
            "failed_sources": 0,
            "entries": [],
        },
    )
    _write_json(
        paper_dir / "reproducibility-manifest.json",
        {
            "paper_title": "Test",
            "date": "2026-03-10",
            "environment": {
                "python_version": "3.12.1",
                "package_manager": "uv",
                "required_packages": [{"package": "numpy", "version": "1.26.4"}],
                "lock_file": "pyproject.toml",
                "system_requirements": {},
            },
            "execution_steps": [{"name": "run", "command": "python scripts/run.py"}],
            "expected_results": [
                {"quantity": "x", "expected_value": "1", "tolerance": "0.1", "script": "scripts/run.py"}
            ],
            "output_files": [{"path": "results/out.json", "checksum_sha256": "a" * 64}],
            "resource_requirements": [{"step": "run", "cpu_cores": 1, "memory_gb": 1.0}],
            "verification_steps": ["rerun", "compare", "inspect"],
            "minimum_viable": "1 core",
            "recommended": "2 cores",
            "last_verified": "2026-03-10T00:00:00+00:00",
            "last_verified_platform": "macOS-15-arm64",
            "random_seeds": [],
            "seeding_strategy": "",
        },
    )

    reports_dir = project_root / "reports"
    reports_dir.mkdir()
    (reports_dir / "referee-report.md").write_text("# Referee Report\n\n1. Clarify the derivation.\n", encoding="utf-8")
    return project_root
