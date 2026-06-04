---
name: gpd:write-paper
description: Structure and write a physics paper from project research results or a bounded external-authoring intake
argument-hint: "[--intake path/to/write-paper-authoring-input.json]"
context_mode: project-aware
command-policy:
  schema_version: 1
  subject_policy:
    subject_kind: publication
    resolution_mode: project_manuscript_or_bootstrap
    explicit_input_kinds:
      - authoring_intake_manifest
    allow_external_subjects: false
    allow_interactive_without_subject: false
    supported_roots:
      - paper
      - manuscript
      - draft
    bootstrap_allowed: true
  supporting_context_policy:
    project_context_mode: project-aware
    project_reentry_mode: disallowed
  output_policy:
    output_mode: manuscript_local_plus_gpd_auxiliary
    managed_root_kind: gpd_managed_durable
    default_output_subtree: GPD/publication/{subject_slug}/manuscript
    stage_artifact_policy: allowed
review-contract:
  review_mode: publication
  schema_version: 1
  required_outputs:
    - "${PAPER_DIR}/{topic_specific_stem}.tex"
    - "${PAPER_DIR}/PAPER-CONFIG.json"
    - "${PAPER_DIR}/ARTIFACT-MANIFEST.json"
    - "${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json"
    - "${PAPER_DIR}/reproducibility-manifest.json"
    - "GPD/review/REVIEW-LEDGER{round_suffix}.json"
    - "GPD/review/REFEREE-DECISION{round_suffix}.json"
    - "GPD/REFEREE-REPORT{round_suffix}.md"
    - "GPD/REFEREE-REPORT{round_suffix}.tex"
  required_evidence:
    - "project-backed lane: research artifacts and verification reports"
    - "external-authoring lane: explicit `--intake` manifest with claim-to-evidence bindings"
    - bibliography / citation-source input
  blocking_conditions:
    - missing project state for project-backed runs
    - missing roadmap for project-backed runs
    - missing conventions for project-backed runs without explicit intake conventions
    - no research artifacts for project-backed runs
    - missing or incomplete explicit `--intake` manifest for external-authoring runs
    - claim without explicit evidence binding in the external-authoring intake
    - degraded review integrity
  preflight_checks:
    - command_context
    - project_state
    - roadmap
    - conventions
    - research_artifacts
    - verification_reports
    - manuscript
    - artifact_manifest
    - bibliography_audit
    - bibliography_audit_clean
    - reproducibility_manifest
    - reproducibility_ready
    - manuscript_proof_review
  scope_variants:
    - scope: explicit_intake_manifest
      activation: validated explicit external authoring intake manifest was supplied outside a project
      relaxed_preflight_checks:
        - project_state
        - roadmap
        - conventions
        - research_artifacts
        - verification_reports
        - manuscript_proof_review
      optional_preflight_checks:
        - artifact_manifest
        - bibliography_audit
        - bibliography_audit_clean
        - reproducibility_manifest
        - reproducibility_ready
      required_outputs_override:
        - "${PAPER_DIR}/{topic_specific_stem}.tex"
        - "${PAPER_DIR}/PAPER-CONFIG.json"
        - "${PAPER_DIR}/ARTIFACT-MANIFEST.json"
        - "${PAPER_DIR}/BIBLIOGRAPHY-AUDIT.json"
        - "${PAPER_DIR}/reproducibility-manifest.json"
      required_evidence_override:
        - validated external authoring intake manifest with explicit claim-to-evidence bindings
      blocking_conditions_override:
        - invalid or incomplete external authoring intake manifest
  conditional_requirements:
    - when: theorem-bearing claims are present
      required_outputs:
        - "GPD/review/PROOF-REDTEAM{round_suffix}.md"
allowed-tools:
  - file_read
  - file_write
  - file_edit
  - shell
  - search_files
  - find_files
  - task
  - web_search
  - ask_user
help:
  group: Writing and publication
  order: 450
  compact_description: Draft a paper from current project results or one explicit external-authoring intake manifest into the resolved manuscript lane
  display_signature: gpd:write-paper [--intake path/to/write-paper-authoring-input.json]
  examples:
    - gpd:write-paper
    - gpd:write-paper --intake intake/write-paper-authoring-input.json
  notes:
    - Uses a bounded external-authoring lane driven by an explicit intake manifest only.
    - GPD-authored outputs live under `GPD/publication/{subject_slug}/...`; `GPD/publication/{subject_slug}/intake/` stores intake/provenance state only.
    - It does not mine arbitrary folders, and embedded external staged-review parity is out of scope.
    - Project-backed review/response/package outputs remain in the resolved GPD manuscript lane.
  root_detail_order: 260
---


<objective>
Structure and write a physics paper from completed research results or a bounded explicit external-authoring intake.

Keep the wrapper thin and let the workflow own the full pipeline.

**Why subagent:** Publication drafting and review coordination burn context fast.
</objective>

<execution_context>
@{GPD_INSTALL_DIR}/workflows/write-paper/paper-bootstrap.md
</execution_context>

<context>
Project manuscript context or intake: $ARGUMENTS

Use only the two frontmatter-authorized lanes: project-backed authoring, or the
explicit `--intake path/to/write-paper-authoring-input.json` external-authoring
manifest. External authoring is fail-closed: no workspace mining,
positional-folder discovery, or `PAPER-CONFIG.json` as intake. Boundary
reference: `{GPD_INSTALL_DIR}/references/publication/publication-pipeline-modes.md`.
Stage 1 owns validation, manuscript-root binding, and durable
`GPD/publication/{subject_slug}/...` routing; `.../intake/` is provenance only.
</context>

<process>
Follow the included first-stage authority exactly. Later stage loading is
manifest-owned. The root workflow index is only a staged-file map.
</process>

<success_criteria>
- [ ] Workflow completed or returned a typed Stage 1 blocker
- [ ] Review-contract outputs and evidence are satisfied for the active scope
- [ ] External-authoring runs produced manuscript-root artifacts and routed review to standalone `gpd:peer-review`
- [ ] Theorem-bearing manuscripts retain the proof-redteam gate
</success_criteria>
