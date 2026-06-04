---
name: gpd:resume-work
description: Resume research from previous session with full context restoration
context_mode: project-required
project_reentry_capable: true
requires:
  files: ["GPD/ROADMAP.md"]
allowed-tools:
  - file_read
  - shell
  - file_write
  - ask_user
help:
  group: Starter commands
  order: 70
  compact_description: Resume the selected project's canonical state inside the runtime
  display_signature: gpd:resume-work
  notes:
    - '`state.json.continuation` is the durable authority. Canonical continuation fields define the public resume vocabulary: `active_resume_kind`, `active_resume_origin`, `active_resume_pointer`, `active_bounded_segment`, `derived_execution_head`, `active_resume_result`, `continuity_handoff_file`, `recorded_continuity_handoff_file`, `missing_continuity_handoff_file`, `resume_candidates`.'
  root_detail_order: 30
---


<objective>
Resume research from the selected project's canonical state.
</objective>

<execution_context>
@{GPD_INSTALL_DIR}/workflows/resume-work/resume-bootstrap.md
</execution_context>

<process>
Read the included resume-work bootstrap authority first. Later resume stages are manifest-owned.
</process>
