---
name: gpd:build-persona
description: Build a private research persona patch from explicit interview and consented local evidence
argument-hint: "[focus | --from-current-project | --interview-only]"
context_mode: project-aware
command-policy:
  schema_version: 1
  subject_policy:
    subject_kind: research_persona_scope
    resolution_mode: explicit_input_or_interactive_scope
    explicit_input_kinds:
      - focus area
      - current-project scan request
      - interview-only request
    allow_interactive_without_subject: true
  supporting_context_policy:
    project_context_mode: project-aware
    project_reentry_mode: disallowed
    optional_file_patterns:
      - GPD/STATE.md
      - GPD/ROADMAP.md
      - GPD/knowledge/*.md
      - GPD/literature/*.md
      - paper/*.tex
      - manuscript/*.tex
      - pyproject.toml
  output_policy:
    output_mode: advisory
    managed_root_kind: none
allowed-tools:
  - file_read
  - file_write
  - shell
  - search_files
  - find_files
  - ask_user
  - task
help:
  group: Tangents, memory, and exports
  order: 545
  compact_description: Draft a private research-persona patch for explicit review
  display_signature: gpd:build-persona [focus|--from-current-project|--interview-only]
  detail_signature: gpd:build-persona [focus|--from-current-project|--interview-only]
  examples:
    - gpd:build-persona --interview-only
    - gpd:build-persona --from-current-project "math/code balance and citation style"
  notes:
    - Emits a candidate ResearchPersonaPatch only; apply it separately with `gpd research-persona apply-patch`.
    - Interviewing and local project scans require explicit user consent.
    - Never writes persona storage directly.
  root_detail_order: 245
---

<objective>
Draft a candidate `ResearchPersonaPatch` JSON object that captures user-approved
research-persona facts, preferences, expertise axes, workstyle signals, and
scientific taste notes.

This wrapper owns the public command surface and the no-direct-mutation rule
only. The same-named workflow owns consent checks, interview design, optional
local evidence gathering, privacy classification, schema validation, and final
patch presentation.

No silent memory: this command must not silently create, infer, or update
persona memory. Explicit user approval is required before any mutation step,
including `gpd research-persona apply-patch`.

When existing persona context is needed, request only a prompt-safe capsule or
projection such as `gpd research-persona export-capsule`; never place the raw
private profile in prompt context.
</objective>

<execution_context>
@{GPD_INSTALL_DIR}/workflows/build-persona.md
</execution_context>

<context>
Requested persona-building scope: $ARGUMENTS

This command is project-aware because the user may explicitly permit current
project evidence, but it must also work without a GPD project through interview
only. Do not auto-reenter a recent project for persona building.
</context>

<process>
Follow the included build-persona workflow end-to-end.

Preserve these command-surface invariants while delegating mechanics to the
workflow:

- Interviewing is opt-in and scoped by the user's answer.
- Project or filesystem scanning is opt-in, path-scoped, and read-only.
- The only output is a candidate `ResearchPersonaPatch` JSON object plus review
  guidance.
- Persona storage is never mutated by this runtime command. The user must apply
  the patch separately with `gpd research-persona apply-patch`.
- Do not call `apply-patch` until explicit user approval is given after the
  candidate patch and diff have been reviewed.
</process>

<success_criteria>

- [ ] Build-persona workflow executed as the authority for mechanics
- [ ] Explicit consent collected before interview questions or local scans
- [ ] Candidate `ResearchPersonaPatch` JSON emitted for review
- [ ] User shown the `gpd research-persona diff` and `gpd research-persona apply-patch` approval route
- [ ] No direct persona storage mutation performed
</success_criteria>
