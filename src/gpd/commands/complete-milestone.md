---
name: gpd:complete-milestone
description: Archive completed research milestone and prepare the next investigation stage
argument-hint: <version>
context_mode: project-required
requires:
  files: ["GPD/ROADMAP.md"]
allowed-tools:
  - file_read
  - file_write
  - shell
help:
  group: Roadmap and milestones
  order: 280
  compact_description: Archive a completed milestone
  display_signature: gpd:complete-milestone <version>
---

<objective>

Mark research milestone {version} complete, archive to milestones/, and prepare
the next research stage.

This wrapper owns the public command surface and required version argument.
The workflow owns audit/readiness checks, milestone statistics, archive
generation, PROJECT.md evolution, MILESTONES.md updates, commit/tag behavior,
and next-step routing.

</objective>

<execution_context>

Load the workflow authority before executing:

- @{GPD_INSTALL_DIR}/workflows/complete-milestone.md

</execution_context>

<late_read_authorities>

Read these templates only when the workflow asks for the corresponding
milestone/archive write step:

- `{GPD_INSTALL_DIR}/templates/milestone.md`
- `{GPD_INSTALL_DIR}/templates/milestone-archive.md`

</late_read_authorities>

<context>

- Version: {version} (for example `1.0`, `1.1`, or `2.0`)
- Primary archive outputs: `GPD/milestones/v{version}-ROADMAP.md` and
  `GPD/milestones/v{version}-REQUIREMENTS.md`

</context>

<process>

Follow the included complete-milestone workflow end-to-end. Do not restate or
fork its readiness, archive, commit, tag, or next-step mechanics.

</process>
