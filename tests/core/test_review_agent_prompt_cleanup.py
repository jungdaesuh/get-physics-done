from __future__ import annotations

from pathlib import Path

from tests.assertion_taxonomy_support import (
    FragmentMode,
    MatchMode,
    assert_prompt_contracts,
    machine_exact,
    semantic_anchor,
    semantic_concept,
)
from tests.markdown_test_support import yaml_fence_bodies
from tests.prompt_metrics_support import count_unfenced_heading

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "src" / "gpd" / "agents"
REFERENCES_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "references"


def _read_agent(name: str) -> str:
    return (AGENTS_DIR / name).read_text(encoding="utf-8")


def test_referee_routes_on_status_and_shows_base_return_fields_first() -> None:
    source = _read_agent("gpd-referee.md")

    assert_prompt_contracts(
        source,
        semantic_anchor(
            "referee completion routes through compact return profile",
            (
                "Use the `status-routing`, `fresh-continuation`, and `files-written-freshness` role kits",
                "gpd return skeleton --role referee --status <status>",
            ),
            match=MatchMode.CASEFOLD_NORMALIZED,
        ),
    )
    assert count_unfenced_heading(source, "## REVIEW COMPLETE") == 0
    assert count_unfenced_heading(source, "## REVIEW INCOMPLETE") == 0
    assert count_unfenced_heading(source, "## CHECKPOINT REACHED") == 0

    return_example = next(block for block in yaml_fence_bodies(source) if 'recommendation: "minor_revision"' in block)
    assert_prompt_contracts(
        return_example,
        machine_exact(
            "referee return example keeps base fields before review extensions",
            ("  status: completed", "  files_written:", '  recommendation: "minor_revision"'),
            mode=FragmentMode.ORDERED,
        ),
    )


def test_referee_late_loads_optional_review_protocol_detail() -> None:
    source = _read_agent("gpd-referee.md")
    playbook = (REFERENCES_DIR / "publication" / "referee-review-playbook.md").read_text(encoding="utf-8")
    boundary = (REFERENCES_DIR / "publication" / "publication-final-adjudication-boundary.md").read_text(
        encoding="utf-8"
    )

    assert "module_policy_summary" in source
    assert "referee.review_playbook" in source
    assert "referee.final_adjudication_boundary" in source
    assert "Initial Review Execution Detail" in playbook
    assert "Revision Review Success Criteria" in playbook
    assert "Final Report And Decision Alignment" in boundary
    assert "find GPD -name" not in source
    assert "Previous `REFEREE-REPORT` loaded and all issue IDs extracted." not in source


def test_project_researcher_uses_presentation_only_heading_mapping_and_base_fields_first() -> None:
    source = _read_agent("gpd-project-researcher.md")

    assert_prompt_contracts(
        source,
        machine_exact(
            "project researcher return fields",
            (
                "gpd_return:",
                "status: completed",
                "files_written:\n    - GPD/literature/SUMMARY.md",
                "confidence: HIGH",
            ),
        ),
        *semantic_concept(
            "project researcher typed status routing",
            required="Route on `gpd_return.status` per the status-routing role kit.",
            forbidden="Mapping: RESEARCH COMPLETE → completed, RESEARCH BLOCKED → blocked",
        ),
    )
    return_example = next(block for block in yaml_fence_bodies(source) if "  confidence: HIGH" in block)
    assert_prompt_contracts(
        return_example,
        machine_exact(
            "project researcher base fields precede confidence extension",
            ("  next_actions:", "  confidence: HIGH"),
            mode=FragmentMode.ORDERED,
        ),
    )


def test_plan_checker_uses_typed_status_and_drops_nested_return_payload_examples() -> None:
    source = _read_agent("gpd-plan-checker.md")
    return_protocol = (REFERENCES_DIR / "verification" / "plan-checker" / "checker-return-protocol.md").read_text(
        encoding="utf-8"
    )

    assert_prompt_contracts(
        source,
        semantic_anchor(
            "plan checker status routing uses gpd_return",
            (
                "The label examples in `checker-return-protocol.md` are UI only; the machine decision comes from `gpd_return.status`",
                "the machine decision comes from `gpd_return.status`",
            ),
            match=MatchMode.CASEFOLD_NORMALIZED,
        ),
        machine_exact(
            "plan checker recognized typed statuses",
            (
                "`completed` approves all fresh plans",
                "`checkpoint` returns explicit approved/blocked sets",
                "`failed` requires planner revision",
                "`blocked` escalates blocker-level issues",
            ),
        ),
    )
    assert_prompt_contracts(
        return_protocol,
        semantic_anchor(
            "plan checker protocol headings are presentation only",
            "Headings above are presentation only. Route on `gpd_return.status`",
            match=MatchMode.CASEFOLD_NORMALIZED,
        ),
    )
    assert count_unfenced_heading(source, "## VERIFICATION PASSED") == 0
    assert count_unfenced_heading(source, "## ISSUES FOUND") == 0

    return_example = next(block for block in yaml_fence_bodies(source) if "  approved_plans:" in block)
    assert_prompt_contracts(
        return_example,
        machine_exact(
            "plan checker base return fields precede approval extensions",
            ("  status: completed", "  files_written: []", "  approved_plans:"),
            mode=FragmentMode.ORDERED,
        ),
    )
    assert_prompt_contracts(
        source,
        machine_exact(
            "plan checker stale nested payload examples absent",
            (
                "contract_gate_summary:",
                "issues_found:",
                "escalation: null | {pattern, options}",
                "# Mapping: all_approved",
            ),
            mode=FragmentMode.ABSENT,
        ),
    )
