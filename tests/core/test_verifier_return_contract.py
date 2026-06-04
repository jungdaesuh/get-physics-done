"""Focused assertions for the verifier return-contract surface."""

from __future__ import annotations

from pathlib import Path

AGENTS_DIR = Path(__file__).resolve().parents[2] / "src" / "gpd" / "agents"


def _read_verifier_prompt() -> str:
    return (AGENTS_DIR / "gpd-verifier.md").read_text(encoding="utf-8")


def test_verifier_prompt_keeps_the_canonical_return_contract_visible() -> None:
    verifier = _read_verifier_prompt()

    required_fragments = (
        "gpd return skeleton --role verifier --status <status>",
        "Role kits own status routing",
        "Local status semantics:",
        "- **completed**",
        "- **checkpoint**",
        "- **blocked**",
        "- **failed**",
        "status: completed",
        "files_written:\n    - GPD/phases/03-spectral-form-factor/03-VERIFICATION.md",
        "issues: []",
        'next_actions:\n    - "gpd:execute-phase 04"',
        "the return file list is fail-closed",
        "include only files that genuinely landed on disk in this run",
        "Non-completed returns may use `[]`",
    )
    missing = [fragment for fragment in required_fragments if fragment not in verifier]
    assert missing == []


def test_verifier_prompt_surfaces_schema_sources_before_the_machine_readable_return_envelope() -> None:
    verifier = _read_verifier_prompt()
    envelope_marker = "### Machine-Readable Return Envelope"
    schema_fragments = (
        "templates/verification-report.md",
        "templates/contract-results-schema.md",
        "references/shared/canonical-schema-discipline.md",
        "## Create VERIFICATION.md",
    )

    envelope_index = verifier.index(envelope_marker)
    positions = [verifier.index(fragment) for fragment in schema_fragments]
    assert all(position < envelope_index for position in positions)
