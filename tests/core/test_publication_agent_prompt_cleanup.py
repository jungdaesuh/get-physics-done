"""Focused assertions for publication-agent prompt cleanup."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PAPER_WRITER = REPO_ROOT / "src/gpd/agents/gpd-paper-writer.md"
BIBLIOGRAPHER = REPO_ROOT / "src/gpd/agents/gpd-bibliographer.md"
PUBLICATION_REFS = REPO_ROOT / "src/gpd/specs/references/publication"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _gpd_return_block(path: Path) -> str:
    source = _read(path)
    return source.split("gpd_return:\n", 1)[1].split("```", 1)[0]


def test_paper_writer_prompt_uses_typed_status_and_one_shot_checkpoint_language() -> None:
    source = _read(PAPER_WRITER)

    assert "continuation-boundary.md" in source
    assert "checkpoint handoffs" in source
    assert "do not wait for user input inside the current run" not in source
    assert "Use `gpd_return.status: checkpoint` as the control surface." in source
    assert "gpd return skeleton --role paper_writer --status <status>" in source
    assert "The `## CHECKPOINT REACHED` heading below is presentation only." not in source
    assert "return with CHECKPOINT status" not in source
    assert "Return WRITING BLOCKED." not in source


def test_paper_writer_return_example_includes_complete_base_fields_and_keeps_extensions() -> None:
    source = _read(PAPER_WRITER)
    envelope = _gpd_return_block(PAPER_WRITER)

    assert (
        "Report section outputs against the resolved manuscript root rather than a hardcoded `paper/` subtree."
        in source
    )
    assert (
        "Use the actual resolved manuscript-root path in `files_written`, for example `paper/results.tex` or `GPD/publication/{subject_slug}/manuscript/results.tex`."
        in source
    )
    assert "  status: completed" in envelope
    assert "  files_written:\n    - paper/results.tex" in envelope
    assert "  issues: []" in envelope
    assert '  next_actions:\n    - "gpd:paper-build"' in envelope
    assert 'section_name: "Results"' in envelope
    assert envelope.index("  next_actions:") < envelope.index('  section_name: "Results"')


def test_paper_writer_late_loads_optional_publication_protocol_detail() -> None:
    source = _read(PAPER_WRITER)
    cookbook = _read(PUBLICATION_REFS / "paper-writer-cookbook.md")
    response_handoff = _read(PUBLICATION_REFS / "publication-response-writer-handoff.md")

    assert "module_policy_summary" in source
    assert "paper_writer.handoff_audit" in source
    assert "Response-pair handoff" in source
    assert "Research-To-Paper Handoff Detail" in cookbook
    assert "Missing Citation Protocol" in cookbook
    assert "Response Pair Detail" in response_handoff
    assert "Result completeness audit:" not in source
    assert "%% CITATIONS NEEDED" not in source


def test_bibliographer_prompt_uses_typed_status_and_deferred_base_fields() -> None:
    source = _read(BIBLIOGRAPHER)
    envelope = _gpd_return_block(BIBLIOGRAPHER)

    assert (
        "Use agent-infrastructure.md for checkpoint ownership, return-envelope base fields, and one-shot handoff semantics."
        in source
    )
    assert "Route on `gpd_return.status`, not presentation headings." in source
    assert "Use `completed` when the bibliography task finished" in source
    assert "Use `gpd_return.status: checkpoint` as the control surface." not in source
    assert "Return BIBLIOGRAPHY UPDATED or CITATION ISSUES FOUND" not in source
    assert "  status: completed" in envelope
    assert "  files_written:\n    - paper/references.bib\n    - GPD/references-status.json" in envelope
    assert "  issues: []" in envelope
    assert "  next_actions: []" in envelope
    assert "entries_added: 3" in envelope
    assert envelope.index("  next_actions: []") < envelope.index("  entries_added: 3")
