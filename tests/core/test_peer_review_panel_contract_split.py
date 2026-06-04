from __future__ import annotations

import json
from pathlib import Path

from gpd.adapters.install_utils import parse_at_include_path
from gpd.core.workflow_staging import validate_workflow_stage_manifest_payload

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_ROOT = REPO_ROOT / "src" / "gpd" / "specs"
WORKFLOWS_DIR = SPEC_ROOT / "workflows"
PANEL_CONTRACT = SPEC_ROOT / "references" / "publication" / "peer-review-panel.md"
PANEL_PLAYBOOK = SPEC_ROOT / "references" / "publication" / "peer-review-panel-playbook.md"


def _load_peer_review_manifest() -> object:
    return validate_workflow_stage_manifest_payload(
        json.loads((WORKFLOWS_DIR / "peer-review-stage-manifest.json").read_text(encoding="utf-8")),
        expected_workflow_id="peer-review",
    )


def _canonical_include_relpath(include_path: str) -> str:
    if include_path.startswith("{GPD_INSTALL_DIR}/"):
        return include_path.removeprefix("{GPD_INSTALL_DIR}/")
    return include_path


def _unfenced_raw_includes(text: str) -> tuple[str, ...]:
    includes: list[str] = []
    active_fence_marker: str | None = None

    for line in text.splitlines():
        stripped = line.strip()
        fence_marker = None
        if stripped.startswith("```"):
            fence_marker = "```"
        elif stripped.startswith("~~~"):
            fence_marker = "~~~"

        if fence_marker is not None:
            if active_fence_marker is None:
                active_fence_marker = fence_marker
            elif active_fence_marker == fence_marker:
                active_fence_marker = None
            continue
        if active_fence_marker is not None:
            continue

        include_path = parse_at_include_path(stripped)
        if include_path is not None:
            includes.append(_canonical_include_relpath(include_path))

    return tuple(includes)


def test_peer_review_panel_contract_is_compact_index_and_playbook_is_lazy_rubric() -> None:
    contract = PANEL_CONTRACT.read_text(encoding="utf-8")
    playbook = PANEL_PLAYBOOK.read_text(encoding="utf-8")
    manifest = _load_peer_review_manifest()

    assert len(contract) < 9_000
    assert "# Peer Review Panel Contract" in contract
    assert "Stage And Artifact Index" in contract
    assert "${REVIEW_ROOT}/CLAIMS{round_suffix}.json" in contract
    assert "${REVIEW_ROOT}/STAGE-interestingness{round_suffix}.json" in contract
    assert "${REVIEW_ROOT}/REVIEW-LEDGER{round_suffix}.json" in contract
    assert "Stage 6 Read-Only Boundary" in contract
    assert "Do not treat `claim_kind: claim` as theorem-bearing by default." in contract
    assert "Recommendation Guardrails" not in contract
    assert "Journal Calibration" not in contract

    assert "# Peer Review Panel Playbook" in playbook
    assert "Recommendation Guardrails" in playbook
    assert "Claim Discipline" in playbook
    assert "Journal Calibration" in playbook
    assert "does not define artifact schemas" in playbook

    panel_stage = manifest.stage("panel_stages")
    final_adjudication = manifest.stage("final_adjudication")
    panel_conditionals = {
        authority for conditional in panel_stage.conditional_authorities for authority in conditional.authorities
    }
    assert "references/publication/peer-review-panel.md" in panel_stage.loaded_authorities
    assert "references/publication/peer-review-panel-playbook.md" not in panel_stage.loaded_authorities
    assert "references/publication/peer-review-panel-playbook.md" in panel_conditionals
    assert "references/publication/stage-recovery-gate.md" not in panel_stage.loaded_authorities
    assert "references/verification/core/proof-redteam-protocol.md" not in panel_stage.loaded_authorities
    assert "references/publication/peer-review-panel-playbook.md" not in final_adjudication.loaded_authorities
    assert "references/publication/peer-review-panel-playbook.md" in final_adjudication.must_not_eager_load
    assert "references/publication/peer-review-panel.md" not in final_adjudication.loaded_authorities
    assert "references/publication/peer-review-panel.md" in final_adjudication.must_not_eager_load
    assert final_adjudication.conditional_authorities[0].authorities == ("references/publication/peer-review-panel.md",)


def test_peer_review_stage_files_do_not_raw_include_manifest_loaded_authorities() -> None:
    manifest = _load_peer_review_manifest()
    offenders: list[str] = []

    for stage_id in ("panel_stages", "final_adjudication"):
        stage = manifest.stage(stage_id)
        loaded_authorities = set(stage.loaded_authorities)
        for mode_path in stage.mode_paths:
            mode_text = (SPEC_ROOT / mode_path).read_text(encoding="utf-8")
            for include_relpath in _unfenced_raw_includes(mode_text):
                if include_relpath in loaded_authorities:
                    offenders.append(f"{stage.id}:{mode_path}:{include_relpath}")

    assert offenders == []
