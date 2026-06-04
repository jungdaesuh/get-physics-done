---
name: gpd:plan-phase
description: Create detailed execution plan for a phase (PLAN.md) with verification loop
argument-hint: "[phase] [--research] [--skip-research] [--gaps] [--skip-verify] [--light] [--inline-discuss]"
context_mode: project-required
agent: gpd-planner
requires:
  files: ["GPD/ROADMAP.md", "GPD/STATE.md"]
allowed-tools:
  - file_read
  - file_write
  - shell
  - find_files
  - search_files
  - task
  - web_fetch
help:
  group: Planning and execution
  order: 180
  compact_description: Build a detailed execution plan for a phase
  display_signature: gpd:plan-phase <number>
  notes:
    - '`--skip-verify` may skip routine verification, but proof-bearing plans still require checker review or an equivalent main-context audit.'
  root_detail_order: 100
---

<objective>
Create executable phase prompts for a research phase.
</objective>

<execution_context>
@{GPD_INSTALL_DIR}/workflows/plan-phase/phase-bootstrap.md
</execution_context>

<context>
Phase number: $ARGUMENTS (optional; auto-detects the next unplanned phase if omitted)
Canonical contract schema and hard validation rules are enforced later by the staged planner and checker handoffs; every proof-bearing plan must surface the theorem statement, named parameters, hypotheses, quantifier/domain obligations, and intended conclusion clauses visibly enough that a later audit can detect missing coverage.

**Flags:**

- `--research` -- Re-research even if `RESEARCH.md` exists
- `--skip-research` -- Skip research and plan directly
- `--gaps` -- Gap-closure mode (`VERIFICATION.md`, no research)
- `--skip-verify` -- Skip non-proof plan checker verification after planning; proof-bearing plans still require checker review or an equivalent main-context audit
- `--light` -- Produce contract-plus-constraints plans only

Normalize the phase input before any directory lookups.
</context>

<process>
Read the included bootstrap authority first. Later stage loading is manifest-owned by the workflow stage authorities; do not duplicate the stage manifest here.
</process>
