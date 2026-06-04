---
name: gpd:execute-phase
description: Execute all plans in a phase with wave-based parallelization
argument-hint: "<phase-number> [--gaps-only]"
context_mode: project-required
requires:
  files: ["GPD/ROADMAP.md"]
allowed-tools:
  - file_read
  - file_write
  - file_edit
  - find_files
  - search_files
  - shell
  - task
  - ask_user
help:
  group: Planning and execution
  order: 190
  compact_description: Run all plans in a phase, or only gap-closure plans
  display_signature: gpd:execute-phase <phase-number> [--gaps-only]
  root_detail_order: 110
---

<objective>
Run staged phase waves: select plans, dispatch work, verify, update state, resume.
</objective>

<execution_context>
@{GPD_INSTALL_DIR}/workflows/execute-phase/phase-bootstrap.md
</execution_context>

<arguments>
Phase: $ARGUMENTS

- `--gaps-only`: only gap-closure plans.
</arguments>

<process>
Read the included bootstrap authority first. Later stage loading and field
access are manifest-owned by the staged workflow.
</process>

<mayfly_maintenance>
**After completing all phase work** — update the Mayfly research notebook so
the next session starts informed. Call these gpd-mayfly tools (project_dir=$CWD):

1. `gpd_mayfly:read_session_log` — check for unprocessed sessions.
2. For each significant finding: `gpd_mayfly:upsert_knowledge(topic, content)`.
   Read the existing entry first; preserve prior bullets; add `→ session NNN` links.
3. `gpd_mayfly:update_frontier` — overwrite FRONTIER.md with updated current best,
   directions, hypotheses, dead ends. Every direction links to a knowledge entry.
4. `gpd_mayfly:append_journal_row` — outcome + summary + knowledge_updated slugs.
5. `gpd_mayfly:write_session_notes` — raw notes (approach, result, what worked/failed).
6. If new topics or status changes: `gpd_mayfly:update_map`.

Skip silently if gpd-mayfly tools are unavailable.
</mayfly_maintenance>
