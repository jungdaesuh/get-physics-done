"""Prompt-visibility assertions for the `gpd-check-proof` agent surface."""

from __future__ import annotations

from pathlib import Path

from gpd.adapters.install_utils import expand_at_includes

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "src" / "gpd" / "agents"
SPEC_ROOT = REPO_ROOT / "src" / "gpd" / "specs"


def _read() -> str:
    return (AGENTS_DIR / "gpd-check-proof.md").read_text(encoding="utf-8")


def _expanded() -> str:
    return expand_at_includes(_read(), SPEC_ROOT, "/runtime/")


def test_gpd_check_proof_prompts_surface_direct_proof_contract_references() -> None:
    source = _read()

    assert "gpd proof-redteam skeleton" in source
    assert "gpd validate proof-redteam" in source
    assert "helper-owned frontmatter" in source
    assert "Do not hand-author or reflow proof-redteam YAML." in source
    assert "Passed proof-redteam frontmatter is helper/finalizer-owned" in source
    assert "do not hand-author `status: passed` YAML" in source
    assert "{GPD_INSTALL_DIR}/templates/proof-redteam-schema.md" in source
    assert "{GPD_INSTALL_DIR}/references/verification/core/proof-redteam-protocol.md" in source
    assert "@{GPD_INSTALL_DIR}/references/publication/peer-review-panel.md" not in source


def test_gpd_check_proof_prompt_does_not_request_hand_authored_passed_yaml() -> None:
    source = _read()

    assert "hand-author passed proof YAML" not in source
    assert "hand-authored passed proof YAML" not in source
    assert "hand-author `status: passed` YAML" in source
    assert "return blocked" in source


def test_gpd_check_proof_prompt_no_longer_inlines_the_publication_panel() -> None:
    expanded = _expanded()

    assert "Peer Review Panel Protocol" not in expanded
    assert "Six-Agent Panel" not in expanded
    assert "Stage 3. Mathematical Soundness" not in expanded
