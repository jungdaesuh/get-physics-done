"""Focused validation for workflow-visible ``gpd_return`` examples."""

from __future__ import annotations

from pathlib import Path

from tests.return_example_support import (
    GpdReturnExample,
    extract_gpd_return_examples,
    validated_gpd_return_examples,
)
from tests.workflow_authority_support import STAGED_WORKFLOW_AUTHORITY_NAMES, workflow_authority_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "src" / "gpd" / "specs" / "workflows"
EXECUTION_REFERENCES_DIR = REPO_ROOT / "src/gpd/specs/references/execution"


def _workflow_gpd_return_examples(path: Path) -> list[GpdReturnExample]:
    if path.parent == WORKFLOWS_DIR and path.stem in STAGED_WORKFLOW_AUTHORITY_NAMES:
        text = workflow_authority_text(WORKFLOWS_DIR, path.stem)
    else:
        text = path.read_text(encoding="utf-8")
    return extract_gpd_return_examples(text, source_name=path.name)


def _validated_workflow_return_examples(path: Path, *, expected_count: int) -> list[dict[str, object]]:
    examples = _workflow_gpd_return_examples(path)
    assert len(examples) == expected_count

    return validated_gpd_return_examples(
        "\n\n".join(example.markdown for example in examples),
        source_name=path.name,
        require_required_fields=True,
    )


def test_execute_plan_defers_visible_return_examples_to_completion_reference() -> None:
    assert _workflow_gpd_return_examples(WORKFLOWS_DIR / "execute-plan.md") == []

    completion = EXECUTION_REFERENCES_DIR / "executor-completion.md"
    examples = extract_gpd_return_examples(completion, source_name=completion.name)
    assert len(examples) == 2
    envelopes = validated_gpd_return_examples(completion, source_name=completion.name, require_required_fields=True)

    assert any(envelope["status"] == "completed" for envelope in envelopes)
    assert any(
        envelope["status"] == "checkpoint"
        and "state_updates" in envelope
        and "contract_updates" in envelope
        and "decisions" in envelope
        and "blockers" in envelope
        and "continuation_update" in envelope
        for envelope in envelopes
    )
    assert "gpd apply-return-updates" in completion.read_text(encoding="utf-8")


def test_map_research_visible_return_example_is_a_complete_valid_envelope() -> None:
    [envelope] = _validated_workflow_return_examples(WORKFLOWS_DIR / "map-research.md", expected_count=1)

    assert envelope["status"] == "completed"
    assert envelope["files_written"] == ["GPD/research-map/FORMALISM.md", "GPD/research-map/REFERENCES.md"]
    assert envelope["focus"] == "theory"
