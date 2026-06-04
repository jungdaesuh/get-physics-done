---
name: gpd:new-milestone
description: Start a new research milestone cycle — staged init, requirements, and roadmap
argument-hint: "[milestone name, e.g., 'v1.1 Finite-Temperature Extension']"
context_mode: project-required
allowed-tools:
  - file_read
  - file_write
  - shell
  - task
  - ask_user
help:
  group: Roadmap and milestones
  order: 270
  compact_description: Start the next milestone
  display_signature: gpd:new-milestone <name>
---


<objective>
Start a new research milestone: questioning -> literature research (optional) -> requirements -> staged roadmap handoff.

Continuation equivalent of new-project. Research project exists, PROJECT.md has history. Gathers "what's next", updates PROJECT.md, then runs requirements → roadmap cycle while honoring `planning.commit_docs` for milestone artifact commits.

**Creates/Updates:**

- `GPD/PROJECT.md` — updated with new milestone goals
- `GPD/literature/` — domain and literature survey (optional, NEW research objectives only)
- `GPD/REQUIREMENTS.md` — scoped requirements for this milestone
- `GPD/ROADMAP.md` — phase structure (continues numbering)
- `GPD/STATE.md` — reset for new milestone

**After:** `gpd:discuss-phase [N]` to clarify the first new phase before planning. Use `gpd:plan-phase [N]` only when the phase context is already clear.
</objective>

<execution_context>
@{GPD_INSTALL_DIR}/workflows/new-milestone/milestone-bootstrap.md
</execution_context>

<context>
Milestone name: $ARGUMENTS (optional - will prompt if not provided)

**Load project context:**
@GPD/PROJECT.md
@GPD/STATE.md
@GPD/MILESTONES.md
@GPD/config.json

**Load milestone context (if exists, from gpd:discuss-phase):**
@GPD/MILESTONE-CONTEXT.md
</context>

<process>
**Read the included new-milestone bootstrap authority first.**
Later survey/objective and roadmapper stages are manifest-owned. The roadmapper handoff must prove freshness with a typed return and `files_written`.

Load local late authorities only at matching stages: questioning reference for guided milestone questions; project/requirements templates for those writes; UI brand for completion or status blocks.

**Argument parsing:**

- `$ARGUMENTS` → milestone name (optional, will prompt if not provided)
- Parse milestone name from arguments if present

**Flags:** None currently defined.
</process>

<success_criteria>

- [ ] New-milestone workflow executed as the authority for staged milestone mechanics
- [ ] Late-stage authorities loaded only at their workflow-owned stages
- [ ] `planning.commit_docs` and next-step routing preserved by the workflow contract
</success_criteria>
