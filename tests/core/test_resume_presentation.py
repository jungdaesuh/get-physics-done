from __future__ import annotations

from gpd.core.recovery_advice import RecoveryAdvice
from gpd.core.resume_presentation import (
    public_resume_origin_family,
    resume_augmented_payload,
    resume_candidate_notes,
    resume_candidate_origin,
    resume_candidate_rerun_anchor,
    resume_result_summary,
    resume_status_label,
    resume_status_message,
)


def test_resume_status_message_and_labels_are_core_owned() -> None:
    payload = {
        "planning_exists": True,
        "state_exists": True,
        "roadmap_exists": True,
        "project_exists": True,
        "project_root_auto_selected": True,
    }
    advice = RecoveryAdvice(status="bounded-segment")

    assert resume_status_label("bounded-segment") == "Bounded segment"
    assert resume_status_message(payload, recovery_advice=advice) == (
        "A bounded segment is resumable from an auto-selected recent project."
    )


def test_resume_candidate_projection_helpers_match_current_private_cli_contract() -> None:
    assert resume_candidate_rerun_anchor({"last_result_id": "R-bridge-01"}) == "rerun anchor: R-bridge-01"

    notes = resume_candidate_notes(
        {
            "last_result_id": "R-bridge-01",
            "last_result": {
                "id": "R-bridge-01",
                "description": "Benchmark reproduction",
                "equation": "F = ma",
                "verified": True,
            },
        },
        active_execution=None,
        current_execution=None,
    )
    assert "Benchmark reproduction" in notes
    assert "R-bridge-01" in notes

    origin, label = resume_candidate_origin(
        {"source": "current_execution"},
        active_execution={"resume_file": "GPD/phases/02/.continue-here.md"},
        current_execution={"resume_file": "GPD/phases/02/alternate.md"},
    )
    assert origin == "canonical_continuation"
    assert label == "canonical continuation; current execution points at a different handoff file"


def test_resume_result_summary_keeps_verified_marker_and_optional_id() -> None:
    result = {
        "id": "result-1",
        "description": "Bridge equation",
        "equation": "R = A + B",
        "verified": True,
    }

    assert resume_result_summary(result) == "Bridge equation [R = A + B] (result-1) · verified"
    assert resume_result_summary(result, include_id=False) == "Bridge equation [R = A + B] · verified"


def test_resume_augmented_payload_normalizes_public_origins_and_drops_malformed_candidates() -> None:
    resume_file = "GPD/phases/01/.continue-here.md"
    payload = {
        "planning_exists": True,
        "state_exists": True,
        "roadmap_exists": True,
        "project_exists": True,
        "resume_candidates": [
            {
                "source": "handoff_resume_file",
                "status": "handoff",
                "resume_file": resume_file,
                "resumable": False,
                "kind": "continuity_handoff",
                "origin": "continuation.handoff",
                "resume_pointer": resume_file,
            },
            "not-a-candidate",
        ],
        "has_live_execution": False,
        "active_resume_kind": "continuity_handoff",
        "active_resume_origin": "continuation.handoff",
        "active_resume_pointer": resume_file,
        "active_execution_segment": {"backend": "private"},
    }
    advice = RecoveryAdvice(
        status="session-handoff",
        active_resume_origin="continuation.handoff",
        active_resume_kind="continuity_handoff",
        active_resume_pointer=resume_file,
    )

    augmented = resume_augmented_payload(payload, recovery_advice=advice)

    assert "active_execution_segment" not in augmented
    assert augmented["active_resume_origin"] == "canonical_continuation"
    assert augmented["recovery_advice"]["active_resume_origin"] == "canonical_continuation"
    assert augmented["resume_candidates"] == [
        {
            "source": "handoff_resume_file",
            "status": "handoff",
            "resume_file": resume_file,
            "resumable": False,
            "kind": "continuity_handoff",
            "origin": "canonical_continuation",
            "resume_pointer": resume_file,
        }
    ]
    assert augmented["recovery_candidates"][0]["origin"] == "canonical_continuation"
    assert augmented["primary_recovery_target"]["target"].endswith("GPD/phases/01/.continue-here.md")


def test_public_resume_origin_family_preserves_derived_execution_without_canonical_active_segment() -> None:
    assert public_resume_origin_family("current_execution", current_execution={"resume_file": "next.md"}) == (
        "derived_execution_head"
    )
