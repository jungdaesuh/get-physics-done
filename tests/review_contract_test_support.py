"""Expected review-contract surfaces shared by review command tests."""

from __future__ import annotations

PEER_REVIEW_COMMON_PREFLIGHT_CHECKS = [
    "command_context",
    "manuscript",
    "manuscript_proof_review",
]
PROJECT_BACKED_PEER_REVIEW_CONDITIONAL = {
    "when": "project-backed manuscript review",
    "required_outputs": [],
    "required_evidence": [
        "phase summaries or milestone digest",
        "verification reports",
        "manuscript-root bibliography audit",
        "manuscript-root artifact manifest",
        "manuscript-root reproducibility manifest",
        "manuscript-root publication artifacts",
    ],
    "blocking_conditions": [
        "missing project state",
        "missing roadmap",
        "missing conventions",
        "no research artifacts",
    ],
    "preflight_checks": [
        "project_state",
        "roadmap",
        "conventions",
        "research_artifacts",
        "verification_reports",
        "artifact_manifest",
        "bibliography_audit",
        "bibliography_audit_clean",
        "reproducibility_manifest",
        "reproducibility_ready",
    ],
    "blocking_preflight_checks": [
        "project_state",
        "roadmap",
        "conventions",
        "research_artifacts",
        "verification_reports",
        "artifact_manifest",
        "bibliography_audit",
        "bibliography_audit_clean",
        "reproducibility_manifest",
        "reproducibility_ready",
    ],
    "stage_artifacts": [],
}
THEOREM_BEARING_PEER_REVIEW_CONDITIONAL = {
    "when": "theorem-bearing claims are present",
    "required_outputs": ["${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md"],
    "required_evidence": [],
    "blocking_conditions": [],
    "preflight_checks": [],
    "blocking_preflight_checks": [],
    "stage_artifacts": ["${REVIEW_ROOT}/PROOF-REDTEAM{round_suffix}.md"],
}
