---
name: gpd:research-phase
description: Research how to tackle a phase (standalone - usually use gpd:plan-phase instead)
argument-hint: "<phase-number>"
context_mode: project-required
command-policy:
  schema_version: 1
  subject_policy:
    subject_kind: phase
    resolution_mode: phase_number
    explicit_input_kinds:
      - phase-number
    allow_interactive_without_subject: false
allowed-tools:
  - ask_user
  - file_read
  - shell
  - task
help:
  group: Planning and execution
  order: 130
  compact_description: Run a focused phase literature survey
  display_signature: gpd:research-phase <number>
---
<objective>
Research how to tackle a phase. Use this command when you want phase-specific investigation before planning or when you need to re-research after planning is complete.

Orchestrator role: validate the phase input, then hand off to the workflow-owned staged init, typed-return routing, and artifact gating.

**Why subagent:** Fresh context keeps the phase survey scoped instead of carrying stale planning detail.
</objective>

<execution_context>
@{GPD_INSTALL_DIR}/workflows/research-phase/phase-bootstrap.md
</execution_context>

<context>
Phase number: $ARGUMENTS (required)

Normalize phase input before any directory lookups.
</context>

<process>
Follow the included research-phase bootstrap authority. Research handoff loading is manifest-owned by the active workflow stage.
Do not duplicate init, spawn, or return routing here.
Research depth follows the workflow-owned `research_mode`.
</process>
