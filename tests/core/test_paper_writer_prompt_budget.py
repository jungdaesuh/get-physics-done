"""Prompt budget assertions for the `gpd-paper-writer` agent surface."""

from __future__ import annotations

from pathlib import Path

from tests.prompt_metrics_support import expanded_prompt_text, measure_prompt_surface

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "src" / "gpd" / "agents"
SOURCE_ROOT = REPO_ROOT / "src" / "gpd"
PATH_PREFIX = "/runtime/"
REFERENCES_DIR = SOURCE_ROOT / "specs" / "references" / "publication"


def test_gpd_paper_writer_prompt_stays_within_expected_budget_and_keeps_contract_paths_lightweight() -> None:
    path = AGENTS_DIR / "gpd-paper-writer.md"
    source = path.read_text(encoding="utf-8")
    cookbook = (REFERENCES_DIR / "paper-writer-cookbook.md").read_text(encoding="utf-8")
    handoff = (REFERENCES_DIR / "publication-response-writer-handoff.md").read_text(encoding="utf-8")
    metrics = measure_prompt_surface(path, src_root=SOURCE_ROOT, path_prefix=PATH_PREFIX)
    expanded = expanded_prompt_text(path, src_root=SOURCE_ROOT, path_prefix=PATH_PREFIX)

    assert metrics.raw_include_count == 0
    assert len(source) < 27_300
    assert metrics.expanded_line_count < 3_400
    assert metrics.expanded_char_count < 160_000
    assert "gpd return skeleton --role paper_writer --status <status>" in source
    assert "section_name" in source
    assert "Report section outputs against the resolved manuscript root" in source
    assert "external_authoring_intake" in source
    assert "Missing `CONFIDENCE:` tags are a calibration warning, not a writing block." in source
    assert "{GPD_INSTALL_DIR}/templates/notation-glossary.md" in source
    assert "{GPD_INSTALL_DIR}/templates/latex-preamble.md" in source
    assert "{GPD_INSTALL_DIR}/templates/paper/author-response.md" in source
    assert "{GPD_INSTALL_DIR}/references/shared/shared-protocols.md" in source
    assert "{GPD_INSTALL_DIR}/references/orchestration/agent-infrastructure.md" in source
    assert "{GPD_INSTALL_DIR}/references/publication/paper-writer-cookbook.md" in source
    assert "{GPD_INSTALL_DIR}/references/publication/figure-generation-templates.md" in source
    assert "{GPD_INSTALL_DIR}/references/publication/publication-pipeline-modes.md" in source
    assert "paper_writer.handoff_audit" in source
    assert "protocol_bundle_load_manifest" in source
    for token in ("before", "domain", "method", "judgment", "tensor-network", "caveats"):
        assert token in source
    assert "Research-To-Paper Handoff Detail" in cookbook
    assert "Confidence-To-Language Mapping" in cookbook
    assert "Response Pair Detail" in handoff
    assert "ls GPD/phases/*-*/*-SUMMARY.md" not in source
    assert "@{GPD_INSTALL_DIR}/references/shared/shared-protocols.md" not in source
    assert "@{GPD_INSTALL_DIR}/references/orchestration/agent-infrastructure.md" not in source
    assert "@{GPD_INSTALL_DIR}/templates/notation-glossary.md" not in source
    assert "@{GPD_INSTALL_DIR}/templates/latex-preamble.md" not in source
    assert "@{GPD_INSTALL_DIR}/templates/paper/author-response.md" not in source
    assert "# Notation Glossary Template" not in expanded
    assert "# LaTeX Preamble Template" not in expanded
    assert "# Author Response Template" not in expanded
    assert "# Tensor Networks" not in expanded
