"""Assertions for respond-to-referees handoff and artifact-gate semantics."""

from __future__ import annotations

from pathlib import Path

import yaml

from gpd.core.child_handoff import ChildGateTuple, child_gate_tuple_from_payload
from tests.assertion_taxonomy_support import MatchMode, assert_prompt_contracts, semantic_anchor
from tests.workflow_authority_support import workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"


def _workflow() -> str:
    return workflow_authority_text(WORKFLOWS_DIR, "respond-to-referees")


def _yaml_blocks(source: str) -> list[dict]:
    blocks: list[dict] = []
    for block in source.split("```yaml")[1:]:
        yaml_text = block.split("```", 1)[0]
        payload = yaml.safe_load(yaml_text)
        if isinstance(payload, dict):
            blocks.append(payload)
    return blocks


def _child_gate(source: str, gate_id: str) -> ChildGateTuple:
    for payload in _yaml_blocks(source):
        child_gate = payload.get("child_gate")
        if isinstance(child_gate, dict) and child_gate.get("id") == gate_id:
            return child_gate_tuple_from_payload(payload)
    raise AssertionError(f"missing child gate {gate_id}")


def _aggregate_gate(source: str, gate_id: str) -> dict:
    for payload in _yaml_blocks(source):
        aggregate_gate = payload.get("aggregate_child_gate")
        if isinstance(aggregate_gate, dict) and aggregate_gate.get("id") == gate_id:
            return aggregate_gate
    raise AssertionError(f"missing aggregate child gate {gate_id}")


def _artifact_paths(gate: ChildGateTuple) -> tuple[str, ...]:
    return tuple(artifact.path for artifact in gate.expected_artifacts)


def _assert_semantic(source: str, label: str, *fragments: str) -> None:
    assert_prompt_contracts(
        source,
        semantic_anchor(label, fragments, match=MatchMode.CASEFOLD_NORMALIZED, context=label),
    )


def test_respond_to_referees_group_b_completion_requires_fresh_child_files_written_and_rejects_stale_edits() -> None:
    source = _workflow()
    gate = _child_gate(source, "respond_to_referees_revision_section")

    _assert_semantic(
        source,
        "respond-to-referees revision section return gate",
        "respond_to_referees_revision_section",
        "child_gate",
        "revised section",
        "RESPONSE_AUTHOR_PATH",
        "RESPONSE_REFEREE_PATH",
    )
    assert gate.role == "gpd-paper-writer"
    assert gate.required_status == "completed"
    assert _artifact_paths(gate) == (
        "${PAPER_DIR}/{resolved_section_file}",
        "${RESPONSE_AUTHOR_PATH}",
        "${RESPONSE_REFEREE_PATH}",
    )
    assert gate.allowed_roots == ("${PAPER_DIR}", "${selected_publication_root}", "${selected_review_root}")
    assert gate.freshness is not None
    assert gate.freshness.marker == "$REVISION_SECTION_HANDOFF_STARTED_AT"
    assert "gpd validate handoff-artifacts for revised section plus both response artifacts" in gate.validators
    assert "publication-response-writer-handoff.md frontmatter, round, and manuscript binding" in source
    _assert_semantic(
        source,
        "respond-to-referees section revision evidence",
        "target section",
        "revision markers",
        "substantive edits",
    )
    _assert_semantic(
        source,
        "respond-to-referees revision tuple reapplied first",
        "respond_to_referees_revision_section",
        "tuple first",
    )
    assert "stage-recovery-gate.md" in source
    _assert_semantic(
        source,
        "respond-to-referees mirrored section response failure",
        "section edits and tracker updates",
        "both fresh and consistent",
        "failed",
    )


def test_respond_to_referees_response_letter_generation_stays_file_backed_and_fresh_return_based() -> None:
    source = _workflow()
    gate = _aggregate_gate(source, "respond_to_referees_response_pair_current")

    assert gate["required_child_gates"] == ["respond_to_referees_revision_section for every launched Group B section"]
    assert gate["expected_artifacts"] == [
        "every required revised section under ${PAPER_DIR}",
        "${RESPONSE_AUTHOR_PATH}",
        "${RESPONSE_REFEREE_PATH}",
    ]
    assert any(
        all(fragment in validator for fragment in ("expected mirrored artifacts", "disk"))
        for validator in gate["validators"]
    )
    assert (
        "response frontmatter binds to the active manuscript path and review round when the subject is explicit"
        in source
    )
    assert (
        "Those two Markdown artifacts under selected GPD publication/review roots are the\nrequired outputs." in source
    )
    assert "canonical GPD-authored response artifacts live under the selected publication/review roots" in source
