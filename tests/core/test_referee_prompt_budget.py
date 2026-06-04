"""Prompt budget assertions for the `gpd-referee` agent surface."""

from __future__ import annotations

from pathlib import Path

from tests.prompt_metrics_support import expanded_prompt_text, measure_prompt_surface

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "src" / "gpd" / "agents"
SOURCE_ROOT = REPO_ROOT / "src" / "gpd"
PATH_PREFIX = "/runtime/"
REFERENCES_DIR = SOURCE_ROOT / "specs" / "references" / "publication"


def test_gpd_referee_prompt_stays_within_expected_budget() -> None:
    referee = (AGENTS_DIR / "gpd-referee.md").read_text(encoding="utf-8")
    metrics = measure_prompt_surface(
        AGENTS_DIR / "gpd-referee.md",
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )

    assert len(referee) < 30_300
    assert metrics.raw_include_count == 0
    assert metrics.expanded_line_count < 800
    assert metrics.expanded_char_count < 50_000


def test_gpd_referee_prompt_uses_return_role_profile_without_losing_stage6_boundary() -> None:
    referee = (AGENTS_DIR / "gpd-referee.md").read_text(encoding="utf-8")

    assert "status-routing" in referee
    assert "fresh-continuation" in referee
    assert "files-written-freshness" in referee
    assert "gpd return skeleton --role referee --status <status>" in referee
    assert "Checkpoint ownership is orchestrator-side" not in referee
    assert "fresh continuation handoff" not in referee
    assert "Preexisting files are stale and do not count." not in referee

    assert "Stage 6 writable allowlist" in referee
    assert "${selected_publication_root}/REFEREE-REPORT{round_suffix}.md" in referee
    assert "${selected_publication_root}/REFEREE-REPORT{round_suffix}.tex" in referee
    assert "${selected_review_root}/REVIEW-LEDGER{round_suffix}.json" in referee
    assert "${selected_review_root}/REFEREE-DECISION{round_suffix}.json" in referee
    assert "${selected_publication_root}/CONSISTENCY-REPORT.md" in referee
    assert (
        "Treat upstream `CLAIMS{round_suffix}.json`, `STAGE-*.json`, and "
        "`PROOF-REDTEAM{round_suffix}.md` artifacts as read-only evidence."
        in referee
    )
    assert "proof-redteam clearance" in referee
    assert "`blocked`: unrecoverable review-state or upstream staged-review integrity failure" in referee
    assert "`failed`: partial review because available evidence is insufficient" in referee
    assert "Never issue `minor_revision`" in referee


def test_gpd_referee_prompt_keeps_publication_path_mentions_without_eager_schema_expansion() -> None:
    referee = (AGENTS_DIR / "gpd-referee.md").read_text(encoding="utf-8")
    playbook = (REFERENCES_DIR / "referee-review-playbook.md").read_text(encoding="utf-8")
    expanded = expanded_prompt_text(
        AGENTS_DIR / "gpd-referee.md",
        src_root=SOURCE_ROOT,
        path_prefix=PATH_PREFIX,
    )

    assert "references/publication/peer-review-panel.md" in referee
    assert "references/publication/referee-review-playbook.md" in referee
    assert "templates/paper/review-ledger-schema.md" in referee
    assert "templates/paper/referee-decision-schema.md" in referee
    assert "templates/paper/referee-report.tex" in referee
    assert "full Markdown skeleton" in referee
    assert "referee.review_playbook" in referee
    assert "referee.final_adjudication_boundary" in referee
    assert "Initial Review Execution Detail" in playbook
    assert "Claim And Physics Audit Detail" in playbook
    assert "Revision Review Success Criteria" in playbook
    assert "Referee Report Template" in playbook
    assert "Anti-Pattern Examples" in playbook
    assert "Revision Report Template" in playbook
    assert "find GPD -name" not in referee
    assert "Referee Report Template" not in referee
    assert "Anti-Pattern Examples" not in referee
    assert "Revision Report Template" not in referee
    assert "Peer Review Panel Protocol" not in expanded
    assert "Referee Review Playbook" not in expanded
    assert "Review Ledger Schema" not in expanded
    assert "Referee Decision Schema" not in expanded
    assert "Referee Report Template" not in expanded
