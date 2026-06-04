"""Assertions for write-paper handoff and artifact-gate semantics."""

from __future__ import annotations

from pathlib import Path

import yaml

from gpd.core.child_handoff import ChildGateTuple, child_gate_tuple_from_payload
from tests.assertion_taxonomy_support import (
    MatchMode,
    assert_prompt_contracts,
    semantic_anchor,
    semantic_concept,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
STAGE_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows" / "write-paper"
RESPOND_STAGE_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows" / "respond-to-referees"
BOOTSTRAP = STAGE_DIR / "paper-bootstrap.md"
AUTHORING = STAGE_DIR / "authoring.md"
CONSISTENCY = STAGE_DIR / "consistency-references.md"
FINALIZATION = STAGE_DIR / "publication-review-finalization.md"
RESPONSE_AUTHORING = RESPOND_STAGE_DIR / "response-authoring.md"


def _child_gate_payload(source: str, gate_id: str) -> dict[object, object]:
    for block in source.split("```yaml")[1:]:
        yaml_text = block.split("```", 1)[0]
        payload = yaml.safe_load(yaml_text)
        if not isinstance(payload, dict):
            continue
        child_gate = payload.get("child_gate")
        if isinstance(child_gate, dict) and child_gate.get("id") == gate_id:
            return payload
    raise AssertionError(f"missing child gate {gate_id}")


def _child_gate(source: str, gate_id: str) -> ChildGateTuple:
    return child_gate_tuple_from_payload(_child_gate_payload(source, gate_id))


def _artifact_paths(gate: ChildGateTuple) -> tuple[str, ...]:
    return tuple(artifact.path for artifact in gate.expected_artifacts)


def _assert_fresh_files_written_gate(gate: ChildGateTuple, marker: str) -> None:
    assert gate.required_status == "completed"
    assert gate.freshness is not None
    assert gate.freshness.marker == marker
    assert gate.freshness.require_mtime_at_or_after_marker is True
    assert gate.freshness.preexisting_artifacts == "recovery_evidence_only"
    assert all(artifact.must_be_named_in_files_written for artifact in gate.expected_artifacts)
    assert gate.applicator.command == "none"
    assert gate.applicator.require_passed_true is False


def _assert_semantic(source: str, label: str, *fragments: str) -> None:
    assert_prompt_contracts(
        source,
        semantic_anchor(label, fragments, match=MatchMode.CASEFOLD_NORMALIZED, context=label),
    )


def _assert_absent(source: str, label: str, *fragments: str) -> None:
    assert_prompt_contracts(
        source,
        *semantic_concept(label, forbidden=fragments, match=MatchMode.CASEFOLD_NORMALIZED, context=label),
    )


def test_write_paper_writer_completion_requires_typed_status_files_written_and_disk_artifact() -> None:
    source = AUTHORING.read_text(encoding="utf-8")
    payload = _child_gate_payload(source, "write_paper_section_writer")
    gate = _child_gate(source, "write_paper_section_writer")

    assert "stage-recovery-gate.md" in source
    assert payload["child_gate"]["return_profile"] == "paper_writer"
    assert gate.return_profile == "paper_writer"
    assert gate.role == "gpd-paper-writer"
    assert _artifact_paths(gate) == ("${PAPER_DIR}/{section_path}.tex",)
    assert gate.allowed_roots == ("${PAPER_DIR}",)
    _assert_fresh_files_written_gate(gate, "$SECTION_WRITER_HANDOFF_STARTED_AT")
    assert any(
        "--require-status completed --require-files-written --fresh-after $SECTION_WRITER_HANDOFF_STARTED_AT"
        in validator
        for validator in gate.validators
    )
    _assert_semantic(
        source,
        "write-paper resumed tex files are not fresh child success",
        "existing `.tex` files",
        "resumed wave current",
        "not fresh child handoff success",
    )
    _assert_semantic(
        source,
        "write-paper section completion requires emitted tex gate",
        "section authoring is complete",
        "emitted `.tex` path",
        "passes",
    )


def test_write_paper_bibliography_completion_requires_typed_status_files_written_and_disk_artifacts() -> None:
    source = CONSISTENCY.read_text(encoding="utf-8")
    payload = _child_gate_payload(source, "write_paper_bibliographer")
    gate = _child_gate(source, "write_paper_bibliographer")

    assert payload["child_gate"]["return_profile"] == "bibliographer"
    assert gate.return_profile == "bibliographer"
    assert gate.role == "gpd-bibliographer"
    assert _artifact_paths(gate) == (
        "${PAPER_DIR}/CITATION-AUDIT.md",
        "GPD/references-status.json",
        "{ACTIVE_BIBLIOGRAPHY_PATH} only when changed",
        "${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json after paper-build refresh",
    )
    assert gate.allowed_roots == ("${PAPER_DIR}", "GPD")
    _assert_fresh_files_written_gate(gate, "$BIBLIO_HANDOFF_STARTED_AT")
    assert any(
        all(fragment in validator for fragment in ("bibliography_audit_clean", "strict review"))
        for validator in gate.validators
    )
    _assert_semantic(
        source,
        "write-paper bibliography typed return",
        "typed `gpd_return`",
        "write_paper_bibliographer",
        "child_gate",
    )
    _assert_semantic(
        source,
        "write-paper bibliography files-written policy",
        "CITATION-AUDIT.md",
        "references-status.json",
        "gpd_return.files_written",
        "ACTIVE_BIBLIOGRAPHY_PATH",
        "only when",
        "changed",
    )
    _assert_absent(
        source,
        "write-paper bibliography stale active bibliography wording",
        "and `{ACTIVE_BIBLIOGRAPHY_PATH}` only if the bibliography file changed",
    )
    _assert_semantic(
        source,
        "write-paper bibliography path label",
        "Bibliography",
        "ACTIVE_BIBLIOGRAPHY_PATH",
        "resolved active bibliography",
    )
    assert "${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json after paper-build refresh" in source
    _assert_semantic(source, "write-paper bibliography strict review gate", "bibliography_audit_clean", "strict review")
    _assert_semantic(source, "write-paper older audit recovery evidence", "older audit files", "recovery evidence")


def test_write_paper_response_artifact_completion_requires_typed_status_files_written_and_disk_artifacts() -> None:
    source = FINALIZATION.read_text(encoding="utf-8")
    payload = _child_gate_payload(source, "write_paper_response_pair")
    gate = _child_gate(source, "write_paper_response_pair")

    assert "stage-recovery-gate.md" in source
    assert payload["child_gate"]["return_profile"] == "paper_writer"
    assert gate.return_profile == "paper_writer"
    assert gate.role == "gpd-paper-writer"
    assert _artifact_paths(gate) == (
        "${selected_publication_root}/AUTHOR-RESPONSE{round_suffix}.md",
        "${selected_review_root}/REFEREE_RESPONSE{round_suffix}.md",
    )
    assert gate.allowed_roots == ("${selected_publication_root}", "${selected_review_root}")
    _assert_fresh_files_written_gate(gate, "$RESPONSE_HANDOFF_STARTED_AT")
    assert "publication-response-writer-handoff.md frontmatter, round, and manuscript binding" in source
    _assert_semantic(
        source,
        "write-paper response-pair callsite tuple",
        "response-pair completion",
        "callsite tuple",
        "both paths",
    )


def test_respond_to_referees_revision_section_completion_keeps_fresh_response_pair_gate() -> None:
    source = RESPONSE_AUTHORING.read_text(encoding="utf-8")
    payload = _child_gate_payload(source, "respond_to_referees_revision_section")
    gate = _child_gate(source, "respond_to_referees_revision_section")

    assert payload["child_gate"]["return_profile"] == "response_writer"
    assert gate.return_profile == "executor"
    assert gate.role == "gpd-paper-writer"
    assert _artifact_paths(gate) == (
        "${PAPER_DIR}/{resolved_section_file}",
        "${RESPONSE_AUTHOR_PATH}",
        "${RESPONSE_REFEREE_PATH}",
    )
    assert gate.allowed_roots == ("${PAPER_DIR}", "${selected_publication_root}", "${selected_review_root}")
    _assert_fresh_files_written_gate(gate, "$REVISION_SECTION_HANDOFF_STARTED_AT")
    assert "affected comment block updated in both response artifacts" in gate.validators
    _assert_semantic(
        source,
        "respond-to-referees stale response pair is not success",
        "stale drafts or one-sided files do not count",
    )
    _assert_semantic(
        source,
        "respond-to-referees selected roots own response pair",
        "Use `selected_publication_root` / `selected_review_root`",
        "Do not write",
        "beside `${PAPER_DIR}`",
    )


def test_write_paper_bootstrap_contract_is_explicit_about_project_and_bounded_external_lanes() -> None:
    source = BOOTSTRAP.read_text(encoding="utf-8")

    _assert_semantic(
        source,
        "write-paper bootstrap strict preflight fields",
        "publication_subject",
        "manuscript",
        "publication_bootstrap",
        "strict preflight",
    )
    _assert_semantic(source, "write-paper bootstrap resolved manuscript root", "resolved manuscript root")
    assert "project_backed`: current GPD project, including managed manuscripts at" in source
    assert "`GPD/publication/{subject_slug}/manuscript`" in source
    _assert_semantic(
        source,
        "write-paper external intake uses managed subject handoff",
        "external_authoring_intake",
        "strict command preflight",
        "managed subject handoff",
    )
    assert "`GPD/publication/{subject_slug}/intake/` holds intake/provenance state only" in source
    assert (
        "bind `PAPER_DIR` to the only\nmanuscript/build root at `GPD/publication/{subject_slug}/manuscript`" in source
    )
    assert "no generic folder mining or arbitrary external-manuscript discovery" in source
    _assert_absent(
        source,
        "write-paper stale external manuscript flow wording",
        "do not invent an external-manuscript `write-paper` flow or relax the project-required contract",
    )


def test_write_paper_external_lane_stops_at_manuscript_root_handoff_and_routes_to_peer_review() -> None:
    source = FINALIZATION.read_text(encoding="utf-8")

    _assert_semantic(
        source,
        "write-paper external lane avoids embedded staged panel",
        "External-authoring lane",
        "embedded staged panel",
    )
    _assert_semantic(
        source,
        "write-paper external review parity deferred",
        "review parity",
        "bounded external-authoring lane",
        "deferred",
    )
    assert "`${PAPER_DIR}/PAPER-CONFIG.json`" in source
    assert "`${PAPER_DIR}/ARTIFACT-MANIFEST.json`" in source
    assert "`${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json`" in source
    assert "`${PAPER_DIR}/reproducibility-manifest.json`" in source
    assert "route the user to standalone `gpd:peer-review`" in source
    assert "do not recommend `gpd:arxiv-submission` directly from this lane" in source
