"""Shared staged-context field-name catalogs.

The constants in this module are string-only field families. Keep manifest
loading, stage ordering, and runtime payload builders in their existing owners.
"""

from __future__ import annotations

PROJECT_CONTRACT_GATE_FIELDS = frozenset(
    {
        "project_contract",
        "project_contract_gate",
        "project_contract_load_info",
        "project_contract_validation",
    }
)
STRUCTURED_STATE_FIELDS = frozenset(
    {
        "state_load_source",
        "state_integrity_issues",
        "convention_lock",
        "convention_lock_count",
        "intermediate_results",
        "intermediate_result_count",
        "approximations",
        "approximation_count",
        "propagated_uncertainties",
        "propagated_uncertainty_count",
    }
)
STATE_MEMORY_FIELDS = frozenset(
    {
        "derived_convention_lock",
        "derived_convention_lock_count",
        "derived_intermediate_results",
        "derived_intermediate_result_count",
        "derived_approximations",
        "derived_approximation_count",
    }
)

PLAN_PHASE_CONTRACT_GATE_FIELDS = PROJECT_CONTRACT_GATE_FIELDS
PLAN_PHASE_REFERENCE_RUNTIME_FIELDS = frozenset(
    {
        "contract_intake",
        "effective_reference_intake",
        "selected_protocol_bundle_ids",
        "protocol_bundle_count",
        "protocol_bundle_load_manifest",
        "protocol_bundle_context",
        "protocol_bundle_verifier_extensions",
        "active_reference_context",
        "reference_artifact_files",
        "reference_artifacts_content",
        "literature_review_files",
        "literature_review_count",
        "research_map_reference_files",
        "research_map_reference_count",
        "derived_manuscript_proof_review_status",
    }
)
PLAN_PHASE_STRUCTURED_STATE_FIELDS = STRUCTURED_STATE_FIELDS
PLAN_PHASE_STATE_MEMORY_FIELDS = STATE_MEMORY_FIELDS
PLAN_PHASE_FILE_CONTENT_FIELDS = frozenset(
    {
        "state_content",
        "roadmap_content",
        "requirements_content",
        "context_content",
        "research_content",
        "experiment_design_content",
        "verification_content",
        "validation_content",
    }
)
QUICK_CONTRACT_GATE_FIELDS = PROJECT_CONTRACT_GATE_FIELDS
QUICK_REFERENCE_RUNTIME_FIELDS = PLAN_PHASE_REFERENCE_RUNTIME_FIELDS

RESUME_REFERENCE_RUNTIME_FIELDS = frozenset(
    {
        "contract_intake",
        "effective_reference_intake",
        "active_reference_context",
        "reference_artifact_files",
        "reference_artifacts_content",
    }
)
RESUME_FILE_CONTENT_FIELDS = frozenset(
    {
        "state_content",
        "project_content",
        "roadmap_content",
        "derivation_state_content",
        "continuity_handoff_content",
    }
)
SYNC_STATE_FILE_CONTENT_FIELDS = frozenset(
    {
        "state_md_content",
        "state_json_content",
        "state_json_backup_content",
    }
)
SYNC_STATE_STRUCTURED_STATE_FIELDS = frozenset({"state_load_source", "state_integrity_issues"})

WRITE_PAPER_BOOTSTRAP_REFERENCE_FIELDS = frozenset(
    {
        "active_reference_context",
        "contract_intake",
        "derived_manuscript_proof_review_status",
        "derived_manuscript_reference_status",
        "derived_manuscript_reference_status_count",
        "effective_reference_intake",
        "protocol_bundle_context",
        "protocol_bundle_load_manifest",
        "selected_protocol_bundle_ids",
    }
)
WRITE_PAPER_PUBLICATION_BOOTSTRAP_FIELDS = frozenset(
    {
        "publication_subject",
        "publication_subject_status",
        "publication_subject_source",
        "publication_subject_detail",
        "publication_subject_slug",
        "publication_lane_kind",
        "publication_lane_owner",
        "publication_artifact_base",
        "selected_publication_root",
        "selected_review_root",
        "publication_intake_root",
        "manuscript_resolution_status",
        "manuscript_resolution_detail",
        "manuscript_root",
        "manuscript_entrypoint",
        "artifact_manifest_path",
        "bibliography_audit_path",
        "reproducibility_manifest_path",
        "managed_publication_root",
        "managed_manuscript_root",
        "publication_bootstrap",
        "publication_bootstrap_mode",
        "publication_bootstrap_root",
        "publication_bootstrap_detail",
    }
)
WRITE_PAPER_REFERENCE_RUNTIME_FIELDS = frozenset(
    {
        *WRITE_PAPER_BOOTSTRAP_REFERENCE_FIELDS,
        "reference_artifact_files",
        "reference_artifacts_content",
        "literature_review_files",
        "literature_review_count",
        "research_map_reference_files",
        "research_map_reference_count",
        "citation_source_files",
        "citation_source_count",
        "citation_source_warnings",
        "derived_citation_sources",
        "derived_citation_source_count",
    }
)
WRITE_PAPER_FILE_CONTENT_FIELDS = frozenset({"state_content", "roadmap_content", "requirements_content"})
PEER_REVIEW_REFERENCE_RUNTIME_FIELDS = PROJECT_CONTRACT_GATE_FIELDS | WRITE_PAPER_REFERENCE_RUNTIME_FIELDS

PUBLICATION_REVIEW_SNAPSHOT_FIELDS = frozenset(
    {
        "publication_subject_slug",
        "publication_lane_kind",
        "publication_lane_owner",
        "managed_publication_root",
        "selected_publication_root",
        "selected_review_root",
        "manuscript_resolution_status",
        "manuscript_resolution_detail",
        "manuscript_root",
        "manuscript_entrypoint",
        "artifact_manifest_path",
        "bibliography_audit_path",
        "reproducibility_manifest_path",
        "publication_blockers",
        "publication_blocker_count",
        "latest_review_round",
        "latest_review_round_suffix",
        "latest_review_ledger",
        "latest_referee_decision",
        "latest_referee_report_md",
        "latest_referee_report_tex",
        "latest_proof_redteam",
        "latest_review_artifacts",
        "latest_response_round",
        "latest_response_round_suffix",
        "latest_author_response",
        "latest_referee_response",
        "latest_response_artifacts",
        "latest_response_freshness_policy",
        "latest_response_requires_fresh_review",
        "latest_response_required_review_round",
        "latest_response_required_review_round_suffix",
        "latest_response_freshness_detail",
        "latest_response_freshness",
    }
)
ARXIV_SUBMISSION_BOOTSTRAP_FIELDS = frozenset(
    {
        "commit_docs",
        "arxiv_submission_argument_input",
        "project_root",
        "state_exists",
        "project_exists",
        "autonomy",
        "research_mode",
        *PROJECT_CONTRACT_GATE_FIELDS,
        "selected_protocol_bundle_ids",
        "protocol_bundle_load_manifest",
        "protocol_bundle_context",
        "active_reference_context",
        "derived_manuscript_reference_status",
        "derived_manuscript_reference_status_count",
        "derived_manuscript_proof_review_status",
        "platform",
    }
)
ARXIV_SUBMISSION_SNAPSHOT_FIELDS = PUBLICATION_REVIEW_SNAPSHOT_FIELDS | frozenset(
    {"manuscript_reference_status_warnings"}
)

NEW_MILESTONE_REFERENCE_RUNTIME_FIELDS = frozenset(
    {
        "active_reference_context",
        "contract_intake",
        "effective_reference_intake",
        "literature_review_count",
        "literature_review_files",
        "reference_artifact_files",
        "reference_artifacts_content",
        "research_map_reference_count",
        "research_map_reference_files",
    }
)
NEW_MILESTONE_FILE_CONTENT_FIELDS = frozenset(
    {
        "project_content",
        "state_content",
        "milestones_content",
        "requirements_content",
        "roadmap_content",
    }
)

EXECUTE_PHASE_CONTRACT_GATE_FIELDS = PROJECT_CONTRACT_GATE_FIELDS
EXECUTE_PHASE_REFERENCE_RUNTIME_FIELDS = frozenset(
    {
        "contract_intake",
        "effective_reference_intake",
        "derived_active_references",
        "derived_active_reference_count",
        "derived_knowledge_docs",
        "derived_knowledge_doc_count",
        "knowledge_doc_warnings",
        "citation_source_files",
        "citation_source_count",
        "citation_source_warnings",
        "derived_citation_sources",
        "derived_citation_source_count",
        "derived_manuscript_reference_status",
        "derived_manuscript_reference_status_count",
        "selected_protocol_bundle_ids",
        "protocol_bundle_count",
        "protocol_bundle_load_manifest",
        "protocol_bundle_verifier_extensions",
        "protocol_bundle_context",
        "active_reference_context",
        "active_references",
        "active_reference_count",
        "knowledge_doc_files",
        "knowledge_doc_count",
        "stable_knowledge_doc_files",
        "stable_knowledge_doc_count",
        "knowledge_doc_status_counts",
        "reference_artifact_files",
        "reference_artifacts_content",
        "literature_review_files",
        "literature_review_count",
        "research_map_reference_files",
        "research_map_reference_count",
        "derived_manuscript_proof_review_status",
    }
)
EXECUTE_PHASE_STRUCTURED_STATE_FIELDS = STRUCTURED_STATE_FIELDS
EXECUTE_PHASE_STATE_MEMORY_FIELDS = STATE_MEMORY_FIELDS
EXECUTE_PHASE_EXECUTION_RUNTIME_FIELDS = frozenset(
    {
        "current_execution",
        "has_live_execution",
        "execution_review_pending",
        "execution_pre_fanout_review_pending",
        "execution_skeptical_requestioning_required",
        "execution_downstream_locked",
        "execution_blocked",
        "execution_resumable",
        "execution_paused_at",
        "current_execution_resume_file",
        "handoff_resume_file",
        "recorded_handoff_resume_file",
        "missing_handoff_resume_file",
        "execution_resume_file",
        "execution_resume_file_source",
        "resume_projection",
        "current_hostname",
        "current_platform",
        "session_hostname",
        "session_platform",
        "session_last_date",
        "session_stopped_at",
        "machine_change_detected",
        "machine_change_notice",
        "derived_execution_head",
        "continuity_handoff_file",
        "recorded_continuity_handoff_file",
        "missing_continuity_handoff_file",
        "has_continuity_handoff",
    }
)
EXECUTE_PHASE_TASK_OVERLAY_FIELDS = frozenset(
    {
        "selected_task_overlay_ids",
        "task_overlay_load_manifest",
        "task_overlay_policy_summary",
    }
)
EXECUTE_PHASE_SCHEMA_BRIDGE_FIELDS = frozenset(
    {
        "verification_report_finalizer_bridge",
        "verification_report_skeleton_bridge",
    }
)

VERIFY_WORK_CONTRACT_GATE_FIELDS = PROJECT_CONTRACT_GATE_FIELDS
VERIFY_WORK_REFERENCE_RUNTIME_FIELDS = EXECUTE_PHASE_REFERENCE_RUNTIME_FIELDS
VERIFY_WORK_STRUCTURED_STATE_FIELDS = STRUCTURED_STATE_FIELDS
VERIFY_WORK_STATE_MEMORY_FIELDS = STATE_MEMORY_FIELDS
VERIFY_WORK_SCHEMA_BRIDGE_FIELDS = EXECUTE_PHASE_SCHEMA_BRIDGE_FIELDS | frozenset({"proof_redteam_finalizer_bridge"})

STAGED_REFERENCE_CONTRACT_HANDLE_STATUS_FIELDS = frozenset(
    {
        "contract_intake",
        "effective_reference_intake",
        "selected_protocol_bundle_ids",
        "protocol_bundle_count",
        "protocol_bundle_load_manifest",
        "protocol_bundle_verifier_extensions",
        "active_references",
        "active_reference_count",
    }
)
STAGED_REFERENCE_RENDERED_CONTEXT_FIELDS = frozenset({"protocol_bundle_context", "active_reference_context"})
STAGED_REFERENCE_ARTIFACT_HANDLE_STATUS_FIELDS = frozenset(
    {
        "derived_active_references",
        "derived_active_reference_count",
        "derived_knowledge_docs",
        "derived_knowledge_doc_count",
        "knowledge_doc_warnings",
        "citation_source_files",
        "citation_source_count",
        "citation_source_warnings",
        "derived_citation_sources",
        "derived_citation_source_count",
        "derived_manuscript_reference_status",
        "derived_manuscript_reference_status_count",
        "knowledge_doc_files",
        "knowledge_doc_count",
        "stable_knowledge_doc_files",
        "stable_knowledge_doc_count",
        "knowledge_doc_status_counts",
        "reference_artifact_files",
        "literature_review_files",
        "literature_review_count",
        "research_map_reference_files",
        "research_map_reference_count",
        "derived_manuscript_proof_review_status",
    }
)
STAGED_REFERENCE_HANDLE_STATUS_FIELDS = (
    STAGED_REFERENCE_CONTRACT_HANDLE_STATUS_FIELDS | STAGED_REFERENCE_ARTIFACT_HANDLE_STATUS_FIELDS
)
STAGED_REFERENCE_BODY_FIELDS = frozenset({"reference_artifacts_content"})
STAGED_REFERENCE_SUMMARY_FIELDS = (
    STAGED_REFERENCE_CONTRACT_HANDLE_STATUS_FIELDS | STAGED_REFERENCE_RENDERED_CONTEXT_FIELDS
)
STAGED_FULL_REFERENCE_RUNTIME_FIELDS = STAGED_REFERENCE_ARTIFACT_HANDLE_STATUS_FIELDS | STAGED_REFERENCE_BODY_FIELDS
STAGED_REFERENCE_RUNTIME_FIELDS = STAGED_FULL_REFERENCE_RUNTIME_FIELDS | STAGED_REFERENCE_SUMMARY_FIELDS
STAGED_REFERENCE_ARTIFACT_CONTENT_FIELDS = STAGED_REFERENCE_BODY_FIELDS

RESEARCH_PHASE_FILE_CONTENT_FIELDS = frozenset({"state_content", "config_content", "roadmap_content"})
STAGED_FILE_BODY_FIELDS = (
    PLAN_PHASE_FILE_CONTENT_FIELDS
    | RESUME_FILE_CONTENT_FIELDS
    | SYNC_STATE_FILE_CONTENT_FIELDS
    | WRITE_PAPER_FILE_CONTENT_FIELDS
    | NEW_MILESTONE_FILE_CONTENT_FIELDS
    | RESEARCH_PHASE_FILE_CONTENT_FIELDS
)
STAGED_BODY_FIELDS = STAGED_REFERENCE_BODY_FIELDS | STAGED_FILE_BODY_FIELDS


__all__ = [
    "ARXIV_SUBMISSION_BOOTSTRAP_FIELDS",
    "ARXIV_SUBMISSION_SNAPSHOT_FIELDS",
    "EXECUTE_PHASE_CONTRACT_GATE_FIELDS",
    "EXECUTE_PHASE_EXECUTION_RUNTIME_FIELDS",
    "EXECUTE_PHASE_REFERENCE_RUNTIME_FIELDS",
    "EXECUTE_PHASE_SCHEMA_BRIDGE_FIELDS",
    "EXECUTE_PHASE_STATE_MEMORY_FIELDS",
    "EXECUTE_PHASE_STRUCTURED_STATE_FIELDS",
    "EXECUTE_PHASE_TASK_OVERLAY_FIELDS",
    "NEW_MILESTONE_FILE_CONTENT_FIELDS",
    "NEW_MILESTONE_REFERENCE_RUNTIME_FIELDS",
    "PEER_REVIEW_REFERENCE_RUNTIME_FIELDS",
    "PLAN_PHASE_CONTRACT_GATE_FIELDS",
    "PLAN_PHASE_FILE_CONTENT_FIELDS",
    "PLAN_PHASE_REFERENCE_RUNTIME_FIELDS",
    "PLAN_PHASE_STATE_MEMORY_FIELDS",
    "PLAN_PHASE_STRUCTURED_STATE_FIELDS",
    "PROJECT_CONTRACT_GATE_FIELDS",
    "PUBLICATION_REVIEW_SNAPSHOT_FIELDS",
    "QUICK_CONTRACT_GATE_FIELDS",
    "QUICK_REFERENCE_RUNTIME_FIELDS",
    "RESEARCH_PHASE_FILE_CONTENT_FIELDS",
    "RESUME_FILE_CONTENT_FIELDS",
    "STAGED_BODY_FIELDS",
    "STAGED_FILE_BODY_FIELDS",
    "RESUME_REFERENCE_RUNTIME_FIELDS",
    "STAGED_FULL_REFERENCE_RUNTIME_FIELDS",
    "STAGED_REFERENCE_ARTIFACT_CONTENT_FIELDS",
    "STAGED_REFERENCE_ARTIFACT_HANDLE_STATUS_FIELDS",
    "STAGED_REFERENCE_BODY_FIELDS",
    "STAGED_REFERENCE_CONTRACT_HANDLE_STATUS_FIELDS",
    "STAGED_REFERENCE_HANDLE_STATUS_FIELDS",
    "STAGED_REFERENCE_RENDERED_CONTEXT_FIELDS",
    "STAGED_REFERENCE_RUNTIME_FIELDS",
    "STAGED_REFERENCE_SUMMARY_FIELDS",
    "STATE_MEMORY_FIELDS",
    "STRUCTURED_STATE_FIELDS",
    "SYNC_STATE_FILE_CONTENT_FIELDS",
    "SYNC_STATE_STRUCTURED_STATE_FIELDS",
    "VERIFY_WORK_CONTRACT_GATE_FIELDS",
    "VERIFY_WORK_REFERENCE_RUNTIME_FIELDS",
    "VERIFY_WORK_SCHEMA_BRIDGE_FIELDS",
    "VERIFY_WORK_STATE_MEMORY_FIELDS",
    "VERIFY_WORK_STRUCTURED_STATE_FIELDS",
    "WRITE_PAPER_BOOTSTRAP_REFERENCE_FIELDS",
    "WRITE_PAPER_FILE_CONTENT_FIELDS",
    "WRITE_PAPER_PUBLICATION_BOOTSTRAP_FIELDS",
    "WRITE_PAPER_REFERENCE_RUNTIME_FIELDS",
]
